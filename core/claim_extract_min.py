from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Dict, Any

_BULLET = re.compile(r"^\s*(?:[-*•]|(\d+)[\.\)])\s+")

def _normalize_ws(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _split_blocks(text: str) -> List[str]:
    text = _normalize_ws(text)
    if not text:
        return []
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    return blocks if blocks else [text]

def _split_bullets(block: str) -> List[str]:
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    if sum(1 for ln in lines if _BULLET.search(ln)) >= max(2, len(lines)//2):
        out = []
        for ln in lines:
            ln2 = _BULLET.sub("", ln).strip()
            if ln2:
                out.append(ln2)
        return out
    return [block.strip()]

def _split_sentences(block: str, max_chars: int = 260) -> List[str]:
    # 雑に句点/終端記号で分割→短い塊は束ねる
    parts = re.split(r"(?<=[\.\!\?。！？])\s+", block.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []
    chunks = []
    buf = ""
    for p in parts:
        if not buf:
            buf = p
            continue
        if len(buf) + 1 + len(p) <= max_chars:
            buf = f"{buf} {p}"
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks

def extract_claims(text: str, claim_prefix: str = "claim") -> List[Dict[str, Any]]:
    """
    最小ヒューリスティクス：
    - 空行ブロック
    - 箇条書きっぽければ bullet 単位
    - それ以外は sentence chunk
    """
    blocks = _split_blocks(text)
    claims: List[str] = []
    for b in blocks:
        for bb in _split_bullets(b):
            bb = bb.strip()
            if len(bb) < 5:
                continue
            if len(bb) > 420:
                claims.extend(_split_sentences(bb))
            else:
                claims.append(bb)
    # 冪等：空/重複を落とす
    uniq = []
    seen = set()
    for c in claims:
        c2 = _normalize_ws(c)
        key = c2.lower()
        if not c2 or key in seen:
            continue
        seen.add(key)
        uniq.append(c2)

    out = []
    for i, c in enumerate(uniq, 1):
        out.append({"claim_id": f"{claim_prefix}_{i:03d}", "text": c})
    return out
