#!/usr/bin/env python3
import os, sys, json, subprocess, time, argparse, re, difflib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # providers import safety
sys.path.insert(0, str(REPO / "tools"))
from domain_registry import get_domain_spec, guess_domain


def _git_sha_short() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO), text=True, timeout=2)
        return out.strip() or "unknown"
    except Exception:
        return "unknown"


RUN_SHA = _git_sha_short()

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
DECISION_CARDS_DIR = INCOMING / "decision_cards"
DECISION_CARDS_DIR.mkdir(exist_ok=True)
DECISION_CARD_LATEST = INCOMING / "decision_card_latest.json"

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
    s = re.sub(r"^.*?なら", "", s)
    s = re.sub(r"(どっち|どちら).*$", "", s)
    s = re.sub(r"(方がいい|べき).*$", "", s)
    s = re.sub(r"(と思う|でしょう).*$", "", s)
    s = re.sub(r"(のか|か)$", "", s)
    s = re.sub(r"^(その時間を|この時間を)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > 28:
        s = s[:28].rstrip()
    return s


def _option_noise_score(label: str) -> int:
    s = str(label or "").strip()
    if not s:
        return 10
    score = 0
    if len(s) > 14:
        score += 2
    if re.search(r"[。！？?？]", s):
        score += 2
    if re.search(r"(どっち|どちら|相応しい|でしょう|ですか|と思う|方がいい)", s):
        score += 3
    if re.search(r"(を|に|で|が|は|から|まで|より|について)", s) and len(s) > 10:
        score += 1
    return score


def _pick_short_jp_token(text: str, side: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ンー]{2,24}", text or "")
    if not tokens:
        return ""
    stop = {"どっち", "どちら", "ですか", "でしょう", "相応しい", "比較", "検討", "候補", "今日", "普段"}
    cands = [t for t in tokens if t not in stop]
    if not cands:
        cands = tokens
    scored = sorted(
        cands,
        key=lambda x: (_option_noise_score(x), abs(len(x) - 4), 0 if 2 <= len(x) <= 12 else 1),
    )
    if side == "left":
        return scored[-1] if len(scored) > 1 and _option_noise_score(scored[0]) > _option_noise_score(scored[-1]) else scored[0]
    return scored[0]


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
        ("制限", "制限"),
        ("画像生成", "画像生成の相性"),
        ("画像", "画像生成の相性"),
        ("表計算", "表計算/資料作成の相性"),
        ("資料作成", "表計算/資料作成の相性"),
        ("資料", "表計算/資料作成の相性"),
        ("料金", "料金"),
        ("課金", "料金"),
        ("待ち時間", "制限（回数/待ち/速度）"),
        ("回数制限", "制限（回数/待ち/速度）"),
        ("速度", "制限（回数/待ち/速度）"),
        ("頻度", "利用頻度"),
        ("検索程度", "利用頻度"),
        ("仕事", "仕事適性"),
        ("趣味", "趣味適性"),
        ("待ち", "制限"),
        ("継続性", "継続性"),
        ("治安", "治安"),
        ("夜移動", "移動リスク"),
        ("移動", "移動リスク"),
        ("医療", "医療アクセス"),
        ("情勢", "情勢変動"),
        ("健康", "健康効果"),
        ("栄養", "健康効果"),
        ("価格", "価格"),
        ("費用", "費用"),
        ("継続", "継続可能性"),
        ("期待リターン", "期待リターン"),
        ("リターン", "期待リターン"),
        ("流動性", "流動性"),
        ("換金", "流動性"),
        ("ボラ", "価格変動リスク"),
        ("変動", "価格変動リスク"),
        ("管理", "管理負担"),
        ("手間", "管理負担"),
        ("分散", "分散効果"),
        ("怪我", "怪我リスク"),
        ("テンション", "満足度"),
        ("気分", "満足度"),
        ("満足", "満足度"),
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
    if "週" in t and "時間" in t:
        m.append("利用時間")
    if "仕事" in t:
        m.append("仕事比率")
    if "治安" in t:
        m.append("安全度")
    if "夜移動" in t:
        m.append("夜間移動リスク")
    if "運用期間" in t or "長期" in t or "中期" in t or "短期" in t:
        m.append("運用期間")
    if "レバ" in t:
        m.append("レバレッジ可否")
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
    options, quality = _extract_options_nway(q)
    ok = len(options) >= 2
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
    if not ok:
        missing_fields.append("options_list")
    if domain_conf < 0.55:
        missing_fields.extend(["goal_metric", "priority_axis"])
    elif domain == "travel_safety":
        if not any(k in (q or "") for k in ("都市", "市", "地域")):
            missing_fields.append("city")
        if not any(k in (q or "") for k in ("夜移動", "夜", "深夜")):
            missing_fields.append("night_move")
    elif domain == "subscription_pricing":
        if not any(k in (q or "") for k in ("予算", "上限", "課金", "円", "万円")):
            missing_fields.append("budget_cap")
        if not any(k in (q or "") for k in ("仕事", "業務", "収益")):
            missing_fields.append("work_ratio")
    elif domain == "ai_tool_subscription_compare":
        if not any(k in (q or "") for k in ("画像", "画像生成", "表計算", "資料作成")):
            missing_fields.append("task_mix")
        if not any(k in (q or "") for k in ("頻度", "毎日", "週", "時間", "検索程度")):
            missing_fields.append("usage_frequency")
    elif domain == "asset_allocation":
        if not any(k in (q or "") for k in ("短期", "中期", "長期", "運用期間", "年")):
            missing_fields.append("operation_horizon")
        if not any(k in (q or "") for k in ("レバ", "借入", "信用", "レバレッジ")):
            missing_fields.append("leverage_allowed")
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
        "options": options,
        "option_count": len(options),
        "option_quality": quality,
        "axes": user_axes,
        "metrics": metrics,
        "constraints": constraints,
        "horizon": {"type": "long" if long_horizon else "normal", "year": year},
        "domain": domain,
        "domain_guess": {"name": domain, "confidence": domain_conf},
        "missing_fields": missing_fields,
    }


def _asset_horizon_bucket(q: str) -> str:
    t = (q or "")
    if any(k in t for k in ("〜3年", "~3年", "3年以内", "短期")):
        return "short"
    if any(k in t for k in ("3–10年", "3-10年", "中期")):
        return "mid"
    if any(k in t for k in ("10年以上", "長期")):
        return "long"
    return ""


def _asset_usage_bucket(q: str) -> str:
    t = (q or "")
    if any(k in t for k in ("住む", "居住", "自分で住")):
        return "live"
    if any(k in t for k in ("貸す", "賃貸", "家賃収入")):
        return "rent"
    if "未定" in t:
        return "undecided"
    return ""


def _preflight_check(q: str, canonical: dict) -> dict:
    domain = str(canonical.get("domain") or "general")
    options = list(canonical.get("options") or [])
    option_quality = float(canonical.get("option_quality") or 0.0)
    domain_conf = float((canonical.get("domain_guess") or {}).get("confidence") or 0.0)
    missing: list[str] = []

    options_ok = len(options) >= 2 and option_quality >= 0.55
    if not options_ok:
        missing.append("選択肢の定義（2案を短く）")
    if domain_conf < 0.55:
        missing.append("比較ドメインの確定")
    required_fields: list[str] = []
    satisfied_fields: list[str] = []
    missing_fields_ids: list[str] = []
    need_k = 1
    questions: list[dict] = []
    unlock_when_text = "必須前提を1つ固定すると深掘り可能"

    t = (q or "")
    if domain == "asset_allocation":
        required_fields = ["horizon", "priority_axis"]
        need_k = 2
        questions = [
            {"field": "horizon", "type": "choice", "label": "投資期間", "choices": ["〜3年", "3–10年", "10年以上"]},
            {"field": "use", "type": "choice", "label": "用途", "choices": ["住む", "貸す", "未定"]},
            {"field": "priority_axis", "type": "choice", "label": "最優先軸", "choices": ["リスク最小", "リターン最大", "流動性", "手間最小"]},
        ]
        has_horizon = bool(_asset_horizon_bucket(t))
        has_usage = bool(_asset_usage_bucket(t))
        if has_horizon:
            satisfied_fields.append("horizon")
        if has_usage:
            satisfied_fields.append("use_case")
        if any(k in t for k in ("リスク", "最大損失", "損失", "下振れ")):
            satisfied_fields.append("priority_axis")
        if not has_horizon:
            missing.append("運用期間（〜3年 / 3–10年 / 10年以上）")
            missing_fields_ids.append("horizon")
        if not has_usage:
            missing.append("用途（住む/貸す/未定）")
            missing_fields_ids.append("use")
        if "priority_axis" not in satisfied_fields:
            missing_fields_ids.append("priority_axis")
        unlock_when_text = "投資期間を選ぶと深掘り可能（〜3年/3–10年/10年以上）"
    elif domain == "leisure":
        required_fields = ["priority_axis"]
        need_k = 1
        questions = [
            {"field": "priority_axis", "type": "choice", "label": "優先軸", "choices": ["没入", "気楽さ", "予算", "混雑回避", "移動負荷"]},
        ]
        has_axis = any(k in t for k in ("没入", "気楽", "予算", "混雑", "移動"))
        if has_axis:
            satisfied_fields.append("priority_axis")
        if not has_axis:
            missing.append("優先軸（没入/気楽さ/予算 など）")
            missing_fields_ids.append("priority_axis")
        unlock_when_text = "優先軸を1つ選ぶと深掘り可能（没入/気楽さ/予算）"
    elif domain == "ai_tool_subscription_compare":
        required_fields = ["task_mix_ratio"]
        need_k = 1
        questions = [
            {"field": "task_mix_ratio", "type": "choice", "label": "主用途比率", "choices": ["画像寄り", "半々", "表計算寄り"]},
        ]
        has_usage_ratio = ("比率" in t) or (("画像" in t) and ("表計算" in t or "資料作成" in t))
        if has_usage_ratio:
            satisfied_fields.append("task_mix_ratio")
        if not has_usage_ratio:
            missing.append("主用途比率（画像寄り/半々/表計算寄り）")
            missing_fields_ids.append("task_mix_ratio")
        unlock_when_text = "主用途比率を選ぶと深掘り可能（画像寄り/半々/表計算寄り）"

    missing_top2 = missing[:2]
    next_q = "最重要な判断軸を1つ指定してください。"
    next_choices: list[str] = []
    if domain == "asset_allocation":
        if any("運用期間" in m for m in missing_top2):
            next_q = "投資期間は？（〜3年 / 3–10年 / 10年以上）"
            next_choices = ["〜3年", "3–10年", "10年以上"]
        elif any("用途" in m for m in missing_top2):
            next_q = "用途は？（住む/貸す/未定）"
            next_choices = ["住む", "貸す", "未定"]
        else:
            next_choices = ["〜3年", "3–10年", "10年以上"]
    elif domain == "leisure":
        next_q = "今日は没入（映画館）と気楽さ（家）のどちらを優先しますか？（二択）"
        next_choices = ["没入", "気楽さ"]
    elif domain == "ai_tool_subscription_compare":
        next_q = "画像生成 : 表計算（/資料作成）の比率は？（画像寄り / 半々 / 表計算寄り）"
        next_choices = ["画像寄り", "半々", "表計算寄り"]

    required_satisfied = 0
    for rf in required_fields:
        if rf in satisfied_fields:
            required_satisfied += 1
    sufficient = required_satisfied >= max(1, int(need_k))
    cap_split = 55 if (not sufficient and domain == "asset_allocation") else 70
    return {
        "sufficient": sufficient,
        "missing_top2": missing_top2,
        "missing_fields": missing_fields_ids,
        "next_question": next_q,
        "next_choices": next_choices[:3],
        "required_fields": required_fields,
        "satisfied_fields": satisfied_fields,
        "need_k": int(need_k),
        "questions": questions,
        "unlock_when_text": unlock_when_text,
        "cap_split": cap_split,
    }


