#!/usr/bin/env python3
import os, sys, json, subprocess, time, argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # providers import safety

INCOMING = REPO / "incoming"
INCOMING.mkdir(exist_ok=True)

TURNP = INCOMING / "triad_turn.json"
MERGED_TXT = INCOMING / "merged_answer.txt"

TAB_FILES = {
    "compare": INCOMING / "out_compare.txt",
    "expand": INCOMING / "out_expand.txt",
    "guard":  INCOMING / "out_guard.txt",
    "diff":   INCOMING / "out_diff.txt",
    "merge":  INCOMING / "out_merge.txt",
}

def log(msg: str) -> None:
    print(msg, flush=True)

def call_openai(prompt: str, timeout_s: int = 60) -> str:
    try:
        from providers.openai_min import responses_create
        return responses_create(prompt, timeout_s=timeout_s)
    except Exception as e:
        log(f"[warn] OpenAI failed -> Dummy fallback: {e}")
        return (
            "SSOT:\n- (dummy)\n\n"
            "Δ:\n- (dummy)\n- (dummy)\n\n"
            "Next step: (dummy)\n"
        )

def master_merge_prompt() -> str:
    # Master Contract (fixed)
    return (
        "Merge to MASTER (fixed contract).\n"
        "Output MUST include these sections:\n"
        "1) SSOT (1-3 lines)\n"
        "2) Δ (>=2 bullet points changed due to counters; be concrete)\n"
        "3) Next step (1 concrete step)\n"
        "Rules: avoid generic advice; if info missing, add ASSUMPTIONS (max 3 bullets).\n"
    )

