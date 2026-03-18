from __future__ import annotations
from .base import Provider, LLMResult

class DummyProvider(Provider):
    name = "dummy"

    def available(self) -> bool:
        return True

    def generate(self, *, prompt: str, model: str = "dummy", temperature: float = 0.2) -> LLMResult:
        # deterministic placeholder
        txt = f"[DUMMY:{model}] " + prompt.strip().splitlines()[0][:180]
        return LLMResult(text=txt, raw={"prompt": prompt, "temperature": temperature}, provider=self.name, model=model)
