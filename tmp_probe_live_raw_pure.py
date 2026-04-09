from __future__ import annotations

import json
import os
import time
import traceback
import uuid
from pathlib import Path

from tools import debate_api_pure as pure


TOPIC = "宇宙人はこの銀河に存在するか"
SIDE_A = "存在しない"
SIDE_B = "存在する"
TIMEOUT_SECONDS = 45
ARTIFACT_DIR = Path("/tmp/live_raw_probe")
JSON_PATH = ARTIFACT_DIR / "live_raw_probe.json"
LOG_PATH = ARTIFACT_DIR / "live_raw_probe.log"


def _log(lines: list[str], message: str) -> None:
    stamped = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    lines.append(stamped)


def _flush(json_payload: dict, log_lines: list[str]) -> None:
    JSON_PATH.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    pure.REQUEST_TIMEOUT_S = TIMEOUT_SECONDS
    run_id = uuid.uuid4().hex[:12]
    payload = {
        "topic": TOPIC,
        "side_a": SIDE_A,
        "side_b": SIDE_B,
        "turn_count": 3,
        "mode": "pro",
        "fighter_a_provider": "openai",
        "fighter_b_provider": "openai",
        "_disable_live_judge": True,
    }
    cfg = pure._normalize_config(payload)
    session = pure._session_runtime(cfg)
    turns: list[dict] = []
    transcript = ""
    log_lines: list[str] = []
    results: list[dict] = []
    total_started = time.time()

    _log(log_lines, f"run_id={run_id} topic={TOPIC!r} timeout={TIMEOUT_SECONDS}s model={cfg.fighter_a_model}")
    payload_out = {
        "run_id": run_id,
        "topic": TOPIC,
        "timeout_seconds": TIMEOUT_SECONDS,
        "total_elapsed_sec": 0.0,
        "results": results,
    }
    _flush(payload_out, log_lines)

    for turn_no in range(1, 4):
        stage_label = pure._stage_label(turn_no, cfg.turn_count)
        for speaker in ("A", "B"):
            provider = cfg.fighter_a_provider if speaker == "A" else cfg.fighter_b_provider
            own_previous = pure._clean_text(pure._speaker_last_statement(speaker, turns))
            latest_opponent = pure._opponent_last_statement(speaker, turns)
            prompt = pure._pure_turn_prompt(cfg, speaker, turns, transcript, turn_no)
            fallback = pure._pure_turn_fallback(cfg, speaker, turn_no, latest_opponent, transcript, own_previous)

            started = time.time()
            started_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(started))
            status = "success"
            exception_message = ""
            raw_text = ""
            response_char_count = 0
            provider_mode = ""

            _log(log_lines, f"turn={turn_no} speaker={speaker} start provider={provider}")

            try:
                data = pure._speaker_turn_data(speaker, provider, prompt, cfg, fallback)
                ended = time.time()
                provider_mode = str(data.get("_provider_mode") or "")
                raw_text = pure._clean_text(data.get("_provider_raw_speech") or "")
                response_char_count = len(raw_text)
                provider_status = data.get("_provider_status") or {}
                reason = str(provider_status.get("reason") or "")
                if provider_mode != "live":
                    if reason == "timeout":
                        status = "timeout"
                    else:
                        status = "exception"
                    exception_message = reason or str(provider_status)
                visible_text = pure._sanitize_fighter_speech(pure._clean_text(data.get("speech") or fallback))
            except Exception as exc:  # defensive: should not happen if helper swallows provider errors
                ended = time.time()
                status = "exception"
                exception_message = f"{type(exc).__name__}: {exc}"
                visible_text = fallback
                provider_mode = "exception"
                raw_text = ""
                response_char_count = 0
                _log(log_lines, traceback.format_exc().rstrip())

            ended_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ended))
            elapsed = round(ended - started, 3)
            _log(
                log_lines,
                f"turn={turn_no} speaker={speaker} end status={status} provider_mode={provider_mode} elapsed={elapsed}s chars={response_char_count}",
            )

            results.append(
                {
                    "run_id": run_id,
                    "topic": TOPIC,
                    "turn_index": turn_no,
                    "speaker": speaker,
                    "start_ts": started_ts,
                    "end_ts": ended_ts,
                    "elapsed_sec": elapsed,
                    "status": status,
                    "model_name": cfg.fighter_a_model if speaker == "A" else cfg.fighter_b_model,
                    "response_char_count": response_char_count,
                    "exception_message": exception_message,
                    "raw_text": raw_text,
                    "provider_mode": provider_mode,
                }
            )
            payload_out["total_elapsed_sec"] = round(time.time() - total_started, 3)
            _flush(payload_out, log_lines)

            # Keep the run moving so later calls can still be observed even after a timeout.
            turn_entry = next((item for item in turns if item["turn"] == turn_no), None)
            if not turn_entry:
                turn_entry = {"turn": turn_no, "stage_label": stage_label, "a": "", "b": ""}
                turns.append(turn_entry)
            turn_entry["a" if speaker == "A" else "b"] = visible_text
            transcript = pure._append_transcript(transcript, turn_no, speaker, visible_text)

    total_elapsed = round(time.time() - total_started, 3)
    payload_out["total_elapsed_sec"] = total_elapsed
    _flush(payload_out, log_lines)
    print(json.dumps(payload_out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
