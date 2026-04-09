import json
import time
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8912"
OUT = Path("/tmp/mmar_history_run_verify_8912")
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


def post_json(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as res:
        return json.loads(res.read().decode("utf-8"))


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def output_meta(response: dict) -> str:
    statuses = response.get("provider_statuses") or {}
    def label(name: str) -> str:
        mode = ((statuses.get(name) or {}).get("mode") or "mock").strip() or "mock"
        return "live" if mode == "live" else "mock"
    turn_count = (((response.get("debate") or {}).get("turns")) or [])
    return f"{len(turn_count)} turns · A {label('openai')} · B {label('openai')} · J {label('judge')}"


def build_record(case: dict, response: dict) -> dict:
    debate = response["debate"]
    return {
        "id": f"verify_{case['key']}_{int(time.time() * 1000)}",
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
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "source_mode": response.get("mode", "mock"),
        "provider_statuses": response.get("provider_statuses", {}),
        "output_meta": output_meta(response),
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
                "turns": [[t.get("turn"), t.get("a"), t.get("b")] for t in debate.get("turns", [])],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def main() -> None:
    results = {"health": get_json("/api/health"), "cases": []}
    for case in CASES:
        debate_payload = {
            "topic": case["topic"],
            "side_a": case["side_a"],
            "side_b": case["side_b"],
            "turn_count": 3,
            "mode": "casual",
            "fighter_a_provider": "openai",
            "fighter_b_provider": "openai",
            "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        }
        response = post_json("/api/debate", debate_payload)
        record = build_record(case, response)
        saved = post_json("/api/history/save", record)
        saved_id = saved["record"]["id"]
        loaded = get_json(f"/api/history/{saved_id}")["item"]
        results["cases"].append(
            {
                "key": case["key"],
                "topic": case["topic"],
                "run_id": response.get("run_id", ""),
                "topic_hash": response.get("topic_hash", ""),
                "saved_id": saved_id,
                "response_topic": ((response.get("debate") or {}).get("topic") or ""),
                "loaded_topic": loaded.get("topic", ""),
                "response_turns": ((response.get("debate") or {}).get("turns") or []),
                "loaded_turns": loaded.get("transcript_json", []),
                "output_meta": loaded.get("output_meta", ""),
            }
        )
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
