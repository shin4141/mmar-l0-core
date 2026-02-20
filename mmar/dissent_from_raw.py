from __future__ import annotations
from typing import Any, Dict, List, Tuple
from .raw_extract import extract_text

def _lines(t: str, max_lines: int = 50) -> List[str]:
    # normalize
    t = (t or "").replace("\r\n", "\n").replace("\r", "\n")
    # split, strip, drop empties
    ls = [x.strip() for x in t.split("\n")]
    ls = [x for x in ls if x]
    return ls[:max_lines]

def build_dissent_diff(raw_docs: List[Dict[str, Any]]) -> List[dict]:
    """
    v1: line-based dissent.
    - baseline = first non-empty provider text
    - keys = line_001.. based on baseline lines
    - stance per provider: same/diff/unknown (compare line-by-line; missing line => unknown)
    - resolution defaults pending
    """
    texts: Dict[str, str] = {}
    order: List[str] = []
    for d in raw_docs:
        src = (d.get("meta") or {}).get("source", "unknown")
        texts[src] = extract_text(d)
        order.append(src)

    baseline_src = None
    for src in order:
        if texts.get(src):
            baseline_src = src
            break

    if not baseline_src:
        return []

    base_lines = _lines(texts[baseline_src])
    items: List[dict] = []

    for idx, base in enumerate(base_lines, start=1):
        key = f"line_{idx:03d}"
        stances: Dict[str, str] = {}
        for src in set(order):
            ls = _lines(texts.get(src, ""))
            if len(ls) < idx:
                stances[src] = "unknown"
            else:
                stances[src] = "same" if ls[idx-1] == base else "diff"

        # skip if all known are same
        vals = [v for v in stances.values() if v != "unknown"]
        if vals and all(v == "same" for v in vals):
            continue

        items.append({
            "key": key,
            "baseline": {"source": baseline_src, "text": base},
            "stances": stances,
            "raw_refs": {"note": "v1 line-based: compare extracted output text per line"},
            "resolution": {"status": "pending", "by": None, "note": None},
        })

    return items
