import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, "/Users/sn/workspaces/mmar-l0-core/tools")

from history_store import save_history_record, get_history_record, list_history_records  # noqa: E402
from dev_api import BOOT_AT, GIT_SHA  # noqa: E402


OUT = Path("/tmp/mmar_history_from_bundles_8912")
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    {
        "key": "A",
        "topic": "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。",
        "side_a": "手を出すべきでなかった",
        "side_b": "手を出すべきだった",
        "bundle": "/tmp/mmar_run_bundle_manual_case_a/response.json",
    },
    {
        "key": "B",
        "topic": "人の命に値段をつけることは許されるか？",
        "side_a": "許される",
        "side_b": "許されない",
        "bundle": "/tmp/mmar_run_bundle_manual_case_b/response.json",
    },
    {
        "key": "C",
        "topic": "警察はパチンコで換金が行われていることを知っているか？",
        "side_a": "知っている",
        "side_b": "知らない",
        "bundle": "/tmp/mmar_run_bundle_manual_case_c/response.json",
    },
]


def build_record(case: dict, response: dict) -> dict:
    debate = response["debate"]
    output_meta = response.get("output_meta")
    if not isinstance(output_meta, str):
        output_meta = f"{len(debate.get('turns', []))} turns · A live · B live · J mock"
    return {
        "id": f"history_{case['key']}_{int(time.time() * 1000)}",
        "run_id": response.get("run_id", ""),
        "topic_hash": response.get("topic_hash", ""),
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
        "source_mode": response.get("mode", "live"),
        "provider_statuses": response.get("provider_statuses", {}),
        "output_meta": output_meta,
        "saved_from_ui": True,
        "fingerprint": json.dumps(
            {
                "run_id": response.get("run_id", ""),
                "topic_hash": response.get("topic_hash", ""),
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
        response = json.loads(Path(case["bundle"]).read_text())
        record = build_record(case, response)
        saved = save_history_record(record)
        loaded = get_history_record(saved["saved_id"])
        results["cases"].append(
            {
                "key": case["key"],
                "topic": case["topic"],
                "saved_id": saved["saved_id"],
                "record": loaded,
                "response": response,
                "history_match": {
                    "topic": loaded.get("topic") == case["topic"],
                    "run_id": loaded.get("run_id") == response.get("run_id", ""),
                    "topic_hash": loaded.get("topic_hash") == response.get("topic_hash", ""),
                    "turns": loaded.get("transcript_json") == ((response.get("debate") or {}).get("turns") or []),
                },
            }
        )
    results["history_list"] = list_history_records(sort="recent")
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
