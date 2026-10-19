from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class Platform(StrEnum):
    MAHJONG_SOUL = "mahjong-soul"
    RIICHI_CITY = "riichi-city"
    FILE = "file"


class ServerRegion(StrEnum):
    CN = "cn"
    JP = "jp"
    EN = "en"


class ReplayFormat(StrEnum):
    TENHOU6 = "tenhou6"
    MJAI = "mjai"
    MJLOG = "mjlog"


@dataclass(frozen=True)
class ReplayReference:
    platform: Platform
    replay_id: str
    requested_seat: int | None = None
    viewer_account_id: int | None = None
    source_url: str = ""
    source_region: ServerRegion | None = None


@dataclass(frozen=True)
class MahjongSoulCredentials:
    region: ServerRegion
    account: str = ""
    password: str = ""
    email: str = ""
    yostar_uid: str = ""
    yostar_token: str = ""
    yostar_device_id: str = ""
    verification_code: str = ""


@dataclass(frozen=True)
class TenhouSummary:
    replay_id: str
    player_count: int
    round_count: int
    game_length: str
    title: str


@dataclass(frozen=True)
class ExportResult:
    reference: ReplayReference
    path: Path
    filename: str
    size_bytes: int
    summary: TenhouSummary
    payload: dict[str, Any]
    source_format: ReplayFormat = ReplayFormat.TENHOU6
    output_format: ReplayFormat = ReplayFormat.TENHOU6


class ReplayConverterError(RuntimeError):
    """Base class for user-facing conversion errors."""


class InvalidReplayUrl(ReplayConverterError):
    pass


class AuthenticationRequired(ReplayConverterError):
    def __init__(self, region: ServerRegion, message: str = "") -> None:
        self.region = region
        super().__init__(message or f"Mahjong Soul authentication is required for {region.value}.")


class VerificationCodeRequired(AuthenticationRequired):
    pass


class RemoteReplayError(ReplayConverterError):
    pass


class InvalidTenhouJson(ReplayConverterError):
    pass


class InvalidReplayFile(ReplayConverterError):
    pass


class ReplayNotFoundError(RemoteReplayError):
    def __init__(self, region: ServerRegion, message: str = "") -> None:
        self.region = region
        super().__init__(message or f"Replay was not found on {region.value}.")
