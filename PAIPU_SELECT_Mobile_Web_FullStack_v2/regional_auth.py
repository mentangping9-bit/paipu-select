"""Per-region Yostar SDK credentials and 2026 Unity connection handshake.

This module reuses upstream's authenticated HTTPS request implementation.
It never logs or returns Yostar credentials. Network login requires live validation.
"""
from __future__ import annotations
import time
import uuid

REGIONS = {
    # Korean web frontend shares the EN game gateway but has its own SDK identity.
    "kr": ("KR", "KR-MAJONGSOUL", "kr", "https://jp-sdk-api.yostarplat.com"),
    "jp": ("JP", "JP-MAJONGSOUL", "jp", "https://jp-sdk-api.yostarplat.com"),
    "en": ("US", "US-MAJONGSOUL", "en", "https://en-sdk-api.yostarplat.com"),
}


def regional_client(region: str, device_id: str = ""):
    if region not in REGIONS:
        raise ValueError("지원하지 않는 Yostar 인증 지역입니다.")
    from mahjong_url_parser.models import ServerRegion
    from mahjong_url_parser.sources.yostar import YostarClient

    identifier, pid, lang, sdk = REGIONS[region]

    class RegionClient(YostarClient):
        def __init__(self):
            super().__init__(ServerRegion.JP if region != "en" else ServerRegion.EN,
                             device_id=device_id)
            self.base_url = sdk
            self.region = ServerRegion.JP if region == "jp" else ServerRegion.EN

        def _head(self, *, uid="", token=""):
            head = super()._head(uid=uid, token=token)
            head.update({"Region": identifier, "PID": pid, "Lang": lang,
                         "Version": "4.16.2"})
            return head

        async def exchange_email_code(self, email, code):
            # New 2026 Yostar SDK expects CheckAccountPlus on user/login.
            from mahjong_url_parser.sources.yostar import YostarSession
            auth = await self._post("yostar/get-auth",
                                    {"Account": email.strip(), "Code": code.strip()})
            try:
                email_token = str(auth["Data"]["Token"])
            except (KeyError, TypeError) as exc:
                raise ValueError("Yostar 인증 토큰을 받지 못했습니다.") from exc
            login = await self._post("user/login", {
                "Type": "yostar", "OpenID": email.strip(), "Token": email_token,
                "Secret": "", "CheckAccountPlus": 0,
            })
            try:
                info = login["Data"]["UserInfo"]
                return YostarSession(uid=str(info["ID"]), token=str(info["Token"]),
                                     device_id=self.device_id)
            except (KeyError, TypeError) as exc:
                raise ValueError("Yostar 계정 세션을 받지 못했습니다.") from exc

    return RegionClient()


def _varint(n: int) -> bytes:
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128)
        n >>= 7
    out.append(n)
    return bytes(out)


def connection_payload(region: str, *, stamp: int | None = None) -> bytes:
    """Wire-encode .lq.Route.ReqRequestConnection fields 2,3,4,6.

    ms-api's generated 2025 proto lacks field 6; encoding it ourselves retains
    the required 'Web' platform field in the July 2026 Unity protocol.
    """
    route = ("jp-2" if region == "jp" else "en-2").encode()
    stamp = int(time.time()) if stamp is None else stamp
    return b"\x10\x01\x1a" + _varint(len(route)) + route + b"\x20" + _varint(stamp) + b"\x32\x03Web"


def patch_connection_handshake(upstream):
    """Install a single safe channel subclass; no per-request monkeypatching."""
    if getattr(upstream.MSRPCChannel, "_paipu_connect_patch", False):
        return
    Base = upstream.MSRPCChannel
    class Channel(Base):
        _paipu_connect_patch = True
        async def connect(self, origin):
            await super().connect(origin)
            region = "jp" if "jpg" in self._endpoint.lower() else "kr"
            packet = connection_payload(region)
            response = await self.send_request(".lq.Route.requestConnection", packet)
            if response is None:
                raise RuntimeError("게임 서버가 연결 초기화에 응답하지 않았습니다.")
            # Older protobuf decoders safely ignore newly added fields.
            from ms.protocol_pb2 import ResRequestConnection
            result = ResRequestConnection()
            result.ParseFromString(response)
            if getattr(result, "error", None) and int(result.error.code):
                raise RuntimeError(f"연결 초기화 실패: {int(result.error.code)}")
    upstream.MSRPCChannel = Channel
    if not getattr(upstream._oauth_login, "_paipu_oauth_patch", False):
        # Upstream's .removeprefix("web-") produces an invalid resource version
        # when the 2026 client sends "WebGL_2022-<version>".
        async def oauth_login(lobby, session, version, target_region):
            from ms import protocol_pb2 as pb
            oauth_type = 21 if target_region.value == "jp" else 22
            req = pb.ReqOauth2Auth(
                type=oauth_type, code=session.token, uid=session.uid,
                client_version_string=version)
            auth = await lobby.oauth2_auth(req)
            if getattr(auth, "error", None) and int(auth.error.code):
                raise upstream.RemoteReplayError(
                    f"雀魂 OAuth2 授权失败，代码 {int(auth.error.code)}。")
            if not str(auth.access_token):
                raise upstream.RemoteReplayError("OAuth2 토큰을 받지 못했습니다.")
            check = await lobby.oauth2_check(pb.ReqOauth2Check(
                type=oauth_type, access_token=auth.access_token))
            if getattr(check, "error", None) and int(check.error.code):
                raise upstream.RemoteReplayError(
                    f"雀魂 OAuth2 会话检查失败，代码 {int(check.error.code)}。")
            if hasattr(check, "has_account") and not check.has_account:
                raise upstream.RemoteReplayError("该 Yostar 账号尚未绑定雀魂账号。")
            login = pb.ReqOauth2Login()
            login.type = oauth_type
            login.access_token = auth.access_token
            login.reconnect = True
            upstream._fill_device(login.device)
            login.random_key = str(uuid.uuid4())
            if "client_version" in login.DESCRIPTOR.fields_by_name:
                login.client_version.resource = version.rsplit("-", 1)[-1]
            login.client_version_string = version
            login.currency_platforms.extend([1, 4, 5, 9, 12])
            upstream._set_if_present(login, "version", 0)
            upstream._set_if_present(login, "tag", "majsoul-hk-client")
            return await lobby.oauth2_login(login)
        oauth_login._paipu_oauth_patch = True
        upstream._oauth_login = oauth_login
