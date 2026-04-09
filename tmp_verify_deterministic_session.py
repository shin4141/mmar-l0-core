from __future__ import annotations

import json
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8912"


def call(payload: dict, timeout: int = 180) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}/api/debate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"ok": False, "error": body}


def summary(status: int, payload: dict) -> dict:
    return {
        "status": status,
        "ok": payload.get("ok"),
        "mode": payload.get("mode"),
        "run_id": payload.get("run_id"),
        "session_id": payload.get("session_id"),
        "route_signature": payload.get("route_signature"),
        "fighter_a_provider": payload.get("fighter_a_provider"),
        "fighter_b_provider": payload.get("fighter_b_provider"),
        "judge_provider": payload.get("judge_provider"),
        "fighter_a_model": payload.get("fighter_a_model"),
        "fighter_b_model": payload.get("fighter_b_model"),
        "judge_model": payload.get("judge_model"),
        "failure_reason": payload.get("failure_reason"),
        "execution_stage": payload.get("execution_stage"),
        "active_speaker": payload.get("active_speaker"),
        "active_provider": payload.get("active_provider"),
        "request_model": payload.get("request_model"),
        "request_phase": payload.get("request_phase"),
        "artifact_bundle_dir": payload.get("artifact_bundle_dir"),
    }


def compare(a: dict, b: dict) -> dict:
    keys = [
        "route_signature",
        "fighter_a_provider",
        "fighter_b_provider",
        "judge_provider",
        "fighter_a_model",
        "fighter_b_model",
        "judge_model",
        "mode",
    ]
    return {key: (a.get(key) == b.get(key)) for key in keys}


def main() -> None:
    topic1 = {
        "topic": "生成AIは初等教育に常時導入すべきか",
        "side_a": "導入すべき。個別最適化と反復学習の補助になる。",
        "side_b": "導入は限定的にすべき。依存と評価の歪みが大きい。",
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        "_disable_live_judge": True,
    }
    topic2 = {
        "topic": "金より銀の方が長期保有に向いているか",
        "side_a": "はい",
        "side_b": "いいえ",
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        "_disable_live_judge": True,
    }
    topic3 = {
        "topic": "戦争をなくすには軍縮よりも抑止の維持が現実的か",
        "side_a": "現実的だ。制度が未成熟な間は抑止が必要。",
        "side_b": "いや、抑止維持は軍拡を固定化し、長期的には逆効果。",
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        "_disable_live_judge": True,
    }
    failure = {
        "topic": "failure semantics",
        "side_a": "a",
        "side_b": "b",
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "bogus",
        "fighter_b_provider": "openai",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        "_disable_live_judge": True,
    }

    out = {}
    for name, payload, timeout in [
        ("topic1", topic1, 180),
        ("topic2", topic2, 180),
        ("topic3", topic3, 180),
    ]:
        s1, p1 = call(payload, timeout=timeout)
        s2, p2 = call(payload, timeout=timeout)
        out[name] = {
            "run1": summary(s1, p1),
            "run2": summary(s2, p2),
            "consistency": compare(summary(s1, p1), summary(s2, p2)),
        }

    fs1, fp1 = call(failure, timeout=20)
    fs2, fp2 = call(failure, timeout=20)
    out["failure_probe"] = {
        "run1": summary(fs1, fp1),
        "run2": summary(fs2, fp2),
        "same_error_shape": {
            "status": fs1 == fs2,
            "mode": fp1.get("mode") == fp2.get("mode"),
            "failure_reason": fp1.get("failure_reason") == fp2.get("failure_reason"),
            "execution_stage": fp1.get("execution_stage") == fp2.get("execution_stage"),
            "active_speaker": fp1.get("active_speaker") == fp2.get("active_speaker"),
            "active_provider": fp1.get("active_provider") == fp2.get("active_provider"),
            "request_model": fp1.get("request_model") == fp2.get("request_model"),
            "request_phase": fp1.get("request_phase") == fp2.get("request_phase"),
            "route_signature": fp1.get("route_signature") == fp2.get("route_signature"),
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
