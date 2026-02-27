#!/usr/bin/env python3
import os, sys, json, subprocess, time, argparse, re, difflib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # providers import safety
sys.path.insert(0, str(REPO / "tools"))
from domain_registry import get_domain_spec, guess_domain

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

def call_openai(prompt: str, timeout_s: int | None = None, question: str = "", max_attempts: int | None = None) -> str:
    """Hard rule: never hang.
    - try up to 2 attempts with short timeout
    - if still failing, return a dummy and continue
    """
    if timeout_s is None:
        timeout_s = 20
        env_timeout = os.getenv("MMAR_LLM_TIMEOUT", "").strip()
        if env_timeout:
            try:
                timeout_s = max(1, int(env_timeout))
            except Exception:
                pass
    if max_attempts is None:
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

    log("[warn] OpenAI failed -> meaningful fallback (continue)")
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


def _clean_option_label(raw: str) -> str:
    s = re.sub(r"^[\s:：\-・,、]+|[\s:：\-・,、?？。]+$", "", raw or "")
    s = re.sub(r"^(問い|question|input)\s*[:：]\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"(どっち|どちら).*$", "", s)
    s = re.sub(r"(方がいい|べき).*$", "", s)
    s = re.sub(r"(と思う|でしょう).*$", "", s)
    s = re.sub(r"(のか|か)$", "", s)
    s = re.sub(r"^(その時間を|この時間を)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > 28:
        s = s[:28].rstrip()
    return s


def _detect_domain(q: str) -> str:
    return str((guess_domain(q or "") or {}).get("name") or "general")


def _extract_user_axes(q: str) -> list[str]:
    t = (q or "")
    ordered: list[tuple[str, str]] = [
        ("学費", "初期コスト"),
        ("予算", "初期コスト"),
        ("回収期間", "回収期間"),
        ("就職率", "就職確率"),
        ("就職", "就職確率"),
        ("収入", "就職確率"),
        ("年収", "就職確率"),
        ("AI", "AI代替耐性"),
        ("陳腐化", "AI代替耐性"),
        ("機会費用", "機会費用"),
        ("時間", "機会費用"),
        ("リスク", "リスク"),
        ("地域", "地域適合"),
        ("地域適合", "地域適合"),
        ("柔軟性", "柔軟性"),
        ("健康", "健康効果"),
        ("栄養", "健康効果"),
        ("価格", "価格"),
        ("費用", "費用"),
        ("継続", "継続可能性"),
        ("怪我", "怪我リスク"),
    ]
    out: list[str] = []
    for k, axis in ordered:
        if k in t and axis not in out:
            out.append(axis)
    domain = _detect_domain(t)
    banned = set(get_domain_spec(domain).get("banned_axes", []))
    out = [a for a in out if a not in banned]
    return out[:5]


def _extract_metrics(q: str) -> list[str]:
    t = (q or "")
    m: list[str] = []
    if "就職率" in t:
        m.append("就職率")
    if "回収期間" in t:
        m.append("回収期間")
    if "年収" in t or "収入" in t:
        m.append("収入見込み")
    if "効果" in t:
        m.append("効果指標")
    return m[:3]


def _extract_constraints(q: str) -> dict:
    t = (q or "")
    budget = None
    deadline = None
    m_budget = re.search(r"(予算|学費上限)\s*[:：]?\s*([0-9０-９]+[万円円]?)", t)
    if m_budget:
        budget = m_budget.group(2)
    m_deadline = re.search(r"(期限|まで)\s*[:：]?\s*([0-9０-９]+(日|ヶ月|か月|年))", t)
    if m_deadline:
        deadline = m_deadline.group(2)
    return {"budget": budget, "deadline": deadline}


def _canonicalize_question(q: str) -> dict:
    g = guess_domain(q or "")
    domain = str(g.get("name") or "general")
    domain_conf = float(g.get("confidence") or 0.0)
    a, b, ok, quality = _extract_ab_options(q)
    user_axes = _extract_user_axes(q)
    metrics = _extract_metrics(q)
    constraints = _extract_constraints(q)
    long_horizon = _is_long_horizon(q)
    year = None
    m_year = re.search(r"(20\d{2})", q or "")
    if m_year:
        try:
            year = int(m_year.group(1))
        except Exception:
            year = None
    missing_fields: list[str] = []
    if domain_conf < 0.55:
        missing_fields.extend(["goal_metric", "priority_axis"])
    elif domain == "education_career":
        if not any(k in (q or "") for k in ("職種", "志望職", "就きたい")):
            missing_fields.append("job_type")
        if not constraints.get("budget"):
            missing_fields.append("budget_cap")
        if not constraints.get("deadline"):
            missing_fields.append("deadline")
    elif domain == "food":
        if not any(k in (q or "") for k in ("摂取量", "量")):
            missing_fields.append("intake_amount")
        if not any(k in (q or "") for k in ("目的", "効果", "血糖", "体重")):
            missing_fields.append("target_metric")
    else:
        if not _has_explicit_goal(q):
            missing_fields.append("goal_metric")
    return {
        "options": {"A": a, "B": b, "ok": ok, "quality": quality},
        "axes": user_axes,
        "metrics": metrics,
        "constraints": constraints,
        "horizon": {"type": "long" if long_horizon else "normal", "year": year},
        "domain": domain,
        "domain_guess": {"name": domain, "confidence": domain_conf},
        "missing_fields": missing_fields,
    }


def _prior_axes(domain: str) -> list[str]:
    return list(get_domain_spec(domain).get("axes_candidates", ["コスト", "リスク", "柔軟性"]))[:5]


def _next_hint_from_missing(domain: str, missing_fields: list[str]) -> str:
    spec = get_domain_spec(domain)
    if not missing_fields:
        cands = list(spec.get("next_question_candidates", []))
        return cands[0] if cands else "不足データを1つ埋め、14日以内に再判定"
    if "goal_metric" in missing_fields or "priority_axis" in missing_fields:
        return "目的/優先軸を1つ選択（例: 収益/リスク/楽しさ/健康/学費/就職）"
    if domain == "education_career":
        if "job_type" in missing_fields:
            return "志望職種を1つ固定し、職種別の就職率を取得"
        if "budget_cap" in missing_fields:
            return "学費上限を金額で指定し、回収期間を再計算"
        if "deadline" in missing_fields:
            return "意思決定期限を日付で固定し、比較条件を確定"
    if domain == "food":
        if "intake_amount" in missing_fields:
            return "1日の摂取量を数値で指定し、比較を再実行"
        if "target_metric" in missing_fields:
            return "目的指標（血糖/体重/便通など）を1つ選択"
    return "目的指標を1つ固定し、再判定条件を明確化"


def _falsifier_line(domain: str, a_label: str, b_label: str, side: str) -> str:
    spec = get_domain_spec(domain)
    templates = list(spec.get("falsifier_templates", []))
    if templates:
        t = templates[0].replace("A", a_label).replace("B", b_label)
        return t
    opp = b_label if side == "A" else a_label
    return f"{opp} 側の第三者検証データで主要軸が優位化した場合に結論を反転"


def _option_quality(a: str, b: str, q: str) -> float:
    if not a or not b or a == b:
        return 0.0
    score = 1.0
    for s in (a, b):
        if len(s) > 22:
            score -= 0.25
        if re.search(r"(どっち|どちら|と思う|方がいい|のか|べき|[?？])", s):
            score -= 0.35
    t = " ".join((q or "").split())
    if len(a) >= max(14, int(len(t) * 0.6)) or len(b) >= max(14, int(len(t) * 0.6)):
        score -= 0.5
    return max(0.0, min(1.0, score))


def _extract_ab_options(q: str) -> tuple[str, str, bool, float]:
    t = " ".join((q or "").split())
    domain = _detect_domain(t)
    if domain == "education_career" and any(k in t for k in ("大学", "進学")) and any(k in t for k in ("専門", "スキル", "実務", "資格")):
        return "大学進学（学歴ルート）", "専門スキル直行（実務→就職）", True, 0.95
    patterns = [
        r"(.+?)と(.+?)どちら",
        r"(.+?)と(.+?)どっち",
        r"(.+?)\s+vs\.?\s+(.+)",
        r"(.+?)\s+[Vv][Ss]\s+(.+)",
        r"(.+?)\s+or\s+(.+)",
        r"(.+?)か(.+?)か",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if not m:
            continue
        a = _clean_option_label(m.group(1))
        b = _clean_option_label(m.group(2))
        if a and b and a != b:
            quality = _option_quality(a, b, q)
            return a, b, (quality >= 0.55), quality
    return "", "", False, 0.0


def _infer_axes(q: str) -> list[str]:
    t = (q or "")
    domain = _detect_domain(t)
    if domain == "education_career":
        return ["初期コスト", "回収期間", "就職確率", "AI代替耐性", "柔軟性"]
    if domain == "sports":
        return ["怪我リスク", "費用", "継続可能性"]
    if domain == "food":
        return ["健康効果", "価格", "継続可能性"]
    axes: list[str] = []
    if any(k in t for k in ("学費", "授業料", "奨学金", "借金", "費用", "コスト")):
        axes.append("初期コスト")
    if any(k in t for k in ("就職", "就職率", "内定", "年収", "収入", "求人")):
        axes.append("就職確率")
    if any(k in t for k in ("AI", "自動化", "陳腐化", "将来性")):
        axes.append("AI耐性")
    if any(k in t for k in ("時間", "年", "最短", "期間", "機会費用")):
        axes.append("機会費用")
    if any(k in t for k in ("ケガ", "怪我", "安全", "故障")):
        axes.append("安全性")
    if any(k in t for k in ("継続", "続け", "習慣")):
        axes.append("継続可能性")

    # Hard rule: for education/future contexts, never force health axis.
    if any(k in t for k in ("学費", "就職", "AI", "将来", "2030", "2035", "2040", "年")):
        axes = [a for a in axes if "健康" not in a]

    dedup: list[str] = []
    for a in axes:
        if a not in dedup:
            dedup.append(a)
    if not dedup:
        dedup = ["コスト", "リスク", "柔軟性"]
    return dedup[:5]


def _is_long_horizon(q: str) -> bool:
    t = (q or "")
    q_l = t.lower()
    return any(k in t for k in ("2030", "2035", "2040", "将来", "今後", "長期")) or any(
        k in q_l for k in ("future", "long-term", "uncertainty", "ai")
    )


def _has_explicit_goal(q: str) -> bool:
    t = (q or "")
    return any(k in t for k in ("目的", "効果", "就職", "年収", "収入", "健康", "コスト", "リスク", "合格", "勝率"))


def _facts3_from_q(q: str) -> list[str]:
    t = " ".join((q or "").split())
    facts: list[str] = []
    m_period = re.search(r"(\d+\s*年)", t)
    if m_period:
        facts.append(f"期間={m_period.group(1)}")
    m_year = re.search(r"(20\d{2})", t)
    if m_year:
        facts.append(f"対象年={m_year.group(1)}")
    if "男性" in t:
        facts.append("対象=男性")
    elif "女性" in t:
        facts.append("対象=女性")
    if "学費" in t:
        facts.append("論点=学費")
    if "就職" in t or "就職率" in t:
        facts.append("論点=就職")
    if "AI" in t:
        facts.append("論点=AI影響")
    if "毎日" in t:
        facts.append("頻度=毎日")
    if "効果" in t:
        facts.append("目的=効果比較")
    if not facts:
        facts.append(f"問い={t[:60]}")
    while len(facts) < 3:
        defaults = ["比較対象=2案", "判定条件=未固定", "追加データで更新可能"]
        facts.append(defaults[len(facts) - 1])
    return facts[:3]


def _build_v2_after(
    q: str,
    recommend_side: str,
    dscore: int,
    outcome: str,
    missing: list[str] | None = None,
) -> str:
    c = _canonicalize_question(q)
    a = c["options"]["A"]
    b = c["options"]["B"]
    ok = bool(c["options"]["ok"])
    option_quality = float(c["options"]["quality"])
    domain = str(c["domain"])
    domain_conf = float((c.get("domain_guess") or {}).get("confidence") or 0.0)
    user_axes = list(c.get("axes") or [])
    axes = user_axes[:] if user_axes else _prior_axes(domain)
    long_horizon = str((c.get("horizon") or {}).get("type") or "") == "long"
    goal_defined = _has_explicit_goal(q)
    missing_fields = list(c.get("missing_fields") or [])
    if not ok or option_quality < 0.55:
        fallback_axes = _prior_axes(domain)
        fallback_facts = _facts3_from_q(q)
        fallback_scores = "\n".join([f"- {ax}: A=3 B=3" for ax in fallback_axes[:3]])
        return (
            "OPTIONS:\n"
            "- A: (unresolved)\n"
            "- B: (unresolved)\n"
            "MODE: HOLD\n"
            "CALL: HOLD\n"
            "CONFIDENCE: 40%\n"
            f"ΔSCORE: {int(dscore):+d}\n"
            "AXES:\n"
            + "\n".join([f"- {ax}" for ax in fallback_axes[:3]]) + "\n"
            + "SCORECARD:\n"
            + fallback_scores + "\n"
            + "FACTS_3:\n"
            + f"- {fallback_facts[0]}\n- {fallback_facts[1]}\n- {fallback_facts[2]}\n"
            + "FALSIFIER:\n- 選択肢定義が確定し次第、結論を再計算\n"
            "NEXT:\n"
            "- 選択肢A/Bを1行で指定してください（例: A=大学進学, B=専門スキル直行）\n"
            f"OUTCOME: {outcome}\n"
        )

    score_map = {
        "初期コスト": (2, 4),
        "回収期間": (2, 4),
        "就職確率": (3, 4),
        "AI耐性": (4, 3),
        "AI代替耐性": (4, 3),
        "機会費用": (2, 4),
        "安全性": (3, 3),
        "継続可能性": (3, 3),
        "コスト": (2, 4),
        "リスク": (3, 3),
        "地域適合": (3, 3),
        "柔軟性": (3, 4),
        "怪我リスク": (3, 3),
        "費用": (2, 4),
        "価格": (3, 2),
        "健康効果": (4, 3),
    }
    scores: dict[str, tuple[int, int]] = {ax: score_map.get(ax, (3, 3)) for ax in axes}
    sum_a = sum(v[0] for v in scores.values())
    sum_b = sum(v[1] for v in scores.values())
    margin = abs(sum_a - sum_b)
    side = "A" if sum_a > sum_b else "B"
    if margin == 0:
        side = recommend_side
    rec = a if side == "A" else b
    opp = b if side == "A" else a
    is_partial = outcome.lower().startswith("partial")
    cap = 65 if is_partial else 85
    if long_horizon:
        cap = min(cap, 60)
    conf_raw = max(50, min(85, 50 + 8 * margin))
    total_slots = 4
    filled_slots = 0
    if c.get("axes"):
        filled_slots += 1
    if c.get("metrics"):
        filled_slots += 1
    if (c.get("constraints") or {}).get("budget") or (c.get("constraints") or {}).get("deadline"):
        filled_slots += 1
    if goal_defined:
        filled_slots += 1
    evidence_completeness = max(0.5, min(1.0, filled_slots / float(total_slots)))
    partial_penalty = 0.85 if is_partial else 1.0
    adjusted = conf_raw * option_quality * evidence_completeness * partial_penalty
    adjusted = adjusted * max(0.4, domain_conf)
    confidence = int(max(40, min(cap, adjusted)))
    facts = _facts3_from_q(q)
    miss_stage = ",".join(missing or []) if missing else "-"
    miss_fields = ",".join(missing_fields) if missing_fields else "-"
    lines = [
        "OPTIONS:",
        f"- A: {a}",
        f"- B: {b}",
    ]
    if domain_conf < 0.55:
        lines.append("MODE: HOLD")
    elif long_horizon:
        lines.append("MODE: CONDITIONAL")
    else:
        lines.append("MODE: NORMAL")
    if domain_conf < 0.55 or (long_horizon and margin <= 1) or (not goal_defined) or len(axes) < 2:
        lines.append("CALL: HOLD")
    else:
        lines.append(f"RECOMMEND: {rec} ({side})")
    lines.extend(
        [
            f"CONFIDENCE: {int(confidence)}%",
            f"ΔSCORE: {int(dscore):+d}",
            "AXES:",
        ]
    )
    lines.extend([f"- {ax}" for ax in axes[:5]])
    lines.append("SCORECARD:")
    for ax in axes[:5]:
        sa, sb = scores.get(ax, (3, 3))
        lines.append(f"- {ax}: A={sa} B={sb}")
    lines.extend(
        [
            "FACTS_3:",
            f"- {facts[0]}",
            f"- {facts[1]}",
            f"- {facts[2]}",
        ]
    )
    if long_horizon:
        lines.extend(
            [
                "SCENARIOS:",
                f"- AI加速: {rec} の優位が維持されるかを就職/収益データで検証",
                f"- AI停滞: {opp} 側の中長期リターン再評価で結論が逆転し得る",
            ]
        )
    lines.extend(
        [
            "FALSIFIER:",
            f"- {_falsifier_line(domain, a, b, side)}",
            "NEXT:",
            f"- {_next_hint_from_missing(domain, missing_fields)}",
            f"- 不足データ(stage={miss_stage}; fields={miss_fields})を1つ埋め、14日以内に再判定",
            f"OUTCOME: {outcome}",
        ]
    )
    return "\n".join(lines) + "\n"


def _judgment_point_changes_from_after(after: str) -> list[str]:
    t = after or ""
    has_axes = ("AXES:" in t and "SCORECARD:" in t)
    has_falsifier = ("FALSIFIER:" in t)
    has_next = ("NEXT:" in t)
    c1 = "比較軸を宣言し、A/Bを軸採点で可視化した（入力文脈に合わせて推定）。" if has_axes else "比較軸を固定し、A/B判定の根拠を数値化した。"
    c2 = "反転条件（FALSIFIER）を定義し、結論が変わる条件を明確化した。" if has_falsifier else "反転条件を定義し、再判定トリガーを明確化した。"
    c3 = "次の一手（NEXT）を“取得データ/期限/閾値”で固定した。" if has_next else "次の一手を具体化し、追加データ収集の方向を固定した。"
    return [c1, c2, c3]


def _stepa_prompt_v2(q: str) -> str:
    c = _canonicalize_question(q)
    a, b = c["options"]["A"], c["options"]["B"]
    ok = bool(c["options"]["ok"])
    quality = float(c["options"]["quality"])
    long_hint = str((c.get("horizon") or {}).get("type") or "") == "long"
    domain = str(c["domain"])
    domain_conf = float((c.get("domain_guess") or {}).get("confidence") or 0.0)
    return (
        "Produce a decision-first answer in EXACT sections below.\n"
        "No extra sections. Keep concise and concrete.\n\n"
        "OPTIONS:\n- A: <label>\n- B: <label>\n"
        "If options cannot be extracted, do NOT output RECOMMEND; output CALL: HOLD and NEXT only.\n"
        "Do not emit long sentence fragments as options.\n"
        "RECOMMEND: choose one side strictly as A or B and include label text\n"
        "CALL: HOLD is allowed when uncertainty is high or options unresolved\n"
        "CONFIDENCE: integer 0-100 with %\n"
        "ΔSCORE: signed integer -100..+100\n"
        "AXES:\n- infer 3-5 axes from input domain\n"
        "SCORECARD:\n- <axis>: A=x B=y\n"
        "FACTS_3:\n- fact 1 from input\n- fact 2 from input\n- fact 3 from input\n"
        "SCENARIOS: only when long-horizon/future uncertainty appears\n"
        "FALSIFIER:\n- one concrete condition that flips conclusion\n"
        "NEXT:\n- one concrete next action with source/deadline/threshold\n\n"
        f"Input question: {q}\n"
        f"Options hint: A={a if ok else '(unresolved)'}, B={b if ok else '(unresolved)'}\n"
        f"Options quality hint: {quality:.2f}\n"
        f"Canonical axes hint: {json.dumps(c.get('axes') or [], ensure_ascii=False)}\n"
        f"Canonical metrics hint: {json.dumps(c.get('metrics') or [], ensure_ascii=False)}\n"
        f"Canonical constraints hint: {json.dumps(c.get('constraints') or {}, ensure_ascii=False)}\n"
        f"Missing fields hint: {json.dumps(c.get('missing_fields') or [], ensure_ascii=False)}\n"
        f"Domain hint: {domain}\n"
        f"Domain confidence hint: {domain_conf:.2f}\n"
        f"Long horizon hint: {'yes' if long_hint else 'no'}\n"
    )


def _pick_key_line(text: str, keys: tuple[str, ...], default_line: str) -> str:
    t = (text or "")
    def _noise(s: str) -> bool:
        low = s.lower()
        return ("openai_error" in low) or ("タイムアウト" in s) or ("timeout" in low and "fallback" in low)
    for line in t.splitlines():
        s = line.strip()
        if not s:
            continue
        if _noise(s):
            continue
        up = s.upper()
        if any(up.startswith(k) for k in keys):
            return s
    for line in t.splitlines():
        s = line.strip()
        if s:
            if _noise(s):
                continue
            return s
    return default_line


def meaningful_after_fallback(q: str, note: str = "", partials: dict | None = None) -> str:
    return _build_v2_after(q, recommend_side="A", dscore=+6, outcome="Fallback")


def build_after_partial(q: str, seed: str, c1: str, c2: str, master: str) -> str:
    return _build_v2_after(q, recommend_side="A", dscore=+12, outcome="Partial_OK", missing=["expand", "diff"])


def build_diff_lite(before: str, after: str, max_lines: int = 30) -> str:
    b = (before or "").splitlines()
    a = (after or "").splitlines()
    lines = list(difflib.unified_diff(b, a, fromfile="before", tofile="after", lineterm=""))
    if not lines:
        return "Δ:\n- LLM timeout -> lite used\n- before/afterに差分はありません\n"
    head = "\n".join(lines[:max_lines]).strip()
    return f"Δ (lite):\n{head}\n"

def build_after_core(q: str) -> str:
    return _build_v2_after(q, recommend_side="A", dscore=+18, outcome="Core_OK")

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
    return _build_v2_after(before_text, recommend_side="A", dscore=+8, outcome="Seed_OK")

def _ensure_deep_after_sections(text: str, q: str, lite: bool = False) -> str:
    t = (text or "").strip()
    # Always keep After as v3 complete shape for partial/timeout paths.
    if _is_valid_after_full(t):
        return t + "\n"
    rebuilt = _build_v2_after(
        q,
        recommend_side="A",
        dscore=+8 if lite else +10,
        outcome="Partial_OK",
        missing=["expand", "diff"] if lite else ["stepA"],
    ).strip()
    return rebuilt + "\n"

def _is_valid_after_full(text: str, min_lines: int = 8) -> bool:
    t = (text or "").strip()
    if not t or "(dummy)" in t:
        return False
    if "OPTIONS:" not in t or "NEXT:" not in t:
        return False
    unresolved = ("- A: (unresolved)" in t and "- B: (unresolved)" in t)
    if unresolved:
        return ("CALL: HOLD" in t and "NEXT:" in t and len(t.splitlines()) >= 5)
    required = ("CONFIDENCE:", "ΔSCORE:", "AXES:", "SCORECARD:", "FACTS_3:", "FALSIFIER:", "NEXT:")
    if not all(k in t for k in required):
        return False
    if not (("RECOMMEND:" in t) or ("CALL: HOLD" in t)):
        return False
    if "MODE: CONDITIONAL" in t and "SCENARIOS:" not in t:
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
    if "RECOMMEND:" in (text or "") and "SCORECARD:" in (text or ""):
        return text
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
    fallback_reason_primary = ""
    fallback_reason_secondary: list[str] = []
    missing_stages: list[str] = []
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

    stage_timeout_default = {
        "stepA": 40,
        "seed": 20,
        "counter_1": 20,
        "counter_2": 20,
        "master": 22,
        "expand": 30,
        "diff": 30,
        "guard": 22,
    }

    deep_retries = 1
    env_retries = os.getenv("MMAR_OPENAI_RETRIES", "").strip()
    if env_retries:
        try:
            deep_retries = max(1, int(env_retries))
        except Exception:
            pass

    def set_primary_reason(reason: str) -> None:
        nonlocal fallback_reason_primary
        if not fallback_reason_primary:
            fallback_reason_primary = reason

    def add_secondary_reason(reason: str) -> None:
        if reason and reason not in fallback_reason_secondary:
            fallback_reason_secondary.append(reason)

    def mark_missing(stage: str) -> None:
        if stage not in missing_stages:
            missing_stages.append(stage)

    def timed_call(stage: str, prompt: str, timeout_override: int | None = None) -> str:
        nonlocal deep_status
        if think_mode and remaining_s() < 12.0:
            if deep_status == "ok":
                deep_status = "partial"
            set_primary_reason("budget_exhausted")
            add_secondary_reason(f"budget_exhausted_before_{stage}")
            mark_missing(stage)
            timings[stage] = 0.0
            return ""
        default_s = int(timeout_override or stage_timeout_default.get(stage, 20))
        timeout_s = max(8, min(default_s, int(max(8.0, remaining_s() - 6.0))))
        t0 = time.perf_counter()
        out = call_openai(prompt, timeout_s=timeout_s, question=q, max_attempts=deep_retries)
        timings[stage] = round(time.perf_counter() - t0, 3)
        if "(openai_error:" in out:
            if deep_status == "ok":
                deep_status = "partial"
            mark_missing(stage)
            low = out.lower()
            if "timed out" in low:
                set_primary_reason("openai_timeout")
                add_secondary_reason(f"openai_timeout:{stage}")
            else:
                set_primary_reason("openai_error")
                add_secondary_reason(f"openai_error:{stage}")
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
    lite_after = build_seed_after_core(q) if no_llm else meaningful_after_fallback(q, "LLM timeout; lite first")
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

    # 2) StepA (required): build strong After v2 first
    if no_llm:
        log("[2/5] MMAR_NO_LLM=1 -> skip OpenAI and use After-Core")
        seed = normalize_before_seed(q)
        c1 = "- Counter: 証拠不足/バイアスの可能性を確認"
        c2 = "- Counter: 逆条件が成立するケースを確認"
        master = build_seed_after_core(q)
    else:
        log("[2/5] OpenAI StepA (strong after v2)...")
        stepa_timeout = int(os.getenv("MMAR_STEPA_TIMEOUT", "40") or "40")
        stepa = timed_call("stepA", _stepa_prompt_v2(q), timeout_override=stepa_timeout)
        if _is_valid_after_full(stepa):
            master = stepa.strip()
        else:
            if deep_status == "ok":
                deep_status = "partial"
            set_primary_reason("stepA_invalid_or_timeout")
            add_secondary_reason("stepA_fallback_local_v2")
            mark_missing("stepA")
            master = _build_v2_after(q, recommend_side="A", dscore=+10, outcome="Partial_OK", missing=["stepA"])
        seed = normalize_before_seed(q)
        c1 = "- Counter: 比較軸を固定しないと結論が揺らぐ"
        c2 = "- Counter: 反転条件を事前定義しないと再現性が落ちる"
    canonical = _canonicalize_question(q)
    domain_guess = canonical.get("domain_guess") or {}
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
            out = build_seed_after_core(q) if tab == "expand" else dummy_fallback_text(f"tab-{tab}")
            if tab == "expand":
                out = _ensure_deep_after_sections(out, q, lite=True)
            TAB_FILES[tab].write_text(out, encoding="utf-8")
            if tab == "expand":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, out), encoding="utf-8")
            if tab == "diff":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, build_seed_after_core(q)), encoding="utf-8")
        else:
            # StepB is optional: keep StepA(master) as default and enrich only if budget remains.
            out = master if tab == "expand" else ""
            do_stepb = remaining_s() >= 18.0
            if do_stepb:
                prompt = tab_prompt(tab, q, seed, c1, c2, master, turn_after)
                out = timed_call("expand", prompt) if tab == "expand" else timed_call(tab, prompt)
            else:
                if deep_status == "ok":
                    deep_status = "partial"
                add_secondary_reason("stepB_skipped_budget")
                if tab == "expand":
                    mark_missing("expand")
                if tab == "diff":
                    mark_missing("diff")
            lite_used = False
            if tab == "expand" and not _is_valid_after_full(out):
                if deep_status == "ok":
                    deep_status = "partial"
                add_secondary_reason("validator_mismatch")
                out = build_after_partial(q, seed, c1, c2, master)
                lite_used = True
            elif tab == "expand" and do_stepb:
                out = out.rstrip() + "\n(full)\n"
            if tab == "expand":
                out = _ensure_deep_after_sections(out, q, lite=lite_used)
            if think_mode:
                out = _append_decision_sections(out, q)
            TAB_FILES[tab].write_text(out, encoding="utf-8")
            # If running EXPAND, also generate DIFF in the background for compare view
            if tab == "expand":
                if remaining_s() >= 14.0:
                    diff_prompt = tab_prompt("diff", q, seed, c1, c2, master, turn_after)
                    diff_out = timed_call("diff", diff_prompt)
                    if _is_pure_dummy(diff_out):
                        diff_out = build_diff_lite(seed, out)
                    if think_mode:
                        diff_out = _append_decision_sections(diff_out, q)
                    TAB_FILES["diff"].write_text(diff_out, encoding="utf-8")
                else:
                    mark_missing("diff")
                    add_secondary_reason("stepB_diff_skipped_budget")
                    TAB_FILES["diff"].write_text(build_diff_lite(seed, out), encoding="utf-8")
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
        if seed.strip() or c1.strip() or c2.strip() or master.strip():
            expand_txt = build_after_partial(q, seed, c1, c2, master).strip()
        else:
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
            deep_status = "partial"
        set_primary_reason("openai_timeout")
        add_secondary_reason("expand_dummy_fallback")

    if TAB_FILES.get("diff") and Path(TAB_FILES["diff"]).exists():
        diff_txt = Path(TAB_FILES["diff"]).read_text(encoding="utf-8", errors="replace").strip()
    if _is_pure_dummy(diff_txt):
        diff_txt = build_diff_lite(seed, expand_txt).strip()
        Path(TAB_FILES["diff"]).write_text(diff_txt, encoding="utf-8")

    diff_head = "\n".join(diff_txt.splitlines()[:60]).strip()
    if not diff_head:
        diff_head = "- LLM timeout -> lite used"

    if think_mode:
        all_stages = ["seed", "counter_1", "counter_2", "master", "expand", "diff"]
        if all(s in missing_stages for s in all_stages):
            if fallback_reason_primary == "openai_timeout":
                deep_status = "timeout"
            else:
                deep_status = "llm_error"
                if not fallback_reason_primary:
                    set_primary_reason("openai_error")
        elif missing_stages and deep_status == "ok":
            deep_status = "partial"
        if deep_status == "partial" and "OUTCOME:" in expand_txt and "OUTCOME: Partial_OK" not in expand_txt:
            expand_txt = expand_txt.rstrip() + "\nOUTCOME: Partial_OK\n"
            Path(TAB_FILES["expand"]).write_text(expand_txt, encoding="utf-8")
    judgment_point_changes = _judgment_point_changes_from_after(expand_txt)

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
        f"domain: {canonical.get('domain')}\n"
        f"domain_guess: {json.dumps(domain_guess, ensure_ascii=False)}\n"
        f"domain_confidence: {float(domain_guess.get('confidence') or 0.0):.2f}\n"
        f"missing_fields: {json.dumps(canonical.get('missing_fields') or [], ensure_ascii=False)}\n"
        f"fallback_reason_primary: {fallback_reason_primary or '-'}\n"
        f"fallback_reason_secondary: {json.dumps(fallback_reason_secondary, ensure_ascii=False)}\n"
        f"missing_stages: {json.dumps(missing_stages, ensure_ascii=False)}\n"
        f"judgment_point_changes: {json.dumps(judgment_point_changes, ensure_ascii=False)}\n"
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
                "domain": canonical.get("domain"),
                "domain_guess": domain_guess,
                "domain_confidence": float(domain_guess.get("confidence") or 0.0),
                "missing_fields": canonical.get("missing_fields") or [],
                "fallback_reason": fallback_reason_primary or "",
                "fallback_reason_primary": fallback_reason_primary or "",
                "fallback_reason_secondary": fallback_reason_secondary,
                "missing_stages": missing_stages,
                "judgment_point_changes": judgment_point_changes,
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
