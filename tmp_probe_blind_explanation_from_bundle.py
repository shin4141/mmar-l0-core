from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tools import debate_api


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tmp_probe_blind_explanation_from_bundle.py /tmp/mmar_run_bundle_xxx")

    load_dotenv(Path("/Users/sn/workspaces/mmar-l0-core/.env"))
    bundle = Path(sys.argv[1])
    request_payload = json.loads((bundle / "request.json").read_text(encoding="utf-8"))
    response_payload = json.loads((bundle / "response.json").read_text(encoding="utf-8"))
    debate = response_payload.get("debate") or {}
    turns = debate.get("turns") or []
    transcript = "\n".join(
        f"Turn {turn.get('turn')} A: {turn.get('a', '')}\nTurn {turn.get('turn')} B: {turn.get('b', '')}"
        for turn in turns
    )
    payload = {
        "topic": request_payload.get("topic") or debate.get("topic") or "",
        "side_a": request_payload.get("side_a") or "",
        "side_b": request_payload.get("side_b") or "",
    }
    cfg = debate_api._normalize_config(
        {
            **payload,
            "turn_count": request_payload.get("turn_count") or debate.get("turn_count") or 3,
            "mode": request_payload.get("mode") or "casual",
            "fighter_a_provider": request_payload.get("fighter_a_provider") or response_payload.get("fighter_a_provider") or "openai",
            "fighter_b_provider": request_payload.get("fighter_b_provider") or response_payload.get("fighter_b_provider") or "openai",
            "judge_provider": "gemini",
            "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
        }
    )
    prompt = debate_api._judge_blind_explanation_prompt(payload["topic"], payload["side_a"], payload["side_b"], transcript)
    metrics = debate_api._judge_metrics(transcript, prompt)
    raw_text, debug = debate_api._call_gemini_match_chat(
        prompt,
        cfg.gemini_key,
        timeout_s=debate_api.JUDGE_PASS2_TIMEOUT_S,
        retries=debate_api.GEMINI_JUDGE_PASS2_RETRIES,
        max_output_tokens=debate_api.GEMINI_JUDGE_MAX_OUTPUT_TOKENS,
        debug_context={**metrics, "pass_label": "blind_explanation"},
        error_cls=debate_api.JudgeError,
        response_mime_type="application/json",
        thinking_budget=0,
    )
    parsed = debate_api._normalize_blind_explanation_result(
        debate_api._parse_judge_json_object(raw_text, mode="blind_explanation")
    )
    print(
        json.dumps(
            {
                "topic": payload["topic"],
                "side_a": payload["side_a"],
                "side_b": payload["side_b"],
                "debug": {
                    "model": debug.get("model"),
                    "finish_reason": debug.get("finish_reason"),
                    "status_code": debug.get("status_code"),
                },
                "result": parsed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
