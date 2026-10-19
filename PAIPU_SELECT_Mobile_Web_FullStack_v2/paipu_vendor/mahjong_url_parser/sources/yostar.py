from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import aiohttp

from ..models import RemoteReplayError, ServerRegion, VerificationCodeRequired

SDK_VERSION = "4.16.0"
PROJECT_ID = "JP-MJ"
SIGNING_SALT = bytes(
    [52, 116, 103, 19, 26, 70, 111, 104, 101, 215, 242, 102, 46, 56, 132, 31, 190, 42, 219, 35]
).hex()


@dataclass(frozen=True)
class YostarSession:
    uid: str
    token: str
    device_id: str


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _response_message(payload: dict[str, Any]) -> str:
    return str(
        payload.get("Message")
        or payload.get("Msg")
        or payload.get("Desc")
        or "unknown error"
    )


class YostarApiError(RemoteReplayError):
    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(f"Yostar 登录失败（代码 {code or '未知'}）：{message}")


class YostarClient:
    def __init__(self, region: ServerRegion, *, device_id: str = "") -> None:
        if region not in {ServerRegion.JP, ServerRegion.EN}:
            raise ValueError("Yostar authentication only supports the international account.")
        # 日服、美服和韩服共用同一个 Yostar 账号体系。统一从日服 SDK
        # 登录，避免让用户维护多套验证码会话。
        self.region = ServerRegion.JP
        self.base_url = "https://jp-sdk-api.yostarplat.com"
        self.device_id = device_id or str(uuid.uuid4())

    def _head(self, *, uid: str = "", token: str = "") -> dict[str, str | int]:
        head: dict[str, str | int] = {
            "Region": "JP",
            "PID": PROJECT_ID,
            "Channel": "web",
            "Platform": "pc",
            "Version": SDK_VERSION,
            "Lang": "ja",
            "DeviceID": self.device_id,
            "Time": int(time.time()),
        }
        if uid:
            head["UID"] = uid
        if token:
            head["Token"] = token
        return head

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any],
        *,
        uid: str = "",
        token: str = "",
    ) -> dict[str, Any]:
        head = self._head(uid=uid, token=token)
        signature = hashlib.md5(
            f"{_compact(head)}{_compact(body)}{SIGNING_SALT}".encode()
        ).hexdigest().upper()
        authorization = _compact({"Head": head, "Sign": signature})
        try:
            async with (
                aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"User-Agent": "Mahjong-Replay-Converter/0.2"},
                ) as session,
                session.post(
                    f"{self.base_url}/{endpoint.lstrip('/')}",
                    data=_compact(body).encode(),
                    headers={
                        "Authorization": authorization,
                        "Accept": "application/json, text/plain, */*",
                        "Content-Type": "application/json",
                    },
                ) as response,
            ):
                text = await response.text()
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise RemoteReplayError("无法连接 Yostar 登录服务，请检查网络后重试。") from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RemoteReplayError("Yostar 登录服务返回了无法解析的数据。") from exc
        try:
            code = int(payload.get("Code", 0)) if isinstance(payload, dict) else 0
        except (TypeError, ValueError):
            code = 0
        if not isinstance(payload, dict) or code != 200:
            message = (
                _response_message(payload)
                if isinstance(payload, dict)
                else "invalid response"
            )
            raise YostarApiError(code, message)
        return payload

    async def send_email_code(self, email: str) -> None:
        await self._post(
            "yostar/send-code",
            {"Account": email.strip(), "Randstr": "", "Ticket": ""},
        )

    async def exchange_email_code(self, email: str, code: str) -> YostarSession:
        auth = await self._post(
            "yostar/get-auth",
            {"Account": email.strip(), "Code": code.strip()},
        )
        try:
            email_token = str(auth["Data"]["Token"])
        except (KeyError, TypeError) as exc:
            raise RemoteReplayError("Yostar 验证码响应中缺少登录令牌。") from exc
        login = await self._post(
            "user/login",
            {
                "CheckAccount": 0,
                "Geetest": {
                    "CaptchaID": None,
                    "CaptchaOutput": None,
                    "GenTime": None,
                    "LotNumber": None,
                    "PassToken": None,
                },
                "OpenID": email.strip(),
                "Secret": "",
                "Token": email_token,
                "Type": "yostar",
                "UserName": email.strip(),
            },
        )
        try:
            info = login["Data"]["UserInfo"]
            uid = str(info["ID"])
            token = str(info["Token"])
        except (KeyError, TypeError) as exc:
            raise RemoteReplayError("Yostar 登录响应中缺少用户会话。") from exc
        return YostarSession(uid=uid, token=token, device_id=self.device_id)

    async def refresh(self, uid: str, token: str) -> YostarSession:
        try:
            payload = await self._post("user/quick-login", {}, uid=uid, token=token)
        except YostarApiError as exc:
            raise VerificationCodeRequired(
                self.region,
                "保存的 Yostar 登录会话已失效，请重新获取并填写邮箱验证码。",
            ) from exc
        try:
            refreshed = str(payload["Data"]["UserInfo"]["Token"])
        except (KeyError, TypeError) as exc:
            raise VerificationCodeRequired(
                self.region,
                "保存的 Yostar 登录会话已失效，请重新获取并填写邮箱验证码。",
            ) from exc
        return YostarSession(uid=uid, token=refreshed, device_id=self.device_id)