def _build_need_info_after(q: str, canonical: dict, preflight: dict) -> str:
    options = [str(o.get("label") or "").strip() for o in list(canonical.get("options") or []) if str(o.get("label") or "").strip()]
    if len(options) < 2:
        options = ["候補A", "候補B"]
    options = options[:5]
    domain = str(canonical.get("domain") or "general")
    axes = _prior_axes(domain)[:5]
    facts = _facts3_from_q(q)
    missing_top2 = list(preflight.get("missing_top2") or [])[:2]
    next_q = str(preflight.get("next_question") or "最重要な判断軸を1つ指定してください。")
    next_choices = [str(x).strip() for x in list(preflight.get("next_choices") or []) if str(x).strip()][:3]
    unlock_when = str(preflight.get("unlock_when_text") or "必須前提を1つ固定すると深掘り可能")
    split_top = int(min(55, max(50, int(preflight.get("cap_split") or 55))))
    split_runner = 100 - split_top
    a = options[0]
    b = options[1]
    lines = [
        "OPTIONS:",
        *[f"- {o}" for o in options],
        "MODE: NEED_INFO",
        "CALL: NEED_INFO",
        "LEAN: ほぼ同等（暫定）",
        f"ALT: {b}",
        f"LEAN_SPLIT: {a} {split_top} / {b} {split_runner}",
        "WHY: 前提未固定のため、暫定判定のみ提示",
        f"STABILITY: {40 if domain == 'asset_allocation' else 45}",
        "RESOLUTION: low",
        "ΔSCORE: +0",
        "AXES:",
        *[f"- {ax}" for ax in axes],
        "SCORECARD:",
        *[f"- {ax}: {a}=2 {b}=2" for ax in axes[:3]],
        "FACTS_3:",
        f"- {facts[0]}",
        f"- {facts[1]}",
        f"- {facts[2]}",
        "MISSING_TOP2:",
        *([f"- {m}" for m in missing_top2] if missing_top2 else ["- 追加情報なし"]),
        "FLIP:",
        "- 前提条件（期間/用途/優先軸）が固定されると傾きが反転し得る",
        "FALSIFIER:",
        "- 追加情報で主要軸が逆転した場合に再判定",
        "NEXT:",
        f"- {next_q}",
        "CHOICES:",
        *([f"- {c}" for c in next_choices] if next_choices else ["- なし"]),
        "UNLOCK_WHEN:",
        f"- {unlock_when}",
        "OUTCOME: Need_Info",
    ]
    return "\n".join(lines) + "\n"


def _prior_axes(domain: str) -> list[str]:
    return list(get_domain_spec(domain).get("axes_candidates", ["コスト", "リスク", "柔軟性"]))[:5]


def _next_hint_from_missing(domain: str, missing_fields: list[str], q: str = "") -> str:
    spec = get_domain_spec(domain)
    if domain == "subscription_pricing":
        # Keep pricing NEXT to one fixed question to tighten loop.
        return "仕事利用比率は何%ですか？（0/30/70/100 のどれに近いか）"
    if domain == "leisure":
        return "今日は没入（映画館）と気楽さ（家）のどちらを優先しますか？（二択）"
    if domain == "travel_safety":
        return "行く都市はどこですか？（例: シェムリアップ/プノンペン/ルアンパバーン/ビエンチャン）"
    if domain == "ai_tool_subscription_compare":
        return "画像生成 : 表計算（/資料作成）の比率は？（画像寄り / 半々 / 表計算寄り）"
    if domain == "asset_allocation":
        if "operation_horizon" in missing_fields:
            return "投資期間は？（〜3年 / 3–10年 / 10年以上）"
        if "leverage_allowed" in missing_fields:
            return "レバレッジを許容しますか？（可/不可）"
        return "投資期間は？（〜3年 / 3–10年 / 10年以上）"
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
            return "目的指標（血糖/体重/体調（コンディション）など）を1つ選択"
    if domain == "subscription_pricing":
        if "budget_cap" in missing_fields:
            return "予算上限を1つ指定してください（例: 月額3,000円）"
        if "work_ratio" in missing_fields:
            return "仕事利用の比率（%）を指定してください"
    if domain == "travel_safety":
        if "city" in missing_fields or "night_move" in missing_fields:
            return "行く都市（候補）と夜移動の有無を1行で指定してください"
    return "目的指標を1つ固定し、再判定条件を明確化"


def _falsifier_line(domain: str, a_label: str, b_label: str, side: str) -> str:
    spec = get_domain_spec(domain)
    templates = list(spec.get("falsifier_templates", []))
    if templates:
        t = templates[0].replace("A", a_label).replace("B", b_label)
        return t
    opp = b_label if side == "A" else a_label
    return f"{opp} 側の第三者検証データで主要軸が優位化した場合に結論を反転"


def _why_top2(domain: str, axes: list[str], top_label: str, q: str) -> str:
    if domain == "subscription_pricing":
        has_work = any(k in (q or "") for k in ("仕事", "業務", "収益"))
        has_hours = bool(re.search(r"週\s*\d+\s*時間", q or ""))
        has_budget = any(k in (q or "") for k in ("予算", "上限", "課金", "円", "万円"))
        l1 = f"1) 回数制限・待ち時間の面で {top_label} が無料より安定"
        l2 = f"2) 仕事影響を考えると {top_label} はProより費用対効果が高い"
        if has_budget:
            l2 = f"2) 予算制約を踏まえると {top_label} はProより費用対効果が高い"
        elif not has_work and not has_hours:
            l2 = f"2) 待ち時間と予算のバランスで {top_label} が中位プランとして妥当"
        return f"{l1} {l2}"
    if domain == "leisure":
        return f"1) 没入感と気楽さのバランスで {top_label} に傾く 2) 混雑耐性/移動負荷/予算の優先で傾きが変わる"
    if domain == "travel_safety":
        solo = ("一人" in (q or "")) or ("一人旅" in (q or ""))
        soon = any(k in (q or "") for k in ("来月", "今月", "来週"))
        cost = any(k in (q or "") for k in ("費用", "予算", "安く"))
        cond = "一人旅" if solo else "滞在条件"
        time_cond = "来月" if soon else "渡航時期"
        cost_cond = "費用重視" if cost else "予算条件"
        return f"1) {cond}+{time_cond}+{cost_cond} では都市/夜移動でリスク差が拡大 2) 国名より都市条件の差が順位を決める"
    if domain == "ai_tool_subscription_compare":
        return (
            f"1) 画像生成と表計算/資料作成の相性で {top_label} が上位 "
            f"2) 料金・制限（回数/待ち/速度）と利用頻度のバランスで差が付く"
        )
    if domain == "asset_allocation":
        return (
            f"1) 期待リターンと価格変動リスクのバランスで {top_label} に傾く "
            f"2) 流動性・管理負担・分散効果の差で順位が分かれる"
        )
    a0 = axes[0] if axes else "主要軸"
    a1 = axes[min(1, len(axes) - 1)] if axes else "補助軸"
    return f"1) {a0} で {top_label} が優位 2) {a1} で差が出る"


