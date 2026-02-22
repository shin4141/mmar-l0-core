from __future__ import annotations
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import argparse
import json
import os
import re
from itertools import combinations
from typing import Any, Dict, List, Optional

from core.claim_extract_min import extract_claims
from core.claim_match_min import match_claims, sim

def _collect_strings(obj: Any, keys_hint: Optional[set] = None, out: Optional[List[str]] = None) -> List[str]:
    if out is None:
        out = []
    if keys_hint is None:
        keys_hint = {"text", "content", "message", "output_text", "final", "response", "completion"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and (k in keys_hint or len(v) > 0):
                out.append(v)
            else:
                _collect_strings(v, keys_hint, out)
    elif isinstance(obj, list):
        for it in obj:
            _collect_strings(it, keys_hint, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out

def extract_text_from_raw(payload: Any) -> str:
    # 最小：全文文字列を集めて、長いものを優先してまとめる
    strs = _collect_strings(payload)
    strs = [s.strip() for s in strs if isinstance(s, str) and s.strip()]
    if not strs:
        return json.dumps(payload, ensure_ascii=False)
    # ノイズ対策：短すぎる断片は削る
    keep = [s for s in strs if len(s) >= 10]
    if not keep:
        keep = strs
    # 先頭から重複除去
    seen = set()
    uniq = []
    for s in keep:
        key = re.sub(r"\s+", " ", s).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return "\n".join(uniq)

def build_v2(
    raw_openai: Dict[str, Any],
    raw_gemini: Dict[str, Any],
    raw_claude: Dict[str, Any],
    match_threshold: float = 0.72,
    diff_threshold: float = 0.90,
) -> Dict[str, Any]:
    texts = {
        "openai": extract_text_from_raw(raw_openai),
        "gemini": extract_text_from_raw(raw_gemini),
        "claude": extract_text_from_raw(raw_claude),
    }

    claims_by_model = {m: extract_claims(t) for m, t in texts.items()}
    clusters = match_claims(claims_by_model, threshold=match_threshold)

    def dissent_flag(texts_map: Dict[str, str]) -> Dict[str, Any]:
        present = {k: v for k, v in texts_map.items() if isinstance(v, str) and v.strip()}
        missing = [m for m in ("openai", "gemini", "claude") if m not in present]
        if missing:
            return {"dissent": True, "reason": "missing", "missing_models": missing, "min_pair_sim": None}
        sims = []
        maxlen = 0
        for (m1, t1), (m2, t2) in combinations(present.items(), 2):
            sims.append(sim(t1, t2))
            maxlen = max(maxlen, len(t1), len(t2))
        min_sim = min(sims) if sims else 1.0

        # v2.1: short-text threshold
        diff_threshold_short = 0.75
        short_len = 60
        th = diff_threshold_short if maxlen <= short_len else diff_threshold

        return {
            "dissent": (min_sim < th),
            "reason": "pairwise",
            "missing_models": [],
            "min_pair_sim": round(min_sim, 4),
            "threshold_used": th,
            "short_len": short_len,
        }

    out_claims = []
    dissent_count = 0
    for cl in clusters:
        info = dissent_flag(cl["texts"])
        dissent_count += 1 if info["dissent"] else 0
        out_claims.append({
            "claim_id": cl["claim_id"],
            "texts": {k: cl["texts"].get(k, "") for k in ("openai", "gemini", "claude")},
            "match_scores": cl["match_scores"],
            "dissent": info["dissent"],
            "dissent_meta": info,
        })

    return {
        "schema": "mmar.dissent_diff.v2",
        "key_type": "claim",
        "params": {
            "match_threshold": match_threshold,
            "diff_threshold": diff_threshold,
        },
        "stats": {
            "claims_total": len(out_claims),
            "claims_dissent": dissent_count,
            "claims_agreed": len(out_claims) - dissent_count,
        },
        "claims": out_claims,
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-openai", required=True)
    ap.add_argument("--raw-gemini", required=True)
    ap.add_argument("--raw-claude", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--match-threshold", type=float, default=0.72)
    ap.add_argument("--diff-threshold", type=float, default=0.90)
    args = ap.parse_args()

    def load(p: str) -> Any:
        # robust loader: JSON / JSONL / plain text
        txt = open(p, 'r', encoding='utf-8', errors='replace').read()
        txt = txt.lstrip('\ufeff').strip('\n')
        try:
            return json.loads(txt)
        except Exception:
            pass

        # JSONL fallback
        objs = []
        ok = True
        for ln in txt.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                objs.append(json.loads(ln))
            except Exception:
                ok = False
                break
        if ok and objs:
            return objs

        # plain text fallback
        return {'text': txt}
    raw_o = load(args.raw_openai)
    raw_g = load(args.raw_gemini)
    raw_c = load(args.raw_claude)

    out = build_v2(raw_o, raw_g, raw_c, args.match_threshold, args.diff_threshold)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
