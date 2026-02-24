from __future__ import annotations
import json
import os, sys
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'..'))
if ROOT not in sys.path: sys.path.insert(0, ROOT)

from pathlib import Path
from providers.dummy import DummyProvider

def main():
    # minimal seed question
    q_path = Path("incoming/demo_question.txt")
    if q_path.exists():
        question = q_path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        question = "Explain the idea in 5 bullets."

    seed = DummyProvider().generate(prompt=question, model="seed").text
    counter_a = DummyProvider().generate(prompt=f"Counter+improve:\n{seed}", model="counter_a").text
    counter_b = DummyProvider().generate(prompt=f"Counter+improve:\n{seed}", model="counter_b").text
    merged = "MERGED:\n" + "\n".join([seed, counter_a, counter_b])

    turn = {
        "case_id": "Case TRIAD",
        "question": question,
        "seed_model": "dummy",
        "seed_answer": seed,
        "counter_a_model": "dummy",
        "counter_a": counter_a,
        "counter_b_model": "dummy",
        "counter_b": counter_b,
        "merged_answer": merged
    }
    Path("incoming/triad_turn.json").write_text(json.dumps(turn, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[WROTE] incoming/triad_turn.json")

if __name__ == "__main__":
    main()
