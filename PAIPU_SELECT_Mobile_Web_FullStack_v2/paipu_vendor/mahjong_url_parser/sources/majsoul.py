from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import random
import re
import uuid
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp
import ms.protocol_pb2 as pb
from ms.base import MSRPCChannel
from ms.rpc import Lobby

from ..models import (
    AuthenticationRequired,
    MahjongSoulCredentials,
    RemoteReplayError,
    ReplayNotFoundError,
    ReplayReference,
    ServerRegion,
    VerificationCodeRequired,
)
from ..tenhou import validate_tenhou_json
from .yostar import YostarClient, YostarSession

MAX_REPLAY_BYTES = 16 * 1024 * 1024
CN_GATEWAYS = (
    "wss://route-2.maj-soul.com/gateway",
    "wss://route-3.maj-soul.com:8443/gateway",
    "wss://route-4.maj-soul.com/gateway",
    "wss://gateway-cdn.maj-soul.com/gateway",
)
JP_GATEWAYS = (
    "wss://jpgs.mahjongsoul.com:443/gateway",
    "wss://jpgsbk.mahjongsoul.com:443/gateway",
)
EN_GATEWAYS = (
    "wss://engs.mahjongsoul.com:443/gateway",
    "wss://engsbk.mahjongsoul.com:443/gateway",
)
GLOBAL_ROUTE_SERVERS = {
    ServerRegion.JP: (
        "https://jpgs.mahjongsoul.com",
        "https://jpgsbk.mahjongsoul.com",
    ),
    ServerRegion.EN: (
        "https://engs.mahjongsoul.com",
        "https://engsbk.mahjongsoul.com",
    ),
}
UNITY_VERSION_PATTERNS = (
    re.compile(r'productVersion\s*:\s*"([0-9]+(?:\.[0-9]+){2,})"'),
    re.compile(r"(?:jp|en)-WebGL-release-([0-9]+(?:\.[0-9]+){2,})"),
)


def _region_label(region: ServerRegion) -> str:
    return {
        ServerRegion.CN: "国服",
        ServerRegion.JP: "日服",
        ServerRegion.EN: "美服/韩服",
    }[region]


def _network_guidance(region: ServerRegion) -> str:
    if region in {ServerRegion.JP, ServerRegion.EN}:
        return "请检查网络以及代理/VPN设置；中国大陆网络环境可能无法直接访问该区域。"
    return "请检查网络连接、防火墙或 DNS 设置后重试。"


def _connection_reason(error: Exception | None) -> str:
    if error is None:
        return "未知网络错误"
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        return f"HTTP {status}"
    if isinstance(error, TimeoutError):
        return "连接超时"
    if isinstance(error, OSError):
        return "系统网络错误"
    return type(error).__name__


@dataclass(frozen=True)
class MahjongSoulFetch:
    payload: dict[str, Any]
    yostar_session: YostarSession | None = None


def _http_base(region: ServerRegion) -> str:
    if region is ServerRegion.CN:
        return "https://game.maj-soul.com/1"
    if region is ServerRegion.JP:
        return "https://game.mahjongsoul.com"
    return "https://mahjongsoul.game.yo-star.com"


def _origin(region: ServerRegion) -> str:
    if region is ServerRegion.CN:
        return "https://game.maj-soul.com"
    return _http_base(region)


def _fallback_gateways(region: ServerRegion) -> tuple[str, ...]:
    if region is ServerRegion.CN:
        return CN_GATEWAYS
    if region is ServerRegion.JP:
        return JP_GATEWAYS
    return EN_GATEWAYS


async def _read_limited(
    stream: aiohttp.StreamReader,
    limit: int,
    error_message: str,
) -> bytes:
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining > 0:
        chunk = await stream.read(min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > limit:
        raise RemoteReplayError(error_message)
    return raw


async def _json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    limit: int = 4 * 1024 * 1024,
) -> dict[str, Any]:
    async with session.get(url) as response:
        response.raise_for_status()
        raw = await _read_limited(
            response.content,
            limit,
            "雀魂配置响应超过安全上限。",
        )
    value = await asyncio.to_thread(json.loads, raw)
    if not isinstance(value, dict):
        raise RemoteReplayError("雀魂配置响应不是 JSON 对象。")
    return value


async def _text(
    session: aiohttp.ClientSession,
    url: str,
    *,
    limit: int = 1024 * 1024,
) -> str:
    async with session.get(url) as response:
        response.raise_for_status()
        raw = await _read_limited(
            response.content,
            limit,
            "雀魂网页响应超过安全上限。",
        )
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RemoteReplayError("雀魂网页不是有效的 UTF-8 文本。") from exc


