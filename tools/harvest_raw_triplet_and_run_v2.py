from __future__ import annotations
import json, os, re, sys, subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- scan scope: repo only (exclude .venv/.git) ---
EXCLUDE_DIRS = {".venv", ".git", "__pycache__"}
MAX_FILE_BYTES = 80_000_000   # 80MBまで
MIN_FILE_BYTES = 2_000        # 2KB以上
READ_HEAD = 600_000           # 先頭だけ読む

OPENAI_SIGS = [r'"choices"\s*:', r'"tool_calls"\s*:', r'"usage"\s*:', r'"model"\s*:\s*"(gpt|o\d)"']
GEMINI_SIGS = [r'"candidates"\s*:', r'"promptFeedback"\s*:', r'"parts"\s*:', r'"model"\s*:\s*"(gemini|models/)"']
CLAUDE_SIGS = [r'"anthropic_version"\s*:', r'"content"\s*:\s*\[', r'"type"\s*:\s*"text"', r'"model"\s*:\s*"(claude|anthropic)"']

WANT_KEYS = {"text","content","message","completion","output_text","final","response"}

def walk_files() -> List[Path]:
    out = []
    for p in Path(".").rglob("*"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".json",".jsonl",".ndjson",".txt"):
            continue
        try:
            sz = p.stat().st_size
        except Exception:
            continue
        if sz < MIN_FILE_BYTES or sz > MAX_FILE_BYTES:
            continue
        out.append(p)
    # 新しめ優先
    out.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return out

def read_head(p: Path) -> str:
    try:
        b = p.open("rb").read(READ_HEAD)
        return b.decode("utf-8", "ignore")
    except Exception:
        return ""

def score(head: str, sigs: List[str]) -> int:
    return sum(1 for pat in sigs if re.search(pat, head, flags=re.IGNORECASE))

def robust_load_text(p: Path) -> Any:
    txt = p.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    # JSON
    try:
        return json.loads(txt)
    except Exception:
        pass
    # JSONL
    objs = []
    ok = True
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln: 
            continue
        try:
            objs.append(json.loads(ln))
        except Exception:
            ok = False
            break
    if ok and objs:
        return objs
    # plain
    return {"text": txt}

def collect_strings(obj: Any, out: Optional[List[str]] = None) -> List[str]:
    if out is None: out = []
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
        if key in seen: 
            continue
        seen.add(key); uniq.append(s)
    uniq.sort(key=len, reverse=True)
    return ("\n".join(uniq[:10]))[:2_000_000]

def main() -> int:
    files = walk_files()

    best: Dict[str, Tuple[int, Path]] = {"openai": (0, Path()), "gemini": (0, Path()), "claude": (0, Path())}

    for p in files:
        head = read_head(p)
        so = score(head, OPENAI_SIGS)
        sg = score(head, GEMINI_SIGS)
        sc = score(head, CLAUDE_SIGS)
        if so > best["openai"][0]: best["openai"] = (so, p)
        if sg > best["gemini"][0]: best["gemini"] = (sg, p)
        if sc > best["claude"][0]: best["claude"] = (sc, p)

    # 採用条件：スコア2以上（誤爆防止）
    chosen = {}
    for k in ("openai","gemini","claude"):
        sc, p = best[k]
        if sc >= 2 and p.exists():
            chosen[k] = (sc, p)

    if len(chosen) < 3:
        print("[MISS] repo内に3本のraw候補が見つからない（=保存されてない可能性が高い）")
        print("best(openai):", best["openai"][0], str(best["openai"][1]))
        print("best(gemini):", best["gemini"][0], str(best["gemini"][1]))
        print("best(claude):", best["claude"][0], str(best["claude"][1]))
        return 2

    Path("logs/raw_latest").mkdir(parents=True, exist_ok=True)
    Path("examples/raw_local").mkdir(parents=True, exist_ok=True)
    Path("examples/tmp").mkdir(parents=True, exist_ok=True)

    for k in ("openai","gemini","claude"):
        sc, src = chosen[k]
        payload = robust_load_text(src)
        Path(f"logs/raw_latest/{k}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        text = extract_text(payload)
        Path(f"examples/raw_local/{k}.json").write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] {k}: {src} (score={sc}) -> logs/raw_latest/{k}.json, examples/raw_local/{k}.json chars={len(text)}")

    outp = Path("examples/tmp/dissent_diff_v2.claim.json")
    if outp.exists(): outp.unlink()

    cmd = [sys.executable, "core/dissent_from_raw_v2.py",
           "--raw-openai", "examples/raw_local/openai.json",
           "--raw-gemini", "examples/raw_local/gemini.json",
           "--raw-claude", "examples/raw_local/claude.json",
           "--out", str(outp)]
    subprocess.check_call(cmd)

    data = json.loads(outp.read_text(encoding="utf-8"))
    print("[DONE]", outp)
    print("[STATS]", data.get("stats"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
