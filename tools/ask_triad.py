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
DEEP_META = INCOMING / "deep_meta.json"

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
    max_attempts = 2
    env_retries = os.getenv("MMAR_OPENAI_RETRIES", "").strip()
    if env_retries:
        try:
            max_attempts = max(1, int(env_retries))
        except Exception:
            pass
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            from providers.openai_min import responses_create
            return responses_create(prompt, timeout_s=timeout_s)
        except Exception as e:
            last_err = e
            log(f"[warn] OpenAI attempt {attempt}/{max_attempts} failed: {e}")
            if attempt < max_attempts:
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
    call = "HOLD"
    if q_type == "TYPE_AB":
        if re.search(r"\bA\b", q, re.IGNORECASE) and re.search(r"\bB\b", q, re.IGNORECASE):
            call = "A"
        else:
            call = "HOLD"
    elif q_type == "TYPE_ESTIMATE":
        eg = _estimate_evidence_grade(q)
        call = "Very Low" if eg == "E0" else ("Low" if eg == "E1" else "HOLD")
    return (
        f"CALL: {call}\n"
        "WHY: 検証可能データの有無を優先し、現時点の主張は未検証扱い\n"
        "WHY: 判定基準（期限・予算・成功条件）が未固定で比較不能な要素が残る\n"
        "WHY: 反証条件が未定義のため、断定より保留/低確度が再現性高い\n"
        "COUNTER: 取得データの選び方が偏ると逆結論でも同様に説明できる\n"
        "COUNTER: 期間と母数が不足すると短期ノイズを傾向と誤認する\n"
        "FLIP: 第三者検証データで主要仮説が再現されれば判定を引き上げる\n"
        "FLIP: 反証データが閾値を超えれば判定を反転またはHOLDへ戻す\n"
        "NEXT: 判定期間を数値で固定できるか（例: 90日）はい/いいえ\n"
        "NEXT: 判定に使う公開データ源を2つ以上指定できるか（件数）\n"
        "NEXT: 判定を変える閾値を1つ定義できるか（%または件数）\n"
    )


def _pick_key_line(text: str, keys: tuple[str, ...], default_line: str) -> str:
    t = (text or "")
    for line in t.splitlines():
        s = line.strip()
        if not s:
            continue
        up = s.upper()
        if any(up.startswith(k) for k in keys):
            return s
    for line in t.splitlines():
        s = line.strip()
        if s:
            return s
    return default_line


def meaningful_after_fallback(q: str, note: str = "", partials: dict | None = None) -> str:
    p = partials or {}
    weights, assumptions, dominant_axis, flip_threshold = _lite_params_from_q(q)
    strongest = _pick_key_line(
        p.get("master") or p.get("expand_raw") or "",
        ("CALL:", "TENTATIVE_CALL:", "WOW_DELIVERABLES:", "NEXT:", "SSOT:"),
        "CALL: HOLD",
    )
    counter = _pick_key_line(
        p.get("counter_1") or p.get("counter_2") or "",
        ("COUNTER", "-", "WHY"),
        "COUNTER: 反証データ不足のため現時点の結論は脆弱",
    )
    why = _pick_key_line(
        p.get("master") or p.get("seed") or "",
        ("WHY", "SSOT", "-", "CALL"),
        "WHY: 入力制約が未固定のため断定は避ける",
    )
    next_step = _pick_key_line(
        p.get("master") or "",
        ("NEXT", "-", "FLIP"),
        "NEXT: 判定閾値（%または件数）を1つ固定する",
    )
    flip = _pick_key_line(
        p.get("master") or "",
        ("FLIP", "-", "COUNTER"),
        "FLIP: 第三者検証データ追加で判定を更新",
    )
    note_line = f"WHY: fallback={note}" if note else "WHY: fallback=intermediate_best_effort"
    return (
        f"{strongest if strongest.upper().startswith('CALL:') else 'CALL: HOLD'}\n"
        f"{why if why.upper().startswith('WHY') else 'WHY: ' + why}\n"
        f"{note_line}\n"
        f"{counter if counter.upper().startswith('COUNTER') else 'COUNTER: ' + counter}\n"
        f"{flip if flip.upper().startswith('FLIP') else 'FLIP: ' + flip}\n"
        f"{next_step if next_step.upper().startswith('NEXT') else 'NEXT: ' + next_step}\n"
    )


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
        "WHY-3: 証拠の再現性不足 / 主張値と事後確率を分離 / 反証条件を先に固定\n"
        "COUNTER-2: 楽観/悲観バイアス混入の可能性 / 観測母数不足による誤認\n"
        "FLIP-2: 第三者検証データ追加で引上げ / 主要前提反証で反転またはHOLD\n"
        "NEXT-3: 1)判定閾値 2)データ取得元 3)再判定期限 を数値で確定\n"
        f"OUTCOME: {outcome}\n"
    )

