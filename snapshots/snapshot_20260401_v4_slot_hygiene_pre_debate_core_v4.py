from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

try:
    from debate_api import _call_openai
except ModuleNotFoundError:
    from tools.debate_api import _call_openai


OPENAI_MODEL = "gpt-5-mini"
SORA_TOPIC = "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。"
SIDE_A = "GPTは動画サービスに手を出すべきではなかった"
SIDE_B = "GPTは動画サービスに手を出すべきだった"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _sanitize(text: str) -> str:
    return " ".join(_clean_text(text).split())


def _openai_key(payload: dict[str, Any]) -> str:
    api_keys = payload.get("api_keys") if isinstance(payload.get("api_keys"), dict) else {}
    return _clean_text(api_keys.get("openai") or os.getenv("OPENAI_API_KEY"))


def _provider_entry(mode: str, reason: str = "", raw_reason: str = "") -> dict[str, str]:
    entry = {"mode": mode, "reason": reason, "model": OPENAI_MODEL}
    if raw_reason:
        entry["raw_reason"] = raw_reason
    return entry


def _blocked(reason: str, raw_reason: str = "") -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    return {
        "ok": False,
        "mode": "blocked",
        "run_id": run_id,
        "topic": SORA_TOPIC,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "provider_statuses": {
            "openai_a": _provider_entry("blocked", reason, raw_reason),
            "openai_b": _provider_entry("blocked", reason, raw_reason),
        },
        "error": reason,
        "blocked_reason": reason,
        "debate": None,
    }


def _side_card() -> dict[str, str]:
    return {
        "proposition": SORA_TOPIC,
        "side_a_role": "proposition を支持する",
        "side_b_role": "proposition を反対する",
        "side_a_thesis": SIDE_A,
        "side_b_thesis": SIDE_B,
        "side_a_anti_thesis": SIDE_B,
        "side_b_anti_thesis": SIDE_A,
    }


def _contains(text: str, phrase: str) -> bool:
    return _sanitize(phrase) in _sanitize(text)


def _supports_anti(slot_value: str, anti_thesis: str) -> bool:
    text = _sanitize(slot_value)
    if not text:
        return True
    if "手を出すべきではなかった" in anti_thesis:
        return "手を出すべきではなかった" in text
    if "手を出すべきだった" in anti_thesis:
        return "手を出すべきだった" in text and "手を出すべきではなかった" not in text
    return _contains(text, anti_thesis)


def _forbidden_slot_text(text: str) -> bool:
    banned = [
        "私は",
        "結論から言うと",
        "残るのは",
        "私の側は",
        "以上",
        "だが",
        "しかし",
        "ただし",
        "一方で",
    ]
    return any(token in text for token in banned)


def _load_json_object(raw: str) -> dict[str, str]:
    text = _clean_text(raw)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("json missing")
    obj = json.loads(text[start : end + 1])
    return {str(k): _sanitize(v) for k, v in obj.items()}


def _call_slot_json(prompt: str, api_key: str) -> tuple[dict[str, str], dict[str, str]]:
    raw = _call_openai(prompt, api_key, model_name=OPENAI_MODEL)
    return _load_json_object(raw), _provider_entry("live", "")


def _slot_prompt(
    *,
    topic: str,
    role: str,
    thesis: str,
    anti_thesis: str,
    turn_name: str,
    transcript: str = "",
    opponent_last: str = "",
) -> str:
    shared = (
        f"Topic: {topic}\n"
        f"Role: {role}\n"
        f"Thesis: {thesis}\n"
        f"Anti-thesis: {anti_thesis}\n"
    )
    if opponent_last:
        shared += f"Opponent latest turn: {opponent_last}\n"
    if transcript:
        shared += f"Transcript so far:\n{transcript}\n"
    if turn_name == "turn1":
        spec = (
            "Return JSON only with keys: thesis, reason, evidence.\n"
            "- thesis must restate the thesis itself in natural Japanese.\n"
            "- reason must give one strongest reason only.\n"
            "- evidence must give one concrete fact or observation only.\n"
        )
    elif turn_name == "turn2":
        spec = (
            "Return JSON only with keys: thesis, fatal_flaw, metaphor.\n"
            "- fatal_flaw must name one fatal flaw in the opponent.\n"
            "- metaphor must be one concrete image.\n"
            "- thesis must restate your own thesis in natural Japanese.\n"
        )
    else:
        spec = (
            "Return JSON only with keys: thesis, unproven, surviving_reason.\n"
            "- unproven must say one thing the opponent still has not shown.\n"
            "- surviving_reason must say one reason your thesis still stands.\n"
            "- thesis must restate your own thesis in natural Japanese.\n"
        )
    return (
        shared
        + spec
        + "- Every slot must support the thesis only.\n"
        + "- Do not support the anti-thesis in any slot.\n"
        + "- Do not use adversative pivots.\n"
        + "- Do not add labels outside JSON.\n"
        + "- Keep each slot short.\n"
    )


def _render_turn1(slots: dict[str, str]) -> str:
    return f"{slots['thesis']}。 核は{slots['reason']}だ。 例えば{slots['evidence']}。"


def _render_turn2(slots: dict[str, str]) -> str:
    return f"相手の致命傷は{slots['fatal_flaw']}だ。 これは{slots['metaphor']}に近い。 だから{slots['thesis']}。"


def _render_turn3(slots: dict[str, str]) -> str:
    return f"相手は{slots['unproven']}を示せていない。 それでも残るのは{slots['surviving_reason']}だ。 だから{slots['thesis']}。"


