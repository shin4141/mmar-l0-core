#!/usr/bin/env python3
import json
from pathlib import Path

A_KW = [
    "アイデア", "案", "章立て", "比喩", "世界観", "たたき台", "発散", "探索", "仮説", "ブレスト",
    "どう考える", "可能性", "整理して", "分岐", "問い", "論点出し",
]
B_KW = [
    "バグ", "直す", "修正", "原因", "再現", "コミット", "ログ", "指示書", "実装", "設計", "統一",
    "ssot", "payload", "required_fields", "deep", "ui", "state", "テスト", "pr", "diff",
]


def infer_mode(text: str) -> str:
    t = text.lower()
    a = sum(1 for k in A_KW if k.lower() in t)
    b = sum(1 for k in B_KW if k.lower() in t)
    if a > b:
        return "A"
    return "B"


def build_prompt(mode: str) -> str:
    if mode == "A":
        return "MODE=A (EXPLORE)\nHypotheses:\nBranches:\nExperiments:\nOpen questions:\n"
    return "MODE=B (BUILD)\nAssumptions:\nOptions:\nGuardrails:\nNext step:\nUnknowns:\n"


def main() -> int:
    data = json.loads(Path("examples/smoke_ab_mode.json").read_text(encoding="utf-8"))
    failed = []
    for c in data.get("cases", []):
        text = c["text"]
        expected = c["expected_mode"]
        mode = infer_mode(text)
        if mode != expected:
            failed.append(f"{c['id']}: mode expected={expected} got={mode}")
            continue
        prompt = build_prompt(mode)
        for h in c.get("required_headers", []):
            if h not in prompt:
                failed.append(f"{c['id']}: missing header {h}")
    if failed:
        print("AB smoke: FAILED")
        for f in failed:
            print(f"- {f}")
        return 1
    print("AB smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
