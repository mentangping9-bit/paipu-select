from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit

from .models import InvalidReplayUrl, Platform, ReplayReference, ServerRegion

_MAJSOUL_DOMAINS = (
    "maj-soul.com",
    "maj-soul.net",
    "mahjongsoul.com",
    "mahjongsoul.game.yo-star.com",
)
_RIICHI_CITY_DOMAINS = ("mahjong-jp.com", "riichicity.com")
_RIICHI_ID = re.compile(r"^[A-Za-z0-9]{20}$")
_MAJSOUL_STANDARD_ID = re.compile(r"^\d{6}-[0-9a-fA-F-]{36}$")
_MAJSOUL_LOOSE_ID = re.compile(r"^[A-Za-z0-9-]{20,64}$")
_DIRECT_RC = re.compile(r"^(?P<id>[A-Za-z0-9]{20})(?:@(?P<seat>[0-3]))?$")


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _seat(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    if value not in {"0", "1", "2", "3"}:
        raise InvalidReplayUrl("主视角座位必须是 0、1、2 或 3。")
    return int(value)


def _decode_majsoul_account(encoded: str) -> int | None:
    if not encoded.isdigit():
        return None
    try:
        value = int((((int(encoded) - 1_358_437) ^ 86_216_345) - 1_117_113) / 7)
    except (OverflowError, ValueError):
        return None
    return value if value > 0 else None


def _deanonymize_majsoul_id(value: str) -> str:
    """Decode newer character-shifted public replay identifiers when present."""

    if _MAJSOUL_STANDARD_ID.fullmatch(value):
        return value.lower()
    if not any(character.isalpha() and character.lower() > "f" for character in value):
        return value
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    decoded: list[str] = []
    for index, character in enumerate(value.lower()):
        if character == "-":
            decoded.append("-")
            continue
        if character not in alphabet:
            return value
        decoded.append(alphabet[(alphabet.index(character) - index + 55) % 36])
    candidate = "".join(decoded)
    return candidate if _MAJSOUL_STANDARD_ID.fullmatch(candidate) else value


def parse_majsoul_url(value: str) -> ReplayReference:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not _host_matches(host, _MAJSOUL_DOMAINS)
        or parsed.username
        or parsed.password
    ):
        raise InvalidReplayUrl("请输入官方雀魂 HTTPS 牌谱链接。")
    paipu = (parse_qs(parsed.query).get("paipu") or [""])[0].strip()
    if not paipu:
        raise InvalidReplayUrl("雀魂链接中缺少 paipu 参数。")

    pieces = unquote(paipu).split("_")
    replay_id = _deanonymize_majsoul_id(pieces[0])
    if not (_MAJSOUL_STANDARD_ID.fullmatch(replay_id) or _MAJSOUL_LOOSE_ID.fullmatch(replay_id)):
        raise InvalidReplayUrl("雀魂牌谱 ID 格式不正确。")

    viewer_account_id: int | None = None
    requested_seat: int | None = None
    for piece in pieces[1:]:
        if piece.startswith("a") and len(piece) > 1:
            viewer_account_id = _decode_majsoul_account(piece[1:])
        elif piece in {"0", "1", "2", "3"}:
            requested_seat = int(piece)
    return ReplayReference(
        platform=Platform.MAHJONG_SOUL,
        replay_id=replay_id,
        requested_seat=requested_seat,
        viewer_account_id=viewer_account_id,
        source_url=value.strip(),
        source_region=(
            ServerRegion.EN
            if _host_matches(host, ("mahjongsoul.game.yo-star.com",))
            else (
                ServerRegion.JP
                if _host_matches(host, ("mahjongsoul.com",))
                else ServerRegion.CN
            )
        ),
    )


def parse_riichi_city_url(value: str) -> ReplayReference:
    stripped = value.strip()
    direct = _DIRECT_RC.fullmatch(stripped)
    if direct:
        return ReplayReference(
            platform=Platform.RIICHI_CITY,
            replay_id=direct.group("id"),
            requested_seat=_seat(direct.group("seat")),
            source_url=stripped,
        )

    parsed = urlsplit(stripped)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not _host_matches(host, _RIICHI_CITY_DOMAINS)
        or parsed.username
        or parsed.password
    ):
        raise InvalidReplayUrl("请输入官方一番街 HTTPS 牌谱链接。")
    query = parse_qs(parsed.query)
    raw = next(
        (
            (query.get(name) or [""])[0].strip()
            for name in (
                "paipu",
                "record_id",
                "recordId",
                "game_id",
                "replay",
                "log_id",
                "keyValue",
            )
            if (query.get(name) or [""])[0].strip()
        ),
        "",
    )
    if not raw:
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[-2].lower() == "replay":
            raw = parts[-1]
    replay_id, separator, seat_text = raw.partition("@")
    if not _RIICHI_ID.fullmatch(replay_id):
        raise InvalidReplayUrl("一番街链接中缺少 20 位牌谱 ID。")
    return ReplayReference(
        platform=Platform.RIICHI_CITY,
        replay_id=replay_id,
        requested_seat=_seat(seat_text if separator else None),
        source_url=stripped,
    )


def parse_replay_url(value: str) -> ReplayReference:
    stripped = value.strip()
    if not stripped:
        raise InvalidReplayUrl("请先粘贴牌谱 URL。")
    if _DIRECT_RC.fullmatch(stripped):
        return parse_riichi_city_url(stripped)
    parsed = urlsplit(stripped)
    host = (parsed.hostname or "").lower()
    if _host_matches(host, _MAJSOUL_DOMAINS):
        return parse_majsoul_url(stripped)
    if _host_matches(host, _RIICHI_CITY_DOMAINS):
        return parse_riichi_city_url(stripped)
    raise InvalidReplayUrl("目前仅支持雀魂和一番街的官方牌谱链接。")
