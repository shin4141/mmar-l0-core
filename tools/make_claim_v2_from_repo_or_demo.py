from __future__ import annotations
import json, os, re, subprocess, sys
from pathlib import Path
from typing import Any, Dict, Optional

MAX_FILE_BYTES = 50_000_000
MIN_TEXT = 120

CAND_GLOBS = [
    "logs/*.jsonl", "logs/*.ndjson", "logs/*.json",
    "out*/*.jsonl", "out*/*.ndjson", "out*/*.json",
    "out_*/*.jsonl", "out_*/*.ndjson", "out_*/*.json",
]

def detect(label_hint: str) -> Optional[str]:
    s = (label_hint or "").lower()
    if "openai" in s or "gpt" in s: return "openai"
    if "gemini" in s or "google" in s: return "gemini"
    if "claude" in s or "anthropic" in s: return "claude"
    return None

def find_provider(obj: Any) -> Optional[str]:
    if isinstance(obj, dict):
        for k in ("provider","source","vendor","model"):
            v = obj.get(k)
            if isinstance(v,str):
                p = detect(v)
                if p: return p
        # payload signatures
        if "choices" in obj: return "openai"
        if "candidates" in obj: return "gemini"
        if "anthropic_version" in obj: return "claude"
        if "content" in obj and isinstance(obj["content"], list): return "claude"
    return None

WANT_KEYS = {"text","content","message","completion","output_text","final","response"}

def collect_text(obj: Any) -> str:
    best = ""
    def walk(x: Any):
        nonlocal best
        if isinstance(x, dict):
            for k,v in x.items():
                if isinstance(v,str) and (k in WANT_KEYS or len(v) >= MIN_TEXT):
                    if len(v) > len(best): best = v
                else:
                    walk(v)
        elif isinstance(x, list):
            for it in x: walk(it)
        elif isinstance(x, str):
            if len(x) > len(best): best = x
    walk(obj)
    return (best or "").strip()

def read_jsonl(p: Path):
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln: 
            continue
        try:
            yield json.loads(ln)
        except Exception:
            continue

def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

def main() -> int:
    # collect candidates
    files = []
    for g in CAND_GLOBS:
        for p in Path(".").glob(g):
            if not p.is_file():
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except Exception:
                continue
            files.append(p)

    found: Dict[str,str] = {}
    src: Dict[str,str] = {}

    # scan in order (latest-ish by mtime)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for p in files:
        suf = p.suffix.lower()
        if suf in (".jsonl",".ndjson"):
            for obj in read_jsonl(p):
                prov = find_provider(obj) or detect(p.name)
                if not prov:
                    continue
                txt = collect_text(obj)
                if len(txt) >= MIN_TEXT:
                    found[prov] = txt
                    src[prov] = str(p)
        else:
            obj = read_json(p)
            if obj is None:
                continue
            if isinstance(obj, list):
                for it in obj:
                    prov = find_provider(it) or detect(p.name)
                    if not prov:
                        continue
                    txt = collect_text(it)
                    if len(txt) >= MIN_TEXT:
                        found[prov] = txt
                        src[prov] = str(p)
            else:
                prov = find_provider(obj) or detect(p.name)
                if prov:
                    txt = collect_text(obj)
                    if len(txt) >= MIN_TEXT:
                        found[prov] = txt
                        src[prov] = str(p)

        if all(k in found for k in ("openai","gemini","claude")):
            break

    outdir = Path("examples/raw_local")
    outdir.mkdir(parents=True, exist_ok=True)

    if not all(k in found for k in ("openai","gemini","claude")):
        # demo fallback (always works)
        demo = {
            "openai": "DEMO: OpenAI output text here.\n\nClaim A...\nClaim B...",
            "gemini": "DEMO: Gemini output text here.\n\nClaim A...\nClaim B...",
            "claude": "DEMO: Claude output text here.\n\nClaim A...\nClaim B...",
        }
        for k,v in demo.items():
            (outdir/f"{k}.json").write_text(json.dumps({"text":v}, ensure_ascii=False), encoding="utf-8")
        print("[DEMO] repo logs/out did not contain 3 texts. Using demo triplet.")
    else:
        for k in ("openai","gemini","claude"):
            (outdir/f"{k}.json").write_text(json.dumps({"text":found[k]}, ensure_ascii=False), encoding="utf-8")
            print(f"[OK] {k}: extracted chars={len(found[k])} from {src.get(k,'?')}")

    outp = Path("examples/tmp/dissent_diff_v2.claim.json")
    if outp.exists(): outp.unlink()

    cmd = [
        sys.executable, "core/dissent_from_raw_v2.py",
        "--raw-openai", str(outdir/"openai.json"),
        "--raw-gemini", str(outdir/"gemini.json"),
        "--raw-claude", str(outdir/"claude.json"),
        "--out", str(outp),
    ]
    subprocess.check_call(cmd)
    data = json.loads(outp.read_text(encoding="utf-8"))
    print("[DONE]", outp)
    print("[STATS]", data.get("stats"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