def _why_loser(domain: str, top_label: str, loser_label: str, q: str) -> str:
    if domain == "subscription_pricing":
        if ("pro" in loser_label.lower()) or ("プロ" in loser_label):
            return f"{loser_label} は高負荷の仕事比率が高い場合に上振れするが、現入力では {top_label} で十分"
        if ("free" in loser_label.lower()) or ("無料" in loser_label):
            return f"{loser_label} はコスト優位だが、回数制限・待ち時間で {top_label} に劣後"
    if domain == "leisure":
        return f"{loser_label} は没入/気楽さ/移動負荷の優先次第で、現条件では {top_label} より傾きが弱い"
    if domain == "travel_safety":
        return f"{loser_label} は都市と夜移動条件が不利ならリスクが上振れし、{top_label} より下位化する"
    if domain == "ai_tool_subscription_compare":
        return f"{loser_label} は画像生成/表計算の主要用途か制限条件が合わない場合に、{top_label} へ劣後する"
    if domain == "asset_allocation":
        return f"{loser_label} は流動性・価格変動リスク・管理負担の条件が不利な場合、{top_label} より傾きが弱くなる"
    return f"{loser_label} は主要軸の合計で {top_label} に届かず下位化"


def _options_quality(options: list[dict], q: str) -> float:
    if len(options) < 2:
        return 0.0
    score = 1.0
    t = " ".join((q or "").split())
    for o in options[:5]:
        s = str(o.get("label") or "")
        if not s:
            score -= 0.4
            continue
        if len(s) > 24:
            score -= 0.2
        if re.search(r"(どっち|どちら|と思う|方がいい|のか|べき|[?？])", s):
            score -= 0.3
        if len(s) >= max(14, int(len(t) * 0.65)):
            score -= 0.25
    return max(0.0, min(1.0, score))


def _looks_action_phrase(s: str) -> bool:
    t = str(s or "").strip()
    if not t:
        return False
    if re.search(r"(する|買う|売る|積立|運用|保有|賃貸に出す|貸す|投資)$", t):
        return True
    if "を" in t and re.search(r"(する|積立|運用|保有|購入|売却|賃貸|貸し)", t):
        return True
    return False


def _normalize_action_phrase(raw: str) -> str:
    s = _clean_option_label(raw)
    s = re.sub(r"^(投資として|資産配分として|運用として)\s*", "", s)
    s = re.sub(r"^[0-9０-９,，]+(?:万|億)?円で\s*", "", s)
    s = re.sub(r"^(約|およそ)\s*[0-9０-９,，]+(?:万|億)?円で\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[\s:：\-・,、]+|[\s:：\-・,、?？。]+$", "", s)
    return s


def _extract_options_nway(q: str, max_options: int = 5) -> tuple[list[dict], float]:
    t = " ".join((q or "").split())
    domain = _detect_domain(t)
    options: list[dict] = []
    low = t.lower()

    # Tool-family compare: GPT vs Gemini
    if (("gpt" in low) or ("chatgpt" in low)) and ("gemini" in low):
        return (
            [
                {"id": "gpt", "label": "GPT"},
                {"id": "gemini", "label": "Gemini"},
            ],
            0.95,
        )

    # Explicit pricing/subscription names.
    if any(k in low for k in ("free", "plus", "pro")) or any(k in t for k in ("無料", "プラス", "プロ")):
        plan_map = [("free", ["free", "無料"]), ("plus", ["plus", "プラス"]), ("pro", ["pro", "プロ"])]
        for oid, keys in plan_map:
            if any(k in low for k in [x.lower() for x in keys]) or any(k in t for k in keys):
                label = {"free": "無料", "plus": "Plus", "pro": "Pro"}[oid]
                options.append({"id": oid, "label": label})
        if len(options) >= 2:
            return options[:max_options], 0.95

    if domain == "education_career" and any(k in t for k in ("大学", "進学")) and any(k in t for k in ("専門", "スキル", "実務", "資格")):
        return ([
            {"id": "a", "label": "大学進学（学歴ルート）"},
            {"id": "b", "label": "専門スキル直行（実務→就職）"},
        ], 0.95)

    # Leisure short normalization: movie theater vs home rental.
    if any(k in t for k in ("映画館", "劇場")) and any(k in t for k in ("家", "自宅", "レンタル", "配信")):
        return ([
            {"id": "a", "label": "映画館"},
            {"id": "b", "label": "家レンタル"},
        ], 0.95)

    if domain in ("investing", "asset_allocation"):
        action_patterns = [
            r"([^\n。！？]{3,72})か[、,\s]*([^\n。！？]{3,72})か",
            r"([^\n。！？]{3,72})と([^\n。！？]{3,72})(?:どっち|どちら|比較)",
            r"([^\n。！？]{3,72})\s+or\s+([^\n。！？]{3,72})",
        ]
        for pat in action_patterns:
            m = re.search(pat, t, flags=re.IGNORECASE)
            if not m:
                continue
            left = _normalize_action_phrase(m.group(1))
            right = _normalize_action_phrase(m.group(2))
            if not (_looks_action_phrase(left) and _looks_action_phrase(right)):
                continue
            if left == right:
                continue
            return ([{"id": "a", "label": left}, {"id": "b", "label": right}], 0.9)

    # JP binary-island extraction (prefer local candidate island over long preface)
    island_patterns = [
        r"([^\n。！？]{1,24})か[、,\s]*([^\n。！？]{1,24})(?:か|$)",
        r"([^\n。！？]{1,24})と([^\n。！？]{1,24})(?:どっち|どちら)",
        r"([^\n。！？]{1,24})\s+or\s+([^\n。！？]{1,24})",
    ]
    for pat in island_patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if not m:
            continue
        left = _clean_option_label(_pick_short_jp_token(m.group(1), "left"))
        right = _clean_option_label(_pick_short_jp_token(m.group(2), "right"))
        opts = []
        if left:
            opts.append({"id": "a", "label": left})
        if right and right != left:
            opts.append({"id": "b", "label": right})
        if len(opts) >= 2:
            return opts[:max_options], _options_quality(opts, q)

    # Compact binary form: derive tail/head tokens around "と" for prompts like
    # "...カンボジアとラオスを比較..." / "...横浜と鎌倉どちら..."
    m_compact = re.search(r"(.+?)\s*と\s*(.+?)(どちら|どっち|を比較|比較)", t)
    if m_compact:
        left_raw = m_compact.group(1)
        right_raw = m_compact.group(2)
        kw = [str(k) for k in get_domain_spec(domain).get("keywords", []) if len(str(k)) >= 2]
        left_hits = [(left_raw.rfind(k), k) for k in kw if k and k in left_raw]
        right_hits = [(right_raw.find(k), k) for k in kw if k and k in right_raw]
        left_kw = sorted(left_hits, key=lambda x: x[0], reverse=True)[0][1] if left_hits else ""
        right_kw = sorted(right_hits, key=lambda x: x[0])[0][1] if right_hits else ""
        left_tokens = re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ンー]+", left_raw)
        right_tokens = re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ンー]+", right_raw)
        a = _clean_option_label(left_kw or (left_tokens[-1] if left_tokens else left_raw))
        b = _clean_option_label(right_kw or (right_tokens[0] if right_tokens else right_raw))
        opts = []
        if a:
            opts.append({"id": "a", "label": a})
        if b and b != a:
            opts.append({"id": "b", "label": b})
        if len(opts) >= 2:
            return opts[:max_options], _options_quality(opts, q)

    # Generic split by conjunction-like separators.
    seps = ["と", "、", ",", "/", " vs ", " VS ", " or ", "または", "か"]
    candidates: list[str] = [t]
    for sep in seps:
        if sep in t:
            pieces = [p.strip() for p in t.split(sep) if p.strip()]
            if len(pieces) >= 2 and len(pieces) <= max_options and all(len(p) <= 24 for p in pieces):
                candidates = pieces
                break
    for c in candidates:
        label = _clean_option_label(c)
        if not label:
            continue
        if label in [str(o.get("label")) for o in options]:
            continue
        options.append({"id": f"o{len(options)+1}", "label": label})
        if len(options) >= max_options:
            break

    # Pattern fallback for binary phrasing.
    if len(options) < 2:
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
            opts = []
            if a:
                opts.append({"id": "a", "label": a})
            if b and b != a:
                opts.append({"id": "b", "label": b})
            if len(opts) >= 2:
                options = opts
                break
    quality = _options_quality(options, q)
    if domain in ("investing", "asset_allocation") and len(options) >= 2:
        acts = [o for o in options if _looks_action_phrase(str(o.get("label") or ""))]
        if len(acts) < 2:
            return [], 0.2
    return options[:max_options], quality


def _extract_ab_options(q: str) -> tuple[str, str, bool, float]:
    options, quality = _extract_options_nway(q, max_options=2)
    if len(options) < 2:
        return "", "", False, quality
    a = str(options[0].get("label") or "")
    b = str(options[1].get("label") or "")
    return a, b, (quality >= 0.55), quality


