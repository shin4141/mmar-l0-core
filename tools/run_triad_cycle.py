from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
import json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", default="Case TRIAD")
    ap.add_argument("--window-k", type=int, default=3)
    ap.add_argument("--k-consecutive", type=int, default=2)
    ap.add_argument("--theta-evo", type=float, default=1.0)
    ap.add_argument("--gate-unit", default="", help="filter update_unit (e.g., resolution)")
    ap.add_argument("--resolution-file", default="", help="optional resolution file path")
    args = ap.parse_args()

    # 1) triad_turn -> claims + delta (triad_turn)
    subprocess.check_call([sys.executable, "tools/triad_turn_to_claims_and_delta.py"])

    # 1.5) sync resolution template with latest claims (no manual upkeep)
    subprocess.check_call([sys.executable, "tools/sync_resolution_with_claims.py", "--case-id", args.case_id, "--claims", "examples/tmp/triad_claims.latest.json"])
    # 1.6) auto resolution delta (claims diff-based progress, no manual edits)
    subprocess.check_call([sys.executable, "tools/append_resolution_auto_delta.py", "--case-id", args.case_id, "--claims", "examples/tmp/triad_claims.latest.json"])

    # 2) if resolution exists, append resolution delta
    res_path = args.resolution_file or f"incoming/resolution.{args.case_id}.json"
    if Path(res_path).exists():
        # uses latest triad claims
        subprocess.check_call([
            sys.executable, "tools/append_resolution_delta.py",
            "--resolution", res_path,
            "--claims", "examples/tmp/triad_claims.latest.json",
            "--append-log", "logs/delta_entries.jsonl"
        ])

    # 3) gate (optionally resolution-only)
    cmd = [
        sys.executable, "tools/run_evo_gate_from_delta_log.py",
        "--log", "logs/delta_entries.jsonl",
        "--case-id", args.case_id,
        "--window-k", str(args.window_k),
        "--k-consecutive", str(args.k_consecutive),
        "--theta-evo", str(args.theta_evo),
    ]
    if args.gate_unit:
        cmd += ["--unit", args.gate_unit]
    subprocess.check_call(cmd)

    # 4) attach gate reason to triad_turn.json (keeps product trace)
    subprocess.check_call([sys.executable, "tools/attach_gate_reason_to_triad_turn.py"])
    # 4.5) attach auto progress + auto gate reason (product-ready trace)
    subprocess.check_call([sys.executable, "tools/attach_auto_progress_to_triad_turn.py"])

    print("[DONE] triad cycle completed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
