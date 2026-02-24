from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Any, Dict, Optional

MIN_CHARS = 120

def prov_of(s: str) -> Optional[str]:
    s = (s or "").lower()
    if "openai" in s or "gpt" in s:
        return "openai"
    if "gemini" in s or "google" in s:
        return "gemini"
    if "claude" in s or "anthropic" in s:
        return "claude"
    return None

WANT_KEYS = {"text","content","message","final","response","completion","output_text"}

def collect_strings(obj: Any, out=None):
    if out is None: out=[]
    if isinstance(obj, dict):
        for k,v in obj.items():
            if isinstance(v, str) and (k in WANT_KEYS or len(v) >= 40):
                out.append(v)
            else:
                collect_strings(v, out)
    elif isinstance(obj, list):
        for it in obj: collect_strings(it, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out

def extract_text(payload: Any) -> str:
    ss = [s.strip() for s in collect_strings(payload) if isinstance(s,str) and s.strip()]
    if not ss:
        return ""
    seen=set(); uniq=[]
    for s in ss:
        key=re.sub(r"\s+"," ",s).strip().lower()
        if key in seen: continue
        seen.add(key); uniq.append(s)
    uniq.sort(key=len, reverse=True)
    return ("\n".join(uniq[:10]))[:2_000_000]

def iter_log_files():
    # repo内の logs/*.jsonl を優先。なければ jsonl/ndjson 全般を拾う
    cands = list(Path("logs").glob("*.jsonl")) + list(Path("logs").glob("*.ndjson"))
    if cands:
        return cands
    return list(Path(".").rglob("*.jsonl")) + list(Path(".").rglob("*.ndjson"))

def main():
    best: Dict[str, str] = {}
    best_len: Dict[str, int] = {"openai":0,"gemini":0,"claude":0}

    used_files = iter_log_files()
    if not used_files:
        print("[MISS] no jsonl logs found")
        raise SystemExit(2)

    for fp in sorted(used_files, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            for ln in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except Exception:
                    continue

                # provider label candidates
                meta = obj.get("meta") if isinstance(obj, dict) else None
                src = None
                if isinstance(meta, dict):
                    src = meta.get("source") or meta.get("provider") or meta.get("model")
                src = src or (obj.get("provider") if isinstance(obj, dict) else None)
                src = src or (obj.get("model") if isinstance(obj, dict) else None)
                p = prov_of(src) if isinstance(src,str) else None
                if not p:
                    continue

                payload = obj.get("raw") if isinstance(obj, dict) else None
                payload = payload if payload is not None else obj

                txt = extract_text(payload)
                if len(txt) >= MIN_CHARS and len(txt) > best_len[p]:
                    best[p] = txt
                    best_len[p] = len(txt)

            # 3つ揃ったら早期終了
            if all(best_len[k] >= MIN_CHARS for k in ("openai","gemini","claude")):
                break
        except Exception:
            continue

    if not all(best_len[k] >= MIN_CHARS for k in ("openai","gemini","claude")):
        print("[MISS] no real triplet in logs (need generator-side logging)")
        print("lens:", best_len)
        raise SystemExit(2)

    outdir = Path("examples/raw_local")
    outdir.mkdir(parents=True, exist_ok=True)
    for k in ("openai","gemini","claude"):
        (outdir/f"{k}.json").write_text(json.dumps({"text": best[k]}, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] {k}: chars={len(best[k])}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
