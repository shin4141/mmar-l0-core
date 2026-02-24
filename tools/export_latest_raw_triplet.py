from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

CANDIDATES = []
for pat in [
    "logs/*.jsonl",
    "logs/*.ndjson",
    "logs/*.json",
    "out_*/*.jsonl",
    "out_*/*.json",
    "out/*/*.jsonl",
    "out/*/*.json",
]:
    CANDIDATES += list(Path(".").glob(pat))

def detect_provider(obj: Any) -> Optional[str]:
    # best-effort heuristics
    if isinstance(obj, dict):
        # explicit labels
        for k in ("provider","source","vendor"):
            v = obj.get(k)
            if isinstance(v, str):
                lv = v.lower()
                if "openai" in lv or "gpt" in lv: return "openai"
                if "gemini" in lv or "google" in lv: return "gemini"
                if "claude" in lv or "anthropic" in lv: return "claude"
        payload = obj.get("raw") or obj.get("payload") or obj.get("response") or obj
        if isinstance(payload, dict):
            if "choices" in payload: return "openai"
            if "candidates" in payload: return "gemini"
            # anthropic-ish: {"content":[{"type":"text","text":...}], ...}
            if "content" in payload and isinstance(payload["content"], list): return "claude"
            # some wrappers
            if "anthropic" in json.dumps(payload).lower(): return "claude"
        # fallback: look for signature keys in whole obj
        s = json.dumps(obj)[:20000].lower()
        if '"choices"' in s: return "openai"
        if '"candidates"' in s: return "gemini"
        if '"anthropic"' in s or '"content"' in s and '"type"' in s: return "claude"
    return None

def extract_payload(obj: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get("raw") or obj.get("payload") or obj.get("response") or obj
    return obj

best: Dict[str, Tuple[int, Any, str]] = {}  # provider -> (seq, payload, srcfile)

seq = 0
for fp in CANDIDATES:
    try:
        if fp.suffix.lower() in (".jsonl", ".ndjson"):
            for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line: 
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                prov = detect_provider(obj)
                if prov:
                    seq += 1
                    best[prov] = (seq, extract_payload(obj), str(fp))
        else:
            # .json : could be dict or list
            try:
                obj = json.loads(fp.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            if isinstance(obj, list):
                for it in obj:
                    prov = detect_provider(it)
                    if prov:
                        seq += 1
                        best[prov] = (seq, extract_payload(it), str(fp))
            else:
                prov = detect_provider(obj)
                if prov:
                    seq += 1
                    best[prov] = (seq, extract_payload(obj), str(fp))
    except Exception:
        continue

outdir = Path("examples/raw_local")
outdir.mkdir(parents=True, exist_ok=True)

missing = []
for prov in ("openai","gemini","claude"):
    if prov not in best:
        missing.append(prov)
        continue
    _, payload, src = best[prov]
    outp = outdir / f"{prov}.json"
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {prov}: wrote {outp}  (from {src})  bytes={outp.stat().st_size}")

if missing:
    print("[MISS]", ",".join(missing))
    raise SystemExit(2)

