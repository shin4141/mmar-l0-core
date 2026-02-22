from __future__ import annotations
import argparse, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

WEIGHTS = {"resolved":1.0, "partial":0.5, "pending":0.0}

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def load_claims(path: str) -> dict[str,str]:
    d=json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    out={}
    for c in (d.get("claims") or []):
        cid=c.get("claim_id")
        if not cid: 
            continue
        texts=c.get("texts") or {}
        txt=(texts.get("merged") or texts.get("final") or "").strip()
        out[cid]=txt
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--append-log", default="logs/delta_entries.jsonl")
    ap.add_argument("--state", default=None)
    args=ap.parse_args()

    case_id=args.case_id
    state_path = args.state or f"out_state/claims_snapshot.{case_id}.json"

    cur = load_claims(args.claims)
    prev = {}
    sp = Path(state_path)
    if sp.exists():
        prev = json.loads(sp.read_text(encoding="utf-8", errors="replace"))

    # diff -> statuses
    statuses={}
    resolved_sum=0.0
    counts={"resolved":0,"partial":0,"pending":0}

    # prev items: disappear => resolved, changed => partial, same => pending
    for cid, prev_txt in prev.items():
        if cid not in cur:
            st="resolved"
        else:
            st="partial" if (cur[cid] != prev_txt) else "pending"
        statuses[cid]=st
        counts[st]+=1
        resolved_sum += WEIGHTS[st]

    # new claims (not in prev) => pending (no credit yet)
    for cid in cur.keys():
        if cid not in statuses:
            statuses[cid]="pending"
            counts["pending"]+=1

    # content_hash = current claims
    joined="\n".join([cur[k] for k in sorted(cur.keys())])
    content_hash=sha256(joined)

    delta = {
        "schema":"mmar.delta_entry.v0",
        "case_id": case_id,
        "asof": now_iso(),
        "update_unit":"resolution_auto",
        "resolved_count": resolved_sum,
        "resolved_count_v2": resolved_sum,
        "claims_total": len(cur),
        "status_counts": counts,
        "drift_proxy": 0,
        "content_hash": content_hash,
        "source": args.claims,
        "meta": {"state_prev": state_path}
    }

    Path(args.append_log).parent.mkdir(parents=True, exist_ok=True)
    with open(args.append_log,"a",encoding="utf-8") as f:
        f.write(json.dumps(delta, ensure_ascii=False) + "\n")

    # update snapshot to current
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[APPEND]", args.append_log)
    print("[AUTO_RESOLVED_V2]", resolved_sum, "counts=", counts, "claims_total=", len(cur))
    print("[SNAPSHOT]", state_path)

if __name__=="__main__":
    main()
