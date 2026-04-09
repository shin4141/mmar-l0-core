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
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tmp_probe_scorecard_from_bundle.py /tmp/mmar_run_bundle_xxx")

    load_dotenv(Path("/Users/sn/workspaces/mmar-l0-core/.env"))
    bundle = Path(sys.argv[1])
    request_payload = json.loads((bundle / "request.json").read_text(encoding="utf-8"))
    response_payload = json.loads((bundle / "response.json").read_text(encoding="utf-8"))
    debate = response_payload.get("debate") or {}
    turns = debate.get("turns") or []
    transcript = "\n".join(
        f"Turn {turn.get('turn')} A: {turn.get('a', '')}\nTurn {turn.get('turn')} B: {turn.get('b', '')}"
        for turn in turns
    )
    judge_payload = {
        "topic": request_payload.get("topic") or debate.get("topic") or "",
        "side_a": request_payload.get("side_a") or "",
        "side_b": request_payload.get("side_b") or "",
        "turn_count": request_payload.get("turn_count") or debate.get("turn_count") or 3,
        "mode": request_payload.get("mode") or "casual",
        "fighter_a_provider": request_payload.get("fighter_a_provider") or response_payload.get("fighter_a_provider") or "openai",
        "fighter_b_provider": request_payload.get("fighter_b_provider") or response_payload.get("fighter_b_provider") or "openai",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        "judge_mode": "scorecard_v1_shadow",
        "turns": turns,
        "transcript": transcript,
    }
    result = run_live_judge(judge_payload)
    scorecard = result.get("scorecard_v1") or {}
    summary = result.get("summary") or {}
    print(
        json.dumps(
            {
                "topic": judge_payload["topic"],
                "side_a": judge_payload["side_a"],
                "side_b": judge_payload["side_b"],
                "winner": (scorecard.get("winner") or {}).get("side"),
                "winner_reason": (scorecard.get("winner") or {}).get("reason"),
                "judge_mode": result.get("mode"),
                "judge_warning": result.get("judge_warning"),
                "current_summary_winner": ((summary.get("winner") or {}).get("side") if isinstance(summary.get("winner"), dict) else None),
                "side_a_scorecard": scorecard.get("side_a"),
                "side_b_scorecard": scorecard.get("side_b"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