def _infer_axes(q: str) -> list[str]:
    t = (q or "")
    domain = _detect_domain(t)
    if domain == "education_career":
        return ["初期コスト", "回収期間", "就職確率", "AI代替耐性", "柔軟性"]
    if domain == "sports":
        return ["怪我リスク", "費用", "継続可能性"]
    if domain == "food":
        return ["健康効果", "価格", "継続可能性"]
    if domain == "asset_allocation":
        return ["期待リターン", "流動性", "価格変動リスク", "管理負担", "分散効果"]
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
    if any(k in t for k in ("2030", "2035", "2040", "将来", "今後", "長期")):
        return True
    return any(k in q_l for k in ("future", "long-term", "uncertainty"))


def _has_external_evidence(q: str) -> bool:
    t = (q or "")
    return any(k in t for k in ("外務省", "渡航情報", "統計", "犯罪率", "公式", "最新データ", "レポート"))


def _has_explicit_goal(q: str) -> bool:
    t = (q or "")
    return any(k in t for k in ("目的", "効果", "就職", "年収", "収入", "健康", "コスト", "料金", "画像生成", "表計算", "リスク", "合格", "勝率", "仕事", "趣味", "週", "時間", "頻度", "安全", "治安", "テンション", "気分", "満足", "投資", "運用", "分散", "レバ"))


def _facts3_from_q(q: str) -> list[str]:
    t = " ".join((q or "").split())
    domain = _detect_domain(t)
    low = t.lower()
    if domain == "ai_tool_subscription_compare":
        facts_ai: list[str] = []
        if any(k in t for k in ("全体記憶", "長期", "OS", "育て")):
            facts_ai.append("方針=全体記憶を重視した長期OS育成")
        if "画像" in t and ("表計算" in t or "資料作成" in t):
            facts_ai.append("用途=画像生成+表計算/資料作成")
        elif "画像" in t:
            facts_ai.append("用途=画像生成")
        elif "表計算" in t or "資料作成" in t:
            facts_ai.append("用途=表計算/資料作成")
        if "検索程度" in t or "あまり使わない" in t:
            facts_ai.append("頻度=検索程度（低頻度）")
        elif "週" in t and "時間" in t:
            m_hours = re.search(r"週\s*([0-9０-９]+)\s*時間", t)
            if m_hours:
                facts_ai.append(f"頻度=週{m_hours.group(1)}時間")
        if ("gpt" in low or "chatgpt" in low) and ("gemini" in low):
            facts_ai.append("比較対象=GPT/Gemini")
        if "料金" in t or "課金" in t:
            facts_ai.append("論点=料金")
        if "制限" in t or "待ち" in t:
            facts_ai.append("論点=制限")
        dedup_ai: list[str] = []
        for f in facts_ai:
            if f not in dedup_ai:
                dedup_ai.append(f)
        while len(dedup_ai) < 3:
            if "比較対象=GPT/Gemini" not in dedup_ai:
                dedup_ai.append("比較対象=GPT/Gemini")
            elif "用途=画像生成+表計算/資料作成" not in dedup_ai:
                dedup_ai.append("用途=画像生成+表計算/資料作成")
            else:
                dedup_ai.append("頻度=要確認")
        return dedup_ai[:3]

    facts: list[str] = []
    m_pref = re.search(r"^(.{0,40}?)[。.!！?？]\s*[^。!?！？]{1,24}(?:か|と).{0,24}(?:どっち|どちら|か)", t)
    if m_pref:
        pre = m_pref.group(1).strip(" 、,")
        if pre and len(pre) >= 4:
            facts.append(f"状況={pre}")
    m_pair = re.search(r"(.+?)と(.+?)(どちら|どっち)", t)
    if m_pair:
        p1 = _clean_option_label(m_pair.group(1))
        p2 = _clean_option_label(m_pair.group(2))
        if p1 and p2 and p1 != p2:
            facts.append(f"比較対象={p1}/{p2}")
    if "野球" in t and "サッカー" in t:
        facts.append("比較対象=野球/サッカー")
    m_hours = re.search(r"週\s*([0-9０-９]+)\s*時間", t)
    if m_hours:
        facts.append(f"利用時間=週{m_hours.group(1)}時間")
    m_period = re.search(r"(\d+\s*年)", t)
    if m_period:
        facts.append(f"期間={m_period.group(1)}")
    m_year = re.search(r"(20\d{2})", t)
    if m_year:
        facts.append(f"対象年={m_year.group(1)}")
    if "来月" in t:
        facts.append("時期=来月")
    if "一人" in t:
        facts.append("同行条件=一人")
    if "神奈川" in t:
        facts.append("居住地=神奈川")
    if "横浜" in t:
        facts.append("候補=横浜")
    if "鎌倉" in t:
        facts.append("候補=鎌倉")
    if "仕事" in t and "趣味" in t:
        facts.append("用途=仕事+趣味")
    elif "仕事" in t:
        facts.append("用途=仕事")
    elif "趣味" in t:
        facts.append("用途=趣味")
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
    if "検索程度" in t:
        facts.append("頻度=検索程度")
    if "画像" in t:
        facts.append("用途=画像生成")
    if "表計算" in t or "資料作成" in t:
        facts.append("用途=表計算/資料作成")
    if "料金" in t or "課金" in t:
        facts.append("論点=料金")
    if "制限" in t or "待ち" in t:
        facts.append("論点=制限")
    if "費用" in t:
        facts.append("論点=費用")
    if "投資として" in t:
        facts.append("文脈=投資として比較")
    m_money = re.search(r"([0-9０-９,，]+(?:万|億)?円)", t)
    if m_money:
        facts.append(f"資金規模={m_money.group(1)}")
    if "移動時間" in t or "移動" in t:
        facts.append("論点=移動時間")
    if "効果" in t:
        facts.append("目的=効果比較")
    if domain == "leisure":
        if "リラックス" in t:
            facts.append("目的=リラックス")
        if "一人" in t:
            facts.append("滞在形態=単独")
    if domain == "ai_tool_subscription_compare":
        if "gpt" in t.lower() or "chatgpt" in t.lower():
            facts.append("比較対象=GPT")
        if "gemini" in t.lower():
            facts.append("比較対象=Gemini")
    if len(facts) < 3:
        opts, _ = _extract_options_nway(q, max_options=5)
        labels = [str(o.get("label") or "").strip() for o in opts if str(o.get("label") or "").strip()]
        if labels:
            facts.append(f"候補数={len(labels)}")
            if len(labels) >= 2:
                facts.append(f"比較対象={labels[0]}/{labels[1]}")
    if not facts:
        facts.append("比較形式=二択")
    dedup: list[str] = []
    for f in facts:
        if f not in dedup:
            dedup.append(f)
    facts = dedup
    fillers = ["比較形式=二択", "評価条件=要確認", "追加条件=未入力"]
    i = 0
    while len(facts) < 3:
        add = fillers[i % len(fillers)]
        if add not in facts:
            facts.append(add)
        i += 1
    return facts[:3]


