from __future__ import annotations

DOMAIN_REGISTRY: dict[str, dict] = {
    "education_career": {
        "keywords": ["大学", "進学", "学費", "就職", "就職率", "専門", "資格", "AI", "学歴", "回収期間"],
        "axes_candidates": ["初期コスト", "回収期間", "就職確率", "AI代替耐性", "柔軟性"],
        "falsifier_templates": [
            "学歴フィルタが強い業界/地域ならAへ反転",
            "学費負担が大きく回収不能ならBへ反転",
        ],
        "next_question_candidates": ["志望職種は？", "学費上限は？", "地域/国は？"],
        "banned_axes": ["健康効果"],
    },
    "investing": {
        "keywords": ["投資", "利回り", "レバ", "ETF", "暗号", "運用", "NISA", "株", "債券", "DD"],
        "axes_candidates": ["期待リターン", "最大損失", "流動性", "手数料", "税効率"],
        "falsifier_templates": [
            "許容DDを超える下落が想定されるなら保守案へ反転",
            "手数料/税負担で実質リターンが逆転するなら反転",
        ],
        "next_question_candidates": ["投資期間は？", "許容DDは？", "目的は増やす/守るのどちら？"],
        "banned_axes": ["健康効果"],
    },
    "shopping": {
        "keywords": ["買う", "価格", "比較", "コスパ", "レビュー", "保証", "配送", "セール"],
        "axes_candidates": ["総コスト", "性能", "耐久性", "保証", "納期"],
        "falsifier_templates": [
            "保証条件が弱い場合は代替案へ反転",
            "実測性能が公称を下回る場合は反転",
        ],
        "next_question_candidates": ["予算上限は？", "最重要用途は？", "納期制約は？"],
        "banned_axes": [],
    },
    "fitness": {
        "keywords": ["運動", "筋トレ", "体脂肪", "減量", "増量", "ランニング", "持久力"],
        "axes_candidates": ["効果", "ケガリスク", "継続可能性", "時間コスト", "費用"],
        "falsifier_templates": [
            "痛み/故障リスクが閾値超過なら反転",
            "継続率が低下するなら低負荷案へ反転",
        ],
        "next_question_candidates": ["目標指標は？", "週の実施可能時間は？", "既往歴は？"],
        "banned_axes": [],
    },
    "leisure": {
        "keywords": ["旅行", "遊び", "観光", "ホテル", "旅程", "休暇", "チケット"],
        "axes_candidates": ["体験価値", "総コスト", "移動負担", "安全性", "柔軟性"],
        "falsifier_templates": [
            "天候/混雑で体験価値が下がるなら反転",
            "移動遅延リスクが高い場合は代替案へ反転",
        ],
        "next_question_candidates": ["予算上限は？", "日程は？", "優先体験は？"],
        "banned_axes": [],
    },
    "food": {
        "keywords": ["りんご", "納豆", "食", "栄養", "血糖", "体重", "摂取量", "カロリー"],
        "axes_candidates": ["健康効果", "価格", "継続可能性"],
        "falsifier_templates": [
            "目的指標が改善しない場合は反転",
            "継続不能なら代替食へ反転",
        ],
        "next_question_candidates": ["目的指標は？", "1日の摂取量は？", "制約は？"],
        "banned_axes": [],
    },
    "sports": {
        "keywords": ["野球", "サッカー", "テニス", "スポーツ", "競技", "試合", "練習"],
        "axes_candidates": ["怪我リスク", "費用", "継続可能性"],
        "falsifier_templates": [
            "怪我リスクが高い場合は反転",
            "継続コストが閾値超過なら反転",
        ],
        "next_question_candidates": ["目的は？", "頻度は？", "予算は？"],
        "banned_axes": [],
    },
    "general": {
        "keywords": [],
        "axes_candidates": ["コスト", "リスク", "柔軟性"],
        "falsifier_templates": [
            "主要軸で逆転データが出たら反転",
            "制約条件が変われば再判定",
        ],
        "next_question_candidates": ["目的は？", "優先軸は？", "期限は？"],
        "banned_axes": [],
    },
}


def guess_domain(text: str) -> dict:
    t = text or ""
    scores: dict[str, int] = {}
    for name, spec in DOMAIN_REGISTRY.items():
        if name == "general":
            continue
        hits = sum(1 for kw in spec.get("keywords", []) if kw and kw in t)
        if hits > 0:
            scores[name] = hits
    if not scores:
        return {"name": "general", "confidence": 0.35}
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_name, top_score = top[0]
    denom = float(sum(scores.values()) or 1)
    conf = max(0.0, min(1.0, top_score / denom))
    return {"name": top_name, "confidence": conf}


def get_domain_spec(name: str) -> dict:
    return DOMAIN_REGISTRY.get(name or "general", DOMAIN_REGISTRY["general"])
