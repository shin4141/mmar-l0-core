from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    d = json.loads(Path(args.claims).read_text(encoding="utf-8", errors="replace"))
    claims = d.get("claims") or []

    items=[]
    statuses={}
    for c in claims:
        cid = c.get("claim_id")
        if not cid: 
            continue
        # triad_claims: texts.merged / t3f_claims: texts.final
        texts = c.get("texts") or {}
        text = (texts.get("merged") or texts.get("final") or "").strip()
        items.append({"claim_id": cid, "text_head": text[:180]})
        statuses[cid] = "pending"

    outp = args.out or f"incoming/resolution.{args.case_id}.json"
    out = {
        "schema": "mmar.resolution.v0",
        "case_id": args.case_id,
        "asof": now_iso(),
        "source_claims": args.claims,
        "statuses": statuses,
        "items": items
    }
    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    Path(outp).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[WROTE]", outp, "n_items=", len(items))

if __name__ == "__main__":
    main()