def normalize_before_seed(q: str) -> str:
    t = " ".join((q or "").strip().split())
    if not t:
        t = "(no input)"
    head = t[:180] + ("..." if len(t) > 180 else "")
    return (
        f"問い: {head}\n"
        "目的: 判断に使える最小構造へ即時整形\n"
    )

def build_seed_after_core(before_text: str) -> str:
    return (
        "CALL: Low\n"
        "WHY-3: 1)証拠不足を保守評価 2)主張値と事後確率を分離 3)反証条件を先に固定\n"
        "COUNTER-2: 1)楽観バイアス混入の可能性 2)観測不足による見落としの可能性\n"
        "FLIP-2: 1)第三者検証データ追加 2)前提条件(期限/予算/制約)の反証\n"
        "NEXT-3: 1)判定閾値を1つ定義 2)必要データ源を特定 3)再判定時刻を設定\n"
    )

def _ensure_deep_after_sections(text: str, q: str, lite: bool = False) -> str:
    t = (text or "").strip()
    if lite:
        return (t + "\n") if t else ""
    add = []
    if "COUNTER-2:" not in t:
        add.append(
            "COUNTER-2:\n"
            "- 反対仮説: 前提が過度に単純化されていないか\n"
            "- 反対仮説: 代替説明で同じ観測を説明できないか"
        )
    if "FLIP-2:" not in t:
        add.append(
            "FLIP-2:\n"
            "- 第三者検証済みデータが追加される\n"
            "- 主要前提（期限/予算/制約）が反証される"
        )
    if "Δ_GAIN:" not in t:
        add.append(
            "Δ_GAIN:\n"
            "- 争点を2軸以上で分解して比較可能性を向上\n"
            "- 反証条件を先に定義し、判断の更新点を明確化\n"
            "- 次の取得データを限定し、再実行の質を改善"
        )
    if add:
        t = (t + "\n\n" + "\n\n".join(add)).strip()
    return t + "\n"

