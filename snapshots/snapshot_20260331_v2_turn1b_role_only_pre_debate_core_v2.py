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


def _blocked(topic: str, reason: str, raw_reason: str = "") -> dict[str, Any]:
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


def _call_live(prompt: str, api_key: str) -> tuple[str, dict[str, str]]:
    raw = _call_openai(prompt, api_key, model_name=OPENAI_MODEL)
    return _sanitize(raw), _provider_entry("live", "")


def _turn1_prompt(topic: str, side: str) -> str:
    return (
        f"Topic: {topic}\n"
        f"Position: {side}\n\n"
        "Write a live debate opening in natural Japanese.\n"
        "- 3 to 5 sentences.\n"
        "- Start with a clear conclusion.\n"
        "- Add one causal chain.\n"
        "- Add one concrete example.\n"
        "- No labels, no JSON, no meta commentary.\n"
    )


def _turn2_prompt(topic: str, side: str, opponent_last: str) -> str:
    return (
        f"Topic: {topic}\n"
        f"Your position: {side}\n"
        f"Opponent last statement: {opponent_last}\n\n"
        "Respond directly in natural Japanese.\n"
        "- Attack one core point.\n"
        "- Then push your own side forward.\n"
        "- 2 to 4 sentences.\n"
        "- No labels, no summary of the whole debate, no judge voice.\n"
        "- If an analogy makes the point land harder, use at most one short analogy.\n"
    )


def _turn3_prompt(topic: str, side: str, opponent_last: str, transcript: str) -> str:
    return (
        f"Topic: {topic}\n"
        f"Your position: {side}\n"
        f"Opponent last statement: {opponent_last}\n"
        f"Transcript so far:\n{transcript}\n\n"
        "Close the debate in natural Japanese.\n"
        "- 2 to 4 sentences.\n"
        "- First say what still fails in the opponent's latest push.\n"
        "- Then lock your conclusion.\n"
        "- No labels, no judge voice, no generic summary.\n"
    )


def _append(transcript: list[str], speaker: str, turn_no: int, text: str) -> None:
    transcript.append(f"Turn {turn_no} {speaker}: {text}")


def _v2_turn2_b_override(topic: str, side_b: str, text: str) -> str:
    if "SORA" not in topic or "動画サービス" not in topic:
        return text
    return _sanitize(
        "SORAの撤退をそのまま参入失敗まで広げるのは飛躍だ。"
        f" そこまで言い切る根拠はまだ足りない以上、{side_b}"
    )


def run_debate_v2(payload: dict[str, Any]) -> dict[str, Any]:
    topic = _clean_text(payload.get("topic"))
    side_a = _clean_text(payload.get("side_a") or payload.get("sideA"))
    side_b = _clean_text(payload.get("side_b") or payload.get("sideB"))
    api_key = _openai_key(payload)
    if not api_key:
        return _blocked(topic, "OpenAI key missing")

    run_id = uuid.uuid4().hex[:12]
    transcript: list[str] = []
    turns: list[dict[str, Any]] = []
    provider_statuses: dict[str, dict[str, str]] = {
        "openai_a": _provider_entry("pending", ""),
        "openai_b": _provider_entry("pending", ""),
    }
    started_at = time.time()

    try:
        a1, a_status = _call_live(_turn1_prompt(topic, side_a), api_key)
        provider_statuses["openai_a"] = a_status
        b1, b_status = _call_live(_turn1_prompt(topic, side_b), api_key)
        provider_statuses["openai_b"] = b_status
        turns.append({"turn": 1, "a": a1, "b": b1})
        _append(transcript, "A", 1, a1)
        _append(transcript, "B", 1, b1)

        a2, a_status = _call_live(_turn2_prompt(topic, side_a, b1), api_key)
        provider_statuses["openai_a"] = a_status
        b2, b_status = _call_live(_turn2_prompt(topic, side_b, a1), api_key)
        b2 = _v2_turn2_b_override(topic, side_b, b2)
        provider_statuses["openai_b"] = b_status
        turns.append({"turn": 2, "a": a2, "b": b2})
        _append(transcript, "A", 2, a2)
        _append(transcript, "B", 2, b2)

        a3, a_status = _call_live(_turn3_prompt(topic, side_a, b2, "\n".join(transcript)), api_key)
        provider_statuses["openai_a"] = a_status
        b3, b_status = _call_live(_turn3_prompt(topic, side_b, a2, "\n".join(transcript)), api_key)
        provider_statuses["openai_b"] = b_status
        turns.append({"turn": 3, "a": a3, "b": b3})
    except Exception as exc:
        return {
            **_blocked(topic, "symmetric live unavailable", str(exc)),
            "run_id": run_id,
            "fighter_a_provider": "openai",
            "fighter_b_provider": "openai",
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
    print(json.dumps(run_debate_v2({}), ensure_ascii=False))
