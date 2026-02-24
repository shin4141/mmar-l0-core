from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path
from typing import Any, Dict, Optional, List

EXCLUDE = {".git", ".venv", "__pycache__"}
LINE_KEY_RE = re.compile(r"^line_(\d+)$")

def load_any(p: Path) -> Optional[Any]:
    txt = p.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        # JSONL fallback
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

def looks_like_v1(obj: Any) -> bool:
    # Accept schema marker or "lines" dict with line_### keys
    if isinstance(obj, dict):
        if obj.get("schema") == "mmar.dissent_diff.v1":
            return True
        lines = obj.get("lines")
        if isinstance(lines, dict) and any(LINE_KEY_RE.match(k) for k in lines.keys()):
            return True
        if any(LINE_KEY_RE.match(k) for k in obj.keys()):
            return True
    return False

def extract_lines(obj: Any) -> Dict[int, Dict[str, str]]:
    """
    Return: {line_no: {openai:..., gemini:..., claude:...}}
    """
    def get_texts(d: Dict[str, Any]) -> Dict[str, str]:
        mapping = {
            "openai": ["openai", "gpt"],
            "gemini": ["gemini", "google"],
            "claude": ["claude", "anthropic"],
        }
        out={}
        for k, keys in mapping.items():
            v=""
            for kk in keys:
                if kk in d and isinstance(d[kk], str):
                    v = d[kk]
                    break
            out[k]=v or ""
        return out

    lines: Dict[int, Dict[str,str]] = {}

    if isinstance(obj, dict):
        # preferred: obj["lines"]
        if isinstance(obj.get("lines"), dict):
            for k, vv in obj["lines"].items():
                m = LINE_KEY_RE.match(k)
                if not m:
                    continue
                i=int(m.group(1))
                if isinstance(vv, dict):
                    lines[i]=get_texts(vv)
            return lines

        # top-level line_###
        for k, vv in obj.items():
            m = LINE_KEY_RE.match(k)
            if not m:
                continue
            i=int(m.group(1))
            if isinstance(vv, dict):
                lines[i]=get_texts(vv)
        return lines

    return lines

def scan_repo_for_v1() -> Optional[Path]:
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
        if looks_like_v1(obj):
            return p
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1", default="out_v1/dissent_diff.latest.json", help="path to v1 line-key json")
    ap.add_argument("--out", default="examples/tmp/dissent_diff_v2.claim.json", help="path to v2 claim-key json")
    args = ap.parse_args()

    v1p = Path(args.v1)
    if not v1p.exists():
        found = scan_repo_for_v1()
        if not found:
            print("[MISS] v1 not found (file missing and repo scan empty).", file=sys.stderr)
            raise SystemExit(2)
        v1p = found

    obj = load_any(v1p)
    if obj is None or not looks_like_v1(obj):
        print("[MISS] v1 file exists but format not recognized:", v1p, file=sys.stderr)
        raise SystemExit(2)

    lines = extract_lines(obj)
    if len(lines) < 1:
        print("[MISS] v1 recognized but no lines extracted:", v1p, file=sys.stderr)
        raise SystemExit(2)

    # reconstruct per-provider full text from ordered lines
    keys = sorted(lines.keys())
    def join(provider: str) -> str:
        parts=[]
        for i in keys:
            t = (lines[i].get(provider) or "").strip()
            if t:
                parts.append(t)
        return "\n".join(parts)

    outdir = Path("examples/raw_local")
    outdir.mkdir(parents=True, exist_ok=True)
    for prov in ("openai","gemini","claude"):
        txt = join(prov)
        (outdir/f"{prov}.json").write_text(json.dumps({"text": txt}, ensure_ascii=False), encoding="utf-8")

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    if outp.exists(): outp.unlink()

    cmd = [sys.executable, "core/dissent_from_raw_v2.py",
           "--raw-openai", str(outdir/"openai.json"),
           "--raw-gemini", str(outdir/"gemini.json"),
           "--raw-claude", str(outdir/"claude.json"),
           "--out", str(outp)]
    subprocess.check_call(cmd)

    data = json.loads(outp.read_text(encoding="utf-8"))
    print("[USED_V1]", str(v1p))
    print("[DONE]", str(outp))
    print("[STATS]", data.get("stats"))
    # DEMO_GUARD: stop if demo text is present
    import re as _re
    _txt = json.dumps(data, ensure_ascii=False)
    if _re.search(r"DEMO:", _txt):
        print("[DEMO_GUARD] demo detected -> stop (need real texts in examples/raw_local/)")
        raise SystemExit(2)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
