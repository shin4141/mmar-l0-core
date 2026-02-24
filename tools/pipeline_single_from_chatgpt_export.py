from __future__ import annotations
import argparse, json, os, sys, re
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.run_claim_v2_single import main as run_single  # uses core.claim_extract_min internally

def _extract_text_from_message(msg: dict) -> str:
    # ChatGPT export: best-effort across format variants
    if not isinstance(msg, dict):
        return ""
    c = msg.get("content")
    # v1: {"content":{"parts":[...]}}
    if isinstance(c, dict):
        parts = c.get("parts")
        if isinstance(parts, list):
            s = "\n".join([p for p in parts if isinstance(p, str)]).strip()
            if s:
                return s
        t = c.get("text")
        if isinstance(t, str) and t.strip():
            return t.strip()
    # sometimes list
    if isinstance(c, list):
        ss=[]
        for it in c:
            if isinstance(it, str) and it.strip():
                ss.append(it)
            elif isinstance(it, dict):
                for k in ("text","content","message"):
                    v = it.get(k)
                    if isinstance(v, str) and v.strip():
                        ss.append(v)
        s="\n".join(ss).strip()
        if s:
            return s
    # fallback keys
    for k in ("text","message","output_text","final","response"):
        v = msg.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _latest_assistant_text(convo: dict) -> str:
    mapping = convo.get("mapping")
    if not isinstance(mapping, dict):
        return ""
    nodes = list(mapping.values())
    def ts(n):
        try:
            return float(n.get("create_time") or 0)
        except Exception:
            return 0.0
    nodes.sort(key=ts)
    latest = ""
    for n in nodes:
        m = n.get("message") if isinstance(n, dict) else None
        if not isinstance(m, dict):
            continue
        author = m.get("author")
        role = author.get("role") if isinstance(author, dict) else ""
        if role != "assistant":
            continue
        t = _extract_text_from_message(m)
        if t:
            latest = t
    return latest

def _best_assistant_text(data: list) -> str:
    # priority: latest convo -> latest assistant
    for convo in reversed(data):
        if isinstance(convo, dict):
            t = _latest_assistant_text(convo)
            if t:
                return t
    # fallback: longest assistant text anywhere
    best = ""
    def walk(x):
        nonlocal best
        if isinstance(x, dict):
            if "author" in x and "content" in x:
                role = ""
                a = x.get("author")
                if isinstance(a, dict):
                    role = a.get("role") or ""
                if role == "assistant":
                    t = _extract_text_from_message(x)
                    if len(t) > len(best):
                        best = t
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for it in x:
                walk(it)
    walk(data)
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conversations", required=True, help="path to ChatGPT export conversations.json")
    ap.add_argument("--openai-out", default="examples/raw_local/openai.json")
    ap.add_argument("--convo-offset", type=int, default=0, help="0=latest convo, 1=one before, ...")
    ap.add_argument("--claim-out", default="examples/tmp/dissent_diff_v2.single.claim.json")
    args = ap.parse_args()

    p = Path(args.conversations)
    if not p.exists():
        raise SystemExit(f"[MISS] conversations.json not found: {p}")

    data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, list) or not data:
        raise SystemExit("[ERR] conversations.json is empty or not a list")

    text = ""
    off = max(0, int(args.convo_offset))
    idx = max(0, len(data)-1-off)
    text = _latest_assistant_text(data[idx]) if isinstance(data[idx], dict) else ""
    if not text:
        text = _best_assistant_text(data)
    if not text.strip():
        raise SystemExit("[ERR] could not extract assistant text from export")

    # DEMO guard: refuse if the extracted text is obviously a DEMO placeholder
    if re.search(r"\bDEMO:", text):
        raise SystemExit("[ERR] extracted text contains DEMO:. Choose another conversation export or source.")

    Path(args.openai_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.openai_out).write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")

    print("[OK] wrote", args.openai_out, "chars=", len(text))
    print("HEAD:", text[:180].replace("\n"," "))

    # run claim v2 single (calls tools/run_claim_v2_single.py main via import)
    sys.argv = ["run_claim_v2_single.py", "--raw-openai", args.openai_out, "--out", args.claim_out]
    run_single()

if __name__ == "__main__":
    main()
