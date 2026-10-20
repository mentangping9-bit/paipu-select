"""Per-region Yostar SDK credentials and 2026 Unity connection handshake.

This module reuses upstream's authenticated HTTPS request implementation.
It never logs or returns Yostar credentials. Network login requires live validation.
"""
from __future__ import annotations
import hashlib
import json

import aiohttp

REGIONS = {
    # KR/EN retain their established issuers. JP uses JP-MJ from the game
    # migration URL and Mahjong-Replay-Converter; JP-MAJONGSOUL is rejected
    # by the live SDK with PROJECT_NOT_EXIST (300200).
    "kr": ("KR", "KR-MAJONGSOUL", "kr", "https://jp-sdk-api.yostarplat.com"),
    "jp": ("JP", "JP-MJ", "ja", "https://jp-sdk-api.yostarplat.com"),
    "en": ("US", "US-MAJONGSOUL", "en", "https://en-sdk-api.yostarplat.com"),
}


def regional_client(region: str, device_id: str = ""):
    if region not in REGIONS:
        raise ValueError("지원하지 않는 Yostar 인증 지역입니다.")
    from paipu_vendor.mahjong_url_parser.models import ServerRegion
    from paipu_vendor.mahjong_url_parser.sources.yostar import YostarClient, YostarSession
    from paipu_vendor.mahjong_url_parser.sources.yostar import SIGNING_SALT, YostarApiError
    from paipu_vendor.mahjong_url_parser.models import RemoteReplayError

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

        async def _post(self, endpoint, body, *, uid="", token=""):
            compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            head = self._head(uid=uid, token=token)
            encoded = compact(body)
            signature = hashlib.md5((compact(head) + encoded + SIGNING_SALT).encode()).hexdigest().upper()
            headers = {'Authorization': compact({'Head': head, 'Sign': signature}),
                       'Content-Type': 'application/json', 'Accept': 'application/json'}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), trust_env=True) as http:
                async with http.post(f'{self.base_url}/{endpoint}', data=encoded.encode(), headers=headers,
                                     allow_redirects=False) as response:
                    raw = await response.content.read(262145)
                    if response.status != 200 or len(raw) > 262144:
                        raise RemoteReplayError('Yostar 응답을 확인하지 못했습니다.')
            try:
                payload = json.loads(raw)
                code = int(payload.get('Code', 0))
            except (ValueError, AttributeError, TypeError):
                raise RemoteReplayError('Yostar 응답 형식 오류입니다.') from None
            if code != 200:
                # Provider messages can echo submitted values. Keep only a code.
                error = YostarApiError(code, 'Authentication rejected')
                error.stage = {'yostar/send-code':'send_code', 'yostar/get-auth':'exchange_code',
                               'user/login':'sdk_login', 'user/quick-login':'sdk_refresh'}.get(endpoint, 'sdk')
                raise error
            return payload

        async def send_email_code(self, email):
            await self._post("yostar/send-code", {"Account": email.strip()})

        async def exchange_email_code(self, email, code):
            auth = await self._post("yostar/get-auth", {
                "Account": email.strip(), "Code": code.strip()
            })
            otp_token = str(auth["Data"]["Token"])
            login = await self._post("user/login", {
                "Type": "yostar", "OpenID": email.strip(),
                "Token": otp_token, "Secret": "", "CheckAccountPlus": 0,
            })
            info = login["Data"]["UserInfo"]
            if not info.get("ID") or not info.get("Token"):
                raise RuntimeError("Yostar session missing")
            return YostarSession(uid=str(info["ID"]), token=str(info["Token"]),
                                 device_id=self.device_id)

        async def refresh(self, uid, token):
            # The upstream implementation treats *every* API error and even
            # malformed responses as expired credentials. Without documented
            # provider error-code semantics we must preserve the saved token.
            # HTTP/network/API failures are reported without deleting it.
            result = await self._post('user/quick-login', {}, uid=uid, token=token)
            try:
                refreshed = result['Data']['UserInfo']['Token']
                if not isinstance(refreshed, str) or not refreshed:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise RemoteReplayError('Yostar 자동 인증 응답에 세션 정보가 없습니다.') from None
            return YostarSession(uid=uid, token=refreshed, device_id=self.device_id)

    return RegionClient()