def _unity_version_from_html(html: str) -> str:
    for pattern in UNITY_VERSION_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    raise RemoteReplayError("雀魂国际服网页未返回可识别的客户端版本。")


async def _global_bootstrap(
    session: aiohttp.ClientSession,
    region: ServerRegion,
) -> tuple[str, list[str]]:
    version = _unity_version_from_html(
        await _text(session, f"{_http_base(region)}/")
    )
    discovered: list[str] = []
    language = region.value
    for route in GLOBAL_ROUTE_SERVERS[region]:
        url = (
            f"{route}/api/clientgate/routes?platform=Web"
            f"&version={quote(version)}&lang={language}"
            f"&randv={random.randint(1, 999_999_999)}"
        )
        try:
            routes = await _json(session, url)
        except (aiohttp.ClientError, TimeoutError, RemoteReplayError):
            continue
        data = routes.get("data")
        route_items = data.get("routes") if isinstance(data, dict) else None
        if not isinstance(route_items, list):
            continue
        sorted_items = sorted(
            (item for item in route_items if isinstance(item, dict)),
            key=lambda item: int(item.get("order") or 0),
        )
        for item in sorted_items:
            domain = str(item.get("domain") or "")
            if (
                domain
                and item.get("ssl") is not False
                and item.get("state") != "maintain"
            ):
                discovered.append(f"wss://{domain}/gateway")
        if discovered:
            break
    return f"web-{version}", list(
        dict.fromkeys([*discovered, *_fallback_gateways(region)])
    )


async def _bootstrap(region: ServerRegion) -> tuple[str, list[str]]:
    base = _http_base(region)
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20),
        headers={"User-Agent": "Mahjong-Replay-Converter/0.2"},
    ) as session:
        try:
            if region is not ServerRegion.CN:
                return await _global_bootstrap(session, region)
            version_payload = await _json(session, f"{base}/version.json")
            version_with_suffix = str(version_payload.get("version") or "")
            version = version_with_suffix.removesuffix(".w")
            if not version:
                raise RemoteReplayError("雀魂版本接口未返回版本号。")
            config = await _json(session, f"{base}/v{version}.w/config.json")
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise RemoteReplayError(
                f"无法连接雀魂{_region_label(region)}配置服务器"
                f"（{_connection_reason(exc)}）。{_network_guidance(region)}"
            ) from exc

        route_urls: list[str] = []
        for cluster in config.get("ip") or []:
            if not isinstance(cluster, dict):
                continue
            if cluster.get("name") not in {None, "", "player"}:
                continue
            for gateway in cluster.get("gateways") or []:
                if isinstance(gateway, dict) and str(gateway.get("url") or "").startswith("https://"):
                    route_urls.append(str(gateway["url"]).rstrip("/"))

        discovered: list[str] = []
        language = "en" if region is ServerRegion.CN else region.value
        for route in route_urls[:4]:
            url = (
                f"{route}/api/clientgate/routes?platform=Web"
                f"&version={quote(version_with_suffix)}&lang={language}"
                f"&randv={random.randint(1, 999_999_999)}"
            )
            try:
                routes = await _json(session, url)
            except (aiohttp.ClientError, TimeoutError, RemoteReplayError):
                continue
            data = routes.get("data")
            route_items = data.get("routes") if isinstance(data, dict) else None
            if not isinstance(route_items, list):
                continue
            sorted_items = sorted(
                (item for item in route_items if isinstance(item, dict)),
                key=lambda item: int(item.get("order") or 0),
            )
            for item in sorted_items:
                domain = str(item.get("domain") or "")
                if domain and item.get("ssl") is not False and item.get("state") != "maintain":
                    discovered.append(f"wss://{domain}/gateway")
            if discovered:
                break
    return f"web-{version}", list(dict.fromkeys([*discovered, *_fallback_gateways(region)]))


def _password_digest(password: str) -> str:
    return hmac.new(b"lailai", password.encode(), hashlib.sha256).hexdigest()


def _set_if_present(message: Any, field: str, value: Any) -> None:
    if field in message.DESCRIPTOR.fields_by_name:
        setattr(message, field, value)


def _fill_device(device: Any) -> None:
    values = {
        "platform": "pc",
        "hardware": "pc",
        "os": "windows",
        "os_version": "Windows 10",
        "is_browser": True,
        "software": "Chrome",
        "sale_platform": "web",
        "hardware_vendor": "",
        "model_number": "",
        "screen_width": 1920,
        "screen_height": 1080,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36"
        ),
        "screen_type": 1,
    }
    for field, value in values.items():
        _set_if_present(device, field, value)


