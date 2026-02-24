from __future__ import annotations
import argparse, json, subprocess, sys
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="logs/delta_entries.jsonl")
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--unit", default="", help="filter update_unit (e.g., resolution, resolution_auto)")
    ap.add_argument("--window-k", type=int, default=3)
    ap.add_argument("--k-consecutive", type=int, default=2)
    ap.add_argument("--theta-evo", type=float, default=1.0)
    ap.add_argument("--use-drift", action="store_true")
    ap.add_argument("--out-in", default="examples/tmp/evo_gate_min.from_delta_log.json")
    ap.add_argument("--out-out", default="examples/tmp/evo_gate_min.from_delta_log.out.json")
    args = ap.parse_args()

    p = Path(args.log)
    if not p.exists():
        raise SystemExit(f"[MISS] log not found: {p}")

    rows=[]
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln=ln.strip()
        if not ln: 
            continue
        try:
            obj=json.loads(ln)
        except Exception:
            continue
        if obj.get("schema") != "mmar.delta_entry.v0":
            continue
        if obj.get("case_id") != args.case_id:
            continue
        if args.unit and obj.get("update_unit") != args.unit:
            continue
        rows.append(obj)

    if not rows:
        raise SystemExit(f"[MISS] no mmar.delta_entry.v0 rows for case_id={args.case_id} unit={args.unit or '*'}")

    rows.sort(key=lambda r: parse_time(r.get("asof","")))

    # Build series for evo_gate_min (it uses deltas of series).
    # - use_drift: cumsum(drift_proxy)
    # - resolution/resolution_auto: cumsum(resolved_count_v2) but scaled (0.5 -> 1 tick) to avoid int truncation anywhere
    # - otherwise: raw resolved_count series
    if args.use_drift:
        cum=0
        series=[]
        for r in rows:
            cum += int(r.get("drift_proxy") or 0)
            series.append(cum)
    elif args.unit in ("resolution","resolution_auto"):
        cum=0
        series=[]
        for r in rows:
            v = r.get("resolved_count_v2")
            if v is None:
                v = r.get("resolved_count")
            inc = float(v or 0.0)
            ticks = int(round(inc * 2.0))   # 1.0->2, 0.5->1, 0.0->0
            cum += ticks
            series.append(cum)
    else:
        series=[float(r.get("resolved_count") or 0) for r in rows]

    inp = {
        "schema": "mmar.evo_gate_input.v0",
        "cases": [{
            "case_id": args.case_id,
            "update_unit": "delta_entry",
            "window_k": args.window_k,
            "k_consecutive": args.k_consecutive,
            "theta_evo": args.theta_evo,
            "resolved_count": series,
        }],
        "meta": {"source_log": args.log, "n_entries": len(series), "unit": args.unit, "use_drift": args.use_drift}
    }

    Path(args.out_in).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_in).write_text(json.dumps(inp, ensure_ascii=False, indent=2), encoding="utf-8")

    subprocess.check_call([sys.executable, "core/evo_gate_min.py", "--in", args.out_in, "--out", args.out_out])

    out = json.loads(Path(args.out_out).read_text(encoding="utf-8"))
    r0 = out["results"][0]
    ev = r0.get("evidence", {})
    print("[OK] wrote", args.out_in)
    print("[OK] wrote", args.out_out)
    print("[SUMMARY] n_entries=", len(series), "last_resolved=", series[-1])
    print("[GATE] trigger=", r0.get("trigger"), "max_consec=", ev.get("max_consecutive_passes"), "pass_idx=", ev.get("pass_indices"))

if __name__ == "__main__":
    main()
