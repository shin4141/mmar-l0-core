#!/usr/bin/env python3
import os, sys, json, subprocess, time, argparse, re, difflib
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

def call_openai(prompt: str, timeout_s: int = 20, question: str = "") -> str:
    """Hard rule: never hang.
    - try up to 2 attempts with short timeout
    - if still failing, return a dummy and continue
    """
    env_timeout = os.getenv("MMAR_LLM_TIMEOUT", "").strip()
    if env_timeout:
        try:
            timeout_s = max(1, int(env_timeout))
        except Exception:
            pass
    last_err = None
    for attempt in range(1, 3):
        try:
            from providers.openai_min import responses_create
            return responses_create(prompt, timeout_s=timeout_s)
        except Exception as e:
            last_err = e
            log(f"[warn] OpenAI attempt {attempt}/2 failed: {e}")
            time.sleep(0.5)

    log("[warn] OpenAI failed twice -> meaningful fallback (continue)")
    decision = _decision_sections(question) if question else (
        "\nDOMINANT_AXIS:\n"
        "- 暫定: Growth（情報不足のため仮置き）\n\n"
        "FLIP_THRESHOLD:\n"
        "- Time または Money が1段階上がると結論が反転し得る\n"
    )
    return (
        "SSOT:\n"
        "- OpenAI応答がタイムアウトしたため、暫定の構造化ドラフトを返します。\n\n"
        "PURPOSE/CONSTRAINTS:\n"
        "- 目的: まず比較可能な初稿を出し、Thinkで精度を上げる。\n"
        "- 制約: 外部LLM応答なし。入力テキストと既存ルールのみで生成。\n\n"
        "WEIGHTS (Low/Med/High, optional):\n"
        "- Time:\n"
        "- Money:\n"
        "- Growth:\n"
        f"{decision}\n"
        "NEXT_3_QUESTIONS:\n"
        "1) いつまでに意思決定が必要ですか？（期限）\n"
        "2) 許容できるコスト上限は？（予算レンジ）\n"
        "3) 今回の成功条件は何ですか？（成長KPI）\n\n"
        "Next step: 上の3質問に回答し、Thinkモードで再実行してください。\n"
        f"(openai_error: {last_err})\n"
    )


def dummy_fallback_text(label: str = "dummy") -> str:
    return (
        f"SSOT:\n- ({label})\n\n"
        "WEIGHTS (Low/Med/High, optional):\n"
        "- Time:\n"
        "- Money:\n"
        "- Growth:\n\n"
        "Δ:\n- (dummy)\n- (dummy)\n\n"
        "Next step: (dummy)\n"
    )

