from __future__ import annotations
from typing import Any, Dict, List
from .resolution import Resolution
from .raw_extract import extract_text

def build_dissent_diff(raw_docs: List[Dict[str, Any]]) -> List[dict]:
    """
    Minimal dissent:
    - key = "output_text"
    - stance = "same"/"diff" compared to the first non-empty text
    - resolution.status default "pending" (so resolved_count stays 0 until resolution is set)
    """
    texts = {}
    order = []
    for d in raw_docs:
        src = (d.get("meta") or {}).get("source", "unknown")
        t = extract_text(d)
        texts[src] = t
        order.append(src)

    # pick baseline = first non-empty
    baseline = ""
    for src in order:
        if texts.get(src):
            baseline = texts[src]
            break

    stances = {}
    for src, t in texts.items():
        if not t or not baseline:
            stances[src] = "unknown"
        else:
            stances[src] = "same" if t == baseline else "diff"

    # if everything same or unknown, no dissent item
    vals = [v for v in stances.values() if v != "unknown"]
    if vals and all(v == "same" for v in vals):
        return []

    return [{
        "key": "output_text",
        "stances": stances,
        "raw_refs": {"note": "v0 minimal: compare extracted output text"},
        "resolution": {"status": "pending", "by": None, "note": None}
    }]
