import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, "/Users/sn/workspaces/mmar-l0-core/tools")

from debate_api import run_debate  # noqa: E402
from history_store import save_history_record, list_history_records, get_history_record  # noqa: E402
from dev_api import BOOT_AT, GIT_SHA  # noqa: E402


OUT = Path("/tmp/mmar_history_seed_8912")
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    {
        "key": "A",
        "topic": "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。",
        "side_a": "手を出すべきでなかった",
        "side_b": "手を出すべきだった",
    },
    {
        "key": "B",
        "topic": "人の命に値段をつけることは許されるか？",
        "side_a": "許される",
        "side_b": "許されない",
    },
    {
        "key": "C",
        "topic": "警察はパチンコで換金が行われていることを知っているか？",
        "side_a": "知っている",
        "side_b": "知らない",
    },
]


def topic_hash(topic: str) -> str:
    return hashlib.sha1(topic.strip().encode("utf-8")).hexdigest()[:12]


def output_meta(result: dict) -> str:
    statuses = result.get("provider_statuses") or {}
    def label(name: str) -> str:
        return "live" if ((statuses.get(name) or {}).get("mode") == "live") else "mock"
    turns = (((result.get("debate") or {}).get("turns")) or [])
    return f"{len(turns)} turns · A {label('openai')} · B {label('openai')} · J {label('judge')}"


def make_record(case: dict, result: dict) -> dict:
    debate = result["debate"]
    return {
        "id": f"match_{case['key']}_{int(time.time() * 1000)}",
        "run_id": result.get("run_id", ""),
        "topic_hash": result.get("topic_hash", ""),
        "topic": case["topic"],
        "stance_a": case["side_a"],
        "stance_b": case["side_b"],
        "turn_count": debate.get("turn_count", 3),
        "mode": "casual",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "judge_provider": "judge",
        "fighter_a_model": "GPT-5-mini",
        "fighter_b_model": "GPT-5-mini",
        "judge_model": "mock judge",
        "transcript_json": debate.get("turns", []),
        "judge_json": debate.get("summary", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": result.get("mode", "mock"),
        "provider_statuses": result.get("provider_statuses", {}),
        "output_meta": output_meta(result),
        "saved_from_ui": True,
        "fingerprint": json.dumps(
            {
                "run_id": result.get("run_id", ""),
                "topic_hash": result.get("topic_hash", ""),
                "topic": case["topic"],
                "side_a": case["side_a"],
                "side_b": case["side_b"],
                "turn_count": debate.get("turn_count", 3),
                "mode": "casual",
                "fighters": {"a": "openai", "b": "openai", "judge": "judge"},
                "winner": (((debate.get("summary") or {}).get("winner") or {}).get("side") or ""),
                "turns": [[t.get("turn"), t.get("a"), t.get("b")] for t in debate.get("turns", [])],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def main() -> None:
    results = {
        "port": "8912",
        "build_sha": GIT_SHA,
        "boot_at": BOOT_AT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": [],
    }
    for case in CASES:
        run_id = uuid.uuid4().hex[:12]
        th = topic_hash(case["topic"])
        payload = {
            "topic": case["topic"],
            "side_a": case["side_a"],
            "side_b": case["side_b"],
            "turn_count": 3,
            "mode": "casual",
            "fighter_a_provider": "openai",
            "fighter_b_provider": "openai",
            "api_keys": {
                "openai": os.getenv("OPENAI_API_KEY", ""),
                "anthropic": "",
                "gemini": "",
            },
            "_disable_live_judge": True,
            "_artifact_meta": {
                "run_id": run_id,
                "topic_hash": th,
                "artifact_dir": str(OUT / f"bundle_{case['key']}"),
                "port": "8912",
                "build_sha": GIT_SHA,
                "boot_at": BOOT_AT,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        result = run_debate(payload)
        record = make_record(case, result)
        saved = save_history_record(record)
        saved_record = get_history_record(saved["saved_id"])
        results["cases"].append(
            {
                "key": case["key"],
                "topic": case["topic"],
                "run_id": run_id,
                "topic_hash": th,
                "response": result,
                "saved_record": saved_record,
                "history_match": {
                    "topic": saved_record.get("topic") == case["topic"],
                    "run_id": saved_record.get("run_id") == run_id,
                    "topic_hash": saved_record.get("topic_hash") == th,
                    "turns": saved_record.get("transcript_json") == ((result.get("debate") or {}).get("turns") or []),
                },
            }
        )
    results["history_list"] = list_history_records(sort="recent")
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
