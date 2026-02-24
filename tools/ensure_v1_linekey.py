from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

EXCLUDE = {".git", ".venv", "__pycache__"}
LINE_KEY_RE = re.compile(r"^line_(\d+)$")

def load_any(p: Path) -> Optional[Any]:
    txt = p.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        # JSONL
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

def extract_texts(obj: Any) -> Dict[str,str]:
    # Accept several layouts; best-effort.
    aliases = {
        "openai": ["openai","gpt"],
        "gemini": ["gemini","google"],
        "claude": ["claude","anthropic"],
    }
    out = {"openai":"", "gemini":"", "claude":""}

    def pick(d: Dict[str,Any], keys: List[str]) -> str:
        for k in keys:
            v = d.get(k)
            if isinstance(v,str) and v.strip():
                return v.strip()
            if isinstance(v,dict):
                # common nested
                for kk in ("text","content","message","final","response"):
                    vv = v.get(kk)
                    if isinstance(vv,str) and vv.strip():
                        return vv.strip()
        return ""

    if isinstance(obj, dict):
        for prov, keys in aliases.items():
            out[prov] = pick(obj, keys) or out[prov]

        # sometimes stored under "texts" / "answers" / "outputs"
        for wrap in ("texts","answers","outputs","model_texts"):
            w = obj.get(wrap)
            if isinstance(w, dict):
                for prov, keys in aliases.items():
                    out[prov] = pick(w, keys) or out[prov]

        # sometimes provider+text
        prov = obj.get("provider") or obj.get("source") or obj.get("vendor") or obj.get("model")
        txt  = obj.get("text") or obj.get("content") or obj.get("message") or obj.get("final")
        if isinstance(prov,str) and isinstance(txt,str):
            lp = prov.lower()
            if "openai" in lp or "gpt" in lp: out["openai"] = txt.strip()
            if "gemini" in lp or "google" in lp: out["gemini"] = txt.strip()
            if "claude" in lp or "anthropic" in lp: out["claude"] = txt.strip()

    return out

def find_existing_v1() -> Optional[Tuple[Path, Any]]:
    # Look for a saved v1 (schema marker or many line_ keys)
    files=[]
    for p in Path(".").rglob("*.json"):
        if any(part in EXCLUDE for part in p.parts): 
            continue
        try:
            if p.stat().st_size < 200:
                continue
        except Exception:
            continue
        files.append(p)
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    for p in files:
        obj = load_any(p)
        if obj is None:
            continue
        s = ""
        try:
            s = json.dumps(obj)[:20000]
        except Exception:
            pass
        if "mmar.dissent_diff.v1" in s:
            return (p, obj)
        if isinstance(obj, dict) and any(LINE_KEY_RE.match(k) for k in obj.keys()):
            return (p, obj)
        if isinstance(obj, dict) and isinstance(obj.get("lines"), dict) and any(LINE_KEY_RE.match(k) for k in obj["lines"].keys()):
            return (p, obj)
    return None

def build_from_logs() -> Dict[str, Any]:
    # Try to reconstruct triplets from logs/*.jsonl or logs/*.json
    candidates=[]
    for pat in ["logs/*.jsonl","logs/*.ndjson","logs/*.json","out*/*.jsonl","out*/*.json","out_*/*.jsonl","out_*/*.json"]:
        candidates += list(Path(".").glob(pat))
    candidates = [p for p in candidates if p.is_file()]
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    lines: Dict[str, Dict[str,str]] = {}
    line_no = 1

    last = {"openai":"", "gemini":"", "claude":""}

    def commit_if_ready():
        nonlocal line_no
        if all(last[k] for k in ("openai","gemini","claude")):
            lid = f"line_{line_no:03d}"
            lines[lid] = dict(last)
            line_no += 1
            return True
        return False

    for p in candidates:
        obj = load_any(p)
        if obj is None:
            continue
        # if already looks like v1, just reuse
        if isinstance(obj, dict) and isinstance(obj.get("lines"), dict) and any(LINE_KEY_RE.match(k) for k in obj["lines"].keys()):
            return {"schema":"mmar.dissent_diff.v1","key_type":"line","lines":obj["lines"],"source":str(p)}
        if isinstance(obj, dict) and any(LINE_KEY_RE.match(k) for k in obj.keys()):
            # normalize to lines
            only = {k:v for k,v in obj.items() if LINE_KEY_RE.match(k) and isinstance(v,dict)}
            if only:
                return {"schema":"mmar.dissent_diff.v1","key_type":"line","lines":only,"source":str(p)}

        # stream parse
        stream = obj if isinstance(obj, list) else [obj]
        for it in stream:
            if not isinstance(it, dict):
                continue
            t = extract_texts(it)
            changed = False
            for k in ("openai","gemini","claude"):
                if t.get(k):
                    last[k] = t[k]
                    changed = True
            if changed:
                commit_if_ready()
            if len(lines) >= 50:  # cap
                break
        if len(lines) >= 3:
            break

    if lines:
        return {"schema":"mmar.dissent_diff.v1","key_type":"line","lines":lines,"source":"logs/out reconstruction"}

    # demo fallback (guaranteed)
    demo = {
        "line_001": {"openai":"DEMO: OpenAI line 1","gemini":"DEMO: Gemini line 1","claude":"DEMO: Claude line 1"},
        "line_002": {"openai":"DEMO: OpenAI line 2","gemini":"DEMO: Gemini line 2","claude":"DEMO: Claude line 2"},
    }
    return {"schema":"mmar.dissent_diff.v1","key_type":"line","lines":demo,"source":"DEMO"}

def main():
    existing = find_existing_v1()
    outp = Path("out_v1/dissent_diff.latest.json")
    outp.parent.mkdir(parents=True, exist_ok=True)

    if existing:
        p, obj = existing
        # normalize
        if isinstance(obj, dict) and "lines" in obj and isinstance(obj["lines"], dict):
            data = {"schema":"mmar.dissent_diff.v1","key_type":"line","lines":obj["lines"],"source":str(p)}
        elif isinstance(obj, dict) and any(LINE_KEY_RE.match(k) for k in obj.keys()):
            only = {k:v for k,v in obj.items() if LINE_KEY_RE.match(k) and isinstance(v,dict)}
            data = {"schema":"mmar.dissent_diff.v1","key_type":"line","lines":only,"source":str(p)}
        else:
            data = obj
        outp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[OK] used existing v1:", p)
        print("[WROTE]", outp)
        return 0

    data = build_from_logs()
    outp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[WROTE]", outp)
    print("[SOURCE]", data.get("source"))
    print("[LINES]", len((data.get("lines") or {})))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
