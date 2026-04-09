from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tools.debate_api import run_live_judge


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


def main() -> None:
    load_dotenv(Path("/Users/sn/workspaces/mmar-l0-core/.env"))
    bundle = Path(sys.argv[1])
    request_payload = json.loads((bundle / "request.json").read_text(encoding="utf-8"))
    payload = json.loads((bundle / "response.json").read_text(encoding="utf-8"))
    debate = payload["debate"]
    turns = debate.get("turns") or []
    judge_payload = {
        "topic": request_payload.get("topic") or debate.get("topic") or "",
        "side_a": request_payload.get("side_a") or "",
        "side_b": request_payload.get("side_b") or "",
        "turn_count": request_payload.get("turn_count") or debate.get("turn_count") or 3,
        "mode": request_payload.get("mode") or "casual",
        "fighter_a_provider": request_payload.get("fighter_a_provider") or payload.get("fighter_a_provider") or "openai",
        "fighter_b_provider": request_payload.get("fighter_b_provider") or payload.get("fighter_b_provider") or "openai",
        "api_keys": {
            "openai": "",
            "anthropic": "",
            "gemini": "",
        },
        "turns": turns,
        "transcript": "\n".join(
            f"Turn {turn.get('turn')} A: {turn.get('a', '')}\nTurn {turn.get('turn')} B: {turn.get('b', '')}"
            for turn in turns
        ),
    }
    result = run_live_judge(judge_payload)
    summary = result.get("summary") or {}
    print(
        json.dumps(
            {
                "winner": summary.get("winner"),
                "reason_one_liner": summary.get("reason_one_liner"),
                "turning_point": summary.get("turning_point"),
                "fatal_phrase": summary.get("fatal_phrase"),
                "frame_owner": summary.get("frame_owner"),
                "frame_survival": summary.get("frame_survival"),
                "self_frame_held": summary.get("self_frame_held"),
                "opponent_core_damage_owner": summary.get("opponent_core_damage_owner"),
                "opponent_core_damage_strength": summary.get("opponent_core_damage_strength"),
                "opponent_core_damage_basis": summary.get("opponent_core_damage_basis"),
                "burden_closure": summary.get("burden_closure"),
                "weak_spot": summary.get("weak_spot"),
                "definition_drift_owner": summary.get("definition_drift_owner"),
                "burden_shift_detected": summary.get("burden_shift_detected"),
                "residue_owner": summary.get("residue_owner"),
                "parasitic_rebuttal": summary.get("parasitic_rebuttal"),
                "opening_axis_locked": summary.get("opening_axis_locked"),
                "opening_acceptance_locked": summary.get("opening_acceptance_locked"),
                "drift_from_opening_contract": summary.get("drift_from_opening_contract"),
                "reframe_attempt_detected": summary.get("reframe_attempt_detected"),
                "reframe_detected": summary.get("reframe_detected"),
                "reframe_owner": summary.get("reframe_owner"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
