from __future__ import annotations
import os, sys, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.claim_extract_min import extract_claims

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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

def read_merged_from_file() -> str:
    fp = Path("incoming/merged_answer.txt")
    if not fp.exists():
        return ""
    txt = fp.read_text(encoding="utf-8", errors="replace")
    # コメント行は除去
    txt = "\n".join([ln for ln in txt.splitlines() if not ln.lstrip().startswith("#")]).strip()
    return txt

def main():
    inp = Path("incoming/triad_turn.json")
    if not inp.exists():
        raise SystemExit("[MISS] incoming/triad_turn.json not found")

    d = json.loads(inp.read_text(encoding="utf-8", errors="replace"))
    case_id = (d.get("case_id") or "Case TRIAD").strip()

    merged = read_merged_from_file() or (d.get("merged_answer") or "").strip()
    if not merged:
        raise SystemExit("[MISS] triad_turn.json missing non-empty merged_answer (and merged_answer.txt empty)")

    # SSOT更新（以後は merged_answer.txt が真実）
    d["merged_answer"] = merged
    inp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    # claims
    claims = extract_claims(merged)
    out_claims = [{
        "claim_id": c["claim_id"],
        "texts": {"merged": c["text"]},
        "match_scores": {"merged": 1.0},
        "dissent": False,
        "dissent_meta": {"reason": "triad_merged_single"}
    } for c in claims]

    joined = "\n".join([c["texts"]["merged"] for c in out_claims])
    content_hash = sha256(joined)

    logp = "logs/delta_entries.jsonl"
    prev = last_hash_in_log(logp, case_id)
    drift_proxy = 1 if (prev is not None and prev != content_hash) else 0

    delta = {
        "schema": "mmar.delta_entry.v0",
        "case_id": case_id,
        "asof": now_iso(),
        "update_unit": "triad_turn",
        "resolved_count": len(out_claims),
        "dissent_count": 0,
        "agree_count": len(out_claims),
        "dissent_rate": 0.0,
        "drift_proxy": drift_proxy,
        "content_hash": content_hash,
        "source": str(inp),
        "meta": {
            "question_head": (d.get("question") or "")[:200],
            "seed_model": d.get("seed_model"),
            "counter_a_model": d.get("counter_a_model"),
            "counter_b_model": d.get("counter_b_model"),
        }
    }

    Path("examples/tmp").mkdir(parents=True, exist_ok=True)
    Path("out_delta").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)

    Path("examples/tmp/triad_claims.latest.json").write_text(json.dumps({
        "schema": "mmar.triad_claims.v0",
        "case_id": case_id,
        "asof": delta["asof"],
        "stats": {"claims_total": len(out_claims)},
        "claims": out_claims
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    Path("out_delta/delta_entry.latest.json").write_text(json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(logp, "a", encoding="utf-8") as f:
        f.write(json.dumps(delta, ensure_ascii=False) + "\n")

    print("[WROTE] examples/tmp/triad_claims.latest.json")
    print("[APPEND]", logp)
    print("[STATS]", {"claims_total": len(out_claims), "drift_proxy": drift_proxy})

if __name__ == "__main__":
    main()
