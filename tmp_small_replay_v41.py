from __future__ import annotations

import json
import os
import time
from pathlib import Path

from tools import debate_api
from tools.debate_core_v4 import run_debate_v4


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


def transcript_from_turns(turns: list[dict]) -> str:
    return "\n".join(
        f"Turn {turn.get('turn')} A: {turn.get('a', '')}\nTurn {turn.get('turn')} B: {turn.get('b', '')}"
        for turn in turns
    )


def run_judge_from_turns(topic: str, side_a: str, side_b: str, turns: list[dict], mode: str = "casual") -> dict:
    transcript = transcript_from_turns(turns)
    payload = {
        "topic": topic,
        "side_a": side_a,
        "side_b": side_b,
        "turn_count": 3,
        "mode": mode,
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "judge_provider": "gemini",
        "judge_mode": "scorecard_v1_shadow",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        "turns": turns,
        "transcript": transcript,
    }
    result = debate_api.run_live_judge(payload)
    summary = result.get("summary") or {}
    scorecard = result.get("scorecard_v1") or {}
    winner = (scorecard.get("winner") or {}).get("side") if isinstance(scorecard.get("winner"), dict) else ""
    winner_reason = (scorecard.get("winner") or {}).get("reason") if isinstance(scorecard.get("winner"), dict) else ""
    side_a_score = ((scorecard.get("side_a") or {}).get("score") if isinstance(scorecard.get("side_a"), dict) else None)
    side_b_score = ((scorecard.get("side_b") or {}).get("score") if isinstance(scorecard.get("side_b"), dict) else None)
    blind = scorecard.get("blind_explanation") if isinstance(scorecard.get("blind_explanation"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "mode": result.get("mode"),
        "judge_warning": result.get("judge_warning"),
        "winner": winner,
        "winner_reason": winner_reason,
        "weak_spot_label": ((summary.get("weak_spot") or {}).get("label") if isinstance(summary.get("weak_spot"), dict) else ""),
        "draw_tiebreak_applied": scorecard.get("draw_tiebreak_applied"),
        "draw_tiebreak_side": scorecard.get("draw_tiebreak_side"),
        "draw_tiebreak_reason": scorecard.get("draw_tiebreak_reason"),
        "score_a": side_a_score,
        "score_b": side_b_score,
        "blind_explanation": {
            "normative_superiority_side": blind.get("normative_superiority_side"),
            "bridge_valid": blind.get("bridge_valid"),
            "constitutive_break_side": blind.get("constitutive_break_side"),
            "constitutive_break_confidence": blind.get("constitutive_break_confidence"),
            "block_tiebreak_reason": blind.get("block_tiebreak_reason"),
        } if blind else {},
    }


def load_bundle_case(bundle_path: str) -> tuple[str, str, str, list[dict]]:
    bundle = Path(bundle_path)
    request_payload = json.loads((bundle / "request.json").read_text(encoding="utf-8"))
    response_payload = json.loads((bundle / "response.json").read_text(encoding="utf-8"))
    debate = response_payload.get("debate") or {}
    turns = debate.get("turns") or []
    return (
        request_payload.get("topic") or debate.get("topic") or "",
        request_payload.get("side_a") or "",
        request_payload.get("side_b") or "",
        turns,
    )


def generate_private_violence_swapped() -> tuple[str, str, str, list[dict], dict]:
    payload = {
        "topic": "外国人観光客による女性への乱暴が多発し、警察が機能していない地域では、地元住民による一定の実力行使は部分的に正当化されるのか",
        "side_a": "正当化されない",
        "side_b": "部分的に正当化される",
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
    }
    response = run_debate_v4(payload)
    debate = response.get("debate") or {}
    turns = debate.get("turns") or []
    return payload["topic"], payload["side_a"], payload["side_b"], turns, response


def main() -> None:
    load_dotenv(Path("/Users/sn/workspaces/mmar-l0-core/.env"))
    cases = {
        "life_pricing_base": "/tmp/mmar_run_bundle_a9c15c3b035f",
        "life_pricing_swapped": "/tmp/mmar_run_bundle_cfe7abca7549",
        "love_money_base": "/tmp/mmar_run_bundle_273df733b99a",
        "love_money_swapped": "/tmp/mmar_run_bundle_30720eb51da6",
        "private_violence_base": "/tmp/mmar_run_bundle_1bd754572ac2",
        "sora_base": "/tmp/mmar_run_bundle_ad1691e748be",
        "sora_swapped": "/tmp/mmar_run_bundle_08ba272ddee8",
    }
    results: dict[str, dict] = {}

    for name, bundle_path in cases.items():
        topic, side_a, side_b, turns = load_bundle_case(bundle_path)
        results[name] = run_judge_from_turns(topic, side_a, side_b, turns)
        time.sleep(0.2)

    topic, side_a, side_b, turns, raw_response = generate_private_violence_swapped()
    results["private_violence_swapped_generation"] = {
        "mode": raw_response.get("mode"),
        "ok": raw_response.get("ok"),
        "provider_statuses": raw_response.get("provider_statuses"),
        "turn_count": len(turns),
        "original_error": raw_response.get("original_error"),
    }
    if raw_response.get("ok") and raw_response.get("mode") == "live" and len(turns) == 3:
        results["private_violence_swapped"] = run_judge_from_turns(topic, side_a, side_b, turns)
    else:
        results["private_violence_swapped"] = {
            "ok": False,
            "mode": raw_response.get("mode"),
            "winner": "",
            "winner_reason": "",
            "weak_spot_label": "",
            "draw_tiebreak_applied": None,
            "draw_tiebreak_side": None,
            "draw_tiebreak_reason": None,
            "score_a": None,
            "score_b": None,
            "blind_explanation": {},
        }

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
