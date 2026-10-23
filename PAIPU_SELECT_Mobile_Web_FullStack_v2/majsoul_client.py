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
import hashlib
import threading

import aiohttp
import websockets
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


class RequestChannel(MSRPCChannel):
    async def connect(self, ms_host):
        # Idle sockets close on a finite timer. Do not send periodic pings or
        # game heartbeats to keep free infrastructure or sessions alive.
        self._ws = await websockets.connect(self._endpoint, origin=ms_host,
            ping_interval=None, open_timeout=20, max_size=MAX_RECORD+65536)
        self._msg_dispatcher = asyncio.create_task(self.dispatch_msg())


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
    # JP game NetRouteGroup_Entrance supplies tail="gateway"; NetRoute.Connect
    # appends it to the route domain. Preserve the established KR/EN path.
    tail = "/gateway" if authority.startswith("jp") else ""
    return [("wss://" + host + tail, rid) for _, _, host, rid in result]


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
        print("Game RPC rejected:", stage, code, flush=True)
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
        print("Game RPC rejected:", "account_unbound", 0, flush=True)
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


async def _read_record(lobby, replay_id, profile):
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


async def _close_channel(channel):
    if channel._ws is not None:
        with suppress(Exception):
            await asyncio.wait_for(channel.close(), timeout=3)


class GameConnections:
    """Reuse authenticated connections only while requests keep arriving.

    All methods that mutate connections run on the server's one game event loop.
    Finite idle timers close sockets; they never send RPCs or keep a host awake.
    """
    def __init__(self, idle_seconds=300, max_age=900, capacity=20, clock=time.monotonic):
        self.idle_seconds, self.max_age, self.capacity = idle_seconds, max_age, capacity
        self.clock = clock
        self.entries = {}
        self.counts = {'opened':0, 'reused':0, 'closed':0}
        self.stats_lock = threading.Lock()
        self.operation = asyncio.Lock()

    def stats(self):
        with self.stats_lock:
            return {**self.counts, 'active':len(self.entries)}

    async def discard(self, key, expected=None):
        entry = self.entries.get(key)
        if entry is None or (expected is not None and entry is not expected):
            return
        self.entries.pop(key, None)
        if entry.get('timer'):
            entry['timer'].cancel()
        await _close_channel(entry['channel'])
        with self.stats_lock:
            self.counts['closed'] += 1

    async def close_all(self):
        for key in list(self.entries):
            await self.discard(key)

    def _alive(self, entry):
        dispatcher = getattr(entry['channel'], '_msg_dispatcher', None)
        return (not entry.get('invalid') and entry['channel']._ws is not None
                and (dispatcher is None or not dispatcher.done())
                and self.clock()-entry['created'] < self.max_age)

    async def fetch(self, replay_id, session, profile):
        async with self.operation:
            return await self._fetch(replay_id, session, profile)

    async def _fetch(self, replay_id, session, profile):
        # Keep secrets out of keys/stats/logs. A rotated/re-enrolled SDK token
        # invalidates the old game connection, even for the same account.
        key = (profile.region, hashlib.sha256((session.uid+'\0'+session.device_id).encode()).hexdigest())
        fingerprint = hashlib.sha256(session.token.encode()).digest()
        entry = self.entries.get(key)
        if entry and (entry['token'] != fingerprint or entry['profile'] != profile or not self._alive(entry)):
            await self.discard(key, entry)
            entry = None
        if entry is None:
            if len(self.entries) >= self.capacity:
                oldest = min(self.entries, key=lambda k:self.entries[k]['used'])
                await self.discard(oldest)
            routes = await bootstrap(profile)
            for index, (endpoint, route_id) in enumerate(routes):
                channel = RequestChannel(endpoint)
                try:
                    await connect(channel, profile, route_id)
                    lobby = Lobby(channel)
                    await login(lobby, session, profile)
                    entry = {'channel':channel, 'lobby':lobby, 'profile':profile,
                             'token':fingerprint, 'created':self.clock(), 'used':self.clock(),
                             'invalid':False, 'timer':None, 'lock':asyncio.Lock()}
                    async def logged_out(_data, current=entry):
                        current['invalid'] = True
                    channel.add_hook('.lq.NotifyAccountLogout', logged_out)
                    self.entries[key] = entry
                    with self.stats_lock:
                        self.counts['opened'] += 1
                    break
                except (OSError, TimeoutError, aiohttp.ClientError):
                    await _close_channel(channel)
                    if index == len(routes)-1:
                        raise GameError('gateway') from None
                except BaseException:
                    await _close_channel(channel)
                    raise
        else:
            with self.stats_lock:
                self.counts['reused'] += 1
        if entry.get('timer'):
            entry['timer'].cancel()
        try:
            async with entry['lock']:
                return await _read_record(entry['lobby'], replay_id, profile)
        except BaseException:
            # Surface the original provider error once; never retry a 540 by
            # reconnecting or silently repeating the same replay request.
            await self.discard(key, entry)
            raise
        finally:
            if self.entries.get(key) is entry:
                entry['used'] = self.clock()
                entry['timer'] = asyncio.get_running_loop().call_later(
                    self.idle_seconds, lambda:asyncio.create_task(self.discard(key, entry)))


async def fetch_record(replay_id, session, region, *, connections=None):
    from version_resolver import resolve
    try:
        resolved = await resolve(region)
    except Exception as exc:
        raise GameError('client_version') from exc
    profile = Profile(region, product=resolved['product'], resource=resolved['resource'])
    if connections is not None:
        return await connections.fetch(replay_id, session, profile)
    routes = await bootstrap(profile)
    for index, (endpoint, route_id) in enumerate(routes):
        channel = MSRPCChannel(endpoint)
        try:
            await connect(channel, profile, route_id)
            lobby = Lobby(channel)
            await login(lobby, session, profile)
            return await _read_record(lobby, replay_id, profile)
        except GameError:
            raise
        except (OSError, TimeoutError, aiohttp.ClientError):
            if index == len(routes) - 1:
                raise GameError("gateway") from None
        finally:
            await _close_channel(channel)
    raise GameError("gateway")