def tab_prompt(tab: str, q: str, seed: str, c1: str, c2: str, master: str, turn_after: dict) -> str:
    auto = turn_after.get("auto_progress") or {}
    gate = turn_after.get("gate_reason_auto") or turn_after.get("gate_reason") or {}

    common_ctx = (
        f"Q: {q}\n\n"
        f"MASTER_MERGE:\n{master}\n\n"
        f"SEED:\n{seed}\n\n"
        f"COUNTER-1:\n{c1}\n\n"
        f"COUNTER-2:\n{c2}\n\n"
        f"AUTO_PROGRESS_JSON:\n{json.dumps(auto, ensure_ascii=False)}\n\n"
        f"GATE_REASON_JSON:\n{json.dumps(gate, ensure_ascii=False)}\n"
    )

        if tab == "expand":
        flavor = os.getenv("MMAR_EXPAND_FLAVOR", "wow").strip().lower()
        if flavor == "plan":
            return (
                "TAB=EXPAND (plan).\n"
                "Goal: produce an executable pilot plan to discover thresholds via real trials.\n"
                "Output MUST include:\n"
                "1) Pilot plan (timebox + session count)\n"
                "2) Metrics to measure (3 bullets)\n"
                "3) Thresholds to tune (3 bullets)\n"
                "4) Failure modes + fallback (3 bullets)\n"
                "5) Ask: what inputs you need next (max 3 items)\n"
                "Keep it practical.\n\n"
                + common_ctx
            )
        # default: wow
        return (
            "TAB=EXPAND (wow).\n"
            "Goal: produce impressive, dense, structural output (not auditing).\n"
            "Output MUST include:\n"
            "1) WOW_DELIVERABLES: concept frame + example + counterexample + diagram outline\n"
            "2) 3 alternative angles (bullets)\n"
            "3) Next 3 experiments (numbered 1-3)\n"
            "Keep it executable.\n\n"
            + common_ctx
        )

    if tab == "guard":
        return (
            "TAB=GUARD (制御/セキュリティ).\n"
            "Goal: apply constraints only when threshold is exceeded.\n"
            "Output MUST include:\n"
            "1) Risk flags (max 5 bullets)\n"
            "2) Decision: PASS / DELAY / BLOCK (one)\n"
            "3) If DELAY/BLOCK: provide a safe alternative plan (must)\n"
            "4) Minimal hedge checklist (max 5 items)\n"
            "Do not over-block; prefer conditional execution.\n\n"
            + common_ctx
        )

    if tab == "diff":
        return (
            "TAB=DIFF (差分).\n"
            "Goal: show what actually changed and why.\n"
            "Output MUST include:\n"
            "1) Δ_FROM_SEED (>=3 bullets)\n"
            "2) ADDED_FROM_COUNTERS (>=3 bullets)\n"
            "3) REMOVED/REJECTED (>=2 bullets)\n"
            "4) Impact (2 bullets)\n"
            "No fluff.\n\n"
            + common_ctx
        )

    # tab == "merge" handled outside (no extra call)
    return common_ctx

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", choices=["expand", "guard", "diff", "merge"], default="merge",
                    help="output tab view (expand/guard/diff/merge). Base triad cycle always runs.")
    ap.add_argument("question", nargs="+", help="question text")
    args = ap.parse_args()

    q = " ".join(args.question).strip()
    tab = args.tab

    log(f"[0/5] tab={tab}")

    # 1) triad_turn skeleton (existing generator)
    log("[1/5] generate_triad_turn_min.py -> incoming/triad_turn.json")
    subprocess.check_call([sys.executable, "tools/generate_triad_turn_min.py", q], cwd=str(REPO))

    # 2) LLM calls for seed/counters/master-merge
    log("[2/5] OpenAI seed...")
    seed = call_openai(f"Answer the question clearly in 6-10 lines.\nQ: {q}")

    log("[2/5] OpenAI counter-1...")
    c1 = call_openai(
        "Counter-1: Improve the answer by adding missing assumptions + concrete corrections.\n"
        "Return: (a) 3 weaknesses (bullets) (b) corrected version (short).\n\n"
        f"Q: {q}\n\nSEED:\n{seed}"
    )

    log("[2/5] OpenAI counter-2...")
    c2 = call_openai(
        "Counter-2: Provide a different angle than Counter-1.\n"
        "Return: (a) 2 alternative frames (bullets) (b) 1 failure mode.\n\n"
        f"Q: {q}\n\nSEED:\n{seed}\n\nCOUNTER-1:\n{c1}"
    )

    log("[2/5] OpenAI MASTER merge...")
    master = call_openai(
        master_merge_prompt() + "\n\n" +
        f"Q: {q}\n\nSEED:\n{seed}\n\nCOUNTER-1:\n{c1}\n\nCOUNTER-2:\n{c2}"
    )

    # 3) write merged_answer.txt (required by triad_turn_to_claims_and_delta)
    log("[3/5] write incoming/merged_answer.txt + attach to triad_turn.json")
    MERGED_TXT.write_text(master, encoding="utf-8")

    turn = json.loads(TURNP.read_text(encoding="utf-8", errors="replace"))
    turn["question"] = q
    turn["seed_answer"] = seed
    turn["counter_1"] = c1
    turn["counter_2"] = c2
    turn["merged_answer"] = master
    turn["merged_answer_path"] = str(MERGED_TXT)
    turn["asof"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    turn["selected_tab"] = tab
    TURNP.write_text(json.dumps(turn, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) run base triad cycle (fixed pipeline)
    log("[4/5] run_triad_cycle.py (claims -> resolution -> gate -> attach...)")
    subprocess.check_call([sys.executable, "tools/run_triad_cycle.py"], cwd=str(REPO))
    log("[DONE] triad cycle completed")

    # 5) produce tab output without re-running the base pipeline
    log("[5/5] render tab output (no re-run)")
    turn_after = json.loads(TURNP.read_text(encoding="utf-8", errors="replace"))

    # always write merge tab as the master merge
    TAB_FILES["merge"].write_text(master, encoding="utf-8")

    if tab in ("expand", "guard", "diff"):
    # Always generate DIFF as well when running EXPAND (for compare)
        prompt = tab_prompt(tab, q, seed, c1, c2, master, turn_after)
        out = call_openai(prompt)
        TAB_FILES[tab].write_text(out, encoding="utf-8")
    else:
        out = master

    # attach output paths for future browser tabs
    turn_after["tab_outputs"] = {k: str(v) for k, v in TAB_FILES.items()}
    # --- COMPARE (Before/After/Δ) for "social proof" ---
    expand_txt = ""
    diff_txt = ""

    if TAB_FILES.get("expand") and Path(TAB_FILES["expand"]).exists():
        expand_txt = Path(TAB_FILES["expand"]).read_text(encoding="utf-8", errors="replace").strip()

    if TAB_FILES.get("diff") and Path(TAB_FILES["diff"]).exists():
        diff_txt = Path(TAB_FILES["diff"]).read_text(encoding="utf-8", errors="replace").strip()

    diff_head = "\n".join(diff_txt.splitlines()[:60]).strip()

    compare = (
        "=== INPUT ===\n"
        f"{q}\n\n"
        "=== BEFORE (Single / seed) ===\n"
        f"{seed}\n\n"
        "=== AFTER (MMAR / EXPAND) ===\n"
        f"{expand_txt}\n\n"
        "=== Δ (Diff head) ===\n"
        f"{diff_head}\n"
    )
    Path(TAB_FILES["compare"]).write_text(compare, encoding="utf-8")
    TURNP.write_text(json.dumps(turn_after, ensure_ascii=False, indent=2), encoding="utf-8")

    # minimal summary (same as before)
    rec = turn_after.get("recommended_mode_auto") or turn_after.get("recommended_mode") or "triad"
    auto = turn_after.get("auto_progress") or {}
    gate = turn_after.get("gate_reason_auto") or {}

    log("=== MMAR SUMMARY (no re-run) ===")
    print("recommended_mode_auto:", rec)
    print("selected_tab:", tab)
    print("tab_output_path:", str(TAB_FILES[tab]))
    print("auto_progress:", json.dumps(auto, ensure_ascii=False))
    print("gate_reason_auto:", json.dumps(gate, ensure_ascii=False))
    log("[DONE]")

if __name__ == "__main__":
    main()
