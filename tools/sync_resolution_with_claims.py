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
    ap.add_argument("--resolution", default=None)
    args = ap.parse_args()

    res_path = args.resolution or f"incoming/resolution.{args.case_id}.json"
    Path("incoming").mkdir(parents=True, exist_ok=True)

    claims_doc = json.loads(Path(args.claims).read_text(encoding="utf-8", errors="replace"))
    claims = claims_doc.get("claims") or []
    claim_ids = [c.get("claim_id") for c in claims if c.get("claim_id")]

    # load existing resolution if any
    if Path(res_path).exists():
        res = json.loads(Path(res_path).read_text(encoding="utf-8", errors="replace"))
    else:
        res = {"schema":"mmar.resolution.v0", "case_id": args.case_id, "asof": now_iso(),
               "source_claims": args.claims, "statuses": {}, "items": []}

    statuses = res.get("statuses") or {}
    items_by = {it.get("claim_id"): it for it in (res.get("items") or []) if isinstance(it, dict) and it.get("claim_id")}

    # add new ids as pending
    for cid in claim_ids:
        if cid not in statuses:
            statuses[cid] = "pending"

    # refresh items (text_head)
    new_items=[]
    for c in claims:
        cid = c.get("claim_id")
        if not cid: 
            continue
        texts = c.get("texts") or {}
        txt = (texts.get("merged") or texts.get("final") or "").strip()
        new_items.append({"claim_id": cid, "text_head": txt[:180], "status": statuses.get(cid, "pending")})

    res["schema"] = "mmar.resolution.v0"
    res["case_id"] = args.case_id
    res["asof"] = now_iso()
    res["source_claims"] = args.claims
    res["statuses"] = statuses
    res["items"] = new_items

    Path(res_path).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[WROTE]", res_path, "n_claims=", len(claim_ids), "n_status=", len(statuses))

if __name__ == "__main__":
    main()
