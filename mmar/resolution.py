# mmar/resolution.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

RESOLVED_STATUSES = {"resolved", "accepted", "rejected"}

@dataclass(frozen=True)
class Resolution:
    status: str  # resolved|accepted|rejected|pending|unknown|needs-evidence
    by: Optional[str] = None
    note: Optional[str] = None

    @property
    def is_resolved(self) -> bool:
        return self.status in RESOLVED_STATUSES
