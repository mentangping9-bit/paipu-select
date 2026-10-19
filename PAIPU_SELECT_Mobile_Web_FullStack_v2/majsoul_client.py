"""International replay client: explicit, bounded RPC stages, no monkeypatches.

SDK region is the account's login region, independently of the replay URL.
Protocol facts and version provenance are recorded in AUTH_REVIEW.md.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid

import aiohttp
from ms import protocol_pb2 as pb
from ms.base import MSRPCChannel
from ms.rpc import Lobby
from paipu_vendor.mahjong_url_parser.models import RemoteReplayError
from paipu_vendor.mahjong_url_parser.sources.majsoul import _convert_record, _fill_device

VERSIONS = json.loads(Path(__file__).with_name("client_versions.json").read_text())["regions"]
HOSTS = {"kr": "engs.mahjongsoul.com", "en": "engs.mahjongsoul.com", "jp": "jpgs.mahjongsoul.com"}
MAX_RECORD = 16 * 1024 * 1024


class GameError(RemoteReplayError):
    def __init__(self, stage: str, code: int = 0):
        self.stage, self.code = stage, code
        super().__init__(f"Game stage {stage}: code {code}")


@dataclass(frozen=True)
class Profile:
    region: str
    product: str
    resource: str

    @property
    def version_string(self):
        return "WebGL_2022-" + self.resource


def profile_for(region: str) -> Profile:
    if region not in VERSIONS:
        raise ValueError("지원하지 않는 로그인 지역입니다.")
    return Profile(region, product=VERSIONS[region]['product'], resource=VERSIONS[region]['resource'])


def select_gateway_routes(routes, authority):
    allowed = {"engs.mahjongsoul.com", "engsbk.mahjongsoul.com",
               "jpgs.mahjongsoul.com", "jpgsbk.mahjongsoul.com"}
    if authority not in allowed or not isinstance(routes, list):
        return []
    result = []
    for item in routes:
        if not isinstance(item, dict):
            continue
        rid, domain = item.get("id"), item.get("domain")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", rid):
            continue
        if not isinstance(domain, str):
            continue
        match = re.fullmatch(r"([a-z0-9-]+\.mahjongsoul\.com)(?::443)?", domain)
        if not match or match[1] not in allowed or match[1][:2] != authority[:2]:
            continue
        if item.get("ssl") is False or item.get("state") == "maintain":
            continue
        result.append((match[1] != authority, str(item.get("order", 0)), match[1], rid))
    result.sort()
    return [("wss://" + host, rid) for _, _, host, rid in result]


async def bootstrap(profile: Profile):
    authority = HOSTS[profile.region]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20), trust_env=True) as http:
        async with http.get(f"https://{authority}/api/clientgate/routes", params={
            "platform": "Web", "version": profile.product, "lang": profile.region,
        }) as response:
            response.raise_for_status()
            raw = await response.content.read(65537)
            if len(raw) > 65536:
                raise GameError("routes")
            payload = json.loads(raw)
    routes = select_gateway_routes(payload.get("data", {}).get("routes"), authority)
    if not routes:
        raise GameError("routes")
    return routes


def _varint(value):
    data = bytearray()
    while value > 127:
        data.append((value & 127) | 128)
        value >>= 7
    data.append(value)
    return bytes(data)


def connection_payload(route_id: str, stamp: int | None = None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", route_id):
        raise GameError("route_id")
    route = route_id.encode("ascii")
    # ReqRequestConnection fields 2=type, 3=route_id, 4=timestamp, 6=platform.
    # ms-api 0.11.100 lacks platform; retain this field on the wire explicitly.
    return (b"\x10\x01\x1a" + _varint(len(route)) + route + b"\x20" +
            _varint(int(time.time()) if stamp is None else stamp) + b"\x32\x03Web")


async def rpc(stage, call):
    result = await asyncio.wait_for(call, timeout=20)
    code = int(getattr(getattr(result, "error", None), "code", 0))
    if code:
        raise GameError(stage, code)
    return result


async def login(lobby, session, profile):
    # GameUtility.ELoginSocialType + YostarWebGLSDK.Login in the game client.
    # Soulless 0.3.2 hardcodes 22 and does not implement the KR value 23.
    oauth_type = {'jp': 21, 'en': 22, 'kr': 23}[profile.region]
    auth = await rpc("oauth_auth", lobby.oauth2_auth(pb.ReqOauth2Auth(
        type=oauth_type, code=session.token, uid=session.uid,
        client_version_string=profile.version_string,
    )))
    if not auth.access_token:
        raise GameError("oauth_auth")
    check = await rpc("oauth_check", lobby.oauth2_check(pb.ReqOauth2Check(
        type=oauth_type, access_token=auth.access_token,
    )))
    if not check.has_account:
        raise GameError("account_unbound")
    request = pb.ReqOauth2Login(
        type=oauth_type, access_token=auth.access_token, reconnect=False,
        random_key=str(uuid.uuid4()), client_version_string=profile.version_string,
        tag=profile.region,
    )
    request.client_version.package = profile.product
    request.client_version.resource = profile.resource
    request.currency_platforms.extend([1, 4, 5, 9, 12])
    _fill_device(request.device)
    result = await rpc("oauth_login", lobby.oauth2_login(request))
    if result.account_id <= 0:
        raise GameError("oauth_login")
    return result


async def connect(channel, profile, route_id):
    origin = "https://game.mahjongsoul.com" if profile.region == "jp" else "https://mahjongsoul.game.yo-star.com"
    await asyncio.wait_for(channel.connect(origin), timeout=20)
    raw = await asyncio.wait_for(channel.send_request(
        ".lq.Route.requestConnection", connection_payload(route_id)), timeout=20)
    response = pb.ResRequestConnection()
    response.ParseFromString(raw)
    if response.error.code:
        raise GameError("connection", response.error.code)
    if response.result != 1:
        raise GameError('connection_result', response.result)
    return response


def safe_record_url(url):
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if (u.scheme != "https" or not host.endswith((".mahjongsoul.com", ".maj-soul.com", ".aliyuncs.com"))
            or u.username or u.password or u.port):
        raise GameError("record_url")
    return url


async def download_record(url):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45), trust_env=True) as http:
        async with http.get(safe_record_url(url), allow_redirects=False) as response:
            if response.status != 200:
                raise GameError("record_download", response.status)
            chunks, size = [], 0
            async for part in response.content.iter_chunked(65536):
                size += len(part)
                if size > MAX_RECORD:
                    raise GameError("record_size")
                chunks.append(part)
            return b"".join(chunks)


async def fetch_record(replay_id, session, region):
    from version_resolver import resolve
    try:
        resolved = await resolve(region)
    except Exception as exc:
        raise GameError('client_version') from exc
    profile = Profile(region, product=resolved['product'], resource=resolved['resource'])
    routes = await bootstrap(profile)
    for index, (endpoint, route_id) in enumerate(routes):
        channel = MSRPCChannel(endpoint)
        try:
            await connect(channel, profile, route_id)
            lobby = Lobby(channel)
            await login(lobby, session, profile)
            request = pb.ReqGameRecord(game_uuid=replay_id, client_version_string=profile.version_string)
            record = await asyncio.wait_for(lobby.fetch_game_record(request), timeout=25)
            if record.error.code == 151:
                await rpc("read_record", lobby.read_game_record(request))
                record = await asyncio.wait_for(lobby.fetch_game_record(request), timeout=25)
            if record.error.code:
                raise GameError("fetch_record", record.error.code)
            if record.head.uuid != replay_id or len(record.head.accounts) != 4:
                raise GameError("record_shape")
            if not record.data and record.data_url:
                record.data = await download_record(record.data_url)
            if not record.data or len(record.data) > MAX_RECORD:
                raise GameError("record_size")
            try:
                return _convert_record(record)
            except RemoteReplayError as exc:
                raise GameError("conversion") from exc
        except GameError:
            raise
        except (OSError, TimeoutError, aiohttp.ClientError):
            if index == len(routes) - 1:
                raise GameError("gateway") from None
        finally:
            if channel._ws is not None:
                with suppress(Exception):
                    await channel.close()
    raise GameError("gateway")