def _is_valid_after_full(text: str, min_lines: int = 8) -> bool:
    t = (text or "").strip()
    if not t or "(dummy)" in t:
        return False
    has_modern = all(k in t for k in ("CALL:", "WHY", "COUNTER", "FLIP", "NEXT"))
    has_wow = ("WOW_DELIVERABLES" in t and ("Next 3 experiments" in t or "NEXT" in t))
    if not (has_modern or has_wow):
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
    deep_status = "ok"
    fallback_reason = ""
    timings: dict[str, float] = {}
    budget_s = 85
    env_budget = os.getenv("MMAR_TIME_BUDGET_S", "").strip()
    if env_budget:
        try:
            budget_s = max(20, int(env_budget))
        except Exception:
            pass
    started = time.perf_counter()

    def remaining_s() -> float:
        return max(0.0, float(budget_s) - (time.perf_counter() - started))

    def timed_call(stage: str, prompt: str) -> str:
        nonlocal deep_status, fallback_reason
        if think_mode and remaining_s() < 15.0:
            if deep_status == "ok":
                deep_status = "timeout"
            if not fallback_reason:
                fallback_reason = f"budget_exhausted_before_{stage}"
            timings[stage] = 0.0
            return ""
        t0 = time.perf_counter()
        out = call_openai(prompt, question=q)
        timings[stage] = round(time.perf_counter() - t0, 3)
        if "(openai_error:" in out and deep_status == "ok":
            deep_status = "llm_error"
            if not fallback_reason:
                fallback_reason = "openai_timeout"
        return out

    log(f"[0/5] tab={tab}")

    if seed_only:
        before_seed = normalize_before_seed(q)
        after_seed = "(Deep running...)"
        diff_seed = "(Deep running...)"
        TAB_FILES["compare"].write_text(
            "=== INPUT ===\n"
            f"{q}\n\n"
            "=== BEFORE (Single / seed) ===\n"
            f"{before_seed}\n\n"
            "=== AFTER (MMAR / EXPAND) ===\n"
            f"{after_seed}\n\n"
            "=== Δ (Diff head) ===\n"
            f"{diff_seed}\n",
            encoding="utf-8",
        )
        TAB_FILES["expand"].write_text(after_seed, encoding="utf-8")
        TAB_FILES["diff"].write_text(diff_seed, encoding="utf-8")
        TAB_FILES["merge"].write_text(before_seed, encoding="utf-8")
        log("[seed_only] wrote out_compare placeholders and returned")
        return

    # 1) triad_turn skeleton (existing generator)
    log("[1/5] generate_triad_turn_min.py -> incoming/triad_turn.json")
    subprocess.check_call([sys.executable, "tools/generate_triad_turn_min.py", q], cwd=str(REPO))
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
    lite_before = normalize_before_seed(q) if no_llm else "初期SEED生成中（lite first）"
    lite_after = build_seed_after_core(lite_before) if no_llm else meaningful_after_fallback(q, "LLM timeout; lite first")
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
        log("[2/5] MMAR_NO_LLM=1 -> skip OpenAI and use After-Core")
        seed = normalize_before_seed(q)
        c1 = "- Counter: 証拠不足/バイアスの可能性を確認"
        c2 = "- Counter: 逆条件が成立するケースを確認"
        master = build_seed_after_core(seed)
    else:
        log("[2/5] OpenAI seed...")
        seed = timed_call("seed", f"Answer the question clearly in 6-10 lines.\nQ: {q}")
        if not seed.strip():
            seed = normalize_before_seed(q)

        log("[2/5] OpenAI counter-1...")
        c1 = timed_call("counter_1",
            "Counter-1: Improve the answer by adding missing assumptions + concrete corrections.\n"
            "Return: (a) 3 weaknesses (bullets) (b) corrected version (short).\n\n"
            f"Q: {q}\n\nSEED:\n{seed}"
        )
        if not c1.strip():
            c1 = "- Counter: データ不足で結論の頑健性が低い"

        log("[2/5] OpenAI counter-2...")
        c2 = timed_call("counter_2",
            "Counter-2: Provide a different angle than Counter-1.\n"
            "Return: (a) 2 alternative frames (bullets) (b) 1 failure mode.\n\n"
            f"Q: {q}\n\nSEED:\n{seed}\n\nCOUNTER-1:\n{c1}"
        )
        if not c2.strip():
            c2 = "- Counter: 反証条件未固定のため逆結論リスクあり"

        log("[2/5] OpenAI MASTER merge...")
        master = timed_call("master",
            master_merge_prompt() + "\n\n" +
            f"Q: {q}\n\nSEED:\n{seed}\n\nCOUNTER-1:\n{c1}\n\nCOUNTER-2:\n{c2}"
        )
        if not master.strip():
            master = meaningful_after_fallback(
                q,
                note="budget_or_llm_before_master",
                partials={"seed": seed, "counter_1": c1, "counter_2": c2},
            )
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
            out = build_seed_after_core(normalize_before_seed(q)) if tab == "expand" else dummy_fallback_text(f"tab-{tab}")
            if tab == "expand":
                out = _ensure_deep_after_sections(out, q, lite=True)
            TAB_FILES[tab].write_text(out, encoding="utf-8")
            if tab == "expand":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, out), encoding="utf-8")
            if tab == "diff":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, build_seed_after_core(normalize_before_seed(q))), encoding="utf-8")
        else:
            prompt = tab_prompt(tab, q, seed, c1, c2, master, turn_after)
            out = timed_call("expand", prompt) if tab == "expand" else timed_call(tab, prompt)
            lite_used = False
            if tab == "expand" and not _is_valid_after_full(out):
                if deep_status == "ok":
                    deep_status = "schema_invalid"
                if not fallback_reason:
                    fallback_reason = "validator_mismatch"
                out = meaningful_after_fallback(
                    q,
                    "validator_mismatch",
                    partials={"seed": seed, "counter_1": c1, "counter_2": c2, "master": master, "expand_raw": out},
                )
                lite_used = True
            elif tab == "expand":
                out = out.rstrip() + "\n(full)\n"
            if tab == "expand":
                out = _ensure_deep_after_sections(out, q, lite=lite_used)
            if think_mode:
                out = _append_decision_sections(out, q)
            TAB_FILES[tab].write_text(out, encoding="utf-8")
            # If running EXPAND, also generate DIFF in the background for compare view
            if tab == "expand":
                diff_prompt = tab_prompt("diff", q, seed, c1, c2, master, turn_after)
                diff_out = timed_call("diff", diff_prompt)
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
        expand_txt = _ensure_deep_after_sections(
            meaningful_after_fallback(
                q,
                "LLM timeout; fallback used",
                partials={"seed": seed, "counter_1": c1, "counter_2": c2, "master": master},
            ),
            q,
            lite=True,
        ).strip()
        Path(TAB_FILES["expand"]).write_text(expand_txt, encoding="utf-8")
        if deep_status == "ok":
            deep_status = "llm_error"
        if not fallback_reason:
            fallback_reason = "openai_timeout"

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
        f"{diff_head}\n\n"
        "=== DEEP META ===\n"
        f"deep_status: {deep_status}\n"
        f"fallback_reason: {fallback_reason or '-'}\n"
        f"timings: {json.dumps(timings, ensure_ascii=False)}\n"
    )
    if think_mode:
        compare = _append_decision_sections(compare, q)
    Path(TAB_FILES["compare"]).write_text(compare, encoding="utf-8")
    TURNP.write_text(json.dumps(turn_after, ensure_ascii=False, indent=2), encoding="utf-8")
    DEEP_META.write_text(
        json.dumps(
            {
                "deep_status": deep_status,
                "fallback_reason": fallback_reason or "",
                "timings": timings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

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
