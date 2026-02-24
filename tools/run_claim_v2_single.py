from __future__ import annotations
import os, sys, json, argparse
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.claim_extract_min import extract_claims

def load_json_or_text(p: str):
    txt = Path(p).read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    try:
        return json.loads(txt)
    except Exception:
        return {"text": txt}

def get_text(obj):
    if isinstance(obj, dict) and isinstance(obj.get("text"), str):
        return obj["text"]
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-openai", default="examples/raw_local/openai.json")
    ap.add_argument("--out", default="examples/tmp/dissent_diff_v2.single.claim.json")
    args = ap.parse_args()

    raw = load_json_or_text(args.raw_openai)
    text = get_text(raw)

    claims = extract_claims(text)
    out_claims = []
    for c in claims:
        out_claims.append({
            "claim_id": c["claim_id"],
            "texts": {"openai": c["text"], "gemini": "", "claude": ""},
            "match_scores": {"openai": 1.0},
            "dissent": False,
            "dissent_meta": {"reason": "single_source", "missing_models": ["gemini","claude"]},
        })

    out = {
        "schema": "mmar.dissent_diff.v2.single",
        "key_type": "claim",
        "stats": {
            "claims_total": len(out_claims),
            "claims_dissent": 0,
            "claims_agreed": len(out_claims),
            "coverage_models": 1
        },
        "claims": out_claims,
    }

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[DONE]", str(outp), out["stats"])

if __name__ == "__main__":
    main()
