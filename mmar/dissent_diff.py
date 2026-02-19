# mmar/dissent_diff.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from .resolution import Resolution

@dataclass
class DissentItem:
    key: str                       # claim_id など
    stances: Dict[str, str]        # {"openai":"agree", "gemini":"disagree", "claude":"unknown"}
    raw_refs: Dict[str, Any]       # 各モデルの参照（最小は空dictでOK）
    resolution: Resolution

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resolution"] = asdict(self.resolution)
        return d

def resolved_count(items: List[DissentItem]) -> int:
    return sum(1 for it in items if it.resolution.is_resolved)
