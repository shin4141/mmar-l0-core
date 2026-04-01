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
SIDE_A = "GPTは動画サービスに手を出すべきではなかった。"
SIDE_B = "GPTは動画サービスに手を出すべきだった。"


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


def _call_live(prompt: str, api_key: str) -> tuple[str, dict[str, str]]:
    raw = _call_openai(prompt, api_key, model_name=OPENAI_MODEL)
    return _sanitize(raw), _provider_entry("live", "")


def _turn1_prompt(topic: str, side: str) -> str:
    return (
        f"Topic: {topic}\n"
        f"Side: {side}\n\n"
        "Write turn 1 of a hard 3-turn debate in natural Japanese.\n"
        "- 2 or 3 sentences only.\n"
        "- Sentence 1 must be a blunt conclusion.\n"
        "- Do not start with 「私は」「結論から言うと」 or any throat-clearing phrase.\n"
        "- Sentence 2 must give the single strongest reason.\n"
        "- Sentence 3 is optional and may give one concrete example.\n"
        "- Keep the claim narrow and sharp.\n"
        "- No labels, no meta commentary, no safety hedging.\n"
    )


def _turn2_prompt(topic: str, side: str, opponent_last: str) -> str:
    return (
        f"Topic: {topic}\n"
        f"Side: {side}\n"
        f"Opponent turn 1: {opponent_last}\n\n"
        "Write turn 2 of a hard 3-turn debate in natural Japanese.\n"
        "- 2 or 3 sentences only.\n"
        "- Sentence 1 must name the opponent's fatal flaw.\n"
        "- Include exactly one concrete image or analogy somewhere in the turn.\n"
        "- Sentence 2 must show why your side still stands.\n"
        "- Do not concede.\n"
        "- Do not just restate your opening.\n"
        "- Do not explain broadly or add a new scenario.\n"
        "- No labels, no meta commentary, no judge voice.\n"
    )


def _turn3_prompt(topic: str, side: str, opponent_last: str, transcript: str) -> str:
    return (
        f"Topic: {topic}\n"
        f"Side: {side}\n"
        f"Opponent turn 2: {opponent_last}\n"
        f"Transcript so far:\n{transcript}\n\n"
        "Write turn 3 of a hard 3-turn debate in natural Japanese.\n"
        "- 2 or 3 sentences only.\n"
        "- Close the match.\n"
        "- Sentence 1 must say what the opponent still has not proved.\n"
        "- Sentence 2 must keep only the one thing that remains for your side.\n"
        "- Final sentence must be a short finishing line.\n"
        "- No judge voice.\n"
        "- No meta phrases like 「私の側は」「残るのは」「以上」「説得力に欠ける」.\n"
        "- No new upside, no new evidence, no new dream scenario.\n"
    )


def _append(transcript: list[str], speaker: str, turn_no: int, text: str) -> None:
    transcript.append(f"Turn {turn_no} {speaker}: {text}")


def run_debate_v3(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = _openai_key(payload)
    if not api_key:
        return _blocked("OpenAI key missing")

    run_id = uuid.uuid4().hex[:12]
    transcript: list[str] = []
    turns: list[dict[str, Any]] = []
    provider_statuses: dict[str, dict[str, str]] = {
        "openai_a": _provider_entry("pending", ""),
        "openai_b": _provider_entry("pending", ""),
    }
    started_at = time.time()

    try:
        a1, a_status = _call_live(_turn1_prompt(SORA_TOPIC, SIDE_A), api_key)
        provider_statuses["openai_a"] = a_status
        b1, b_status = _call_live(_turn1_prompt(SORA_TOPIC, SIDE_B), api_key)
        provider_statuses["openai_b"] = b_status
        turns.append({"turn": 1, "a": a1, "b": b1})
        _append(transcript, "A", 1, a1)
        _append(transcript, "B", 1, b1)

        a2, a_status = _call_live(_turn2_prompt(SORA_TOPIC, SIDE_A, b1), api_key)
        provider_statuses["openai_a"] = a_status
        b2, b_status = _call_live(_turn2_prompt(SORA_TOPIC, SIDE_B, a1), api_key)
        provider_statuses["openai_b"] = b_status
        turns.append({"turn": 2, "a": a2, "b": b2})
        _append(transcript, "A", 2, a2)
        _append(transcript, "B", 2, b2)

        a3, a_status = _call_live(_turn3_prompt(SORA_TOPIC, SIDE_A, b2, "\n".join(transcript)), api_key)
        provider_statuses["openai_a"] = a_status
        b3, b_status = _call_live(_turn3_prompt(SORA_TOPIC, SIDE_B, a2, "\n".join(transcript)), api_key)
        provider_statuses["openai_b"] = b_status
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
    print(json.dumps(run_debate_v3({}), ensure_ascii=False))
