from __future__ import annotations
import argparse, json, hashlib, datetime
from pathlib import Path

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def last_hash_in_log(logp: str, case_id: str) -> str | None:
    p = Path(logp)
    if not p.exists():
        return None
    last = None
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if obj.get("schema") != "mmar.delta_entry.v0":
            continue
        if obj.get("case_id") != case_id:
            continue
        h = obj.get("content_hash")
        if isinstance(h, str) and h:
            last = h
    return last

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="examples/tmp/dissent_diff_v2.single.claim.json")
    ap.add_argument("--out", dest="outp", default="out_delta/delta_entry.latest.json")
    ap.add_argument("--append-log", dest="logp", default="logs/delta_entries.jsonl")
    ap.add_argument("--case-id", default="Case SINGLE")
    args = ap.parse_args()

    d = json.loads(Path(args.inp).read_text(encoding="utf-8", errors="replace"))
    stats = d.get("stats") or {}
    claims = d.get("claims") or []

    claims_total = int(stats.get("claims_total") or len(claims))
    claims_dissent = int(stats.get("claims_dissent") or 0)
    claims_agreed = int(stats.get("claims_agreed") or max(0, claims_total - claims_dissent))

    joined = "\n".join([(c.get("texts") or {}).get("openai","") for c in claims])
    content_hash = sha256(joined)

    prev = last_hash_in_log(args.logp, args.case_id)
    drift_proxy = 1 if (prev is not None and prev != content_hash) else 0

    out = {
        "schema": "mmar.delta_entry.v0",
        "case_id": args.case_id,
        "asof": now_iso(),
        "update_unit": "claim",
        "resolved_count": claims_total,     # v2暫定（claim=1.0）
        "dissent_count": claims_dissent,
        "agree_count": claims_agreed,
        "dissent_rate": (claims_dissent / claims_total) if claims_total else 0.0,
        "drift_proxy": drift_proxy,        # v2: hash diff
        "content_hash": content_hash,
        "source": args.inp,
    }

    Path(args.outp).parent.mkdir(parents=True, exist_ok=True)
    Path(args.outp).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    Path(args.logp).parent.mkdir(parents=True, exist_ok=True)
    with open(args.logp, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")

    print("[WROTE]", args.outp)
    print("[APPEND]", args.logp)

if __name__ == "__main__":
    main()
