from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from datetime import datetime

def parse_time(s: str) -> float:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0

def latest_resolution_auto(log_path: str, case_id: str):
    p = Path(log_path)
    if not p.exists():
        return None
    rows=[]
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln=ln.strip()
        if not ln: continue
        try: o=json.loads(ln)
        except: continue
        if o.get("schema")!="mmar.delta_entry.v0": 
            continue
        if o.get("case_id")!=case_id:
            continue
        if o.get("update_unit")!="resolution_auto":
            continue
        rows.append(o)
    rows.sort(key=lambda r: parse_time(r.get("asof","")))
    return rows[-1] if rows else None

def extract_gate_reason(case_id: str):
    outp = Path("examples/tmp/evo_gate_min.from_delta_log.out.json")
    if not outp.exists():
        return None
    out = json.loads(outp.read_text(encoding="utf-8", errors="replace"))
    res = None
    for r in (out.get("results") or []):
        if r.get("case_id")==case_id:
            res=r
            break
    if res is None and (out.get("results") or []):
        res = out["results"][0]
    if res is None:
        return None
    ev = res.get("evidence") or {}
    return {
        "case_id": res.get("case_id"),
        "trigger": bool(res.get("trigger")),
        "window_k": res.get("window_k"),
        "k_consecutive": res.get("k_consecutive"),
        "theta_evo": res.get("theta_evo"),
        "pass_indices": ev.get("pass_indices"),
        "max_consecutive_passes": ev.get("max_consecutive_passes"),
        "first_trigger_index": ev.get("first_trigger_index"),
    }

def main():
    turnp = Path("incoming/triad_turn.json")
    if not turnp.exists():
        raise SystemExit("[MISS] incoming/triad_turn.json not found")
    turn = json.loads(turnp.read_text(encoding="utf-8", errors="replace"))
    case_id = (turn.get("case_id") or "Case TRIAD").strip()

    # 1) run gate for resolution_auto (writes evo_gate_min.from_delta_log.out.json)
    subprocess.check_call([
        sys.executable, "tools/run_evo_gate_from_delta_log.py",
        "--log", "logs/delta_entries.jsonl",
        "--case-id", case_id,
        "--unit", "resolution_auto",
        "--window-k", "3",
        "--k-consecutive", "2",
        "--theta-evo", "1.0",
    ])

    # 2) fetch latest auto progress
    auto = latest_resolution_auto("logs/delta_entries.jsonl", case_id)
    if auto is None:
        raise SystemExit(f"[MISS] no resolution_auto rows for case_id={case_id}")

    # 3) fetch gate reason (auto)
    gate_auto = extract_gate_reason(case_id) or {"trigger": False}

    # 4) attach to triad_turn.json
    turn["auto_progress"] = {
        "asof": auto.get("asof"),
        "resolved_v2": auto.get("resolved_count_v2", auto.get("resolved_count")),
        "claims_total": auto.get("claims_total"),
        "status_counts": auto.get("status_counts"),
        "source": auto.get("source"),
    }
    turn["gate_reason_auto"] = gate_auto
    turn["recommended_mode_auto"] = "t3f" if gate_auto.get("trigger") else "triad"
    turn["cost_meter_auto"] = {
        "triad_est_requests": 4,
        "t3f_est_requests": 13,
        "recommended": turn["recommended_mode_auto"],
        "basis": "resolution_auto gate"
    }

    turnp.write_text(json.dumps(turn, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] updated incoming/triad_turn.json with auto_progress + gate_reason_auto + recommended_mode_auto")

if __name__ == "__main__":
    main()
