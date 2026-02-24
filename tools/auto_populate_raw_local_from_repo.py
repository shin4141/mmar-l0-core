from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXCLUDE = {".git", ".venv", "__pycache__", "node_modules"}
MAX_BYTES = 80_000_000
MIN_BYTES = 200

PROV_KEYS = {
    "openai": ["openai","gpt"],
    "gemini": ["gemini","google"],
    "claude": ["claude","anthropic"],
}
TEXT_KEYS = ["text","content","message","final","response","completion","output_text"]

def load_any(p: Path) -> Optional[Any]:
    txt = p.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        # jsonl fallback
        objs=[]
        ok=True
        for ln in txt.splitlines():
            ln=ln.strip()
            if not ln: 
                continue
            try:
                objs.append(json.loads(ln))
            except Exception:
                ok=False
                break
        return objs if (ok and objs) else None

def pick_text(d: Dict[str,Any]) -> str:
    for k in TEXT_KEYS:
        v=d.get(k)
        if isinstance(v,str) and v.strip():
            return v.strip()
    # nested
    for k,v in d.items():
        if isinstance(v, dict):
            t = pick_text(v)
            if t:
                return t
    return ""

def extract_triplet_from_obj(obj: Any) -> Optional[Dict[str,str]]:
    """
    Accept shapes:
    A) {"openai": "...", "gemini": "...", "claude":"..."} or aliases
    B) {"texts": {...}} / {"answers": {...}} / {"outputs": {...}}
    C) list of items with {"provider"/"model", "text"} etc.
    """
    # dict direct
    if isinstance(obj, dict):
        # wrapper dict
        for wrap in ("texts","answers","outputs","model_texts"):
            w=obj.get(wrap)
            if isinstance(w, dict):
                obj2 = w
                break
        else:
            obj2 = obj

        out = {}
        for prov, keys in PROV_KEYS.items():
            for kk in keys:
                v = obj2.get(kk)
                if isinstance(v, str) and v.strip():
                    out[prov] = v.strip()
                    break
                if isinstance(v, dict):
                    t = pick_text(v)
                    if t:
                        out[prov] = t
                        break
        if len(out)==3 and all(out[k] for k in ("openai","gemini","claude")):
            return out

        # provider-tagged single
        prov = obj.get("provider") or obj.get("source") or obj.get("vendor") or obj.get("model")
        txt  = pick_text(obj)
        if isinstance(prov,str) and txt:
            lp=prov.lower()
            out2={}
            if "openai" in lp or "gpt" in lp: out2["openai"]=txt
            if "gemini" in lp or "google" in lp: out2["gemini"]=txt
            if "claude" in lp or "anthropic" in lp: out2["claude"]=txt
            if out2:
                return out2

    # list stream
    if isinstance(obj, list):
        agg={}
        for it in obj:
            r = extract_triplet_from_obj(it)
            if isinstance(r, dict):
                agg.update(r)
                if len(agg)==3 and all(agg.get(k) for k in ("openai","gemini","claude")):
                    return {k: agg[k] for k in ("openai","gemini","claude")}
        # list of model-tagged records
        agg={}
        for it in obj:
            if not isinstance(it, dict):
                continue
            prov = it.get("provider") or it.get("model") or it.get("source")
            txt = pick_text(it)
            if isinstance(prov,str) and txt:
                lp=prov.lower()
                if "openai" in lp or "gpt" in lp: agg["openai"]=txt
                if "gemini" in lp or "google" in lp: agg["gemini"]=txt
                if "claude" in lp or "anthropic" in lp: agg["claude"]=txt
        if len(agg)==3 and all(agg.get(k) for k in ("openai","gemini","claude")):
            return {k: agg[k] for k in ("openai","gemini","claude")}
    return None

def main():
    files=[]
    for p in Path(".").rglob("*"):
        if any(part in EXCLUDE for part in p.parts):
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".json",".jsonl",".ndjson"):
            continue
        try:
            sz=p.stat().st_size
        except Exception:
            continue
        if sz < MIN_BYTES or sz > MAX_BYTES:
            continue
        files.append(p)

    # newer first
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    found=None
    used=None
    for p in files:
        obj=load_any(p)
        if obj is None:
            continue
        r=extract_triplet_from_obj(obj)
        if isinstance(r, dict) and any(r.get(k) for k in ("openai","gemini","claude")):
            # if partial, keep scanning to complete
            if found is None:
                found={}
            found.update(r)
            used = used or str(p)
            if len(found)==3 and all(found.get(k) for k in ("openai","gemini","claude")):
                break

    if not found or not all(found.get(k) for k in ("openai","gemini","claude")):
        print("[MISS] no real triplet in repo (need generator-side logging)")
        raise SystemExit(2)

    outdir=Path("examples/raw_local"); outdir.mkdir(parents=True, exist_ok=True)
    for k in ("openai","gemini","claude"):
        (outdir/f"{k}.json").write_text(json.dumps({"text": found[k]}, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] {k}: chars={len(found[k])}")
    print("[USED]", used)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
