from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

def parse_time(s: str) -> float:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0

def main():
    turnp = Path("incoming/triad_turn.json")
    gatep = Path("examples/tmp/evo_gate_min.from_delta_log.out.json")
    logp  = Path("logs/delta_entries.jsonl")

    if not turnp.exists():
        raise SystemExit("[MISS] incoming/triad_turn.json not found")
    if not gatep.exists():
        raise SystemExit("[MISS] gate output not found: examples/tmp/evo_gate_min.from_delta_log.out.json")

    turn = json.loads(turnp.read_text(encoding="utf-8", errors="replace"))
    case_id = (turn.get("case_id") or "Case TRIAD").strip()

    gate = json.loads(gatep.read_text(encoding="utf-8", errors="replace"))
    results = gate.get("results") or []
    r = None
    for x in results:
        if x.get("case_id") == case_id:
            r = x
            break
    if r is None:
        # gate出力はcases順で1件だけのこともある
        if results and results[0].get("case_id"):
            r = results[0]
        else:
            raise SystemExit(f"[MISS] no result for case_id={case_id} in gate output")

    # last delta_entry timestamp for this case
    last_asof = None
    if logp.exists():
        rows=[]
        for ln in logp.read_text(encoding="utf-8", errors="replace").splitlines():
            ln=ln.strip()
            if not ln: continue
            try: o=json.loads(ln)
            except: continue
            if o.get("schema")=="mmar.delta_entry.v0" and o.get("case_id")==case_id:
                rows.append(o)
        rows.sort(key=lambda x: parse_time(x.get("asof","")))
        if rows:
            last_asof = rows[-1].get("asof")

    ev = r.get("evidence") or {}
    trigger = bool(r.get("trigger"))

    # cost estimate (API未接続でも“予定コスト”として価値がある)
    cost_meter = {
        "triad_est_requests": 4,   # seed + counter2 + merge
        "t3f_est_requests": 13,    # triad×3 + final merge (概算)
        "recommended": "t3f" if trigger else "triad"
    }

    turn["gate_reason"] = {
        "case_id": r.get("case_id"),
        "trigger": trigger,
        "window_k": r.get("window_k"),
        "k_consecutive": r.get("k_consecutive"),
        "theta_evo": r.get("theta_evo"),
        "pass_indices": ev.get("pass_indices"),
        "max_consecutive_passes": ev.get("max_consecutive_passes"),
        "first_trigger_index": ev.get("first_trigger_index"),
        "asof_last_delta": last_asof
    }
    turn["recommended_mode"] = cost_meter["recommended"]
    turn["cost_meter"] = cost_meter

    turnp.write_text(json.dumps(turn, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] updated incoming/triad_turn.json with gate_reason + recommended_mode + cost_meter")

if __name__ == "__main__":
    main()