def _build_v2_after(
    q: str,
    recommend_side: str,
    dscore: int,
    outcome: str,
    missing: list[str] | None = None,
) -> str:
    c = _canonicalize_question(q)
    preflight = _preflight_check(q, c)
    options = list(c.get("options") or [])
    option_count = int(c.get("option_count") or len(options))
    option_quality = float(c.get("option_quality") or 0.0)
    ok = option_count >= 2
    domain = str(c["domain"])
    domain_conf = float((c.get("domain_guess") or {}).get("confidence") or 0.0)
    user_axes = list(c.get("axes") or [])
    prior_axes = _prior_axes(domain)
    axes = user_axes[:]
    for ax in prior_axes:
        if ax not in axes:
            axes.append(ax)
        if len(axes) >= 5:
            break
    long_horizon = str((c.get("horizon") or {}).get("type") or "") == "long"
    goal_defined = _has_explicit_goal(q)
    decision_context_ok = goal_defined or (
        domain == "subscription_pricing" and option_count >= 3 and any(k in q for k in ("仕事", "趣味", "週", "時間"))
    ) or (
        domain == "ai_tool_subscription_compare" and option_count >= 2 and any(k in q for k in ("画像", "画像生成", "表計算", "資料作成", "料金", "頻度", "検索程度"))
    ) or (
        domain == "asset_allocation" and option_count >= 2 and bool(_asset_horizon_bucket(q))
    ) or (
        domain == "travel_safety" and option_count >= 2 and any(k in q for k in ("来月", "一人", "費用", "安全", "治安"))
    )
    missing_fields = list(c.get("missing_fields") or [])
    if not ok or option_quality < 0.55:
        fallback_axes = _prior_axes(domain)
        fallback_facts = _facts3_from_q(q)
        fallback_scores = "\n".join([f"- {ax}: 候補指定後に採点" for ax in fallback_axes[:3]])
        listed = "\n".join([f"- {str(o.get('label') or '').strip()}" for o in options if str(o.get("label") or "").strip()])
        if not listed:
            listed = "- 候補を箇条書きで指定してください（最大5）"
        return (
            "OPTIONS:\n"
            + listed + "\n"
            "MODE: HOLD\n"
            "CALL: HOLD\n"
            "LEAN: ほぼ同等\n"
            "ALT: 候補確定後に提示\n"
            "LEAN_SPLIT: 候補A 50 / 候補B 50\n"
            "WHY_TOP2: 1) 選択肢定義が未確定 2) 評価軸は仮置き（候補確定後に再採点）\n"
            "WHY_GAP: 情報不足のため比較差分は未確定\n"
            "STABILITY: 25\n"
            "RESOLUTION: low\n"
            f"ΔSCORE: {int(dscore):+d}\n"
            "AXES:\n"
            + "\n".join([f"- {ax}" for ax in fallback_axes[:3]]) + "\n"
            + "SCORECARD:\n"
            + fallback_scores + "\n"
            + "FACTS_3:\n"
            + f"- {fallback_facts[0]}\n- {fallback_facts[1]}\n- {fallback_facts[2]}\n"
            + "FLIP:\n- 選択肢定義が確定したら傾きが反転し得る\n"
            + "FALSIFIER:\n- 選択肢定義が確定し次第、結論を再計算\n"
            "NEXT:\n"
            "- 候補を箇条書きで指定してください（最大5）\n"
            f"OUTCOME: {outcome}\n"
        )

    plan_options = [str(o.get("label") or "").strip() for o in options if str(o.get("label") or "").strip()]
    option_ids = [str(o.get("id") or f"o{i+1}") for i, o in enumerate(options[:5])]
    plan_options = plan_options[:5]
    option_ids = option_ids[: len(plan_options)]
    options_map = {option_ids[i]: plan_options[i] for i in range(len(plan_options))}

    def _is_pricing_triplet(labels: list[str]) -> bool:
        s = " ".join(labels).lower()
        return ("free" in s or "無料" in s) and ("plus" in s or "プラス" in s) and ("pro" in s or "プロ" in s)

    def _score_axis_option(axis: str, oid: str, label: str, idx: int, n: int) -> int:
        ll = label.lower()
        is_free = ("free" in ll) or ("無料" in label)
        is_plus = "plus" in ll or "プラス" in label
        is_pro = "pro" in ll or "プロ" in label
        if _is_pricing_triplet(plan_options):
            if axis in ("コスト", "初期コスト", "費用", "総コスト", "価格"):
                if is_free:
                    return 5
                if is_plus:
                    return 3
                if is_pro:
                    return 1
            if axis in ("制限", "仕事適性", "期待リターン"):
                if is_pro:
                    return 5
                if is_plus:
                    return 4
                if is_free:
                    return 2
            if axis in ("趣味適性", "継続性", "継続可能性"):
                if is_plus:
                    return 5
                if is_pro:
                    return 4
                if is_free:
                    return 3
        # generic fallback by rank position
        if axis in ("コスト", "初期コスト", "費用", "総コスト", "価格"):
            return max(1, 5 - idx)
        return max(1, 5 - abs(idx - min(1, n - 1)))

    scores: dict[str, dict[str, int]] = {}
    unknown_count = 0
    for ax in axes:
        if ax not in prior_axes and ax not in _prior_axes(domain):
            unknown_count += 1
        scores[ax] = {}
        for i, oid in enumerate(option_ids):
            base = _score_axis_option(ax, oid, options_map[oid], i, len(option_ids))
            if "学費" in q and ax in ("初期コスト", "費用", "総コスト") and i > 0:
                base = min(5, base + 1)
            if "就職率" in q and ax == "就職確率" and i > 0:
                base = min(5, base + 1)
            if "AI" in q and ax in ("AI耐性", "AI代替耐性") and i == 0:
                base = min(5, base + 1)
            if "レバ" in q and ax == "最大損失" and ("レバ" in options_map[oid].lower() or "レバ" in options_map[oid]):
                base = max(1, base - 1)
            scores[ax][oid] = base

    totals = {oid: sum(scores[ax].get(oid, 0) for ax in axes[:5]) for oid in option_ids}
    ranked = sorted(option_ids, key=lambda oid: totals.get(oid, 0), reverse=True)
    top_id = ranked[0]
    runner_id = ranked[1] if len(ranked) > 1 else ranked[0]
    top_label = options_map[top_id]
    runner_label = options_map[runner_id]
    margin = max(0, totals.get(top_id, 0) - totals.get(runner_id, 0))
    is_partial = outcome.lower().startswith("partial")
    cap = 70 if is_partial else 80
    if long_horizon:
        cap = min(cap, 60)
    conf_raw = max(35, min(85, 55 + 8 * margin))
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
    if unknown_count > 0:
        evidence_completeness = max(0.45, evidence_completeness - 0.1 * min(2, unknown_count))
    axes_quality = 1.0 if len(axes) >= 3 else 0.6
    facts_quality = 1.0 if any("期間=" in f or "対象年=" in f or "論点=" in f or "比較対象=" in f for f in _facts3_from_q(q)) else 0.6
    external_evidence_needed = (domain == "travel_safety")
    has_external_evidence = _has_external_evidence(q)
    basis_ok = (option_quality >= 0.55 and axes_quality >= 0.6 and facts_quality >= 0.6)
    partial_penalty = 10 if is_partial else 0
    unknown_penalty = min(15, unknown_count * 5)
    domain_penalty = int(round(max(0.0, 0.7 - domain_conf) * 20))
    evidence_penalty = 12 if (external_evidence_needed and not has_external_evidence) else 0
    nway_penalty = max(0, option_count - 2) * 3
    adjusted = conf_raw - partial_penalty - unknown_penalty - domain_penalty - evidence_penalty - nway_penalty
    adjusted = adjusted + int(round((evidence_completeness - 0.5) * 20))
    low_floor = 40 if basis_ok else 30
    if long_horizon or unknown_count > 0 or option_quality < 0.7:
        low_floor = 30
    if domain_conf < 0.55:
        low_floor = 25
    if external_evidence_needed and not has_external_evidence:
        low_floor = max(25, low_floor - 5)
    confidence = int(max(low_floor, min(cap, adjusted)))
    likely_hold = (
        domain_conf < 0.55 or (long_horizon and margin <= 1) or (not decision_context_ok) or len(axes) < 2 or (not basis_ok)
    )
    force_conditional_binary = (option_count == 2 and option_quality >= 0.8 and goal_defined and len(axes) >= 2)
    if likely_hold:
        confidence = min(confidence, 55)
    facts = _facts3_from_q(q)
    if option_count >= 3:
        facts = [f for f in facts if "比較対象=2案" not in f]
        while len(facts) < 3:
            facts.append(f"候補数={option_count}")
        facts[2] = f"比較対象={','.join(plan_options[:3])}"
    miss_stage = ",".join(missing or []) if missing else "-"
    miss_fields = ",".join(missing_fields) if missing_fields else "-"
    lines = [
        "OPTIONS:",
    ]
    lines.extend([f"- {label}" for label in plan_options])
    if not plan_options:
        lines.append("- 候補を箇条書きで指定してください（最大5）")
    if force_conditional_binary:
        lines.append("MODE: CONDITIONAL")
    elif domain_conf < 0.55:
        lines.append("MODE: HOLD")
    elif external_evidence_needed and not has_external_evidence:
        lines.append("MODE: CONDITIONAL")
    elif long_horizon:
        lines.append("MODE: CONDITIONAL")
    else:
        lines.append("MODE: NORMAL")
    can_conditional_proceed = (
        option_quality >= 0.55 and len(axes) >= 3 and facts_quality >= 0.6 and decision_context_ok
    )
    travel_conditional_proceed = (
        domain == "travel_safety" and option_count >= 2 and len(axes) >= 3 and decision_context_ok
    )
    why_top2 = _why_top2(domain, axes, top_label, q)
    why_gap = f"1位と2位の合計差={margin}"
    loser_id = ranked[2] if len(ranked) >= 3 else (runner_id if len(ranked) >= 2 else "")
    why_loser = _why_loser(domain, top_label, options_map.get(loser_id, ""), q) if loser_id else ""
    lean_text = f"{top_label}寄り" if margin >= 2 else "ほぼ同等"
    if margin <= 0:
        split_top = 50
    else:
        split_delta = min(20, max(3, margin * 4))
        split_top = 50 + split_delta
    if domain == "asset_allocation":
        has_horizon = bool(_asset_horizon_bucket(q))
        has_usage = bool(_asset_usage_bucket(q))
        fixed_count = int(has_horizon) + int(has_usage)
        if has_horizon:
            horizon = _asset_horizon_bucket(q)
            if horizon == "short":
                split_top = max(split_top, 58)
            elif horizon == "mid":
                split_top = min(max(split_top, 52), 58)
            elif horizon == "long":
                split_top = max(split_top, 62)
        cap_dynamic = 55 if fixed_count == 0 else (65 if fixed_count == 1 else 70)
        split_top = min(split_top, cap_dynamic)
        split_top = max(100 - cap_dynamic, split_top)
    split_runner = 100 - split_top
    lines.append(f"LEAN: {lean_text}")
    lines.append(f"ALT: {runner_label}")
    lines.append(f"LEAN_SPLIT: {top_label} {split_top} / {runner_label} {split_runner}")

    if domain == "ai_tool_subscription_compare" and option_count >= 2:
        lines.append("CALL: PROCEED_WITH_CONDITIONS")
        lines.append(f"WHY_TOP2: {why_top2}")
        lines.append(f"WHY_GAP: {why_gap}（用途比率で反転余地）")
        if why_loser:
            lines.append(f"WHY_LOSER: {why_loser}")
    elif domain == "asset_allocation" and bool(_asset_horizon_bucket(q)):
        lines.append("CALL: PROCEED_WITH_CONDITIONS")
        lines.append(f"WHY_TOP2: {why_top2}")
        lines.append(f"WHY_GAP: {why_gap}（運用期間の前提で再計算）")
        if why_loser:
            lines.append(f"WHY_LOSER: {why_loser}")
    elif option_count == 2 and option_quality >= 0.8 and goal_defined and len(axes) >= 2:
        lines.append("CALL: PROCEED_WITH_CONDITIONS")
        lines.append(f"WHY_TOP2: {why_top2}")
        lines.append(f"WHY_GAP: {why_gap}")
        if why_loser:
            lines.append(f"WHY_LOSER: {why_loser}")
    elif domain_conf < 0.55 or len(axes) < 2:
        lines.append("CALL: HOLD")
        lines.append(f"WHY_TOP2: {why_top2}")
        lines.append(f"WHY_GAP: {why_gap}")
        if why_loser:
            lines.append(f"WHY_LOSER: {why_loser}")
    elif external_evidence_needed and not has_external_evidence and (can_conditional_proceed or travel_conditional_proceed):
        lines.append("CALL: PROCEED_WITH_CONDITIONS")
        lines.append(f"WHY_TOP2: {why_top2}")
        lines.append(f"WHY_GAP: {why_gap}（都市/夜移動条件で反転余地）")
        if why_loser:
            lines.append(f"WHY_LOSER: {why_loser}")
    elif (not basis_ok) or (long_horizon and margin <= 1) or (not decision_context_ok):
        lines.append("CALL: HOLD")
        lines.append(f"WHY_TOP2: {why_top2}")
        lines.append(f"WHY_GAP: {why_gap}")
        if why_loser:
            lines.append(f"WHY_LOSER: {why_loser}")
    else:
        lines.append("CALL: PROCEED")
        lines.append(f"WHY_TOP2: {why_top2}")
        lines.append(f"WHY_GAP: {why_gap}")
        if why_loser:
            lines.append(f"WHY_LOSER: {why_loser}")
    lines.append(f"GAP: {margin}")
    lines.extend(
        [
            f"STABILITY: {int(confidence)}",
            f"RESOLUTION: {'high' if margin >= 3 else ('medium' if margin >= 1 else 'low')}",
            f"ΔSCORE: {int(dscore):+d}",
            "AXES:",
        ]
    )
    lines.extend([f"- {ax}" for ax in axes[:5]])
    lines.append("SCORECARD:")
    for ax in axes[:5]:
        row = " ".join([f"{oid}={scores.get(ax, {}).get(oid, 2)}" for oid in option_ids])
        lines.append(f"- {ax}: {row}")
    lines.append("AXIS_WINNERS_3:")
    for ax in axes[:3]:
        winner = max(option_ids, key=lambda oid: scores.get(ax, {}).get(oid, 0))
        lines.append(f"- {ax}={winner}")
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
                f"- AI加速: {top_label} の優位が維持されるかを検証",
                f"- AI停滞: {runner_label} の中長期リターン再評価で逆転し得る",
            ]
        )
    if domain == "asset_allocation":
        lines.extend(
            [
                "VARIABLE_TREE:",
                "- 期待リターン: 値上がり / キャッシュフロー / 諸費用",
                "- 最大損失: 金利上昇 / 空室 / 流動性ディスカウント",
                "- レバレッジ効果: 借入可否と返済負担",
            ]
        )
    lines.extend(
        [
            "RULE:",
            "- 比率条件で暫定順位を採用し、反転条件を先に固定する",
            "FLIP:",
            f"- {_falsifier_line(domain, top_label, runner_label, 'A')}",
            "FALSIFIER:",
            f"- {_falsifier_line(domain, top_label, runner_label, 'A')}",
            "NEXT:",
            f"- {_next_hint_from_missing(domain, missing_fields, q)}",
            f"OUTCOME: {outcome}",
        ]
    )
    return "\n".join(lines) + "\n"


