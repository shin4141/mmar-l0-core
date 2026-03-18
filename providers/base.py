from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class LLMResult:
    text: str
    raw: Dict[str, Any]
    provider: str
    model: str
    usage: Optional[Dict[str, Any]] = None

class ProviderError(Exception):
    pass

class Provider:
    name: str = "base"

    def available(self) -> bool:
        """Return True if this provider is configured (env keys etc.)."""
        return False

    def generate(self, *, prompt: str, model: str, temperature: float = 0.2) -> LLMResult:
        raise NotImplementedError
