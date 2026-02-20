from __future__ import annotations
from typing import Any, Dict, Optional

def extract_text(raw_doc: Dict[str, Any]) -> str:
    """
    raw_doc: {"meta": {...}, "raw": {...}} (schemas/ai_raw.v0.json)
    Strategy: prefer raw.text, else try common provider shapes, else empty.
    """
    raw = (raw_doc or {}).get("raw", {}) or {}
    if isinstance(raw.get("text"), str) and raw["text"].strip():
        return raw["text"]

    # generic fallbacks
    # OpenAI-ish: raw.choices[0].message.content
    try:
        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message", {})
            content = msg.get("content")
            if isinstance(content, str):
                return content
    except Exception:
        pass

    # Claude-ish: raw.content[0].text
    try:
        content = raw.get("content")
        if isinstance(content, list) and content:
            t = content[0].get("text")
            if isinstance(t, str):
                return t
    except Exception:
        pass

    # Gemini-ish: raw.candidates[0].content.parts[0].text
    try:
        cands = raw.get("candidates")
        if isinstance(cands, list) and cands:
            parts = cands[0].get("content", {}).get("parts", [])
            if isinstance(parts, list) and parts:
                t = parts[0].get("text")
                if isinstance(t, str):
                    return t
    except Exception:
        pass

    return ""