async def _download_record_data(url: str) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RemoteReplayError("雀魂返回了不安全的牌谱下载地址。")
    async with (
        aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=60),
        headers={"User-Agent": "Mahjong-Replay-Converter/0.2"},
        ) as session,
        session.get(url) as response,
    ):
        response.raise_for_status()
        raw = await _read_limited(
            response.content,
            MAX_REPLAY_BYTES,
            "雀魂牌谱数据超过 16 MiB 安全上限。",
        )
    return raw


def _convert_record(record: pb.ResGameRecord) -> dict[str, Any]:
    try:
        from tensoul.downloader import MajsoulPaipuDownloader

        payload = MajsoulPaipuDownloader()._handle_game_record(record)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RemoteReplayError(
            "雀魂牌谱转换组件不完整，请更新或重新安装工具。"
        ) from exc
    except Exception as exc:  # tensoul exposes parser-specific exception types
        raise RemoteReplayError("雀魂牌谱转换为 Tenhou/6 JSON 失败。") from exc
    if not isinstance(payload, dict):
        raise RemoteReplayError("雀魂转换器返回了无效数据。")
    validate_tenhou_json(payload)
    return payload


async def _cn_login(lobby: Lobby, credentials: MahjongSoulCredentials, version: str) -> Any:
    if not credentials.account.strip() or not credentials.password:
        raise AuthenticationRequired(ServerRegion.CN, "国服雀魂需要账号和密码。")
    request = pb.ReqLogin()
    request.account = credentials.account.strip()
    request.password = _password_digest(credentials.password)
    _fill_device(request.device)
    request.random_key = str(uuid.uuid4())
    request.gen_access_token = True
    request.client_version_string = version
    request.currency_platforms.extend([1, 2, 5, 6, 8, 10, 11])
    _set_if_present(request, "tag", "cn")
    return await lobby.login(request)


async def authenticate_yostar(
    credentials: MahjongSoulCredentials,
) -> YostarSession:
    if not credentials.email.strip():
        raise AuthenticationRequired(ServerRegion.JP, "雀魂国际服需要 Yostar 邮箱登录。")
    client = YostarClient(
        ServerRegion.JP,
        device_id=credentials.yostar_device_id,
    )
    if credentials.verification_code:
        session = await client.exchange_email_code(
            credentials.email,
            credentials.verification_code,
        )
    elif credentials.yostar_uid and credentials.yostar_token:
        session = await client.refresh(credentials.yostar_uid, credentials.yostar_token)
    else:
        raise VerificationCodeRequired(
            ServerRegion.JP,
            "请先发送并填写邮箱验证码。",
        )
    return session


async def _oauth_login(
    lobby: Lobby,
    session: YostarSession,
    version: str,
    target_region: ServerRegion,
) -> Any:
    oauth_type = 21 if target_region is ServerRegion.JP else 22

    auth_request = pb.ReqOauth2Auth(
        type=oauth_type,
        code=session.token,
        uid=session.uid,
        client_version_string=version,
    )
    auth = await lobby.oauth2_auth(auth_request)
    if getattr(auth, "error", None) and int(auth.error.code) != 0:
        raise RemoteReplayError(f"雀魂 OAuth2 授权失败，代码 {int(auth.error.code)}。")
    if not str(auth.access_token):
        raise RemoteReplayError("雀魂 OAuth2 授权未返回访问令牌。")

    check = await lobby.oauth2_check(
        pb.ReqOauth2Check(type=oauth_type, access_token=auth.access_token)
    )
    if getattr(check, "error", None) and int(check.error.code) != 0:
        raise RemoteReplayError(f"雀魂 OAuth2 会话检查失败，代码 {int(check.error.code)}。")
    if hasattr(check, "has_account") and not check.has_account:
        raise RemoteReplayError("该 Yostar 账号尚未绑定雀魂账号。")

    request = pb.ReqOauth2Login()
    request.type = oauth_type
    request.access_token = auth.access_token
    request.reconnect = True
    _fill_device(request.device)
    request.random_key = str(uuid.uuid4())
    if "client_version" in request.DESCRIPTOR.fields_by_name:
        request.client_version.resource = version.removeprefix("web-")
    request.client_version_string = version
    request.currency_platforms.extend([1, 4, 5, 9, 12])
    _set_if_present(request, "version", 0)
    _set_if_present(request, "tag", "majsoul-hk-client")
    return await lobby.oauth2_login(request)