def _turn_ok(turn_name: str, slots: dict[str, str], thesis: str, anti_thesis: str) -> bool:
    required = {
        "turn1": ["thesis", "reason", "evidence"],
        "turn2": ["thesis", "fatal_flaw", "metaphor"],
        "turn3": ["thesis", "unproven", "surviving_reason"],
    }[turn_name]
    for key in required:
        value = _sanitize(slots.get(key))
        if not value:
            return False
        if _forbidden_slot_text(value):
            return False
        if _supports_anti(value, anti_thesis):
            return False
    return _contains(slots["thesis"], thesis)


def _append(transcript: list[str], speaker: str, turn_no: int, text: str) -> None:
    transcript.append(f"Turn {turn_no} {speaker}: {text}")


def run_debate_v4(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = _openai_key(payload)
    if not api_key:
        return _blocked("OpenAI key missing")

    card = _side_card()
    run_id = uuid.uuid4().hex[:12]
    started_at = time.time()
    transcript: list[str] = []
    turns: list[dict[str, Any]] = []
    provider_statuses: dict[str, dict[str, str]] = {
        "openai_a": _provider_entry("pending", ""),
        "openai_b": _provider_entry("pending", ""),
    }

    try:
        a1_slots, a_status = _call_slot_json(
            _slot_prompt(
                topic=SORA_TOPIC,
                role=card["side_a_role"],
                thesis=card["side_a_thesis"],
                anti_thesis=card["side_a_anti_thesis"],
                turn_name="turn1",
            ),
            api_key,
        )
        provider_statuses["openai_a"] = a_status
        b1_slots, b_status = _call_slot_json(
            _slot_prompt(
                topic=SORA_TOPIC,
                role=card["side_b_role"],
                thesis=card["side_b_thesis"],
                anti_thesis=card["side_b_anti_thesis"],
                turn_name="turn1",
            ),
            api_key,
        )
        provider_statuses["openai_b"] = b_status
        if not _turn_ok("turn1", a1_slots, card["side_a_thesis"], card["side_a_anti_thesis"]) or not _turn_ok(
            "turn1", b1_slots, card["side_b_thesis"], card["side_b_anti_thesis"]
        ):
            return _blocked("slot invariant failed", "turn1")
        a1 = _render_turn1(a1_slots)
        b1 = _render_turn1(b1_slots)
        turns.append({"turn": 1, "a": a1, "b": b1})
        _append(transcript, "A", 1, a1)
        _append(transcript, "B", 1, b1)

        a2_slots, a_status = _call_slot_json(
            _slot_prompt(
                topic=SORA_TOPIC,
                role=card["side_a_role"],
                thesis=card["side_a_thesis"],
                anti_thesis=card["side_a_anti_thesis"],
                turn_name="turn2",
                opponent_last=b1,
                transcript="\n".join(transcript),
            ),
            api_key,
        )
        provider_statuses["openai_a"] = a_status
        b2_slots, b_status = _call_slot_json(
            _slot_prompt(
                topic=SORA_TOPIC,
                role=card["side_b_role"],
                thesis=card["side_b_thesis"],
                anti_thesis=card["side_b_anti_thesis"],
                turn_name="turn2",
                opponent_last=a1,
                transcript="\n".join(transcript),
            ),
            api_key,
        )
        provider_statuses["openai_b"] = b_status
        if not _turn_ok("turn2", a2_slots, card["side_a_thesis"], card["side_a_anti_thesis"]) or not _turn_ok(
            "turn2", b2_slots, card["side_b_thesis"], card["side_b_anti_thesis"]
        ):
            return _blocked("slot invariant failed", "turn2")
        a2 = _render_turn2(a2_slots)
        b2 = _render_turn2(b2_slots)
        turns.append({"turn": 2, "a": a2, "b": b2})
        _append(transcript, "A", 2, a2)
        _append(transcript, "B", 2, b2)

        a3_slots, a_status = _call_slot_json(
            _slot_prompt(
                topic=SORA_TOPIC,
                role=card["side_a_role"],
                thesis=card["side_a_thesis"],
                anti_thesis=card["side_a_anti_thesis"],
                turn_name="turn3",
                opponent_last=b2,
                transcript="\n".join(transcript),
            ),
            api_key,
        )
        provider_statuses["openai_a"] = a_status
        b3_slots, b_status = _call_slot_json(
            _slot_prompt(
                topic=SORA_TOPIC,
                role=card["side_b_role"],
                thesis=card["side_b_thesis"],
                anti_thesis=card["side_b_anti_thesis"],
                turn_name="turn3",
                opponent_last=a2,
                transcript="\n".join(transcript),
            ),
            api_key,
        )
        provider_statuses["openai_b"] = b_status
        if not _turn_ok("turn3", a3_slots, card["side_a_thesis"], card["side_a_anti_thesis"]) or not _turn_ok(
            "turn3", b3_slots, card["side_b_thesis"], card["side_b_anti_thesis"]
        ):
            return _blocked("slot invariant failed", "turn3")
        a3 = _render_turn3(a3_slots)
        b3 = _render_turn3(b3_slots)
        turns.append({"turn": 3, "a": a3, "b": b3})
    except Exception as exc:
        return {
            **_blocked("symmetric live unavailable", str(exc)),
            "run_id": run_id,
            "provider_statuses": provider_statuses,
        }

    elapsed_seconds = round(time.time() - started_at, 3)
    return {
        "ok": True,
        "mode": "live",
        "run_id": run_id,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "provider_statuses": provider_statuses,
        "elapsed_seconds": elapsed_seconds,
        "debate": {
            "topic": SORA_TOPIC,
            "turn_count": 3,
            "participants": {"a": "GPT", "b": "GPT"},
            "turns": turns,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_debate_v4({}), ensure_ascii=False))
