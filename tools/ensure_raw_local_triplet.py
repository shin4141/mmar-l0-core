from __future__ import annotations
import json, os, re
from pathlib import Path

OUTDIR = Path("examples/raw_local")
OUTDIR.mkdir(parents=True, exist_ok=True)

# ====== strict signatures (VSCode/巨大ログ誤爆を避ける) ======
OPENAI_SIGS = [r'"choices"\s*:', r'"tool_calls"\s*:', r'"usage"\s*:', r'"model"\s*:\s*"(gpt|o\d)']
GEMINI_SIGS = [r'"candidates"\s*:', r'"promptFeedback"\s*:', r'"parts"\s*:', r'"model"\s*:\s*"(gemini|models/)']
CLAUDE_SIGS = [r'"anthropic_version"\s*:', r'"content"\s*:\s*\[', r'"type"\s*:\s*"text"', r'"model"\s*:\s*"(claude|anthropic)']

SEARCH_GLOBS = [
    "logs/**/*.jsonl", "logs/**/*.ndjson", "logs/**/*.json", "logs/**/*.txt",
    "out*/**/*.jsonl", "out*/**/*.ndjson", "out*/**/*.json", "out*/**/*.txt",
]

def _read_head(p: Path, n=300_000) -> str:
    try:
        b = p.open("rb").read(n)
        return b.decode("utf-8", "ignore")
    except Exception:
        return ""

def _is_placeholder(p: Path) -> bool:
    try:
        return p.stat().st_size < 50
    except Exception:
        return True

def _ok_existing() -> bool:
    for k in ["openai","gemini","claude"]:
        p = OUTDIR / f"{k}.json"
        if not p.exists() or _is_placeholder(p):
            return False
    return True

def _match_score(s: str, sigs: list[str]) -> int:
    return sum(1 for pat in sigs if re.search(pat, s, flags=re.IGNORECASE))

def _best_candidate(sigs: list[str]) -> Path | None:
    best = (0, None)
    for g in SEARCH_GLOBS:
        for p in Path(".").glob(g):
            if not p.is_file():
                continue
            # 巨大ログ誤爆を避ける（50MB超はスキップ）
            try:
                if p.stat().st_size > 50_000_000:
                    continue
            except Exception:
                continue
            head = _read_head(p)
            sc = _match_score(head, sigs)
            if sc > best[0]:
                best = (sc, p)
    return best[1] if best[0] >= 2 else None  # 2ヒット以上のみ採用

def _dump_payload(src: Path, dst: Path):
    txt = src.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    # JSON / JSONL / text の順で吸収
    try:
        obj = json.loads(txt)
    except Exception:
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
        obj = objs if (ok and objs) else {"text": txt}

    dst.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _write_demo():
    (OUTDIR / "openai.json").write_text(json.dumps({"text":"DEMO: OpenAI output text here."}, ensure_ascii=False), encoding="utf-8")
    (OUTDIR / "gemini.json").write_text(json.dumps({"text":"DEMO: Gemini output text here."}, ensure_ascii=False), encoding="utf-8")
    (OUTDIR / "claude.json").write_text(json.dumps({"text":"DEMO: Claude output text here."}, ensure_ascii=False), encoding="utf-8")
    print("[DEMO] No real raw found in repo logs/out. Wrote demo triplet to examples/raw_local/")

def main():
    if _ok_existing():
        print("[OK] raw_local already present.")
        return 0

    found = {}
    for k, sigs in [("openai", OPENAI_SIGS), ("gemini", GEMINI_SIGS), ("claude", CLAUDE_SIGS)]:
        cand = _best_candidate(sigs)
        if cand:
            found[k] = cand

    if len(found) == 3:
        for k, src in found.items():
            dst = OUTDIR / f"{k}.json"
            _dump_payload(src, dst)
            print(f"[OK] {k}: {src} -> {dst} bytes={dst.stat().st_size}")
        return 0

    # 実rawがrepo内に無い＝L0実行時に保存してない、が濃厚
    _write_demo()
    print("[MISS]", ",".join(sorted(set(["openai","gemini","claude"]) - set(found.keys()))))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
