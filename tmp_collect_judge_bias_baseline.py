from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8787"
OUT = Path(os.getenv("MMAR_BASELINE_OUT_DIR") or "/Users/sn/workspaces/mmar-l0-core/snapshots/snapshot_20260407_judge_bias_baseline_start")

CASES = [
    {
        "id": "life_pricing",
        "topic": "人の命に値段をつけることは許されるか？",
        "side_a": "許される。現実の資源配分では必要な比較だ。",
        "side_b": "許されない。尊厳を価格で序列化してはいけない。",
        "expected_strong_side": "B",
    },
    {
        "id": "pachinko_police",
        "topic": "パチンコの三店方式を警察は知っているか",
        "side_a": "知っている。制度運用上、黙認の前提がある。",
        "side_b": "知らない建前を取るしかなく、知っているとは言えない。",
        "expected_strong_side": "A",
    },
    {
        "id": "love_money",
        "topic": "愛は金で買えるか",
        "side_a": "買える。条件を整える力は愛の成立を左右する。",
        "side_b": "買えない。条件と感情の実在は別物だ。",
        "expected_strong_side": "B",
    },
    {
        "id": "aliens_exist",
        "topic": "宇宙人は存在するか",
        "side_a": "存在しない。現時点で確認証拠がない。",
        "side_b": "存在する。宇宙の広さから見て地球だけという方が不自然だ。",
        "expected_strong_side": "B",
    },
    {
        "id": "sora_video",
        "topic": "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。",
        "side_a": "手を出すべきではなかった。配信運営は本業の強みとずれる。",
        "side_b": "手を出すべきだった。挑戦なしにプロダクト拡張は起きない。",
        "expected_strong_side": "A",
    },
]


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


def post_json(path: str, payload: dict, timeout: int) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"ok": False, "error": body}


def run_case(case: dict, swapped: bool) -> dict:
    side_a = case["side_b"] if swapped else case["side_a"]
    side_b = case["side_a"] if swapped else case["side_b"]
    expected = "A" if (case["expected_strong_side"] == "B" and swapped) or (case["expected_strong_side"] == "A" and not swapped) else "B"

    debate_payload = {
        "topic": case["topic"],
        "side_a": side_a,
        "side_b": side_b,
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "api_keys": {
            "openai": "",
            "anthropic": "",
            "gemini": "",
        },
    }
    started = time.time()
    debate_status, debate = post_json("/api/debate_v4", debate_payload, timeout=1200)
    result = {
        "case_id": case["id"],
        "swapped": swapped,
        "topic": case["topic"],
        "side_a": side_a,
        "side_b": side_b,
        "expected_winner_by_human": expected,
        "debate_status": debate_status,
        "debate_mode": debate.get("mode"),
        "debate_error": debate.get("error"),
        "debate_elapsed_seconds": debate.get("elapsed_seconds"),
        "wall_seconds_until_debate": round(time.time() - started, 3),
        "artifact_bundle_dir": debate.get("artifact_bundle_dir"),
        "provider_statuses": debate.get("provider_statuses"),
    }
    if not debate.get("ok"):
        return result

    turns = ((debate.get("debate") or {}).get("turns") or [])
    transcript = "\n".join(
        f"Turn {turn.get('turn')} A: {turn.get('a', '')}\nTurn {turn.get('turn')} B: {turn.get('b', '')}"
        for turn in turns
    )
    judge_payload = {
        "topic": case["topic"],
        "side_a": side_a,
        "side_b": side_b,
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "api_keys": {
            "openai": "",
            "anthropic": "",
            "gemini": "",
        },
        "turns": turns,
        "transcript": transcript,
    }
    judge_started = time.time()
    judge_status, judge = post_json("/api/judge", judge_payload, timeout=600)
    summary = judge.get("summary") if isinstance(judge.get("summary"), dict) else {}
    winner = summary.get("winner") if isinstance(summary.get("winner"), dict) else {}
    weak_spot = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {}
    result.update(
        {
            "judge_status": judge_status,
            "judge_mode": judge.get("mode"),
            "judge_warning": judge.get("judge_warning"),
            "wall_seconds_until_judge": round(time.time() - judge_started, 3),
            "judge_winner": winner.get("side") or "",
            "judge_winner_reason": winner.get("reason") or "",
            "judge_reason_one_liner": summary.get("reason_one_liner") or "",
            "judge_confidence": summary.get("confidence") or "",
            "judge_frame_owner": summary.get("frame_owner") or "",
            "judge_frame_survival": summary.get("frame_survival") or "",
            "judge_burden_closure": summary.get("burden_closure") or {},
            "judge_weak_spot_side": weak_spot.get("side") or "",
            "judge_weak_spot_label": weak_spot.get("label") or "",
            "judge_flip_condition": summary.get("flip_condition") or "",
        }
    )
    return result


def main() -> None:
    load_dotenv(Path(".env"))
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for case in CASES:
        results.append(run_case(case, swapped=False))
        results.append(run_case(case, swapped=True))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": BASE,
        "cases": CASES,
        "results": results,
    }
    (OUT / "judge_bias_baseline.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
