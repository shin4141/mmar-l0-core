from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8912"


def call(payload: dict, timeout: int):
    req = urllib.request.Request(
        f"{BASE}/api/debate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def latest_bundle_for_topic(topic: str) -> str:
    bundles = sorted(Path("/tmp").glob("mmar_run_bundle_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for bundle in bundles:
        req = bundle / "request.json"
        if not req.exists():
            continue
        try:
            payload = json.loads(req.read_text())
        except Exception:
            continue
        if str(payload.get("topic") or "") == topic:
            return str(bundle)
    return ""


def main() -> None:
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

    out: dict[str, object] = {}
    topic3_start = time.time()
    try:
        result = call(topic3, timeout=60)
        out["topic3"] = {
            "bundle": result.get("artifact_bundle_dir"),
            "mode": result.get("mode"),
            "turns": result["debate"]["turns"],
            "timed_out": False,
        }
    except Exception as exc:
        time.sleep(2)
        bundle = latest_bundle_for_topic(topic3["topic"])
        progress = {}
        response = {}
        phase = {}
        if bundle:
            for name in ["progress.json", "response.json", "phase_timings.json"]:
                path = Path(bundle) / name
                if path.exists():
                    try:
                        data = json.loads(path.read_text())
                    except Exception:
                        data = {}
                    if name == "progress.json":
                        progress = data
                    elif name == "response.json":
                        response = data
                    else:
                        phase = data
        out["topic3"] = {
            "timed_out": True,
            "exception": type(exc).__name__,
            "elapsed_seconds": time.time() - topic3_start,
            "bundle": bundle,
            "progress": progress,
            "response": response,
            "phase": phase,
        }

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
