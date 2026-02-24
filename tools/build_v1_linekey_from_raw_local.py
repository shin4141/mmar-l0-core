from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

def robust_load(p: Path) -> Any:
    txt = p.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    try:
        return json.loads(txt)
    except Exception:
        return {"text": txt}

def get_text(obj: Any) -> str:
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str):
            return obj["text"]
        # fallback: dump
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)

def split_lines(t: str) -> list[str]:
    t = t.replace("\r\n","\n").replace("\r","\n")
    lines = [ln.strip() for ln in t.split("\n")]
    lines = [ln for ln in lines if ln]
    return lines

def main():
    outdir = Path("out_v1")
    outdir.mkdir(parents=True, exist_ok=True)
    outp = outdir / "dissent_diff.latest.json"

    src = Path("examples/raw_local")
    files = {k: src / f"{k}.json" for k in ("openai","gemini","claude")}

    # if missing, create demo triplet (guaranteed)
    for k,p in files.items():
        if not p.exists():
            src.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"text": f"DEMO: {k} line 1\nDEMO: {k} line 2"}, ensure_ascii=False), encoding="utf-8")

    texts = {}
    for k,p in files.items():
        texts[k] = get_text(robust_load(p))

    lines_by = {k: split_lines(v) for k,v in texts.items()}
    n = max(len(lines_by["openai"]), len(lines_by["gemini"]), len(lines_by["claude"]))
    n = max(n, 1)
    n = min(n, 200)  # cap

    lines: Dict[str, Dict[str,str]] = {}
    for i in range(n):
        lid = f"line_{i+1:03d}"
        lines[lid] = {
            "openai": lines_by["openai"][i] if i < len(lines_by["openai"]) else "",
            "gemini": lines_by["gemini"][i] if i < len(lines_by["gemini"]) else "",
            "claude": lines_by["claude"][i] if i < len(lines_by["claude"]) else "",
        }

    data = {
        "schema": "mmar.dissent_diff.v1",
        "key_type": "line",
        "lines": lines,
        "source": "examples/raw_local/{openai,gemini,claude}.json",
        "stats": {"lines_total": len(lines)},
    }
    outp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[WROTE]", outp)
    print("[LINES]", len(lines))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
