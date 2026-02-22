from __future__ import annotations
import re
from difflib import SequenceMatcher
from typing import Dict, List, Any, Tuple

def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[\"'`]", "", s)
    return s

def sim(a: str, b: str) -> float:
    a2, b2 = _norm(a), _norm(b)
    if not a2 or not b2:
        return 0.0
    return SequenceMatcher(None, a2, b2).ratio()

def match_claims(
    claims_by_model: Dict[str, List[Dict[str, Any]]],
    threshold: float = 0.72,
) -> List[Dict[str, Any]]:
    """
    貪欲クラスタ：
    - 既存クラスタ代表(rep)との類似度>=thresholdなら同クラスタ
    - 代表は最初に入ったテキスト
    - 各クラスタに model->text を保持
    """
    clusters: List[Dict[str, Any]] = []

    def best_cluster(txt: str) -> Tuple[int, float]:
        best_i, best_s = -1, 0.0
        for i, cl in enumerate(clusters):
            s = sim(txt, cl["rep_text"])
            if s > best_s:
                best_i, best_s = i, s
        return best_i, best_s

    for model, claims in claims_by_model.items():
        for c in claims:
            txt = c.get("text", "").strip()
            if not txt:
                continue
            i, s = best_cluster(txt)
            if i >= 0 and s >= threshold:
                cl = clusters[i]
                # 同一modelが既にあるなら、より近い方を採用
                prev = cl["texts"].get(model)
                if prev is None or sim(txt, cl["rep_text"]) > sim(prev, cl["rep_text"]):
                    cl["texts"][model] = txt
                    cl["match_scores"][model] = s
            else:
                clusters.append({
                    "rep_text": txt,
                    "texts": {model: txt},
                    "match_scores": {model: 1.0},
                })

    # claim_id付与
    out = []
    for idx, cl in enumerate(clusters, 1):
        out.append({
            "claim_id": f"claim_{idx:03d}",
            "texts": cl["texts"],
            "match_scores": cl["match_scores"],
            "rep_text": cl["rep_text"],
        })
    return out