async def _fetch_from_gateway(
    endpoint: str,
    reference: ReplayReference,
    credentials: MahjongSoulCredentials,
    version: str,
    *,
    target_region: ServerRegion,
    yostar_session: YostarSession | None = None,
) -> MahjongSoulFetch:
    channel = MSRPCChannel(endpoint)
    try:
        await channel.connect(_origin(target_region))
        lobby = Lobby(channel)
        if target_region is ServerRegion.CN:
            login = await _cn_login(lobby, credentials, version)
        else:
            if yostar_session is None:
                raise AuthenticationRequired(
                    ServerRegion.JP,
                    "雀魂国际服需要 Yostar 邮箱登录。",
                )
            login = await _oauth_login(
                lobby,
                yostar_session,
                version,
                target_region,
            )
        if getattr(login, "error", None) and int(login.error.code) != 0:
            raise RemoteReplayError(f"雀魂登录失败，代码 {int(login.error.code)}。")
        if int(getattr(login, "account_id", 0)) <= 0:
            raise RemoteReplayError("雀魂登录未返回有效账号。")

        request = pb.ReqGameRecord(
            game_uuid=reference.replay_id,
            client_version_string=version,
        )
        try:
            record = await lobby.fetch_game_record(request)
        except Exception:
            await lobby.read_game_record(request)
            record = await lobby.fetch_game_record(request)
        if getattr(record, "error", None) and int(record.error.code) != 0:
            if int(record.error.code) == 151:
                await lobby.read_game_record(request)
                record = await lobby.fetch_game_record(request)
            if getattr(record, "error", None) and int(record.error.code) != 0:
                if int(record.error.code) == 151:
                    raise ReplayNotFoundError(
                        target_region,
                        f"雀魂{_region_label(target_region)}没有找到这份牌谱。",
                    )
                raise RemoteReplayError(
                    f"雀魂读取牌谱失败，代码 {int(record.error.code)}。"
                )
        if not record.data and str(record.data_url):
            record.data = await _download_record_data(str(record.data_url))
        if str(record.head.uuid) != reference.replay_id:
            raise RemoteReplayError("雀魂服务器返回了不同的牌谱 ID。")
        if len(record.head.accounts) != 4:
            raise RemoteReplayError("自定义牌谱仅支持四人立直麻将。")
        return MahjongSoulFetch(
            payload=_convert_record(record),
            yostar_session=yostar_session,
        )
    finally:
        with suppress(Exception):
            await channel.close()


async def fetch_majsoul(
    reference: ReplayReference,
    credentials: MahjongSoulCredentials,
) -> MahjongSoulFetch:
    primary_region = (
        ServerRegion.CN
        if credentials.region is ServerRegion.CN
        else ServerRegion.JP
    )
    yostar_session = (
        None
        if primary_region is ServerRegion.CN
        else await authenticate_yostar(credentials)
    )

    async def fetch_region(region: ServerRegion) -> MahjongSoulFetch:
        try:
            version, gateways = await _bootstrap(region)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise RemoteReplayError(
                f"无法连接雀魂{_region_label(region)}配置服务器。"
            ) from exc
        last_error: Exception | None = None
        for endpoint in gateways:
            try:
                return await _fetch_from_gateway(
                    endpoint,
                    reference,
                    credentials,
                    version,
                    target_region=region,
                    yostar_session=yostar_session,
                )
            except (
                AuthenticationRequired,
                VerificationCodeRequired,
                ReplayNotFoundError,
                RemoteReplayError,
            ):
                raise
            except Exception as exc:  # try the next official gateway
                last_error = exc
        raise RemoteReplayError(
            f"无法连接雀魂{_region_label(region)}游戏服务器"
            f"（{_connection_reason(last_error)}）。{_network_guidance(region)}"
        ) from last_error

    try:
        return await fetch_region(primary_region)
    except (AuthenticationRequired, VerificationCodeRequired):
        raise
    except RemoteReplayError as primary_error:
        # 美服/韩服链接仍优先从日服读取。只有链接本身来自美服/韩服，
        # 且日服确实没有牌谱或日服网络不可达时，才访问原服务器。
        cause = primary_error.__cause__
        should_fallback = isinstance(primary_error, ReplayNotFoundError) or isinstance(
            cause,
            (aiohttp.ClientError, TimeoutError, OSError),
        )
        if (
            primary_region is ServerRegion.JP
            and reference.source_region is ServerRegion.EN
            and should_fallback
        ):
            return await fetch_region(ServerRegion.EN)
        raise


async def send_yostar_email_code(
    region: ServerRegion,
    email: str,
    *,
    device_id: str = "",
) -> str:
    if region not in {ServerRegion.JP, ServerRegion.EN}:
        raise ValueError("国服不使用 Yostar 邮箱验证码。")
    normalized = email.strip()
    if "@" not in normalized or len(normalized) > 320:
        raise ValueError("请输入有效的邮箱地址。")
    client = YostarClient(ServerRegion.JP, device_id=device_id)
    await client.send_email_code(normalized)
    return client.device_id
