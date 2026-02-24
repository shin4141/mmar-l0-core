from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

def main():
    # 1) triad cycle（delta積む→gate→recommended_mode付与）
    subprocess.check_call([sys.executable, "tools/run_triad_cycle.py", "--case-id", "Case TRIAD", "--window-k", "3", "--k-consecutive", "2", "--theta-evo", "1.0"])

    turn = json.loads(Path("incoming/triad_turn.json").read_text(encoding="utf-8", errors="replace"))
    mode = turn.get("recommended_mode_auto") or turn.get("recommended_mode") or "triad"
    print("[MODE]", mode)

    # 2) t3fは条件成立時だけ
    if mode == "t3f":
        p = Path("incoming/t3f_turn.json")
        if not p.exists():
            print("[SKIP] t3f recommended but incoming/t3f_turn.json missing")
            return 0
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        if not (d.get("final_merged") or "").strip() and not all((d.get(k) or "").strip() for k in ("merged_gpt","merged_gemini","merged_claude")):
            print("[SKIP] t3f recommended but final_merged (or merged_*) empty")
            return 0

        subprocess.check_call([sys.executable, "tools/t3f_turn_to_claims_and_delta.py"])
        subprocess.check_call([sys.executable, "tools/run_evo_gate_from_delta_log.py",
                               "--log", "logs/delta_entries.jsonl",
                               "--case-id", d.get("case_id","Case T3F"),
                               "--window-k", "3", "--k-consecutive", "2", "--theta-evo", "1.0"])
        print("[DONE] t3f executed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