def _is_pure_dummy(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return "(dummy)" in t and "PURPOSE" not in t and "PURPOSE/CONSTRAINTS" not in t


def _lite_params_from_q(q: str):
    q_l = (q or "").lower()
    assumptions = []
    weights = {"Time": "Med", "Money": "Med", "Growth": "Med"}
    for axis, hints in (
        ("Time", ("urgent", "asap", "quick", "fast", "deadline")),
        ("Money", ("budget", "cheap", "cost", "expense", "save money")),
        ("Growth", ("growth", "scale", "revenue", "long-term", "market share")),
    ):
        m = re.search(rf"{axis.lower()}\s*[:=]\s*(low|med|medium|high)", q_l)
        if m:
            v = m.group(1)
            weights[axis] = "High" if v == "high" else ("Low" if v == "low" else "Med")
        elif any(h in q_l for h in hints):
            weights[axis] = "High"
            assumptions.append(f"- {axis}は入力ヒントからHighと仮定")
        else:
            assumptions.append(f"- {axis}は指定なしのためMed仮定")
    score = {"Low": 1, "Med": 2, "High": 3}
    dominant_axis = max(weights, key=lambda k: score[weights[k]])
    flip_threshold = [
        f"- {dominant_axis}が1段階下がる（High→Med/Med→Low）と結論が反転し得る",
        "- 別軸が1段階上がると優先順位が入れ替わり得る",
    ]
    return weights, assumptions[:3], dominant_axis, flip_threshold[:2]

def _detect_q_type(q: str) -> str:
    t = (q or "")
    if re.search(r"(どっち|比較|\bvs\b|A\s*[/\-]?\s*B|\bA\b.*\bB\b)", t, re.IGNORECASE):
        return "TYPE_AB"
    if re.search(r"(確率|可能性|%|未来|起こる|来るか)", t):
        return "TYPE_ESTIMATE"
    if re.search(r"(やり方|方法|どうすれば|手順)", t):
        return "TYPE_HOWTO"
    return "TYPE_AB"

def _qual_to_num(label: str) -> float:
    scale = {"Very_Low": 0.05, "Low": 0.2, "Med": 0.5, "High": 0.8}
    return scale.get(label, 0.5)

def _extract_claim_percent(text: str):
    t = (text or "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def _estimate_evidence_grade(text: str) -> str:
    t = (text or "")
    strong = ("物理証拠", "第三者検証", "公開データ")
    situational = ("兆候", "観測", "報告", "目撃")
    if any(k in t for k in strong):
        return "E2"
    if any(k in t for k in situational):
        return "E1"
    return "E0"

def _estimate_label(text: str, default_label: str = "Med") -> str:
    t = (text or "")
    if re.search(r"(very[_ ]?low|極めて低|ほぼない|まずない)", t, re.IGNORECASE):
        return "Very_Low"
    if re.search(r"(low|低い|低め|難しい|厳しい)", t, re.IGNORECASE):
        return "Low"
    if re.search(r"(high|高い|高め|有望|起こる)", t, re.IGNORECASE):
        return "High"
    return default_label

def _classify_outcome(q_type: str, q: str, weights: dict, dominant_axis: str):
    if q_type == "TYPE_ESTIMATE":
        prior_label = "Low"
        evidence_grade = _estimate_evidence_grade(q)
        after_label = "Med" if evidence_grade == "E2" else "Low"
    else:
        prior_label = _estimate_label(q, "Med")
        after_label = "High" if dominant_axis == "Growth" else ("Low" if dominant_axis == "Money" else weights.get("Time", "Med"))
    prior = _qual_to_num(prior_label)
    after = _qual_to_num(after_label)
    direction_change = False
    if q_type == "TYPE_AB":
        prior_side = "B" if re.search(r"(B優位|B有利|Bが勝つ)", q, re.IGNORECASE) else "A"
        after_side = "B" if dominant_axis == "Money" else "A"
        direction_change = prior_side != after_side
    else:
        direction_change = (prior < 0.5 <= after) or (after < 0.5 <= prior)
    delta = after - prior
    abs_delta = abs(delta)
    if direction_change:
        outcome = "Flip"
    elif abs_delta >= 0.30:
        outcome = "Major_Update"
    elif abs_delta >= 0.10:
        outcome = "Update"
    else:
        outcome = "Reinforced"
    return outcome, delta, abs_delta


def build_after_lite(q, weights, assumptions, dominant_axis, flip_threshold)->str:
    q_type = _detect_q_type(q)
    outcome, delta, abs_delta = _classify_outcome(q_type, q, weights, dominant_axis)
    qs = [
        "1) 期限はいつか（Time）",
        "2) 予算上限はいくらか（Money）",
        "3) 成功KPIは何か（Growth）",
    ]
    if q_type == "TYPE_ESTIMATE":
        claim_pct = _extract_claim_percent(q)
        claim_txt = f"{claim_pct}%" if claim_pct is not None else "未指定"
        evidence_grade = _estimate_evidence_grade(q)
        call = "Low" if evidence_grade == "E0" else ("Med" if evidence_grade == "E1" else "High")
        if evidence_grade == "E0" and call in ("Med", "High"):
            call = "Low"
        direction_change = (outcome == "Flip")
        if direction_change:
            update = "Flip"
        elif evidence_grade in ("E1", "E2"):
            update = "Major_Update"
        else:
            update = "Reinforced"
        return (
            f"CALL: {call}\n"
            f"UPDATE: {update}\n\n"
            "CLAIM:\n"
            f"- ユーザー主張確率: {claim_txt}\n\n"
            "WHY:\n"
            "- 既定レンジは保守側（Low）を基準にするため。\n"
            "- ユーザー%は主張値であり、事後確率を直接決めないため。\n"
            f"- 現在の証拠グレードは {evidence_grade} で、上方更新条件を満たしていないため。\n\n"
            "EVIDENCE_GAP:\n"
            "- 第三者検証済みの公開データが追加される\n"
            "- 反証不能な物理証拠が提示される\n\n"
            f"OUTCOME: {outcome}\n\n"
            "NEXT_3:\n"
            "1) 予測対象の期間はいつまでか？\n"
            "2) 参照できる過去データはあるか？\n"
            "3) 成否判定の基準値は何か？\n"
            "\nNEXT_ACTION:\n"
            "- CALLを変更する証拠条件（第三者検証済み公開データの閾値）を1行で定義する。\n"
        )
    if q_type == "TYPE_HOWTO":
        return (
            "TENTATIVE_CALL:\n"
            "- まず小さく試す3ステップ計画で進めるのが妥当です (lite)。\n\n"
            "PLAN_3:\n"
            "- Step1: 目的と成功条件を1枚に固定する。\n"
            "- Step2: 最小実験を実行して結果を記録する。\n"
            "- Step3: 結果に基づき次の打ち手を1つに絞る。\n\n"
            "PITFALLS_3:\n"
            "- 目的未定義のまま作業し、評価不能になる。\n"
            "- 一度に広げすぎて検証不能になる。\n"
            "- 記録を残さず再現できなくなる。\n\n"
            f"OUTCOME: {outcome}\n\n"
            "NEXT_3:\n"
            "1) 成功条件は何か？\n"
            "2) 最小実験の期間は？\n"
            "3) 失敗時の撤退ラインは？\n"
        )
    return (
        "TENTATIVE_CALL:\n"
        "- LLMタイムアウト時の暫定判断として、比較可能なAfter-liteを採用する (lite)。\n\n"
        "DOMINANT_AXIS:\n"
        f"- {dominant_axis}（Time={weights.get('Time','Med')}, Money={weights.get('Money','Med')}, Growth={weights.get('Growth','Med')}）\n"
        + ("".join([f"{a}\n" for a in assumptions]) if assumptions else "")
        + "\nFLIP_THRESHOLD:\n"
        + "\n".join((flip_threshold or [])[:2]) + "\n\n"
        + f"OUTCOME: {outcome}\n\n"
        + "NEXT_3:\n"
        + "\n".join(qs[:3]) + "\n"
    )


def meaningful_after_fallback(q: str, note: str = "") -> str:
    weights, assumptions, dominant_axis, flip_threshold = _lite_params_from_q(q)
    body = build_after_lite(q, weights, assumptions, dominant_axis, flip_threshold)
    if note:
        body = body.rstrip() + f"\n({note})\n"
    return body


def build_diff_lite(before: str, after: str, max_lines: int = 30) -> str:
    b = (before or "").splitlines()
    a = (after or "").splitlines()
    lines = list(difflib.unified_diff(b, a, fromfile="before", tofile="after", lineterm=""))
    if not lines:
        return "Δ:\n- LLM timeout -> lite used\n- before/afterに差分はありません\n"
    head = "\n".join(lines[:max_lines]).strip()
    return f"Δ (lite):\n{head}\n"

def build_after_core(q: str) -> str:
    q_type = _detect_q_type(q)
    weights, assumptions, dominant_axis, flip_threshold = _lite_params_from_q(q)
    outcome, _, _ = _classify_outcome(q_type, q, weights, dominant_axis)
    call = "Low" if q_type == "TYPE_ESTIMATE" else ("High" if dominant_axis == "Growth" else "Med")
    return (
        f"CALL: {call}\n"
        "WHY-3:\n"
        "- 現時点で再現可能な証拠が不足しているため保守側で判断。\n"
        "- 入力の主張値は仮説として扱い、直接採用しない。\n"
        "- 逆転条件を先に定義して検証可能性を確保する。\n\n"
        "COUNTER-2:\n"
        "- 反対仮説: 前提が過度に悲観的/楽観的でないか。\n"
        "- 反対仮説: 観測バイアスで確率を誤認していないか。\n\n"
        "FLIP-2:\n"
        "- 第三者検証済みデータが追加される。\n"
        "- 主要前提（期限/予算/制約）が反証される。\n\n"
        "NEXT-3:\n"
        "1) 反証可能な閾値を1つ決める\n"
        "2) 必要データの取得元を決める\n"
        "3) 再判定の期限を決める\n\n"
        f"OUTCOME: {outcome}\n"
    )

def _is_valid_after_full(text: str, min_lines: int = 10) -> bool:
    t = (text or "").strip()
    if not t or "(dummy)" in t:
        return False
    required = ("TENTATIVE_CALL:", "DOMINANT_AXIS:", "FLIP_THRESHOLD:", "NEXT_3:")
    if not all(h in t for h in required):
        return False
    return len(t.splitlines()) >= min_lines


def _decision_sections(q: str) -> str:
    q_l = (q or "").lower()
    norm = {"low": "Low", "med": "Med", "medium": "Med", "high": "High"}
    val = {"Low": 1, "Med": 2, "High": 3}
    assumptions: list[str] = []

    def _pick(axis: str, hints: tuple[str, ...]) -> str:
        m = re.search(rf"{axis}\s*[:=]\s*(low|med|medium|high)", q_l)
        if m:
            return norm[m.group(1)]
        for h in hints:
            if h in q_l:
                assumptions.append(f"- inferred {axis.title()}=High from input hint: \"{h}\"")
                return "High"
        assumptions.append(f"- missing {axis.title()} weight; defaulted to Med")
        return "Med"

    time_w = _pick("time", ("urgent", "asap", "quick", "fast", "deadline"))
    money_w = _pick("money", ("budget", "cheap", "cost", "expense", "save money"))
    growth_w = _pick("growth", ("growth", "scale", "revenue", "long-term", "market share"))
    scores = {"Time": val[time_w], "Money": val[money_w], "Growth": val[growth_w]}
    dominant_axis = max(scores, key=scores.get)

    assumptions_txt = ""
    if assumptions:
        assumptions_txt = "\nASSUMPTIONS:\n" + "\n".join(assumptions[:3]) + "\n"

    dom_line = (
        f"- {dominant_axis} dominates under mapped weights "
        f"(Time={time_w}({scores['Time']}), Money={money_w}({scores['Money']}), Growth={growth_w}({scores['Growth']}))."
    )
    return (
        "\nDOMINANT_AXIS:\n"
        f"{dom_line}\n\n"
        "FLIP_THRESHOLD:\n"
        f"- If {dominant_axis} drops by one level (e.g., High->Med), decision may flip.\n"
        "- If another axis rises by one level (e.g., Med->High), ranking can invert.\n"
        "- If two axes tie at High, prefer explicit tie-break criterion (time vs cost vs growth).\n"
        f"{assumptions_txt}"
    )


def _append_decision_sections(text: str, q: str) -> str:
    if "DOMINANT_AXIS:" in text and "FLIP_THRESHOLD:" in text:
        return text
    return (text.rstrip() + "\n\n" + _decision_sections(q)).rstrip() + "\n"

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
    ap.add_argument("--tab", choices=["seed", "expand", "guard", "diff", "merge"], default="merge",
                    help="output tab view (expand/guard/diff/merge). Base triad cycle always runs.")
    ap.add_argument("question", nargs="+", help="question text")
    args = ap.parse_args()

    q = " ".join(args.question).strip()
    tab = args.tab
    core_only = os.getenv("MMAR_CORE_ONLY", "").strip() == "1"
    seed_only = os.getenv("MMAR_SEED_ONLY", "").strip() == "1" or tab == "seed"
    no_llm = os.getenv("MMAR_NO_LLM", "").strip() == "1"
    think_mode = not no_llm

    log(f"[0/5] tab={tab}")

    # 1) triad_turn skeleton (existing generator)
    log("[1/5] generate_triad_turn_min.py -> incoming/triad_turn.json")
    subprocess.check_call([sys.executable, "tools/generate_triad_turn_min.py", q], cwd=str(REPO))
    if seed_only:
        seed = q
        after_ph = "Deep pending..."
        diff_ph = "- Deep pending..."
        TAB_FILES["expand"].write_text(after_ph, encoding="utf-8")
        TAB_FILES["diff"].write_text(diff_ph, encoding="utf-8")
        TAB_FILES["merge"].write_text(seed, encoding="utf-8")
        TAB_FILES["compare"].write_text(
            "=== INPUT ===\n"
            f"{q}\n\n"
            "=== BEFORE (Single / seed) ===\n"
            f"{seed}\n\n"
            "=== AFTER (MMAR / EXPAND) ===\n"
            f"{after_ph}\n\n"
            "=== Δ (Diff head) ===\n"
            f"{diff_ph}\n",
            encoding="utf-8",
        )
        log("[DONE] seed-only output written")
        return
    if core_only:
        after_core = build_after_core(q)
        before_core = q
        diff_core = build_diff_lite(before_core, after_core)
        TAB_FILES["expand"].write_text(after_core, encoding="utf-8")
        TAB_FILES["diff"].write_text(diff_core, encoding="utf-8")
        TAB_FILES["merge"].write_text(after_core, encoding="utf-8")
        TAB_FILES["compare"].write_text(
            "=== INPUT ===\n"
            f"{q}\n\n"
            "=== BEFORE (Single / seed) ===\n"
            f"{before_core}\n\n"
            "=== AFTER (MMAR / EXPAND) ===\n"
            f"{after_core}\n\n"
            "=== Δ (Diff head) ===\n"
            f"{diff_core}\n",
            encoding="utf-8",
        )
        log("[DONE] core-only output written")
        return
    lite_after = meaningful_after_fallback(q, "LLM timeout; lite first")
    lite_before = "初期SEED生成中（lite first）"
    lite_diff = build_diff_lite(lite_before, lite_after)
    TAB_FILES["expand"].write_text(lite_after, encoding="utf-8")
    TAB_FILES["diff"].write_text(lite_diff, encoding="utf-8")
    TAB_FILES["compare"].write_text(
        "=== INPUT ===\n"
        f"{q}\n\n"
        "=== BEFORE (Single / seed) ===\n"
        f"{lite_before}\n\n"
        "=== AFTER (MMAR / EXPAND) ===\n"
        f"{lite_after}\n\n"
        "=== Δ (Diff head) ===\n"
        f"{lite_diff}\n",
        encoding="utf-8",
    )

    # 2) LLM calls for seed/counters/master-merge
    if no_llm:
        log("[2/5] MMAR_NO_LLM=1 -> skip OpenAI and use dummy fallback")
        seed = dummy_fallback_text("seed")
        c1 = dummy_fallback_text("counter-1")
        c2 = dummy_fallback_text("counter-2")
        master = meaningful_after_fallback(q, "LLM timeout; fallback used")
    else:
        log("[2/5] OpenAI seed...")
        seed = call_openai(f"Answer the question clearly in 6-10 lines.\nQ: {q}", question=q)

        log("[2/5] OpenAI counter-1...")
        c1 = call_openai(
            "Counter-1: Improve the answer by adding missing assumptions + concrete corrections.\n"
            "Return: (a) 3 weaknesses (bullets) (b) corrected version (short).\n\n"
            f"Q: {q}\n\nSEED:\n{seed}"
        , question=q)

        log("[2/5] OpenAI counter-2...")
        c2 = call_openai(
            "Counter-2: Provide a different angle than Counter-1.\n"
            "Return: (a) 2 alternative frames (bullets) (b) 1 failure mode.\n\n"
            f"Q: {q}\n\nSEED:\n{seed}\n\nCOUNTER-1:\n{c1}"
        , question=q)

        log("[2/5] OpenAI MASTER merge...")
        master = call_openai(
            master_merge_prompt() + "\n\n" +
            f"Q: {q}\n\nSEED:\n{seed}\n\nCOUNTER-1:\n{c1}\n\nCOUNTER-2:\n{c2}"
        , question=q)
    if think_mode:
        master = _append_decision_sections(master, q)

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

    # always write compare view (no extra LLM call)
    expand_path = TAB_FILES.get("expand")
    diff_path = TAB_FILES.get("diff")

    expand_txt = expand_path.read_text(encoding="utf-8", errors="replace") if expand_path and expand_path.exists() else ""
    diff_txt = diff_path.read_text(encoding="utf-8", errors="replace") if diff_path and diff_path.exists() else ""

    # take top part of diff to keep compare readable
    diff_head = "\n".join(diff_txt.splitlines()[:60]).strip()
    if not diff_head:
        diff_head = "- LLM timeout -> lite used"

    compare = (
        "=== INPUT ===\n"
        f"{q}\n\n"
        "=== SINGLE (seed) ===\n"
        f"{seed}\n\n"
        "=== MMAR EXPAND (tab output) ===\n"
        f"{expand_txt.strip()}\n\n"
        "=== DIFF (head) ===\n"
        f"{diff_head}\n"
    )
    if think_mode:
        compare = _append_decision_sections(compare, q)
    TAB_FILES["compare"].write_text(compare, encoding="utf-8")

    if tab in ("expand", "guard", "diff"):
        if no_llm:
            out = meaningful_after_fallback(q, "LLM timeout; fallback used") if tab == "expand" else dummy_fallback_text(f"tab-{tab}")
            TAB_FILES[tab].write_text(out, encoding="utf-8")
            if tab == "expand":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, out), encoding="utf-8")
            if tab == "diff":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, meaningful_after_fallback(q, "LLM timeout; fallback used")), encoding="utf-8")
        else:
            prompt = tab_prompt(tab, q, seed, c1, c2, master, turn_after)
            out = call_openai(prompt, question=q)
            if tab == "expand" and not _is_valid_after_full(out):
                out = meaningful_after_fallback(q, "LLM timeout; lite used")
            elif tab == "expand":
                out = out.rstrip() + "\n(full)\n"
            if think_mode:
                out = _append_decision_sections(out, q)
            TAB_FILES[tab].write_text(out, encoding="utf-8")
            # If running EXPAND, also generate DIFF in the background for compare view
            if tab == "expand":
                diff_prompt = tab_prompt("diff", q, seed, c1, c2, master, turn_after)
                diff_out = call_openai(diff_prompt, question=q)
                if _is_pure_dummy(diff_out):
                    diff_out = build_diff_lite(seed, out)
                if think_mode:
                    diff_out = _append_decision_sections(diff_out, q)
                TAB_FILES["diff"].write_text(diff_out, encoding="utf-8")
            # If running EXPAND, also generate DIFF in the background for compare view
            if tab == "expand":
                diff_prompt = tab_prompt("diff", q, seed, c1, c2, master, turn_after)
                diff_out = call_openai(diff_prompt, question=q)
                if _is_pure_dummy(diff_out):
                    diff_out = build_diff_lite(seed, out)
                if think_mode:
                    diff_out = _append_decision_sections(diff_out, q)
                TAB_FILES["diff"].write_text(diff_out, encoding="utf-8")
    else:
        out = master

    # attach output paths for future browser tabs
    turn_after["tab_outputs"] = {k: str(v) for k, v in TAB_FILES.items()}
    # --- COMPARE (Before/After/Δ) for "social proof" ---
    expand_txt = ""
    diff_txt = ""

    if TAB_FILES.get("expand") and Path(TAB_FILES["expand"]).exists():
        expand_txt = Path(TAB_FILES["expand"]).read_text(encoding="utf-8", errors="replace").strip()
    if _is_pure_dummy(expand_txt):
        expand_txt = meaningful_after_fallback(q, "LLM timeout; fallback used").strip()
        Path(TAB_FILES["expand"]).write_text(expand_txt, encoding="utf-8")

    if TAB_FILES.get("diff") and Path(TAB_FILES["diff"]).exists():
        diff_txt = Path(TAB_FILES["diff"]).read_text(encoding="utf-8", errors="replace").strip()
    if _is_pure_dummy(diff_txt):
        diff_txt = build_diff_lite(seed, expand_txt).strip()
        Path(TAB_FILES["diff"]).write_text(diff_txt, encoding="utf-8")

    diff_head = "\n".join(diff_txt.splitlines()[:60]).strip()
    if not diff_head:
        diff_head = "- LLM timeout -> lite used"

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
    if think_mode:
        compare = _append_decision_sections(compare, q)
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
