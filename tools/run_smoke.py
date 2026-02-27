#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INCOMING = REPO / "incoming"
ASK_TRIAD = REPO / "tools" / "ask_triad.py"
LATEST_CARD = INCOMING / "decision_card_latest.json"
SMOKE_LAST = INCOMING / "smoke_last.json"
SMOKE_REPORT = INCOMING / "smoke_report.json"

CASES = [
    ("pricing", "AIを仕事と趣味で週7時間使用しています。無料プランとプラスプランとプロプランどれが私に相応しいでしょうか？"),
    ("education", "2030年ごろに高校を卒業した人は学歴を求めて大学に進学する方がいいのかその時間を専門的なことを学ぶ方がいいのかどっちがいいと思う？学費や就職率、AIなどを考慮して考えて"),
    ("leisure", "神奈川在住です。一人でリラックスするなら横浜と鎌倉どちらが良いですか？費用と移動時間も考慮したいです。"),
]


def _run_case(case_id: str, text: str) -> dict:
    env = os.environ.copy()
    env.setdefault("MMAR_NO_LLM", "1")
    proc = subprocess.run(
        [sys.executable, str(ASK_TRIAD), "--tab", "expand", text],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        return {"case_id": case_id, "error": "ask_triad_failed", "returncode": proc.returncode}
    try:
        card = json.loads(LATEST_CARD.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {"case_id": case_id, "error": "missing_decision_card"}
    q = card.get("quality") if isinstance(card.get("quality"), dict) else {}
    return {
        "case_id": case_id,
        "deep_status": card.get("deep_status", "-"),
        "quality_total": int(q.get("total", 0) or 0),
        "quality": q,
        "recommend": card.get("recommend", {}),
    }


def main() -> int:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    prev = {}
    try:
        prev = json.loads(SMOKE_LAST.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        prev = {}
    prev_map = {r.get("case_id"): r for r in (prev.get("results") or []) if isinstance(r, dict)}

    results = []
    for case_id, text in CASES:
        r = _run_case(case_id, text)
        p = prev_map.get(case_id, {})
        if isinstance(r.get("quality_total"), int) and isinstance(p.get("quality_total"), int):
            r["delta_total"] = int(r["quality_total"]) - int(p["quality_total"])
        else:
            r["delta_total"] = None
        results.append(r)

    report = {"timestamp": now, "results": results}
    SMOKE_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    SMOKE_LAST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("SMOKE RESULTS")
    for r in results:
        print(
            f"- {r.get('case_id')}: quality_total={r.get('quality_total', '-')}"
            f" delta={r.get('delta_total', '-')}"
            f" deep_status={r.get('deep_status', '-')}"
        )
    print(f"report: {SMOKE_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