def _judgment_point_changes_from_after(after: str) -> list[str]:
    t = after or ""
    has_axes = ("AXES:" in t and "SCORECARD:" in t)
    has_falsifier = ("FALSIFIER:" in t)
    has_next = ("NEXT:" in t)
    c1 = "比較軸を宣言し、候補を軸採点で可視化した（入力文脈に合わせて推定）。" if has_axes else "比較軸を固定し、候補判定の根拠を数値化した。"
    c2 = "反転条件（FALSIFIER）を定義し、結論が変わる条件を明確化した。" if has_falsifier else "反転条件を定義し、再判定トリガーを明確化した。"
    c3 = "次の一手（NEXT）を“取得データ/期限/閾値”で固定した。" if has_next else "次の一手を具体化し、追加データ収集の方向を固定した。"
    return [c1, c2, c3]


def _stepa_prompt_v2(q: str) -> str:
    c = _canonicalize_question(q)
    options = list(c.get("options") or [])
    ok = (int(c.get("option_count") or len(options)) >= 2)
    quality = float(c.get("option_quality") or 0.0)
    option_hint = ", ".join([str(o.get("label") or "").strip() for o in options if str(o.get("label") or "").strip()][:5]) or "(need options list)"
    long_hint = str((c.get("horizon") or {}).get("type") or "") == "long"
    domain = str(c["domain"])
    domain_conf = float((c.get("domain_guess") or {}).get("confidence") or 0.0)
    return (
        "Produce a decision-first answer in EXACT sections below.\n"
        "No extra sections. Keep concise and concrete.\n\n"
        "OPTIONS:\n- <option 1>\n- <option 2> ... (max 5)\n"
        "If options cannot be extracted, do NOT output recommendation; output MODE/CALL HOLD and NEXT only.\n"
        "Do not emit long sentence fragments as options.\n"
        "LEAN: leaning direction text (e.g., A寄り / ほぼ同等)\n"
        "ALT: alternative option label\n"
        "LEAN_SPLIT: option1 xx / option2 yy (non-probability ratio)\n"
        "CALL: HOLD is allowed when uncertainty is high or options unresolved\n"
        "STABILITY: integer 0-100\n"
        "RESOLUTION: low|medium|high\n"
        "ΔSCORE: signed integer -100..+100\n"
        "AXES:\n- infer 3-5 axes from input domain\n"
        "SCORECARD:\n- <axis>: <option_id>=x ...\n"
        "FACTS_3:\n- fact 1 from input\n- fact 2 from input\n- fact 3 from input\n"
        "SCENARIOS: only when long-horizon/future uncertainty appears\n"
        "FALSIFIER:\n- one concrete condition that flips conclusion\n"
        "NEXT:\n- one concrete next action with source/deadline/threshold\n\n"
        f"Input question: {q}\n"
        f"Options hint: {option_hint}\n"
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


def _section_lines(after_text: str, section: str) -> list[str]:
    t = after_text or ""
    lines = t.splitlines()
    out: list[str] = []
    collecting = False
    for ln in lines:
        s = ln.rstrip()
        if s.strip().startswith(section):
            collecting = True
            continue
        if collecting and re.match(r"^[A-Z_]+(?:\s*[A-Z_]+)?:", s.strip()):
            break
        if collecting and s.strip().startswith("-"):
            out.append(s.strip()[1:].strip())
    return out


def _section_value(after_text: str, key: str) -> str:
    for ln in (after_text or "").splitlines():
        s = ln.strip()
        if s.startswith(f"{key}:"):
            return s.split(":", 1)[1].strip()
    return ""


def _scorecard_from_after(after_text: str) -> dict:
    rows = _section_lines(after_text, "SCORECARD:")
    scorecard: dict[str, dict[str, int]] = {}
    for r in rows:
        if ":" not in r:
            continue
        axis, rest = r.split(":", 1)
        axis = axis.strip()
        scorecard[axis] = {}
        for kv in rest.strip().split():
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            try:
                scorecard[axis][k.strip()] = int(v.strip())
            except Exception:
                continue
    return scorecard


def _quality_from_after(after_text: str, domain: str = "", input_text: str = "") -> dict:
    options = _section_lines(after_text, "OPTIONS:")
    axes = _section_lines(after_text, "AXES:")
    facts = _section_lines(after_text, "FACTS_3:")
    falsifier = " ".join(_section_lines(after_text, "FALSIFIER:"))
    next_lines = _section_lines(after_text, "NEXT:")
    banned = set(get_domain_spec(domain or "general").get("banned_axes", []))

    def _option_too_long_or_noisy(o: str) -> bool:
        s = str(o or "").strip()
        if len(s) > 18:
            return True
        if _option_noise_score(s) >= 4:
            return True
        return False
    options_ok = int(
        len(options) >= 2
        and all("(unresolved)" not in o for o in options)
        and all(len(o) <= 32 for o in options)
        and not any(_option_too_long_or_noisy(o) for o in options)
    )
    axes_ok = int(len(axes) >= 3 and all(a not in banned for a in axes))
    generic_fact_markers = ("判定条件=未固定", "入力語=")
    facts_ok = int(len(facts) >= 3 and all(not any(g in f for g in generic_fact_markers) for f in facts))
    falsifier_ok = int(bool(falsifier) and any(k in falsifier for k in ("なら", "場合", "条件", "if", "when")))
    next_txt = " ".join(next_lines)
    next_ok = int(bool(next_lines) and any(k in next_txt for k in ("職種", "予算", "都市", "期限", "比率", "摂取量", "期間", "移動", "没入", "気楽さ", "混雑")))

    total = options_ok + axes_ok + facts_ok + falsifier_ok + next_ok
    if options_ok == 0:
        total = min(total, 4)
    return {
        "options_ok": options_ok,
        "axes_ok": axes_ok,
        "facts_ok": facts_ok,
        "falsifier_ok": falsifier_ok,
        "next_ok": next_ok,
        "total": total,
    }


def _write_decision_card(
    case_id: str,
    input_text: str,
    after_text: str,
    domain_guess: dict,
    deep_status: str,
    missing_stages: list[str],
    fallback_reason_primary: str,
) -> tuple[dict, Path]:
    options = _section_lines(after_text, "OPTIONS:")
    axes = _section_lines(after_text, "AXES:")
    facts = _section_lines(after_text, "FACTS_3:")
    scorecard = _scorecard_from_after(after_text)
    recommend = {
        "top": _section_value(after_text, "LEAN") or _section_value(after_text, "RECOMMEND_TOP") or _section_value(after_text, "RECOMMEND"),
        "runner_up": _section_value(after_text, "ALT") or _section_value(after_text, "RECOMMEND_RUNNER_UP"),
    }
    confidence = 0
    m_conf = re.search(r"STABILITY:\s*([0-9]+)", after_text or "")
    if m_conf:
        try:
            confidence = int(m_conf.group(1))
        except Exception:
            confidence = 0
    card = {
        "input_text": input_text,
        "domain_guess": domain_guess or {"name": "general", "confidence": 0.0},
        "deep_status": deep_status,
        "options": options,
        "axes": axes,
        "scorecard": scorecard,
        "facts_3": facts,
        "recommend": recommend,
        "confidence": confidence,
        "falsifier": " ".join(_section_lines(after_text, "FALSIFIER:")),
        "next": " ".join(_section_lines(after_text, "NEXT:")),
        "build_sha": RUN_SHA,
        "meta": {
            "missing_stages": missing_stages or [],
            "fallback_reason_primary": fallback_reason_primary or "",
        },
    }
    card["quality"] = _quality_from_after(after_text, domain=str((domain_guess or {}).get("name") or "general"), input_text=input_text)
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    out_path = DECISION_CARDS_DIR / f"{ts}_{case_id}.json"
    out_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    DECISION_CARD_LATEST.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return card, out_path


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
    if _is_valid_stepa_for_question(t, q):
        return t + "\n"
    rebuilt = _build_v2_after(
        q,
        recommend_side="A",
        dscore=+8 if lite else +10,
        outcome="Partial_OK",
        missing=["expand", "diff"] if lite else ["stepA"],
    ).strip()
    return rebuilt + "\n"


def _has_stepa_evidence(after_text: str) -> bool:
    t = (after_text or "").strip()
    if not t:
        return False
    has_lean = bool(_section_value(t, "LEAN"))
    has_axes = len(_section_lines(t, "AXES:")) >= 1
    has_next = len(_section_lines(t, "NEXT:")) >= 1
    return has_lean and has_axes and has_next

def _is_valid_after_full(text: str, min_lines: int = 8) -> bool:
    t = (text or "").strip()
    if not t or "(dummy)" in t:
        return False
    if "OPTIONS:" not in t or "NEXT:" not in t:
        return False
    if "(unresolved)" in t:
        return False
    required = ("LEAN:", "ALT:", "LEAN_SPLIT:", "STABILITY:", "ΔSCORE:", "AXES:", "SCORECARD:", "FACTS_3:", "FALSIFIER:", "NEXT:")
    if not all(k in t for k in required):
        return False
    has_decision = ("LEAN:" in t) or ("CALL: HOLD" in t)
    if not has_decision:
        return False
    if "MODE: CONDITIONAL" in t and "SCENARIOS:" not in t:
        return False
    return len(t.splitlines()) >= min_lines


def _is_pricing_stepa_ready(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    required = ("LEAN:", "ALT:", "LEAN_SPLIT:", "WHY_TOP2:", "WHY_GAP:", "WHY_LOSER:", "NEXT:")
    if not all(k in t for k in required):
        return False
    low = t.lower()
    # WHY_TOP2 should carry concrete pricing tokens.
    why_line = _section_value(t, "WHY_TOP2")
    concrete_tokens = ("回数制限", "待ち時間", "仕事影響", "仕事比率", "予算")
    if not any(tok in why_line for tok in concrete_tokens):
        return False
    # NEXT must stay one fixed question.
    next_lines = _section_lines(t, "NEXT:")
    if len(next_lines) != 1:
        return False
    if "仕事利用比率" not in next_lines[0]:
        return False
    # Ensure options are explicit triad.
    opts = _section_lines(t, "OPTIONS:")
    joined = " ".join(opts).lower()
    if not (("無料" in joined or "free" in joined) and ("plus" in joined) and ("pro" in joined or "プロ" in joined)):
        return False
    return True


def _is_valid_stepa_for_question(text: str, q: str) -> bool:
    if not _is_valid_after_full(text):
        return False
    if "WHY_TOP2:" not in (text or ""):
        return False
    domain = _detect_domain(q or "")
    if domain == "subscription_pricing":
        return _is_pricing_stepa_ready(text)
    return True


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
    if (("LEAN:" in (text or "")) or ("CALL: HOLD" in (text or ""))) and "SCORECARD:" in (text or ""):
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
        if _detect_domain(q or "") == "asset_allocation":
            return (
                "TAB=EXPAND (variable tree for investment only).\n"
                "Goal: decompose variables, not predict outcomes.\n"
                "Output MUST include:\n"
                "1) VARIABLE_TREE with nodes for return/risk/liquidity/management/diversification\n"
                "2) FLIP conditions with numeric thresholds placeholders\n"
                "3) NEXT one question to fix remaining premise\n"
                "No prophecy, no generic advice.\n\n"
                + common_ctx
            )
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
    case_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", (q[:48] or "case")).strip("_") or "case"
    tab = args.tab
    core_only = os.getenv("MMAR_CORE_ONLY", "").strip() == "1"
    seed_only = os.getenv("MMAR_SEED_ONLY", "").strip() == "1" or tab == "seed"
    no_llm = os.getenv("MMAR_NO_LLM", "").strip() == "1"
    think_mode = not no_llm
    deep_status = "ok"
    fallback_reason_primary = ""
    fallback_reason_secondary: list[str] = []
    missing_stages: list[str] = []
    stage_status: dict[str, str] = {"stepA": "pending", "expand": "pending", "diff": "pending"}
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
        if stage in stage_status:
            stage_status[stage] = "missing"

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

    latest_card: dict = {}
    latest_card_path: Path | None = None

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
        g = guess_domain(q or "")
        _write_decision_card(
            case_id=case_id,
            input_text=q,
            after_text="OPTIONS:\n- 候補を箇条書きで指定してください（最大5）\nMODE: HOLD\nCALL: HOLD\nLEAN: ほぼ同等\nALT: 候補確定後に提示\nLEAN_SPLIT: 候補A 50 / 候補B 50\nSTABILITY: 25\nRESOLUTION: low\nΔSCORE: +0\nAXES:\n- コスト\n- リスク\n- 柔軟性\nSCORECARD:\n- コスト: 候補指定後に採点\nFACTS_3:\n- 入力語=比較\n- 入力語=目的\n- 入力語=条件\nFLIP:\n- 候補確定で反転可能\nFALSIFIER:\n- 候補確定で再計算\nNEXT:\n- 候補を箇条書きで指定してください（最大5）\nOUTCOME: Seed_Placeholder\n",
            domain_guess={"name": str(g.get("name") or "general"), "confidence": float(g.get("confidence") or 0.0)},
            deep_status="seed",
            missing_stages=["seed"],
            fallback_reason_primary="seed_only",
        )
        log("[seed_only] wrote out_compare placeholders and returned")
        return

    # 1) triad_turn skeleton (existing generator)
    log("[1/5] generate_triad_turn_min.py -> incoming/triad_turn.json")
    subprocess.check_call([sys.executable, "tools/generate_triad_turn_min.py", q], cwd=str(REPO))
    if core_only:
        c_core = _canonicalize_question(q)
        pf_core = _preflight_check(q, c_core)
        if not bool(pf_core.get("sufficient", True)):
            after_core = _build_need_info_after(q, c_core, pf_core).strip() + "\n"
        else:
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
        g = guess_domain(q or "")
        _write_decision_card(
            case_id=case_id,
            input_text=q,
            after_text=after_core,
            domain_guess={"name": str(g.get("name") or "general"), "confidence": float(g.get("confidence") or 0.0)},
            deep_status=("insufficient" if not bool(pf_core.get("sufficient", True)) else "core"),
            missing_stages=[],
            fallback_reason_primary=("insufficient_context" if not bool(pf_core.get("sufficient", True)) else ""),
        )
        DEEP_META.write_text(
            json.dumps(
                {
                    "deep_status": ("insufficient" if not bool(pf_core.get("sufficient", True)) else "core"),
                    "domain": c_core.get("domain"),
                    "domain_guess": c_core.get("domain_guess"),
                    "domain_confidence": float((c_core.get("domain_guess") or {}).get("confidence") or 0.0),
                    "missing_fields": c_core.get("missing_fields") or [],
                    "fallback_reason": ("insufficient_context" if not bool(pf_core.get("sufficient", True)) else ""),
                    "fallback_reason_primary": ("insufficient_context" if not bool(pf_core.get("sufficient", True)) else ""),
                    "fallback_reason_secondary": [],
                    "missing_stages": [],
                    "stage_status": {"stepA": "done", "expand": "done", "diff": "done"},
                    "judgment_point_changes": _judgment_point_changes_from_after(after_core),
                    "quality": _quality_from_after(after_core, domain=str(c_core.get("domain") or "general"), input_text=q),
                    "quality_total": int(_quality_from_after(after_core, domain=str(c_core.get("domain") or "general"), input_text=q).get("total", 0)),
                    "quality_label": ("insufficient" if not bool(pf_core.get("sufficient", True)) else ""),
                    "decision_card_path": "",
                    "build_sha": RUN_SHA,
                    "timings": {},
                    "sufficiency": pf_core,
                    "ui_state": {
                        "deep_enabled": bool(pf_core.get("sufficient", True)),
                        "deep_block_reason": ("insufficient_context" if not bool(pf_core.get("sufficient", True)) else ""),
                        "missing_top2": list(pf_core.get("missing_top2") or []),
                        "missing_fields": list(pf_core.get("missing_fields") or []),
                        "next_question": str(pf_core.get("next_question") or ""),
                        "next_choices": list(pf_core.get("next_choices") or []),
                        "required_fields": list(pf_core.get("required_fields") or []),
                        "satisfied_fields": list(pf_core.get("satisfied_fields") or []),
                        "need_k": int(pf_core.get("need_k") or 1),
                        "questions": list(pf_core.get("questions") or []),
                        "unlock_when_text": str(pf_core.get("unlock_when_text") or ""),
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log("[DONE] core-only output written")
        return
    canonical = _canonicalize_question(q)
    domain_guess = canonical.get("domain_guess") or {}
    preflight = _preflight_check(q, canonical)
    if think_mode and (not no_llm) and (not bool(preflight.get("sufficient", True))):
        need_after = _build_need_info_after(q, canonical, preflight).strip()
        need_before = normalize_before_seed(q)
        need_diff = build_diff_lite(need_before, need_after)
        TAB_FILES["expand"].write_text(need_after + "\n", encoding="utf-8")
        TAB_FILES["diff"].write_text(need_diff, encoding="utf-8")
        TAB_FILES["merge"].write_text(need_after + "\n", encoding="utf-8")
        TAB_FILES["compare"].write_text(
            "=== INPUT ===\n"
            f"{q}\n\n"
            "=== BEFORE (Single / seed) ===\n"
            f"{need_before}\n\n"
            "=== AFTER (MMAR / EXPAND) ===\n"
            f"{need_after}\n\n"
            "=== Δ (Diff head) ===\n"
            f"{need_diff}\n",
            encoding="utf-8",
        )
        latest_card, latest_card_path = _write_decision_card(
            case_id=case_id,
            input_text=q,
            after_text=need_after,
            domain_guess=domain_guess,
            deep_status="insufficient",
            missing_stages=[],
            fallback_reason_primary="insufficient_context",
        )
        DEEP_META.write_text(
            json.dumps(
                {
                    "deep_status": "insufficient",
                    "domain": canonical.get("domain"),
                    "domain_guess": domain_guess,
                    "domain_confidence": float(domain_guess.get("confidence") or 0.0),
                    "missing_fields": canonical.get("missing_fields") or [],
                    "fallback_reason": "insufficient_context",
                    "fallback_reason_primary": "insufficient_context",
                    "fallback_reason_secondary": [],
                    "missing_stages": [],
                    "stage_status": {"stepA": "done", "expand": "done", "diff": "done"},
                    "judgment_point_changes": _judgment_point_changes_from_after(need_after),
                    "quality": (latest_card or {}).get("quality", {}),
                    "quality_total": int(((latest_card or {}).get("quality") or {}).get("total") or 0),
                    "quality_label": "insufficient",
                    "decision_card_path": str(latest_card_path) if latest_card_path else "",
                    "build_sha": RUN_SHA,
                    "timings": {},
                    "sufficiency": preflight,
                    "ui_state": {
                        "deep_enabled": bool(preflight.get("sufficient", True)),
                        "deep_block_reason": ("insufficient_context" if not bool(preflight.get("sufficient", True)) else ""),
                        "missing_top2": list(preflight.get("missing_top2") or []),
                        "missing_fields": list(preflight.get("missing_fields") or []),
                        "next_question": str(preflight.get("next_question") or ""),
                        "next_choices": list(preflight.get("next_choices") or []),
                        "required_fields": list(preflight.get("required_fields") or []),
                        "satisfied_fields": list(preflight.get("satisfied_fields") or []),
                        "need_k": int(preflight.get("need_k") or 1),
                        "questions": list(preflight.get("questions") or []),
                        "unlock_when_text": str(preflight.get("unlock_when_text") or ""),
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log("[DONE] preflight insufficient -> NEED_INFO (skip LLM)")
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
        stage_status["stepA"] = "done"
    else:
        log("[2/5] OpenAI StepA (strong after v2)...")
        stepa_timeout = int(os.getenv("MMAR_STEPA_TIMEOUT", "40") or "40")
        stepa = timed_call("stepA", _stepa_prompt_v2(q), timeout_override=stepa_timeout)
        if _is_valid_stepa_for_question(stepa, q):
            master = stepa.strip()
            stage_status["stepA"] = "done"
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
    latest_card, latest_card_path = _write_decision_card(
        case_id=case_id,
        input_text=q,
        after_text=master,
        domain_guess=domain_guess,
        deep_status=deep_status,
        missing_stages=missing_stages,
        fallback_reason_primary=fallback_reason_primary,
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
            out = build_seed_after_core(q) if tab == "expand" else dummy_fallback_text(f"tab-{tab}")
            if tab == "expand":
                out = _ensure_deep_after_sections(out, q, lite=True)
                stage_status["expand"] = "done"
            TAB_FILES[tab].write_text(out, encoding="utf-8")
            if tab == "expand":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, out), encoding="utf-8")
                stage_status["diff"] = "done"
            if tab == "diff":
                TAB_FILES["diff"].write_text(build_diff_lite(seed, build_seed_after_core(q)), encoding="utf-8")
                stage_status["diff"] = "done"
        else:
            # StepB is optional: keep StepA(master) as default and enrich only if budget remains.
            out = master if tab == "expand" else ""
            master_after = master if tab == "expand" else ""
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
            if tab == "expand" and not _is_valid_stepa_for_question(out, q):
                if deep_status == "ok":
                    deep_status = "partial"
                mark_missing("expand")
                add_secondary_reason("expand_invalid_kept_master")
                # Sticky StepA: keep master result instead of replacing with generic partial text.
                out = master_after if _is_valid_stepa_for_question(master_after, q) else build_after_partial(q, seed, c1, c2, master)
                lite_used = not _is_valid_stepa_for_question(master_after, q)
            elif tab == "expand" and do_stepb:
                out = out.rstrip() + "\n(full)\n"
            if tab == "expand":
                out = _ensure_deep_after_sections(out, q, lite=lite_used)
                stage_status["expand"] = "done"
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
                    stage_status["diff"] = "done"
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
        if _is_valid_stepa_for_question(master, q):
            expand_txt = master.strip()
        elif seed.strip() or c1.strip() or c2.strip() or master.strip():
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

    final_after = (expand_txt or master or "").strip()
    if _has_stepa_evidence(final_after):
        stage_status["stepA"] = "done"
    elif stage_status.get("stepA") == "pending":
        stage_status["stepA"] = "missing"
    if stage_status.get("expand") == "pending":
        stage_status["expand"] = "done" if bool(expand_txt.strip()) else "missing"
    if stage_status.get("diff") == "pending":
        stage_status["diff"] = "done" if bool(diff_txt.strip()) else "missing"
    missing_stages = [k for k, v in stage_status.items() if v == "missing"]

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
    latest_card, latest_card_path = _write_decision_card(
        case_id=case_id,
        input_text=q,
        after_text=final_after,
        domain_guess=domain_guess,
        deep_status=deep_status,
        missing_stages=missing_stages,
        fallback_reason_primary=fallback_reason_primary,
    )
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
        f"quality: {json.dumps((latest_card or {}).get('quality', {}), ensure_ascii=False)}\n"
        f"timings: {json.dumps(timings, ensure_ascii=False)}\n"
    )
    if think_mode:
        compare = _append_decision_sections(compare, q)
    Path(TAB_FILES["compare"]).write_text(compare, encoding="utf-8")
    TURNP.write_text(json.dumps(turn_after, ensure_ascii=False, indent=2), encoding="utf-8")
    preflight_final = _preflight_check(q, canonical)
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
                "stage_status": stage_status,
                "judgment_point_changes": judgment_point_changes,
                "quality": (latest_card or {}).get("quality", {}),
                "quality_total": int(((latest_card or {}).get("quality") or {}).get("total") or 0),
                "decision_card_path": str(latest_card_path) if latest_card_path else "",
                "build_sha": RUN_SHA,
                "timings": timings,
                "sufficiency": preflight_final,
                "ui_state": {
                    "deep_enabled": bool(preflight_final.get("sufficient", True)),
                    "deep_block_reason": ("insufficient_context" if not bool(preflight_final.get("sufficient", True)) else ""),
                    "missing_top2": list((preflight_final.get("missing_top2") or [])),
                    "missing_fields": list((preflight_final.get("missing_fields") or [])),
                    "next_question": str(preflight_final.get("next_question") or ""),
                    "next_choices": list((preflight_final.get("next_choices") or [])),
                    "required_fields": list((preflight_final.get("required_fields") or [])),
                    "satisfied_fields": list((preflight_final.get("satisfied_fields") or [])),
                    "need_k": int(preflight_final.get("need_k") or 1),
                    "questions": list((preflight_final.get("questions") or [])),
                    "unlock_when_text": str(preflight_final.get("unlock_when_text") or ""),
                },
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
