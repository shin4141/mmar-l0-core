from __future__ import annotations
import os, sys, json, hashlib, datetime
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.claim_extract_min import extract_claims

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
    inp = Path("incoming/t3f_turn.json")
    if not inp.exists():
        raise SystemExit("[MISS] incoming/t3f_turn.json not found")

    d = json.loads(inp.read_text(encoding="utf-8", errors="replace"))
    case_id = (d.get("case_id") or "Case T3F").strip()

    final = (d.get("final_merged") or "").strip()
    if not final:
        # 最小救済：3本が入ってれば自動で連結してfinalにする
        a=(d.get("merged_gpt") or "").strip()
        b=(d.get("merged_gemini") or "").strip()
        c=(d.get("merged_claude") or "").strip()
        if not (a and b and c):
            raise SystemExit("[MISS] t3f_turn.json missing non-empty final_merged (or all merged_* for auto-build)")
        final = "FINAL MERGE (auto)\n\n[M_gpt]\n"+a+"\n\n[M_gemini]\n"+b+"\n\n[M_claude]\n"+c

    claims = extract_claims(final)
    out_claims = [{"claim_id": c["claim_id"], "texts": {"final": c["text"]}, "match_scores": {"final": 1.0},
                   "dissent": False, "dissent_meta": {"reason": "t3f_final_single"}} for c in claims]

    claims_total = len(out_claims)
    joined = "\n".join([c["texts"]["final"] for c in out_claims])
    content_hash = sha256(joined)

    logp = "logs/delta_entries.jsonl"
    prev = last_hash_in_log(logp, case_id)
    drift_proxy = 1 if (prev is not None and prev != content_hash) else 0

    delta = {
        "schema": "mmar.delta_entry.v0",
        "case_id": case_id,
        "asof": now_iso(),
        "update_unit": "t3f_turn",
        "resolved_count": claims_total,
        "dissent_count": 0,
        "agree_count": claims_total,
        "dissent_rate": 0.0,
        "drift_proxy": drift_proxy,
        "content_hash": content_hash,
        "source": str(inp),
        "meta": {"question_head": (d.get("question") or "")[:200], "mode": "t3f"}
    }

    out_claims_path = Path("examples/tmp/t3f_claims.latest.json")
    out_claims_path.write_text(json.dumps({
        "schema": "mmar.t3f_claims.v0",
        "case_id": case_id,
        "asof": delta["asof"],
        "stats": {"claims_total": claims_total},
        "claims": out_claims
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    Path("out_delta").mkdir(parents=True, exist_ok=True)
    Path("out_delta/delta_entry.latest.json").write_text(json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(logp, "a", encoding="utf-8") as f:
        f.write(json.dumps(delta, ensure_ascii=False) + "\n")

    print("[WROTE]", out_claims_path)
    print("[APPEND]", logp)
    print("[STATS]", {"claims_total": claims_total, "drift_proxy": drift_proxy})

if __name__ == "__main__":
    main()
