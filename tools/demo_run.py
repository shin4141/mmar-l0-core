from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from datetime import datetime

LOG = Path("logs/delta_entries.jsonl")
TRIAD_TURN = Path("incoming/triad_turn.json")
T3F_CLAIMS = Path("examples/tmp/t3f_claims.latest.json")
TRIAD_CLAIMS = Path("examples/tmp/triad_claims.latest.json")

def parse_time(s: str) -> float:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0

def last_delta(case_id: str, unit: str | None = None):
    if not LOG.exists():
        return None
    best = None
    best_ts = -1.0
    for ln in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if o.get("schema") != "mmar.delta_entry.v0":
            continue
        if o.get("case_id") != case_id:
            continue
        if unit and o.get("update_unit") != unit:
            continue
        ts = parse_time(o.get("asof",""))
        if ts >= best_ts:
            best_ts = ts
            best = o
    return best

def load_json(p: Path):
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))

def main():
    # 1) run the full adaptive cycle (triad -> auto -> recommend -> t3f if needed)
    subprocess.check_call([sys.executable, "tools/run_adaptive_cycle.py"])

    # 2) summarize
    turn = load_json(TRIAD_TURN) or {}
    case_tri = (turn.get("case_id") or "Case TRIAD").strip()
    rec = turn.get("recommended_mode_auto") or turn.get("recommended_mode") or "triad"
    auto = turn.get("auto_progress") or {}
    gate_auto = turn.get("gate_reason_auto") or {}

    triad_last = last_delta(case_tri, "triad_turn")
    auto_last  = last_delta(case_tri, "resolution_auto")
    manual_last = last_delta(case_tri, "resolution")

    t3f_last = last_delta("Case T3F", "t3f_turn")
    t3f_claims = load_json(T3F_CLAIMS) or {}
    triad_claims = load_json(TRIAD_CLAIMS) or {}

    lines=[]
    lines.append("=== MMAR DEMO SUMMARY ===")
    lines.append(f"[TRIAD] case={case_tri} recommended_mode_auto={rec}")
    if triad_last:
        lines.append(f"  triad_turn asof={triad_last.get('asof')} claims_total={triad_last.get('resolved_count')} drift={triad_last.get('drift_proxy')}")
    if auto_last:
        lines.append(f"  auto asof={auto_last.get('asof')} resolved_v2={auto_last.get('resolved_count_v2')} counts={auto_last.get('status_counts')}")
    if gate_auto:
        lines.append(f"  auto_gate trigger={gate_auto.get('trigger')} pass_idx={gate_auto.get('pass_indices')} max_consec={gate_auto.get('max_consecutive_passes')}")
    if manual_last:
        lines.append(f"  manual asof={manual_last.get('asof')} resolved_v2={manual_last.get('resolved_count_v2')} counts={manual_last.get('status_counts')}")

    if rec == "t3f":
        lines.append("[T3F] recommended and executed if inputs present")
    if t3f_last:
        lines.append(f"  t3f_turn asof={t3f_last.get('asof')} claims_total={t3f_last.get('resolved_count')} drift={t3f_last.get('drift_proxy')}")
        st = (t3f_claims.get("stats") or {})
        if st:
            lines.append(f"  t3f_claims stats={st}")
    else:
        lines.append("[T3F] no t3f_turn logged in this repo yet (or not executed this run)")

    # show current claim counts (optional)
    st_tri = (triad_claims.get("stats") or {})
    if st_tri:
        lines.append(f"[TRIAD_CLAIMS] stats={st_tri}")

    outp = Path("examples/tmp/demo_summary.txt")
    outp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\n[WROTE] examples/tmp/demo_summary.txt")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
