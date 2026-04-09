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


def build_payload(bundle_dir: str) -> dict:
    bundle = Path(bundle_dir)
    request_payload = json.loads((bundle / "request.json").read_text(encoding="utf-8"))
    response_payload = json.loads((bundle / "response.json").read_text(encoding="utf-8"))
    debate = response_payload["debate"]
    turns = debate.get("turns") or []
    return {
        "topic": request_payload.get("topic") or debate.get("topic") or "",
        "side_a": request_payload.get("side_a") or "",
        "side_b": request_payload.get("side_b") or "",
        "turn_count": request_payload.get("turn_count") or debate.get("turn_count") or 3,
        "mode": request_payload.get("mode") or "casual",
        "fighter_a_provider": request_payload.get("fighter_a_provider") or "openai",
        "fighter_b_provider": request_payload.get("fighter_b_provider") or "openai",
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


def main() -> None:
    load_dotenv(Path("/Users/sn/workspaces/mmar-l0-core/.env"))
    baseline_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    replay_results = []
    matches = 0
    for row in baseline.get("results", []):
        bundle_dir = row.get("artifact_bundle_dir")
        if not bundle_dir:
            continue
        judge = run_live_judge(build_payload(bundle_dir))
        summary = judge.get("summary") if isinstance(judge.get("summary"), dict) else {}
        winner = summary.get("winner") if isinstance(summary.get("winner"), dict) else {}
        weak_spot = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {}
        replay_row = {
            "case_id": row.get("case_id"),
            "swapped": row.get("swapped"),
            "expected_winner_by_human": row.get("expected_winner_by_human"),
            "before_winner": row.get("judge_winner"),
            "after_winner": winner.get("side") or "",
            "changed": (row.get("judge_winner") or "") != (winner.get("side") or ""),
            "before_reason": row.get("judge_reason_one_liner") or "",
            "after_reason": summary.get("reason_one_liner") or "",
            "after_frame_owner": summary.get("frame_owner") or "",
            "after_frame_survival": summary.get("frame_survival") or "",
            "after_self_frame_held": summary.get("self_frame_held"),
            "after_opponent_core_damage_owner": summary.get("opponent_core_damage_owner") or "",
            "after_opponent_core_damage_strength": summary.get("opponent_core_damage_strength") or "",
            "after_opponent_core_damage_basis": summary.get("opponent_core_damage_basis") or "",
            "after_burden_closure": summary.get("burden_closure") or {},
            "after_weak_spot_side": weak_spot.get("side") or "",
            "after_weak_spot_label": weak_spot.get("label") or "",
        }
        replay_results.append(replay_row)
        if replay_row["after_winner"] == replay_row["expected_winner_by_human"]:
            matches += 1
    payload = {
        "baseline_path": str(baseline_path),
        "replayed_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
        "match_count": matches,
        "total": len(replay_results),
        "results": replay_results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
