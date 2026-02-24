from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, List, Optional

def extract_text_from_message(msg: Any) -> str:
    # ChatGPT export は形式が揺れるので best-effort
    if not isinstance(msg, dict):
        return ""
    # 1) content が dict/list
    c = msg.get("content")
    if isinstance(c, dict):
        parts = c.get("parts")
        if isinstance(parts, list):
            return "\n".join([p for p in parts if isinstance(p, str)]).strip()
        # sometimes {"text": "..."}
        t = c.get("text")
        if isinstance(t, str):
            return t.strip()
    if isinstance(c, list):
        ss=[]
        for it in c:
            if isinstance(it, str):
                ss.append(it)
            elif isinstance(it, dict):
                # {"text": "..."} or {"content": "..."}
                for k in ("text","content","message"):
                    v = it.get(k)
                    if isinstance(v, str):
                        ss.append(v)
        return "\n".join(ss).strip()

    # 2) message dict style
    for k in ("text","message","output_text","final","response"):
        v = msg.get(k)
        if isinstance(v, str):
            return v.strip()

    return ""

def walk_find_latest_assistant(convo: Any) -> str:
    # export: list of conversations -> each has mapping of nodes
    if not isinstance(convo, dict):
        return ""
    mapping = convo.get("mapping")
    if not isinstance(mapping, dict):
        return ""

    # nodes sorted by create_time if present
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
        role = ""
        if isinstance(author, dict):
            role = author.get("role") or ""
        if role != "assistant":
            continue
        t = extract_text_from_message(m)
        if t:
            latest = t
    return latest

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conversations", required=True)
    ap.add_argument("--out", default="examples/raw_local/openai.json")
    args = ap.parse_args()

    data = json.load(open(args.conversations, "r", encoding="utf-8", errors="replace"))
    if not isinstance(data, list) or not data:
        raise SystemExit("[ERR] conversations.json not list/empty")

    # “最新”は末尾想定（違う場合でも最低限は動く）
    text = walk_find_latest_assistant(data[-1])
    if not text:
        # fallback: 総当たりで最後に見つかったassistant本文
        for convo in reversed(data):
            text = walk_find_latest_assistant(convo)
            if text:
                break

    if not text:
        raise SystemExit("[ERR] could not extract assistant text from export")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    print("[OK] wrote", args.out, "chars=", len(text))
