from __future__ import annotations

import json
from typing import Any

from .models import InvalidTenhouJson, TenhouSummary

MAX_JSON_BYTES = 16 * 1024 * 1024
SOUTH_GAME_MARKERS = (
    "東南",
    "东南",
    "南風",
    "南风",
    "南",
    "半荘",
    "半庄",
    "hanchan",
    "south",
)
EAST_GAME_MARKERS = ("東風", "东风", "東", "东", "tonpu", "east")


def loads_tenhou_json(data: bytes | str) -> dict[str, Any]:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if not raw or len(raw) > MAX_JSON_BYTES:
        raise InvalidTenhouJson("牌谱 JSON 必须介于 1 字节和 16 MiB 之间。")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTenhouJson("文件不是有效的 UTF-8 JSON。") from exc
    if not isinstance(payload, dict):
        raise InvalidTenhouJson("Tenhou/6 JSON 顶层必须是对象。")
    validate_tenhou_json(payload)
    return payload


def validate_tenhou_json(payload: dict[str, Any]) -> TenhouSummary:
    version = str(payload.get("ver") or "")
    if not version:
        raise InvalidTenhouJson("Tenhou/6 JSON 缺少 ver 字段。")
    replay_id = str(payload.get("ref") or "").strip()
    if not replay_id:
        raise InvalidTenhouJson("Tenhou/6 JSON 缺少 ref 牌谱 ID。")
    names = payload.get("name")
    if not isinstance(names, list) or len(names) != 4 or not all(
        isinstance(name, str) for name in names
    ):
        raise InvalidTenhouJson("自定义牌谱仅支持四人立直麻将，name 必须包含 4 名玩家。")
    logs = payload.get("log")
    if not isinstance(logs, list) or not logs:
        raise InvalidTenhouJson("Tenhou/6 JSON 的 log 必须包含至少一局。")
    for index, round_log in enumerate(logs):
        if not isinstance(round_log, list) or len(round_log) < 17:
            raise InvalidTenhouJson(f"第 {index + 1} 局不符合 Tenhou/6 的 17 段结构。")
        round_info = round_log[0]
        scores = round_log[1]
        if not isinstance(round_info, (list, tuple)) or len(round_info) < 3:
            raise InvalidTenhouJson(f"第 {index + 1} 局缺少场次信息。")
        if not isinstance(scores, list) or len(scores) != 4:
            raise InvalidTenhouJson(f"第 {index + 1} 局必须包含 4 名玩家的点数。")
        for hand_index in (4, 7, 10, 13):
            if not isinstance(round_log[hand_index], list):
                raise InvalidTenhouJson(f"第 {index + 1} 局的配牌数据不完整。")
    rating_class = str(payload.get("ratingc") or "")
    if rating_class and rating_class != "PF4":
        raise InvalidTenhouJson("自定义牌谱仅支持四人立直麻将（ratingc=PF4）。")
    title_raw = payload.get("title")
    title = str(title_raw[0]) if isinstance(title_raw, list) and title_raw else ""
    game_length = _game_length(payload, title, logs)
    return TenhouSummary(
        replay_id=replay_id,
        player_count=4,
        round_count=len(logs),
        game_length=game_length,
        title=title,
    )


def _game_length(
    payload: dict[str, Any],
    title: str,
    logs: list[Any],
) -> str:
    rule = payload.get("rule")
    rule_display = str(rule.get("disp") or "") if isinstance(rule, dict) else ""
    for declared_rule in (rule_display, title):
        normalized = declared_rule.casefold()
        if any(marker.casefold() in normalized for marker in SOUTH_GAME_MARKERS):
            return "东南战"
        if any(marker.casefold() in normalized for marker in EAST_GAME_MARKERS):
            return "东风战"

    # Compatibility fallback for custom Tenhou/6 files without a rule label.
    return "东南战" if any(
        isinstance(round_log[0], (list, tuple)) and int(round_log[0][0]) >= 4
        for round_log in logs
    ) else "东风战"


def dumps_tenhou_json(payload: dict[str, Any], *, pretty: bool = False) -> bytes:
    validate_tenhou_json(payload)
    if pretty:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = (text + "\n").encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise InvalidTenhouJson("生成的牌谱 JSON 超过 16 MiB。")
    return encoded
