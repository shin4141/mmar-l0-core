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


def _resolve_topic(payload: dict[str, Any]) -> str:
    return _sanitize(payload.get("topic")) or SORA_TOPIC


def _resolve_side(payload: dict[str, Any], key: str, fallback: str) -> str:
    return _sanitize(payload.get(key)) or fallback


def _blocked(reason: str, raw_reason: str = "", topic: str = SORA_TOPIC) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    return {
        "ok": False,
        "mode": "blocked",
        "run_id": run_id,
        "topic": topic,
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


def _blocked_with_trace(reason: str, raw_reason: str, trace: list[dict[str, Any]], topic: str) -> dict[str, Any]:
    payload = _blocked(reason, raw_reason, topic)
    payload["trace"] = trace
    return payload


def _side_card(topic: str, side_a: str, side_b: str) -> dict[str, str]:
    return {
        "proposition": topic,
        "side_a_role": "proposition を支持する",
        "side_b_role": "proposition を反対する",
        "side_a_thesis": side_a,
        "side_b_thesis": side_b,
        "side_a_anti_thesis": side_b,
        "side_b_anti_thesis": side_a,
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


def _slot_forbidden_patterns(key: str) -> list[str]:
    common = ["。", "例えば", "だから", "相手は"]
    specific = {
        "thesis": [],
        "reason": ["だ", "です", "ます"],
        "evidence": ["例えば"],
        "fatal_flaw": ["致命傷は", "致命的欠陥は"],
        "metaphor": ["に近い"],
        "unproven": ["相手は", "を示せていない"],
        "surviving_reason": ["それでも残るのは", "だ", "です", "ます"],
    }
    return common + specific.get(key, [])


def _strip_prefixes(text: str, prefixes: list[str]) -> str:
    value = _sanitize(text)
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if value.startswith(prefix):
                value = _sanitize(value[len(prefix) :])
                changed = True
    return value


def _strip_suffixes(text: str, suffixes: list[str]) -> str:
    value = _sanitize(text)
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if value.endswith(suffix):
                value = _sanitize(value[: -len(suffix)])
                changed = True
    return value


def _normalize_slot(key: str, value: str) -> str:
    text = _sanitize(value).strip("。")
    rules: dict[str, tuple[list[str], list[str]]] = {
        "thesis": ([], ["。"]),
        "reason": (["核は", "問題は", "痛点は"], ["だから", "だ", "です", "ます", "。"]),
        "evidence": (["例えば、", "例えば"], ["。"]),
        "fatal_flaw": (["相手の致命傷は", "相手の急所は", "致命傷は", "致命的欠陥は"], ["。"]),
        "metaphor": ([], ["に近い", "みたいな話", "ようなもの", "。"]),
        "unproven": (["相手は"], ["を示せていない", "。"]),
        "surviving_reason": (["それでも残るのは"], ["が消えない", "だ", "です", "ます", "。"]),
    }
    prefixes, suffixes = rules.get(key, ([], []))
    text = _strip_prefixes(text, prefixes)
    text = _strip_suffixes(text, suffixes)
    return _sanitize(text).strip("。")


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


def _attempt_slot_acquisition(
    *,
    turn_name: str,
    prompt: str,
    api_key: str,
    thesis: str,
    anti_thesis: str,
    trace: list[dict[str, Any]],
    max_attempts: int = 3,
) -> tuple[dict[str, str], dict[str, str]]:
    last_slots: dict[str, str] | None = None
    last_status = _provider_entry("live", "")
    for attempt in range(1, max_attempts + 1):
        slots, status = _call_slot_json(prompt, api_key)
        normalized = _normalize_slots(turn_name, slots)
        ok = _turn_ok(turn_name, normalized, thesis, anti_thesis)
        trace.append(
            {
                "turn": turn_name,
                "attempt": attempt,
                "ok": ok,
                "slots": normalized,
            }
        )
        if ok:
            return normalized, status
        last_slots = normalized
        last_status = status
    if last_slots is not None:
        trace.append(
            {
                "turn": turn_name,
                "attempt": max_attempts,
                "ok": False,
                "final_slots": last_slots,
            }
        )
    raise ValueError(f"semantic slot invariant failed:{turn_name}")


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
            "- thesis must be one decisive opening sentence that states your side clearly and sounds publishable, without final punctuation.\n"
            "- thesis should carry both the stance and the main pain point, not just restate the position flatly.\n"
            "- reason must name one strongest problem or advantage only, as a short sharp phrase without 「だ」「です」「ます」 or punctuation.\n"
            "- evidence must give one concrete fact, scene, or observation only, without 「例えば」 or punctuation.\n"
        )
    elif turn_name == "turn2":
        spec = (
            "Return JSON only with keys: thesis, fatal_flaw, metaphor.\n"
            "- fatal_flaw must name one opponent-specific fatal flaw only, without 「致命傷は」 or punctuation.\n"
            "- fatal_flaw must sound like a real weakness in the opponent's latest push, not a generic summary.\n"
            "- metaphor must be one concrete image only, vivid and specific, without 「に近い」 or punctuation.\n"
            "- thesis must restate your own thesis in natural Japanese, without final punctuation.\n"
        )
    else:
        spec = (
            "Return JSON only with keys: thesis, unproven, surviving_reason.\n"
            "- unproven must say one thing the opponent still has not shown, without 「相手は」「を示せていない」 or punctuation.\n"
            "- surviving_reason must say one reason your thesis still stands, as a short phrase without 「それでも残るのは」「だ」「です」「ます」 or punctuation.\n"
            "- thesis must restate your own thesis in natural Japanese, without final punctuation.\n"
            "- close with pressure, not with a judge voice or abstract recap.\n"
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
    return f"{slots['thesis']}。 問題は{slots['reason']}だ。 現に、{slots['evidence']}。"


def _render_turn2(slots: dict[str, str]) -> str:
    return f"相手の急所は{slots['fatal_flaw']}だ。 {slots['metaphor']}みたいな話だ。 だから、{slots['thesis']}。"


def _render_turn3(slots: dict[str, str]) -> str:
    return f"相手は{slots['unproven']}を示せていない。 {slots['surviving_reason']}が消えない。 だから、{slots['thesis']}。"


def _slot_format_ok(key: str, value: str) -> bool:
    text = _sanitize(value)
    if not text:
        return False
    return not any(token in text for token in _slot_forbidden_patterns(key))


def _slots_format_ok(turn_name: str, slots: dict[str, str]) -> bool:
    required = {
        "turn1": ["thesis", "reason", "evidence"],
        "turn2": ["thesis", "fatal_flaw", "metaphor"],
        "turn3": ["thesis", "unproven", "surviving_reason"],
    }[turn_name]
    return all(_slot_format_ok(key, slots.get(key, "")) for key in required)


def _normalize_slots(turn_name: str, slots: dict[str, str]) -> dict[str, str]:
    required = {
        "turn1": ["thesis", "reason", "evidence"],
        "turn2": ["thesis", "fatal_flaw", "metaphor"],
        "turn3": ["thesis", "unproven", "surviving_reason"],
    }[turn_name]
    return {key: _normalize_slot(key, slots.get(key, "")) for key in required}


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
    topic = _resolve_topic(payload)
    side_a = _resolve_side(payload, "side_a", SIDE_A)
    side_b = _resolve_side(payload, "side_b", SIDE_B)
    if not api_key:
        return _blocked("OpenAI key missing", "", topic)

    card = _side_card(topic, side_a, side_b)
    run_id = uuid.uuid4().hex[:12]
    started_at = time.time()
    transcript: list[str] = []
    turns: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    provider_statuses: dict[str, dict[str, str]] = {
        "openai_a": _provider_entry("pending", ""),
        "openai_b": _provider_entry("pending", ""),
    }

    try:
        a1_slots, a_status = _attempt_slot_acquisition(
            turn_name="turn1",
            prompt=_slot_prompt(
                topic=topic,
                role=card["side_a_role"],
                thesis=card["side_a_thesis"],
                anti_thesis=card["side_a_anti_thesis"],
                turn_name="turn1",
            ),
            api_key=api_key,
            thesis=card["side_a_thesis"],
            anti_thesis=card["side_a_anti_thesis"],
            trace=trace,
        )
        provider_statuses["openai_a"] = a_status
        b1_slots, b_status = _attempt_slot_acquisition(
            turn_name="turn1",
            prompt=_slot_prompt(
                topic=topic,
                role=card["side_b_role"],
                thesis=card["side_b_thesis"],
                anti_thesis=card["side_b_anti_thesis"],
                turn_name="turn1",
            ),
            api_key=api_key,
            thesis=card["side_b_thesis"],
            anti_thesis=card["side_b_anti_thesis"],
            trace=trace,
        )
        provider_statuses["openai_b"] = b_status
        a1 = _render_turn1(a1_slots)
        b1 = _render_turn1(b1_slots)
        turns.append({"turn": 1, "a": a1, "b": b1})
        _append(transcript, "A", 1, a1)
        _append(transcript, "B", 1, b1)

        a2_slots, a_status = _attempt_slot_acquisition(
            turn_name="turn2",
            prompt=_slot_prompt(
                topic=topic,
                role=card["side_a_role"],
                thesis=card["side_a_thesis"],
                anti_thesis=card["side_a_anti_thesis"],
                turn_name="turn2",
                opponent_last=b1,
                transcript="\n".join(transcript),
            ),
            api_key=api_key,
            thesis=card["side_a_thesis"],
            anti_thesis=card["side_a_anti_thesis"],
            trace=trace,
        )
        provider_statuses["openai_a"] = a_status
        b2_slots, b_status = _attempt_slot_acquisition(
            turn_name="turn2",
            prompt=_slot_prompt(
                topic=topic,
                role=card["side_b_role"],
                thesis=card["side_b_thesis"],
                anti_thesis=card["side_b_anti_thesis"],
                turn_name="turn2",
                opponent_last=a1,
                transcript="\n".join(transcript),
            ),
            api_key=api_key,
            thesis=card["side_b_thesis"],
            anti_thesis=card["side_b_anti_thesis"],
            trace=trace,
        )
        provider_statuses["openai_b"] = b_status
        a2 = _render_turn2(a2_slots)
        b2 = _render_turn2(b2_slots)
        turns.append({"turn": 2, "a": a2, "b": b2})
        _append(transcript, "A", 2, a2)
        _append(transcript, "B", 2, b2)

        a3_slots, a_status = _attempt_slot_acquisition(
            turn_name="turn3",
            prompt=_slot_prompt(
                topic=topic,
                role=card["side_a_role"],
                thesis=card["side_a_thesis"],
                anti_thesis=card["side_a_anti_thesis"],
                turn_name="turn3",
                opponent_last=b2,
                transcript="\n".join(transcript),
            ),
            api_key=api_key,
            thesis=card["side_a_thesis"],
            anti_thesis=card["side_a_anti_thesis"],
            trace=trace,
        )
        provider_statuses["openai_a"] = a_status
        b3_slots, b_status = _attempt_slot_acquisition(
            turn_name="turn3",
            prompt=_slot_prompt(
                topic=topic,
                role=card["side_b_role"],
                thesis=card["side_b_thesis"],
                anti_thesis=card["side_b_anti_thesis"],
                turn_name="turn3",
                opponent_last=a2,
                transcript="\n".join(transcript),
            ),
            api_key=api_key,
            thesis=card["side_b_thesis"],
            anti_thesis=card["side_b_anti_thesis"],
            trace=trace,
        )
        provider_statuses["openai_b"] = b_status
        a3 = _render_turn3(a3_slots)
        b3 = _render_turn3(b3_slots)
        turns.append({"turn": 3, "a": a3, "b": b3})
    except Exception as exc:
        raw_reason = str(exc)
        if raw_reason.startswith("semantic slot invariant failed:"):
            turn_name = raw_reason.split(":", 1)[1]
            return {
                **_blocked_with_trace("slot invariant failed", turn_name, trace, topic),
                "run_id": run_id,
                "provider_statuses": provider_statuses,
            }
        return {
            **_blocked_with_trace("symmetric live unavailable", raw_reason, trace, topic),
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
            "topic": topic,
            "turn_count": 3,
            "participants": {"a": "GPT", "b": "GPT"},
            "turns": turns,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_debate_v4({}), ensure_ascii=False))
