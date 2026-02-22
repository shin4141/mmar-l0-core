from __future__ import annotations
import argparse, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

WEIGHTS = {
    "resolved": 1.0, "accepted": 1.0, "rejected": 1.0,
    "partial": 0.5,
    "pending": 0.0, "unknown": 0.0, "needs-evidence": 0.0
}

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolution", required=True)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--append-log", default="logs/delta_entries.jsonl")
    args = ap.parse_args()

    r = json.loads(Path(args.resolution).read_text(encoding="utf-8", errors="replace"))
    case_id = r.get("case_id") or "Case ?"
    statuses = r.get("statuses") or {}

    c = json.loads(Path(args.claims).read_text(encoding="utf-8", errors="replace"))
    claims = c.get("claims") or []

    # content_hash: claims本文由来（解決状態が変わっても同じ）
    joined=[]
    for x in claims:
        texts = x.get("texts") or {}
        joined.append((texts.get("merged") or texts.get("final") or "").strip())
    content_hash = sha256("\n".join(joined))

    counts = {k:0 for k in WEIGHTS.keys()}
    resolved_sum = 0.0

    for x in claims:
        cid = x.get("claim_id")
        st = (statuses.get(cid) or "pending").strip()
        if st not in WEIGHTS:
            st = "pending"
        counts[st] += 1
        resolved_sum += WEIGHTS[st]

    delta = {
        "schema": "mmar.delta_entry.v0",
        "case_id": case_id,
        "asof": now_iso(),
        "update_unit": "resolution",
        "resolved_count": resolved_sum,     # v2本命
        "resolved_count_v2": resolved_sum,
        "claims_total": len(claims),
        "status_counts": counts,
        "dissent_count": 0,
        "agree_count": len(claims),
        "dissent_rate": 0.0,
        "drift_proxy": 0,
        "content_hash": content_hash,
        "source": args.resolution,
        "meta": {"source_claims": args.claims}
    }

    Path(args.append_log).parent.mkdir(parents=True, exist_ok=True)
    with open(args.append_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(delta, ensure_ascii=False) + "\n")

    print("[APPEND]", args.append_log)
    print("[RESOLVED_V2]", resolved_sum, "of", len(claims))

if __name__ == "__main__":
    main()
