"""Shared Yostar international SDK authentication + game handshake.

Korean, English, and Japanese game regions use the SAME upstream JP SDK token
issuer. The game gateway and oauth type still differ by region. v2.3 issued
an invented KR-MAJONGSOUL SDK identity which caused OAuth2 error 110.
Never log tokens, email or one-time codes.
"""
from __future__ import annotations
import time
import uuid

# The upstream converter documents ONE international Yostar account system.
# IMPORTANT: "kr" / "en" select the game REPLAY gateway, not the issuer of
# the Yostar SDK token. oauth2Auth rejects independently invented SDK PIDs.
# Keep the original upstream YostarClient untouched, including its request
# signing, JP-MJ project identifier, login payload and sdk version.
VALID_REGIONS = frozenset({"kr", "jp", "en"})


def regional_client(region: str, device_id: str = ""):
    if region not in VALID_REGIONS:
        raise ValueError("지원하지 않는 Yostar 인증 지역입니다.")
    from mahjong_url_parser.models import ServerRegion
    from mahjong_url_parser.sources.yostar import YostarClient
    return YostarClient(ServerRegion.JP, device_id=device_id)


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
