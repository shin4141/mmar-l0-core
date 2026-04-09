from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8912"


def post(payload: dict, timeout: int = 180) -> tuple[int, dict]:
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


def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def run_case(payload: dict) -> dict:
    status, data = post(payload, timeout=180)
    out = {
        "status": status,
        "ok": data.get("ok"),
        "mode": data.get("mode"),
        "bundle": data.get("artifact_bundle_dir"),
    }
    if data.get("ok"):
        turns = ((data.get("debate") or {}).get("turns") or [])
        out["turns"] = turns
        progress = load_json(str(Path(out["bundle"]) / "progress.json"))
        spa = load_json(str(Path(out["bundle"]) / "speaker_progress_A.json"))
        spb = load_json(str(Path(out["bundle"]) / "speaker_progress_B.json"))
        out["progress"] = progress
        out["speaker_progress_A"] = spa
        out["speaker_progress_B"] = spb
    else:
        out["failure"] = data
    return out


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
        "topic": "failure path probe",
        "side_a": "a",
        "side_b": "b",
        "turn_count": 3,
        "mode": "casual",
        "fighter_a_provider": "bogus",
        "fighter_b_provider": "openai",
        "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        "_disable_live_judge": True,
    }
    out = {
        "topic1": run_case(topic1),
        "topic2": run_case(topic2),
        "topic3": run_case(topic3),
        "failure": run_case(failure),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
