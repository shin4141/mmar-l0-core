from __future__ import annotations

import json
import os
import re
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


OPENAI_MODEL = os.getenv("MMAR_DEBATE_OPENAI_MODEL", "gpt-5-mini")
ANTHROPIC_MODEL = os.getenv("MMAR_DEBATE_ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
GEMINI_MODEL = os.getenv("MMAR_DEBATE_GEMINI_MODEL", "gemini-1.5-flash")
REQUEST_TIMEOUT_S = 45
JUDGE_TIMEOUT_S = int(os.getenv("MMAR_DEBATE_JUDGE_TIMEOUT_S", "120"))
GEMINI_JUDGE_MAX_OUTPUT_TOKENS = int(os.getenv("MMAR_DEBATE_GEMINI_MAX_OUTPUT_TOKENS", "4096"))
GEMINI_JUDGE_RETRIES = int(os.getenv("MMAR_DEBATE_GEMINI_RETRIES", "1"))
JUDGE_PASS1_TIMEOUT_S = int(os.getenv("MMAR_DEBATE_JUDGE_PASS1_TIMEOUT_S", "60"))
JUDGE_PASS2_TIMEOUT_S = int(os.getenv("MMAR_DEBATE_JUDGE_PASS2_TIMEOUT_S", "90"))
GEMINI_JUDGE_PASS1_RETRIES = int(os.getenv("MMAR_DEBATE_GEMINI_PASS1_RETRIES", "1"))
GEMINI_JUDGE_PASS2_RETRIES = int(os.getenv("MMAR_DEBATE_GEMINI_PASS2_RETRIES", "1"))
GEMINI_JUDGE_DEBUG_PATH = Path(os.getenv("MMAR_GEMINI_JUDGE_DEBUG_PATH", "/tmp/mmar_gemini_judge_last.json"))
ASK_TIMEOUT_S = int(os.getenv("MMAR_DEBATE_ASK_TIMEOUT_S", "90"))
GEMINI_ASK_MAX_OUTPUT_TOKENS = int(os.getenv("MMAR_DEBATE_ASK_MAX_OUTPUT_TOKENS", "2048"))
GEMINI_ASK_RETRIES = int(os.getenv("MMAR_DEBATE_ASK_RETRIES", "1"))


@dataclass
class DebateConfig:
    topic: str
    side_a: str
    side_b: str
    turn_count: int
    mode: str
    openai_key: str
    anthropic_key: str
    gemini_key: str
    fighter_a_provider: str
    fighter_b_provider: str


class JudgeError(RuntimeError):
    def __init__(self, reason: str, message: str, *, debug: dict[str, Any] | None = None):
        super().__init__(message)
        self.reason = reason or "unknown"
        self.debug = debug or {}


JP_STOPWORDS = {
    "こと", "それ", "これ", "ため", "もの", "よう", "どこ", "どの", "その", "この", "あの",
    "そして", "しかし", "だから", "つまり", "直前", "主張", "議論", "制度", "導入", "限定", "常時",
    "評価", "条件", "安全", "立場", "相手", "自分", "要求", "論点", "反論", "理由", "可能", "必要",
    "基準", "定義", "ルール", "勝負", "支配", "議題", "優勢", "劣勢", "決定打", "決着",
}


def run_debate(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = _normalize_config(payload)
    debate, provider_statuses = _run_debate_with_provider_fallbacks(cfg)
    warning = _build_warning(provider_statuses)
    judge_info = provider_statuses.get("gemini", {})
    judge_meta = {
        "judge_mode": judge_info.get("mode", ""),
        "judge_reason": judge_info.get("reason", ""),
        "judge_stage": judge_info.get("judge_stage", ""),
        "judge_provider": judge_info.get("judge_provider", "gemini"),
        "judge_model": judge_info.get("judge_model", GEMINI_MODEL),
        "judge_request_variant": judge_info.get("judge_request_variant", ""),
        "judge_request_url": judge_info.get("judge_request_url", ""),
        "judge_request_body_shape": judge_info.get("judge_request_body_shape", ""),
        "judge_request_has_generation_config": bool(judge_info.get("judge_request_has_generation_config", False)),
        "judge_prompt_chars": int(judge_info.get("judge_prompt_chars", 0) or 0),
        "judge_raw_received": bool(judge_info.get("judge_raw_received", False)),
        "judge_parse_success": bool(judge_info.get("judge_parse_success", False)),
    }
    return {
        "ok": True,
        "mode": _derive_mode(provider_statuses),
        "warning": warning,
        "judge_meta": judge_meta,
        "output_meta": judge_meta,
        "provider_statuses": provider_statuses,
        "debate": debate,
    }


def ask_match_gemini(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    match = payload.get("match")
    if not isinstance(match, dict):
        raise ValueError("missing_match")
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("missing_question")
    api_keys = payload.get("api_keys") if isinstance(payload.get("api_keys"), dict) else {}
    gemini_key = str(api_keys.get("gemini") or os.getenv("GEMINI_API_KEY") or "").strip()
    provider_status = _provider_entry("live-ready" if gemini_key else "mock", "api key missing" if not gemini_key else "")
    if not gemini_key:
        return {
            "ok": False,
            "error": "api key missing",
            "provider_status": provider_status,
            "answer": "",
        }
    prompt = _ask_match_prompt(match, question)
    try:
        answer, debug = _call_gemini_match_chat(prompt, gemini_key)
        cleaned = _clean_text(answer)
        if not cleaned:
            raise RuntimeError("empty_response")
        return {
            "ok": True,
            "answer": cleaned,
            "provider_status": _provider_entry("live", ""),
            "finish_reason": debug.get("finish_reason", ""),
            "truncated": bool(debug.get("truncated")),
            "latency_ms": debug.get("latency_ms"),
        }
    except Exception as exc:
        reason = _classify_provider_reason(str(exc))
        return {
            "ok": False,
            "error": reason,
            "provider_status": _provider_entry("mock-fallback", reason),
            "answer": "",
        }


def _normalize_config(payload: dict[str, Any]) -> DebateConfig:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    topic = str(payload.get("topic") or "").strip()
    side_a = str(payload.get("side_a") or payload.get("sideA") or "").strip()
    side_b = str(payload.get("side_b") or payload.get("sideB") or "").strip()
    turn_count_raw = payload.get("turn_count", payload.get("turnCount", 5))
    try:
        turn_count = int(turn_count_raw)
    except Exception:
        turn_count = 5
    turn_count = max(3, min(7, turn_count))
    mode = str(payload.get("mode") or "casual").strip().lower()
    if mode not in {"casual", "pro"}:
        mode = "casual"
    api_keys = payload.get("api_keys") if isinstance(payload.get("api_keys"), dict) else {}
    fighter_a_provider = _normalize_fighter_provider(
        payload.get("fighter_a_provider")
        or payload.get("fighterAProvider")
        or ((payload.get("fighters") or {}).get("a") if isinstance(payload.get("fighters"), dict) else "")
        or "openai"
    )
    fighter_b_provider = _normalize_fighter_provider(
        payload.get("fighter_b_provider")
        or payload.get("fighterBProvider")
        or ((payload.get("fighters") or {}).get("b") if isinstance(payload.get("fighters"), dict) else "")
        or "anthropic"
    )
    openai_key = str(api_keys.get("openai") or os.getenv("OPENAI_API_KEY") or "").strip()
    anthropic_key = str(api_keys.get("anthropic") or os.getenv("ANTHROPIC_API_KEY") or "").strip()
    gemini_key = str(api_keys.get("gemini") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not topic or not side_a or not side_b:
        raise ValueError("missing_topic_or_positions")
    return DebateConfig(
        topic=topic,
        side_a=side_a,
        side_b=side_b,
        turn_count=turn_count,
        mode=mode,
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        gemini_key=gemini_key,
        fighter_a_provider=fighter_a_provider,
        fighter_b_provider=fighter_b_provider,
    )


def _run_debate_with_provider_fallbacks(cfg: DebateConfig) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    turns: list[dict[str, Any]] = []
    transcript = ""
    provider_statuses = _initial_provider_statuses(cfg)
    for turn_no in range(1, cfg.turn_count + 1):
        stage_label = _stage_label(turn_no, cfg.turn_count)
        prior_transcript = transcript
        a_latest_opponent = _opponent_last_statement("A", turns)
        b_latest_opponent = _opponent_last_statement("B", turns)
        a_prompt = _speaker_prompt("A", cfg.fighter_a_provider, cfg, turns, prior_transcript, turn_no, stage_label)
        a_data = _speaker_turn_data(
            provider=cfg.fighter_a_provider,
            prompt=a_prompt,
            cfg=cfg,
            fallback_speech=_fallback_speech("A", cfg, turns, turn_no, a_latest_opponent),
            provider_statuses=provider_statuses,
        )
        a_text = _clean_text(a_data.get("speech") or _fallback_speech("A", cfg, turns, turn_no, a_latest_opponent))
        a_meta = _normalize_turn_meta(a_data.get("meta"), "A", cfg, turns, a_text, a_latest_opponent)

        b_prompt = _speaker_prompt("B", cfg.fighter_b_provider, cfg, turns, prior_transcript, turn_no, stage_label)
        b_data = _speaker_turn_data(
            provider=cfg.fighter_b_provider,
            prompt=b_prompt,
            cfg=cfg,
            fallback_speech=_fallback_speech("B", cfg, turns, turn_no, b_latest_opponent),
            provider_statuses=provider_statuses,
        )
        b_text = _clean_text(b_data.get("speech") or _fallback_speech("B", cfg, turns, turn_no, b_latest_opponent))
        b_meta = _normalize_turn_meta(b_data.get("meta"), "B", cfg, turns, b_text, b_latest_opponent)

        transcript = _append_transcript(prior_transcript, turn_no, "A", a_text)
        transcript = _append_transcript(transcript, turn_no, "B", b_text)
        turns.append(
            {
                "turn": turn_no,
                "stage_label": stage_label,
                "a": a_text,
                "b": b_text,
                "meta": {"a": a_meta, "b": b_meta},
            }
        )
        if _should_end_match(cfg, turns):
            break

    summary = _judge_summary_data(cfg, turns, transcript, provider_statuses)
    debate = {
        "topic": cfg.topic,
        "turn_count": len(turns),
        "participants": {"a": _provider_label(cfg.fighter_a_provider), "b": _provider_label(cfg.fighter_b_provider), "judge": "Gemini"},
        "turns": turns,
        "summary": summary,
    }
    return debate, provider_statuses


def _initial_provider_statuses(cfg: DebateConfig) -> dict[str, dict[str, str]]:
    return {
        "openai": _provider_entry("live-ready" if cfg.openai_key else "mock", "api key missing" if not cfg.openai_key else ""),
        "anthropic": _provider_entry("live-ready" if cfg.anthropic_key else "mock", "api key missing" if not cfg.anthropic_key else ""),
        "gemini": {
            **_provider_entry("live-ready" if cfg.gemini_key else "mock", "api key missing" if not cfg.gemini_key else ""),
            "judge_provider": "gemini",
            "judge_stage": "provider_select",
            "judge_raw_received": False,
            "judge_parse_success": False,
        },
    }


def _provider_entry(mode: str, reason: str) -> dict[str, str]:
    return {"mode": mode, "reason": reason}


def _normalize_fighter_provider(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"openai", "gpt", "gpt-5-mini", "gpt5", "gpt5mini"}:
        return "openai"
    if text in {"anthropic", "claude", "claude-sonnet", "claude-sonnet-4-5-20250929"}:
        return "anthropic"
    raise ValueError("invalid_fighter_provider")


def _provider_label(provider: str) -> str:
    if provider == "openai":
        return "GPT"
    if provider == "anthropic":
        return "Claude"
    return provider


def _speaker_turn_data(
    provider: str,
    prompt: str,
    cfg: DebateConfig,
    fallback_speech: str,
    provider_statuses: dict[str, dict[str, str]],
) -> dict[str, Any]:
    fallback = {"speech": fallback_speech}
    key = _provider_key(cfg, provider)
    if not key:
        provider_statuses[provider] = _provider_entry("mock", "api key missing")
        return fallback
    try:
        if provider == "openai":
            raw = _call_openai(prompt, key)
        elif provider == "anthropic":
            raw = _call_anthropic(prompt, key)
        else:
            raise RuntimeError(f"unsupported_provider:{provider}")
        provider_statuses[provider] = _provider_entry("live", "")
        return _parse_json_response(raw, fallback)
    except Exception as e:
        provider_statuses[provider] = _provider_entry("mock-fallback", str(e))
        return fallback


def _judge_summary_data(
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    transcript: str,
    provider_statuses: dict[str, dict[str, str]],
) -> dict[str, Any]:
    fallback = _mock_summary(cfg, turns)
    _log_judge_stage(
        "judge-provider",
        {
            "provider": "gemini",
            "model": GEMINI_MODEL,
            "request_url": _gemini_generate_content_url(),
            "selected": True,
            "api_key_present": bool(cfg.gemini_key),
        },
    )
    if not cfg.gemini_key:
        provider_statuses["gemini"] = {
            **_provider_entry("mock", "api key missing"),
            "judge_provider": "gemini",
            "judge_model": GEMINI_MODEL,
            "judge_request_variant": "contents_with_generation_config",
            "judge_request_url": _gemini_generate_content_url(),
            "judge_request_body_shape": "contents+generationConfig",
            "judge_request_has_generation_config": True,
            "judge_prompt_chars": 0,
            "judge_stage": "provider_select",
            "judge_raw_received": False,
            "judge_parse_success": False,
        }
        _log_judge_stage("judge-fallback", {"reason": "api key missing", "stage": "provider_select"})
        return fallback
    judge_prompt_pass1 = _judge_pass1_prompt(cfg, turns, transcript)
    judge_metrics_pass1 = _judge_metrics(transcript, judge_prompt_pass1)
    try:
        try:
            judge_raw_pass1, judge_debug_pass1 = _call_gemini_match_chat(
                judge_prompt_pass1,
                cfg.gemini_key,
                timeout_s=JUDGE_PASS1_TIMEOUT_S,
                retries=GEMINI_JUDGE_PASS1_RETRIES,
                max_output_tokens=GEMINI_JUDGE_MAX_OUTPUT_TOKENS,
                debug_context={**judge_metrics_pass1, "pass_label": "judge_pass1"},
                error_cls=JudgeError,
            )
            try:
                pass1 = _parse_judge_pass1_response(judge_raw_pass1)
            except JudgeError as exc:
                raise JudgeError(exc.reason, str(exc), debug={**judge_debug_pass1, **exc.debug})
            _log_judge_stage(
                "judge-pass1-ok",
                {
                    "raw_received": bool(str(judge_raw_pass1 or "").strip()),
                    "raw_chars": len(str(judge_raw_pass1 or "")),
                    "parse_success": True,
                    "finish_reason": judge_debug_pass1.get("finish_reason", ""),
                },
            )
            provider_statuses["gemini"].update(
                {
                    "judge_provider": "gemini",
                    "judge_model": judge_debug_pass1.get("model", GEMINI_MODEL),
                    "judge_request_variant": judge_debug_pass1.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": judge_debug_pass1.get("request_url", _gemini_generate_content_url()),
                    "judge_request_body_shape": judge_debug_pass1.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(judge_debug_pass1.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                    "judge_stage": "judge_pass1",
                    "judge_raw_received": bool(str(judge_raw_pass1 or "").strip()),
                    "judge_parse_success": True,
                }
            )
        except JudgeError as exc:
            _log_judge_stage(
                "judge-pass1-fail",
                {
                    "raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                    "raw_chars": len(str(exc.debug.get("raw_text") or "")),
                    "parse_success": False,
                    "reason": exc.reason,
                    "provider_error": exc.debug.get("provider_error", ""),
                },
            )
            provider_statuses["gemini"].update(
                {
                    "judge_provider": "gemini",
                    "judge_model": exc.debug.get("model", GEMINI_MODEL),
                    "judge_request_variant": exc.debug.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": exc.debug.get("request_url", _gemini_generate_content_url()),
                    "judge_request_body_shape": exc.debug.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(exc.debug.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(exc.debug.get("judge_prompt_char_count", 0) or 0),
                    "judge_stage": "judge_pass1",
                    "judge_raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                    "judge_parse_success": False,
                }
            )
            raise
        judge_prompt_pass2 = _judge_pass2_prompt(cfg, turns, transcript, pass1)
        judge_metrics_pass2 = _judge_metrics(transcript, judge_prompt_pass2)
        try:
            judge_raw_pass2, judge_debug_pass2 = _call_gemini_match_chat(
                judge_prompt_pass2,
                cfg.gemini_key,
                timeout_s=JUDGE_PASS2_TIMEOUT_S,
                retries=GEMINI_JUDGE_PASS2_RETRIES,
                max_output_tokens=GEMINI_JUDGE_MAX_OUTPUT_TOKENS,
                debug_context={**judge_metrics_pass2, "pass_label": "judge_pass2"},
                error_cls=JudgeError,
            )
            try:
                pass2 = _parse_judge_pass2_response(judge_raw_pass2)
            except JudgeError as exc:
                raise JudgeError(exc.reason, str(exc), debug={**judge_debug_pass2, **exc.debug})
            _log_judge_stage(
                "judge-pass2-ok",
                {
                    "raw_received": bool(str(judge_raw_pass2 or "").strip()),
                    "raw_chars": len(str(judge_raw_pass2 or "")),
                    "parse_success": True,
                    "finish_reason": judge_debug_pass2.get("finish_reason", ""),
                },
            )
            provider_statuses["gemini"].update(
                {
                    "judge_provider": "gemini",
                    "judge_model": judge_debug_pass2.get("model", GEMINI_MODEL),
                    "judge_request_variant": judge_debug_pass2.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": judge_debug_pass2.get("request_url", _gemini_generate_content_url()),
                    "judge_request_body_shape": judge_debug_pass2.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(judge_debug_pass2.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                    "judge_stage": "judge_pass2",
                    "judge_raw_received": bool(str(judge_raw_pass2 or "").strip()),
                    "judge_parse_success": True,
                }
            )
        except JudgeError as exc:
            _log_judge_stage(
                "judge-pass2-fail",
                {
                    "raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                    "raw_chars": len(str(exc.debug.get("raw_text") or "")),
                    "parse_success": False,
                    "reason": exc.reason,
                    "provider_error": exc.debug.get("provider_error", ""),
                },
            )
            provider_statuses["gemini"].update(
                {
                    "judge_provider": "gemini",
                    "judge_model": exc.debug.get("model", GEMINI_MODEL),
                    "judge_request_variant": exc.debug.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": exc.debug.get("request_url", _gemini_generate_content_url()),
                    "judge_request_body_shape": exc.debug.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(exc.debug.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                    "judge_stage": "judge_pass2",
                    "judge_raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                    "judge_parse_success": False,
                }
            )
            raise
        summary = _normalize_summary(
            {
                **pass1,
                **pass2,
                "confidence": pass1.get("confidence") or fallback.get("confidence") or "Medium",
                "rule_expansion": fallback.get("rule_expansion") or "未生成",
                "rule_capture": fallback.get("rule_capture") or "未生成",
                "contradiction": fallback.get("contradiction") or "未生成",
                "contradiction_exposed": fallback.get("contradiction_exposed") or "未生成",
                "unresolved_residue": fallback.get("unresolved_residue") or "未生成",
                "provisional_judgment": pass1.get("reason_one_liner") or fallback.get("provisional_judgment") or "未生成",
                "full_rationale": fallback.get("full_rationale") or pass1.get("reason_one_liner") or "未生成",
                "key_disagreement_top3": fallback.get("key_disagreement_top3") or ["未生成"],
            }
        )
        provider_statuses["gemini"].update(
            {
                **_provider_entry("live", ""),
                "judge_provider": "gemini",
                "judge_model": judge_debug_pass2.get("model", GEMINI_MODEL),
                "judge_request_variant": judge_debug_pass2.get("request_variant", "contents_with_generation_config"),
                "judge_request_url": judge_debug_pass2.get("request_url", _gemini_generate_content_url()),
                "judge_request_body_shape": judge_debug_pass2.get("request_body_shape", "contents+generationConfig"),
                "judge_request_has_generation_config": bool(judge_debug_pass2.get("request_has_generation_config", True)),
                "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                "judge_stage": "judge_pass2",
                "judge_raw_received": bool(str(judge_raw_pass2 or "").strip()),
                "judge_parse_success": True,
            }
        )
        _record_gemini_judge_debug(
            {
                "status": "live",
                "reason": "",
                "model": judge_debug_pass2.get("model", GEMINI_MODEL),
                "status_code": judge_debug_pass2.get("status_code"),
                "latency_ms": (judge_debug_pass1.get("latency_ms") or 0) + (judge_debug_pass2.get("latency_ms") or 0),
                "raw_text": json.dumps({"pass1": pass1, "pass2": pass2}, ensure_ascii=False),
                "judge_pass1": {
                    "raw_text": judge_raw_pass1,
                    "judge_payload_char_count": judge_debug_pass1.get("judge_payload_char_count"),
                    "transcript_char_count": judge_debug_pass1.get("transcript_char_count"),
                    "judge_prompt_char_count": judge_debug_pass1.get("judge_prompt_char_count"),
                    "latency_ms": judge_debug_pass1.get("latency_ms"),
                    "finish_reason": judge_debug_pass1.get("finish_reason"),
                    "retry_count": judge_debug_pass1.get("retry_count"),
                    "provider_error": judge_debug_pass1.get("provider_error", ""),
                },
                "judge_pass2": {
                    "raw_text": judge_raw_pass2,
                    "judge_payload_char_count": judge_debug_pass2.get("judge_payload_char_count"),
                    "transcript_char_count": judge_debug_pass2.get("transcript_char_count"),
                    "judge_prompt_char_count": judge_debug_pass2.get("judge_prompt_char_count"),
                    "latency_ms": judge_debug_pass2.get("latency_ms"),
                    "finish_reason": judge_debug_pass2.get("finish_reason"),
                    "retry_count": judge_debug_pass2.get("retry_count"),
                    "provider_error": judge_debug_pass2.get("provider_error", ""),
                },
            }
        )
        _log_gemini_judge_event("judge_pass1", judge_debug_pass1)
        _log_gemini_judge_event("judge_pass2", judge_debug_pass2)
        return summary
    except JudgeError as exc:
        provider_statuses["gemini"].update(
            {
                **_provider_entry("mock-fallback", exc.reason),
                "judge_provider": "gemini",
                "judge_model": exc.debug.get("model", GEMINI_MODEL),
                "judge_request_variant": exc.debug.get("request_variant", "contents_with_generation_config"),
                "judge_request_url": exc.debug.get("request_url", _gemini_generate_content_url()),
                "judge_request_body_shape": exc.debug.get("request_body_shape", "contents+generationConfig"),
                "judge_request_has_generation_config": bool(exc.debug.get("request_has_generation_config", True)),
                "judge_prompt_chars": int(exc.debug.get("judge_prompt_char_count", 0) or 0),
                "judge_stage": str(exc.debug.get("pass_label", "") or provider_statuses["gemini"].get("judge_stage") or "judge_pass1"),
                "judge_raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                "judge_parse_success": False,
            }
        )
        debug = {
            "status": "mock-fallback",
            "reason": exc.reason,
            "exception_message": str(exc),
            "stack_trace": traceback.format_exc(),
            "model": GEMINI_MODEL,
            "prompt_chars": len(judge_prompt_pass1),
            **judge_metrics_pass1,
            **exc.debug,
        }
        path = _record_gemini_judge_debug(debug)
        _log_gemini_judge_event("mock-fallback", {**debug, "debug_path": str(path) if path else ""})
        _log_judge_stage("judge-fallback", {"reason": exc.reason, "stage": exc.debug.get("pass_label", ""), "debug_path": str(path) if path else ""})
        return fallback
    except Exception as exc:
        reason = _classify_provider_reason(str(exc))
        provider_statuses["gemini"].update(
            {
                **_provider_entry("mock-fallback", reason),
                "judge_provider": "gemini",
                "judge_model": GEMINI_MODEL,
                "judge_request_variant": "contents_with_generation_config",
                "judge_request_url": _gemini_generate_content_url(),
                "judge_request_body_shape": "contents+generationConfig",
                "judge_request_has_generation_config": True,
                "judge_prompt_chars": int(judge_metrics_pass1.get("judge_prompt_char_count", 0) or 0),
                "judge_stage": "",
                "judge_raw_received": False,
                "judge_parse_success": False,
            }
        )
        debug = {
            "status": "mock-fallback",
            "reason": reason,
            "exception_message": str(exc),
            "stack_trace": traceback.format_exc(),
            "model": GEMINI_MODEL,
            "prompt_chars": len(judge_prompt_pass1),
            **judge_metrics_pass1,
            "provider_error": str(exc),
        }
        path = _record_gemini_judge_debug(debug)
        _log_gemini_judge_event("mock-fallback", {**debug, "debug_path": str(path) if path else ""})
        _log_judge_stage("judge-fallback", {"reason": reason, "stage": "", "debug_path": str(path) if path else ""})
        return fallback


def _provider_key(cfg: DebateConfig, provider: str) -> str:
    if provider == "openai":
        return cfg.openai_key
    if provider == "anthropic":
        return cfg.anthropic_key
    if provider == "gemini":
        return cfg.gemini_key
    return ""


def _derive_mode(provider_statuses: dict[str, dict[str, str]]) -> str:
    modes = [entry.get("mode", "") for entry in provider_statuses.values()]
    if any(mode == "mock-fallback" for mode in modes):
        return "mock-fallback"
    if any(mode == "live" for mode in modes):
        return "live"
    return "mock"


def _build_warning(provider_statuses: dict[str, dict[str, str]]) -> str:
    parts = []
    for provider, info in provider_statuses.items():
        mode = info.get("mode", "")
        reason = info.get("reason", "")
        if mode == "live":
            continue
        if reason:
            parts.append(f"{provider}:{mode} ({reason})")
        else:
            parts.append(f"{provider}:{mode}")
    return "; ".join(parts)


def _stage_label(turn_no: int, turn_count: int) -> str:
    if turn_no == 1:
        return "Opening"
    if turn_no == 2:
        return "Rebuttal"
    if turn_no >= turn_count:
        return f"Rally {turn_no} / Closing"
    return f"Rally {turn_no}"


def _speaker_prompt(
    speaker: str,
    provider: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    transcript: str,
    turn_no: int,
    stage_label: str,
) -> str:
    own_position = cfg.side_a if speaker == "A" else cfg.side_b
    opposing_position = cfg.side_b if speaker == "A" else cfg.side_a
    role_name = f"Fighter {speaker} ({_provider_label(provider)})"
    history = _format_history(turns)
    opponent_last = _opponent_last_statement(speaker, turns)
    return (
        f"You are {role_name} in a structured debate prototype.\n"
        f"Topic: {cfg.topic}\n"
        f"Your position: {own_position}\n"
        f"Opponent position: {opposing_position}\n"
        f"Current round: Turn {turn_no} / {cfg.turn_count}\n"
        f"Stage label: {stage_label}\n"
        "Goal: advance your own case while directly engaging the latest opposing claim.\n"
        "Debate objective:\n"
        "- This is competitive debate, not balanced explanation.\n"
        "- Your job is to win the exchange, not to sound fair or neutral.\n"
        "- Generic explanation, polite balance, and safe compromise count as failure here.\n"
        "- If you do not attack the opponent's core, you are failing your role.\n"
        "- If you leave the opponent's win condition intact, you are losing.\n"
        "- Neutral or middle-of-the-road closing is failure.\n"
        "Losing conditions:\n"
        "- repeating generic explanation\n"
        "- failing to answer the opponent's core\n"
        "- flattening into both-sides language\n"
        "- ending with neutral compromise\n"
        "- hiding behind lines like '一概に言えない'\n"
        "- shifting into safe commentary instead of confrontation\n"
        "Requirements:\n"
        "- Respond entirely in natural Japanese.\n"
        "- Return strict JSON only.\n"
        "- Schema: {\"speech\":\"...\",\"move\":\"opening|rebuttal|rally|finish\",\"meta\":{\"phase\":\"opening|rebuttal|rally\",\"target_issue\":\"...\",\"attacked_weakness\":\"...\",\"new_issue\":\"...\",\"collapse_signal\":\"...\",\"finish_intent\":\"push|finish|extend\",\"end_match\":\"yes|no\"}}\n"
        "- Write a dense sequential debate response. In Japanese, target 300 to 800 characters.\n"
        "- Do not start with formulae like 'Turn 2で相手は...' or other mechanical round labels.\n"
        "- Turn 1 is opening: state your thesis, define the initial battlefield, and anticipate the opponent's first line of attack.\n"
        "- Turn 2 is rebuttal: directly counter the opponent opening and set the first pressure point.\n"
        "- Turn 3 is deepening: receive the opponent's core in one short line, attack one weakness, reinforce your stance, and introduce exactly one new issue/condition/counterexample if needed.\n"
        "- Turn 4 is the closing attempt: try to force a decision there if you have a structural break, condition failure, or decisive reframing.\n"
        "- Turn 5 is final argument only: do not open a new issue there; summarize, tighten, close, and push the verdict instead of ending neutrally.\n"
        "- Same-claim paraphrase is prohibited. The content must change in response to the opponent's immediate previous statement.\n"
        "- Do not write long opening summaries of the opponent's previous turn.\n"
        "- Do not use formulas such as 'Turn 1でAは...' or 'Turn 2でBは...'.\n"
        "- When receiving the opponent's previous move, state only its core in one short line.\n"
        "- Do not quote the opponent at length. If quotation is necessary, use only a very short phrase.\n"
        "- Do not add meta commentary about debate method, structure, or what you are trying to do.\n"
        "- Do not narrate the debate in the third person with lines like 'Aは〜', 'Bは〜', 'Aは最後に〜', or 'Bはここで〜'. Speak as the fighter, not as a commentator.\n"
        "- Write only the debate speech itself. Do not leak strategy notes, commentator notes, move labels, or planning language into the speech.\n"
        "- Do not say things like '相手の最新発言は〜を主戦場に据え', '次の一手として〜', 'このラリーは〜', 'ここでは〜を軸に再定義する', or any similar planning or実況 phrasing.\n"
        "- Never describe your debate strategy.\n"
        "- Never narrate what you are doing as a debater.\n"
        "- Speak only as the debater inside the argument.\n"
        "- Do not mention tactics, framing, structure, setup, or next-step planning.\n"
        "- Do not describe the debate as a debate.\n"
        "- Do not explain how you will attack. Just attack.\n"
        "- From Turn 3 onward, write in a direct striking style rather than an explanatory style.\n"
        f"{_mode_prompt_rules(cfg.mode)}"
        "- If there is no opponent statement yet, open by stating your own thesis and the attack line you expect from the opponent.\n"
        "- If needed, you may surface the opponent's implicit premises, motives, or incentives.\n"
        "- If opponent logic collapses, attempt to finish the debate.\n"
        "- If you judge that the opponent's logic has collapsed, end with a short closing argument instead of describing that you are closing.\n"
        "- If the opponent's claim collapses, you may explicitly say that it collapses, but attach one reason.\n"
        "- Set meta.end_match=yes only when you believe the exchange should stop now because of collapse, decisive rebuttal, proposition retreat, or issue loop.\n"
        "- Surface reasoning structure, not style points.\n"
        "- If the opponent changed the proposition, call it out explicitly.\n"
        "- If the opponent shifts burden of proof or breaks its own definition, attack that structure.\n"
        "- You may use one short sentence that compresses the whole debate into a single decisive line if it genuinely captures the break point.\n"
        f"{_speaker_role_rules(provider)}"
        "- Do not mention being an AI or the JSON schema.\n"
        f"Full debate history:\n{history}\n"
        f"Opponent last statement:\n{opponent_last}\n"
        f"Transcript so far:\n{transcript or '(none yet)'}\n"
    )


def _mode_prompt_rules(mode: str) -> str:
    if mode == "pro":
        return (
            "- Debate mode: Pro.\n"
            "- Use structured reasoning when helpful.\n"
            "- Definitions, criteria, and evidence are allowed.\n"
            "- Maintain logical consistency and argument depth.\n"
        )
    return (
        "- Debate mode: Casual.\n"
        "- This is a spectator debate.\n"
        "- Your goal is not to explain carefully.\n"
        "- Your goal is to win the exchange and create a memorable line.\n"
        "- Spectators should feel the clash.\n"
        "- Safe explanations are failure.\n"
        "- Write in normal conversational language.\n"
        "- Do not sound academic or formal.\n"
        "- Prefer examples and analogies over abstract concept words whenever possible.\n"
        "- Prefer concrete examples over abstract wording.\n"
        "- Avoid complex or technical phrasing.\n"
        "- If the same meaning can be said with a simpler word, use the simpler word.\n"
        "- At least once per turn include a simple everyday punch line or analogy.\n"
        "- At least once per turn include one short everyday punchy line such as 'それは苦しい', '話をずらしてる', 'そこが逃げ', or words with the same feel.\n"
        "- Do NOT rewrite the opponent's argument in a polished academic way.\n"
        "- Do not clean up or strengthen the opponent's claim for them.\n"
        "- Keep a natural speaking tone.\n"
        "- Be direct.\n"
        "- A bit sharp is acceptable.\n"
        "- If the opponent makes a clear mistake, point it out plainly.\n"
        "- Do not summarize the opponent academically.\n"
        "- Do not say 'from a structural perspective'.\n"
        "- Do not say 'the central issue is'.\n"
        "- Do not write like a research paper.\n"
        "- The debate should feel like two smart people arguing in real life, not two researchers writing essays.\n"
        "- Turn 1 should feel like a short hard declaration, not a lecture.\n"
        "- Turn 2 should identify the opponent's core and say where it breaks.\n"
        "- Turn 3 should act like Breaker: core -> weakness -> metaphor -> your case.\n"
        "- Turn 4 should try to end the match with a closing attempt.\n"
        "- Turn 5 should state your position in one decisive line and must not add a new issue.\n"
        "- At least once in Turn 4 or Turn 5, produce a decisive line spectators will remember.\n"
        "- The following count as failure: generic explanation, safe neutral tone, both sides language, repeating the same argument, ending without a decisive line.\n"
    )


def _speaker_role_rules(provider: str) -> str:
    if provider == "openai":
        return (
            "- Fighter role: Breaker.\n"
            "- First identify the opponent's core in one short line.\n"
            "- Then stab the weakness in one short line.\n"
            "- Use one audience-friendly analogy or metaphor when it sharpens the point.\n"
            "- After that, advance your own case.\n"
            "- Break the opponent's premise or frame before adding a broad general explanation.\n"
            "- Do not hide in abstract multi-sided commentary.\n"
            "- You may reverse the opponent's wording against them if that exposes a structural contradiction.\n"
            "- Treat metaphor as a weapon for audience understanding, not as decoration.\n"
            "- As GPT, you may take one step up and redefine the battlefield with a higher-order criterion, definition, or comparison frame when that gives you control.\n"
            "- You may attack the hidden premise that the opponent's strike depends on.\n"
            "- When you have regained control, you may end with a short decisive closing line.\n"
            "- Reduce overly polite transitions or hedging when a sharper formulation is stronger.\n"
        )
    if provider == "anthropic":
        return (
            "- Fighter role: Closer.\n"
            "- State one condition that must be true for the opponent's claim to stand.\n"
            "- Check whether that condition is actually met in this debate.\n"
            "- If it is not met, you may plainly declare that the claim collapses.\n"
            "- Prefer condition -> check -> collapse over long negative explanation.\n"
            "- Do not stop at denial; name the condition, test it, and if it fails, press the finish.\n"
            "- Turn 4 is the main place to attempt a finish if the condition is clearly unmet.\n"
            "- Turn 5 is final argument only, so do not add a brand-new line there.\n"
        )
    return ""


def _judge_prompt(cfg: DebateConfig, turns: list[dict[str, Any]], transcript: str) -> str:
    return _judge_pass1_prompt(cfg, turns, transcript)


def _judge_pass1_prompt(cfg: DebateConfig, turns: list[dict[str, Any]], transcript: str) -> str:
    return (
        "You are Judge Gemini Pass1.\n"
        f"Topic: {cfg.topic}\n"
        f"A: {cfg.side_a}\n"
        f"B: {cfg.side_b}\n"
        "Return fast primary judgment only.\n"
        "Respond entirely in natural Japanese.\n"
        "Major rule: the side that stays closer to the original proposition has a strong advantage.\n"
        "The side that stays closer to the original proposition has a major advantage.\n"
        "Penalize subject narrowing, timeframe shift, condition swap, and answering a different question.\n"
        "Replacing 'as before' with 'still possible in some new way' counts as proposition drift.\n"
        "Proposition fidelity must weigh heavily in winner and momentum.\n"
        "If one side commits a major proposition violation and the other side exposes it, that usually decides the match.\n"
        "Return strict JSON only:\n"
        "{"
        "\"winner\":{\"side\":\"A|B|Draw\",\"reason\":\"...\"},"
        "\"reason_one_liner\":\"...\","
        "\"confidence\":\"Low|Medium|High\","
        "\"momentum\":{\"a\":40,\"b\":60},"
        "\"turning_point_turn\":1"
        "}\n"
        "Keep winner/reason short. Momentum is pressure, not truth. Return only the turn number.\n"
        f"Transcript:\n{transcript}\n"
    )


def _judge_pass2_prompt(cfg: DebateConfig, turns: list[dict[str, Any]], transcript: str, pass1: dict[str, Any]) -> str:
    winner = pass1.get("winner") if isinstance(pass1.get("winner"), dict) else {}
    momentum = pass1.get("momentum") if isinstance(pass1.get("momentum"), dict) else {}
    return (
        "You are Judge Gemini Pass2 for a debate structure extraction UI.\n"
        f"Topic: {cfg.topic}\n"
        f"Side A position: {cfg.side_a}\n"
        f"Side B position: {cfg.side_b}\n"
        "Use the primary judgment below as the fixed baseline.\n"
        "Do not re-judge the winner from scratch in this pass.\n"
        "Extract the structural proof points that support that judgment.\n"
        "Respond entirely in natural Japanese.\n"
        "Return strict JSON only with this schema:\n"
        "{"
        "\"fatal_phrase\":{\"turn\":1,\"speaker\":\"A or B or A/B\",\"text\":\"...\",\"reason\":\"...\"},"
        "\"weak_spot\":{\"side\":\"A or B or both\",\"turn\":1,\"speaker\":\"A or B or A/B\",\"label\":\"...\",\"quote_excerpt\":\"...\",\"why_one_sentence\":\"...\",\"how_to_fix\":\"...\"},"
        "\"flip_condition\":\"...\","
        "\"gemini_takeaway\":{\"structural_explanation\":\"...\",\"debate_dynamic\":\"...\",\"quote\":\"...\"},"
        "\"gemini_quote\":{\"text\":\"...\"}"
        "}\n"
        "- Fatal Phrase means the earliest utterance where structural failure becomes visible, not the final blow.\n"
        "- Weak Spot is mandatory in every match, including Draw.\n"
        "- Weak Spot should identify one primary structural weakness such as repetition, drift, definition retreat, unanswered core, abstract evasion, circular logic, weak example, thin evidence, late condition-add, criteria swap, lack of concreteness, or overgeneralization.\n"
        "- Also use proposition-constraint labels when needed: 命題逸脱, 主語の縮小, 時間軸ずらし, 条件すり替え, 問いの再発明.\n"
        "- Weak Spot must include side, turn, speaker, a short quote_excerpt, one-sentence why, and one-sentence how_to_fix.\n"
        "- Flip condition must say what the losing side would have needed to add or change.\n"
        "- The explanation must be consistent with the final winner.\n"
        "- If the turning point favors the other side, explain how the winner ultimately retained control.\n"
        "- Do not let takeaway, fatal phrase, weak spot, or quote contradict the final winner and momentum.\n"
        "- Treat winner and momentum as binding constraints, not optional hints.\n"
        "- Reward the side that keeps answering the original proposition.\n"
        "- Penalize scope shift, timeframe shift, burden shift, proposition drift, condition swap, and answering a different question.\n"
        "- If one side changes 'humans' into exceptional humans, 'short-term' into long-term, or 'as before' into some new version, call that out as a structural weakness.\n"
        "- If one dramatic moment favors the losing side, explain why it did not survive into final control.\n"
        "- Weak Spot should diagnose the losing side in non-draw matches.\n"
        "- Fatal Phrase should support the winning narrative in non-draw matches.\n"
        "- Gemini Quote should match the winning narrative in non-draw matches.\n"
        "- Produce ONE memorable quote about the debate.\n"
        "- gemini_quote.text: maximum 12 Japanese words, must reflect the structural turning point, aphoristic or metaphorical style allowed, avoid generic debate advice, must be punchy and memorable.\n"
        "- The quote must be about THIS debate only.\n"
        "- The quote must refer to the concrete shift, contradiction, or collapse that happened here.\n"
        "- The quote must contain at least one concrete concept from this match.\n"
        "- The quote should sound like something a spectator remembers.\n"
        "- The quote must sound dynamic, not static.\n"
        "- The quote should imply movement, shift, collapse, or failed advance.\n"
        "- The quote should feel like the decisive line of a match.\n"
        "- Do not produce reusable debate wisdom.\n"
        "- Do not output lines like '基準を握った側が議論を支配する', '定義を握った側が勝つ', 'ルールを作る側が有利', 'whoever controls the definition wins', or any similar generic debate proverb.\n"
        "- Prefer contrast, reversal, or compression tied to this match.\n"
        "- Prefer motion verbs or movement words such as 動かなかった, 崩れた, 逃げた, ずれた, 薄まった, 折れた, 守れなかった, 立たなかった, 変わった, or すり替わった when they fit.\n"
        "- After the structural fields, add Gemini Takeaway as a 3-line memory aid.\n"
        "- structural_explanation: explain the structural reason for the result in plain language.\n"
        "- debate_dynamic: explain what actually happened in the debate dynamic.\n"
        "- quote: one short memorable Japanese line, max 20 Japanese words, sharp or insightful, preferably with metaphor, contrast, or reversal.\n"
        "- The quote must not just repeat reason_one_liner.\n"
        f"Pass1 winner: {_clean_text(winner.get('side') or '')}\n"
        f"Pass1 reason: {_clean_text(pass1.get('reason_one_liner') or '')}\n"
        f"Pass1 momentum: {_format_momentum(momentum)}\n"
        f"Pass1 turning point turn: {_clean_text(pass1.get('turning_point_turn') or '')}\n"
        f"Transcript:\n{transcript}\n"
    )


def _ask_match_prompt(match: dict[str, Any], question: str) -> str:
    topic = _clean_text(match.get("topic") or "")
    stance_a = _clean_text(match.get("stance_a") or match.get("side_a") or "")
    stance_b = _clean_text(match.get("stance_b") or match.get("side_b") or "")
    turns = match.get("transcript_json") if isinstance(match.get("transcript_json"), list) else []
    judge = match.get("judge_json") if isinstance(match.get("judge_json"), dict) else {}
    winner = judge.get("winner") if isinstance(judge.get("winner"), dict) else {}
    fatal = judge.get("fatal_phrase") if isinstance(judge.get("fatal_phrase"), dict) else {}
    weak_spot = judge.get("weak_spot") if isinstance(judge.get("weak_spot"), dict) else {}
    return (
        "You are Gemini, acting as the judge-grounded explainer for one specific debate match.\n"
        "Answer only from the material in this match record.\n"
        "Do not widen into generic outside knowledge unless the match itself already supports it.\n"
        "Do not give boilerplate disclaimers.\n"
        "Write in natural Japanese.\n"
        "Be concrete, short, and useful.\n"
        "Prefer pointing to exact turns or phrases from this match.\n"
        "Treat the original winner, momentum, weak spot, fatal phrase, turning point, and flip condition as the baseline judgment.\n"
        "Do not re-judge the winner from scratch unless the user explicitly asks you to challenge the original verdict.\n"
        "Do not flatten the match into a polite draw. If this match shows one side pressing, say that clearly.\n"
        "If the user gives their own opinion, test it against the judged result: say what survives, what fails, and what would still have to change.\n"
        "If the user asks why A lost or how A comes back, answer from the judged pressure first, not from abstract fairness.\n"
        "The first 1 to 2 sentences must state the conclusion first, then the reason.\n"
        "Keep those first 2 sentences short and decisive.\n"
        "If the user asks what would change the result, answer with specific additions, reframing, or burden shifts.\n"
        "If the user asks for a general rule, derive it from this match first and then generalize briefly.\n"
        "Structure:\n"
        "- First 1 to 2 sentences: direct conclusion, then the main reason.\n"
        "- Then 2 or 3 short bullets only.\n"
        "- Each bullet should be one sentence.\n"
        "- Do not use headings.\n"
        "- Do not repeat the same point in different wording.\n"
        "- Prefer one concrete turn or phrase over broad recap.\n"
        "- Keep total length under roughly 220 Japanese words.\n"
        f"Topic: {topic}\n"
        f"Stance A: {stance_a}\n"
        f"Stance B: {stance_b}\n"
        f"Main verdict: {_clean_text(judge.get('verdict_headline') or '')}\n"
        f"Winner: {_clean_text(winner.get('side') or '')}\n"
        f"Confidence: {_clean_text(judge.get('confidence') or '')}\n"
        f"Why: {_clean_text(judge.get('reason_one_liner') or '')}\n"
        f"Turning point: {_clean_text(judge.get('turning_point') or '')}\n"
        f"Fatal phrase: Turn {fatal.get('turn') or '?'} / {_clean_text(fatal.get('speaker') or '')} / {_clean_text(fatal.get('text') or '')}\n"
        f"Weak spot: {_clean_text(weak_spot.get('side') or '')} / Turn {_clean_text(weak_spot.get('turn') or '')} / {_clean_text(weak_spot.get('speaker') or '')} / {_clean_text(weak_spot.get('label') or '')} / {_clean_text(weak_spot.get('quote_excerpt') or '')} / {_clean_text(weak_spot.get('why_one_sentence') or weak_spot.get('why') or '')} / {_clean_text(weak_spot.get('how_to_fix') or '')}\n"
        f"Flip condition: {_clean_text(judge.get('flip_condition') or '')}\n"
        f"Momentum: {_format_momentum(judge.get('momentum'))}\n"
        f"Transcript:\n{_format_saved_transcript(turns)}\n"
        f"User question: {question}\n"
    )


def _format_saved_transcript(turns: list[Any]) -> str:
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        turn_no = turn.get("turn", "?")
        lines.append(f"Turn {turn_no} A: {_clean_text(turn.get('a') or '')}")
        lines.append(f"Turn {turn_no} B: {_clean_text(turn.get('b') or '')}")
    return "\n".join(lines).strip() or "(no transcript)"


def _gemini_generate_content_url() -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _format_momentum(value: Any) -> str:
    if isinstance(value, dict):
        return f"A {value.get('a', '?')} / B {value.get('b', '?')}"
    return _clean_text(value or "")


def _call_openai(prompt: str, api_key: str) -> str:
    payload = {"model": OPENAI_MODEL, "input": prompt}
    response = _post_json(
        "https://api.openai.com/v1/responses",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if isinstance(response.get("output_text"), str) and response["output_text"].strip():
        return response["output_text"]
    parts: list[str] = []
    for item in response.get("output", []) if isinstance(response.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _call_anthropic(prompt: str, api_key: str) -> str:
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 700,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _post_json(
        "https://api.anthropic.com/v1/messages",
        payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    parts: list[str] = []
    for block in response.get("content", []) if isinstance(response.get("content"), list) else []:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts).strip()


def _call_gemini(prompt: str, api_key: str) -> str:
    query = parse.urlencode({"key": api_key})
    url = f"{_gemini_generate_content_url()}?{query}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    response = _post_json(url, payload, headers={})
    parts: list[str] = []
    for candidate in response.get("candidates", []) if isinstance(response.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []) if isinstance(content.get("parts"), list) else []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "\n".join(parts).strip()


def _call_gemini_match_chat(
    prompt: str,
    api_key: str,
    *,
    timeout_s: int = ASK_TIMEOUT_S,
    retries: int = GEMINI_ASK_RETRIES,
    max_output_tokens: int = GEMINI_ASK_MAX_OUTPUT_TOKENS,
    debug_context: dict[str, Any] | None = None,
    error_cls: type[Exception] = RuntimeError,
) -> tuple[str, dict[str, Any]]:
    last_error: Exception | None = None
    current_max_output_tokens = max_output_tokens
    context = dict(debug_context or {})
    pass_label = str(context.get("pass_label") or "")
    for attempt in range(1, retries + 2):
        response, payload = _call_gemini_generate_content(
            prompt,
            api_key,
            temperature=0.15,
            max_output_tokens=current_max_output_tokens,
            timeout_s=timeout_s,
        )
        if not response.get("ok"):
            kind = str(response.get("error_kind") or "provider_error")
            status_code = response.get("status_code")
            message = str(response.get("exception_message") or "")
            reason = _classify_provider_reason(f"{kind}:{message}:{str(response.get('raw_body') or '')}")
            debug = {
                "attempt": attempt,
                "retry_count": max(0, attempt - 1),
                "status_code": status_code,
                "latency_ms": response.get("latency_ms"),
                "raw_body": response.get("raw_body", ""),
                "provider_error": message or kind or reason,
                "request_url": _gemini_generate_content_url(),
                "request_variant": "contents_with_generation_config",
                "request_body_shape": "contents+generationConfig",
                "request_has_generation_config": True,
                "model": GEMINI_MODEL,
                "pass_label": pass_label,
                **context,
            }
            if reason == "timeout" and attempt < retries + 1:
                if error_cls is JudgeError:
                    last_error = JudgeError(reason, message or "timeout", debug=debug)
                else:
                    last_error = error_cls(message or "timeout")
                continue
            if error_cls is JudgeError:
                raise JudgeError(reason, message or kind or reason, debug=debug)
            if kind == "http_error":
                raise error_cls(f"http_error:{status_code}:{str(response.get('raw_body') or '')[:400]}")
            if kind == "network_error":
                raise error_cls(f"network_error:{message}")
            if kind == "timeout":
                raise error_cls(message or "timeout")
            raise error_cls(f"{kind}:{message or str(response.get('raw_body') or '')[:400]}")
        data = response.get("data")
        if not isinstance(data, dict):
            if error_cls is JudgeError:
                raise JudgeError("schema_mismatch", "invalid_response_shape", debug={**context, "pass_label": pass_label})
            raise error_cls("invalid_response_shape")
        finish_reason = _gemini_finish_reason(data)
        text = _extract_gemini_text(data)
        debug = {
            "finish_reason": finish_reason,
            "truncated": finish_reason == "MAX_TOKENS",
            "latency_ms": response.get("latency_ms"),
            "max_output_tokens": current_max_output_tokens,
            "attempt": attempt,
            "request_url": _gemini_generate_content_url(),
            "request_variant": "contents_with_generation_config",
            "request_body_shape": "contents+generationConfig",
            "request_has_generation_config": True,
            "model": GEMINI_MODEL,
            "pass_label": pass_label,
            "judge_payload_char_count": len(json.dumps(payload, ensure_ascii=False)),
            "status_code": response.get("status_code"),
            "raw_body": response.get("raw_body", ""),
            "model_version": data.get("modelVersion", ""),
            "raw_text": text,
            "retry_count": max(0, attempt - 1),
            **context,
        }
        if not text.strip():
            if error_cls is JudgeError:
                raise JudgeError("empty_response", "gemini returned empty text", debug=debug)
            raise error_cls("empty_response")
        if finish_reason == "MAX_TOKENS" and attempt < retries + 1:
            current_max_output_tokens *= 2
            if error_cls is JudgeError:
                last_error = JudgeError("truncated", "truncated", debug=debug)
            else:
                last_error = error_cls("truncated")
            continue
        return text.strip(), debug
    if last_error:
        raise last_error
    if error_cls is JudgeError:
        raise JudgeError("unknown", "gemini call failed", debug={**context, "pass_label": pass_label})
    raise error_cls("ask_match_failed")


def _judge_metrics(transcript: str, judge_prompt: str) -> dict[str, int]:
    return {
        "transcript_char_count": len(str(transcript or "")),
        "judge_prompt_char_count": len(str(judge_prompt or "")),
    }


def _call_gemini_generate_content(
    prompt: str,
    api_key: str,
    *,
    temperature: float,
    max_output_tokens: int,
    timeout_s: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    query = parse.urlencode({"key": api_key})
    url = f"{_gemini_generate_content_url()}?{query}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    response = _post_json_verbose(url, payload, headers={}, timeout_s=timeout_s)
    return response, payload


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    response = _post_json_verbose(url, payload, headers)
    if not response.get("ok"):
        kind = str(response.get("error_kind") or "provider_error")
        status_code = response.get("status_code")
        raw_body = str(response.get("raw_body") or "")
        message = str(response.get("exception_message") or "")
        if kind == "http_error":
            raise RuntimeError(f"http_error:{status_code}:{raw_body[:400]}")
        if kind == "network_error":
            raise RuntimeError(f"network_error:{message}")
        if kind == "timeout":
            raise RuntimeError(message or "timeout")
        raise RuntimeError(f"{kind}:{message or raw_body[:400]}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("invalid_response_shape")
    return data


def _post_json_verbose(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout_s: int = REQUEST_TIMEOUT_S,
) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    started = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            latency_ms = int((time.monotonic() - started) * 1000)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "error_kind": "invalid_json_response",
                    "status_code": resp.getcode(),
                    "latency_ms": latency_ms,
                    "raw_body": body,
                    "exception_message": body[:400],
                }
            if not isinstance(data, dict):
                return {
                    "ok": False,
                    "error_kind": "invalid_response_shape",
                    "status_code": resp.getcode(),
                    "latency_ms": latency_ms,
                    "raw_body": body,
                    "exception_message": "top level response is not an object",
                }
            return {
                "ok": True,
                "status_code": resp.getcode(),
                "latency_ms": latency_ms,
                "raw_body": body,
                "data": data,
            }
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "error_kind": "http_error",
            "status_code": exc.code,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "raw_body": body,
            "exception_message": str(exc),
        }
    except error.URLError as exc:
        message = str(exc.reason)
        reason_kind = "timeout" if "timed out" in message.lower() else "network_error"
        return {
            "ok": False,
            "error_kind": reason_kind,
            "status_code": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "raw_body": "",
            "exception_message": message,
        }
    except TimeoutError as exc:
        return {
            "ok": False,
            "error_kind": "timeout",
            "status_code": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "raw_body": "",
            "exception_message": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_kind": "provider_error",
            "status_code": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "raw_body": "",
            "exception_message": str(exc),
        }


def _parse_json_response(raw_text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return dict(fallback)
    cleaned = text
    block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if block:
        cleaned = block.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            cleaned = text[start : end + 1]
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return dict(fallback)


def _parse_judge_summary_response(raw_text: str) -> dict[str, Any]:
    return _normalize_summary(_parse_judge_json_object(raw_text, mode="summary"))


def _parse_judge_pass1_response(raw_text: str) -> dict[str, Any]:
    parsed = _parse_judge_json_object(raw_text, mode="pass1")
    winner = parsed.get("winner")
    if not isinstance(winner, (dict, str)):
        raise JudgeError("schema_mismatch", "judge pass1 missing winner", debug={"raw_text": raw_text, "parsed_summary": parsed})
    reason = _clean_text(parsed.get("reason_one_liner") or "")
    if not reason:
        raise JudgeError("schema_mismatch", "judge pass1 missing reason_one_liner", debug={"raw_text": raw_text, "parsed_summary": parsed})
    turning_point_turn = extract_turn_number_from_text(parsed.get("turning_point_turn")) or 3
    return {
        "winner": winner,
        "reason_one_liner": reason,
        "confidence": _clean_text(parsed.get("confidence") or "Medium"),
        "momentum": parsed.get("momentum"),
        "turning_point": f"Turn {turning_point_turn}で流れが大きく動いた。",
        "turning_point_turn": turning_point_turn,
    }


def _parse_judge_pass2_response(raw_text: str) -> dict[str, Any]:
    parsed = _parse_judge_json_object(raw_text, mode="pass2")
    if "fatal_phrase" not in parsed or "weak_spot" not in parsed:
        raise JudgeError("schema_mismatch", "judge pass2 missing structural keys", debug={"raw_text": raw_text, "parsed_summary": parsed})
    return {
        "fatal_phrase": parsed.get("fatal_phrase"),
        "weak_spot": parsed.get("weak_spot"),
        "flip_condition": _clean_text(parsed.get("flip_condition") or "未生成"),
        "gemini_takeaway": parsed.get("gemini_takeaway"),
        "gemini_quote": parsed.get("gemini_quote"),
    }


def _parse_judge_json_object(raw_text: str, *, mode: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        raise JudgeError("empty_response", "judge returned empty text", debug={"raw_text": text})
    candidate = _extract_json_candidate(text)
    if not candidate:
        raise JudgeError("json_parse_error", "no JSON object found in judge response", debug={"raw_text": text})
    parsed: Any = None
    last_error = ""
    attempts = [candidate]
    repaired = _repair_json_candidate(candidate)
    if repaired != candidate:
        attempts.append(repaired)
    for attempt in attempts:
        try:
            parsed = json.loads(attempt)
            break
        except json.JSONDecodeError as exc:
            last_error = str(exc)
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise JudgeError(
            "json_parse_error",
            last_error or "judge response JSON could not be parsed as an object",
            debug={"raw_text": text, "parsed_candidate": candidate},
        )
    parsed = _coerce_judge_summary_keys(parsed)
    if mode == "summary" and not _judge_summary_has_minimum_shape(parsed):
        raise JudgeError(
            "schema_mismatch",
            "judge response missing required summary keys",
            debug={"raw_text": text, "parsed_candidate": candidate, "parsed_summary": parsed},
        )
    return parsed


def _normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    fatal_raw = summary.get("fatal_phrase")
    fatal = fatal_raw if isinstance(fatal_raw, dict) else {}
    disagreements = summary.get("key_disagreement_top3")
    if not isinstance(disagreements, list):
        disagreements = [str(disagreements or "未生成")]
    disagreements = [str(item).strip() for item in disagreements if str(item).strip()][:3]
    if not disagreements:
        disagreements = ["未生成"]
    try:
        fatal_turn = int(fatal.get("turn") or 1)
    except Exception:
        fatal_turn = 1
    winner = _normalize_winner(summary)
    reason_one_liner = _normalize_reason_one_liner(summary, winner)
    confidence = _normalize_confidence(summary.get("confidence"))
    unresolved = summary.get("unresolved_residue") or "未生成"
    full_rationale = _clean_text(summary.get("full_rationale") or summary.get("provisional_judgment") or reason_one_liner)
    turning_point = _normalize_turning_point(summary, winner)
    weak_spot = _normalize_weak_spot(summary, winner, turning_point, fatal)
    fatal_phrase = _normalize_fatal_phrase(summary, fatal, winner, turning_point, weak_spot)
    winner = _apply_major_violation_penalty(summary, winner, reason_one_liner, turning_point, weak_spot, fatal_phrase)
    reason_one_liner = _normalize_reason_one_liner(summary, winner)
    weak_spot = _normalize_weak_spot(summary, winner, turning_point, fatal)
    fatal_phrase = _normalize_fatal_phrase(summary, fatal, winner, turning_point, weak_spot)
    momentum = _normalize_momentum(summary.get("momentum"), winner, confidence, fatal_phrase, weak_spot)
    momentum = _apply_violation_momentum_boost(momentum, winner, weak_spot)
    gemini_takeaway = _normalize_gemini_takeaway(summary, winner, reason_one_liner, momentum, turning_point, weak_spot)
    gemini_quote = _normalize_gemini_quote(summary, winner, turning_point, weak_spot)
    return {
        "winner": winner,
        "reason_one_liner": reason_one_liner,
        "confidence": confidence,
        "momentum": momentum,
        "turning_point": turning_point,
        "fatal_phrase": fatal_phrase,
        "weak_spot": weak_spot,
        "rule_expansion": _clean_text(summary.get("rule_expansion") or "未生成"),
        "rule_capture": _clean_text(summary.get("rule_capture") or "未生成"),
        "contradiction": _clean_text(summary.get("contradiction") or summary.get("contradiction_exposed") or "未生成"),
        "contradiction_exposed": _clean_text(summary.get("contradiction_exposed") or summary.get("contradiction") or "未生成"),
        "unresolved_residue": _clean_text(unresolved),
        "provisional_judgment": _clean_text(summary.get("provisional_judgment") or "未生成"),
        "full_rationale": full_rationale,
        "flip_condition": _clean_text(summary.get("flip_condition") or "未生成"),
        "gemini_takeaway": gemini_takeaway,
        "gemini_quote": gemini_quote,
        "key_disagreement_top3": disagreements,
    }


def _coerce_judge_summary_keys(summary: dict[str, Any]) -> dict[str, Any]:
    data = dict(summary)
    aliases = {
        "key_disagreement": "key_disagreement_top3",
        "key_disagreements": "key_disagreement_top3",
        "contradiction_exposed_text": "contradiction_exposed",
        "why_in_1_sentence": "reason_one_liner",
        "why_one_liner": "reason_one_liner",
        "reasonOneLiner": "reason_one_liner",
        "turningPointTurn": "turning_point_turn",
        "turningPoint": "turning_point",
        "fatalPhrase": "fatal_phrase",
        "weakSpot": "weak_spot",
        "flipCondition": "flip_condition",
        "geminiTakeaway": "gemini_takeaway",
        "geminiQuote": "gemini_quote",
    }
    for source, target in aliases.items():
        if source in data and target not in data:
            data[target] = data[source]
    if "contradiction_exposed" not in data and "contradiction" in data:
        data["contradiction_exposed"] = data["contradiction"]
    if "contradiction" not in data and "contradiction_exposed" in data:
        data["contradiction"] = data["contradiction_exposed"]
    fatal = data.get("fatal_phrase")
    if isinstance(fatal, dict):
        nested_aliases = {
            "quoteExcerpt": "quote_excerpt",
            "whyOneSentence": "why_one_sentence",
            "howToFix": "how_to_fix",
        }
        normalized_fatal = dict(fatal)
        for source, target in nested_aliases.items():
            if source in normalized_fatal and target not in normalized_fatal:
                normalized_fatal[target] = normalized_fatal[source]
        data["fatal_phrase"] = normalized_fatal
    weak_spot = data.get("weak_spot")
    if isinstance(weak_spot, dict):
        nested_aliases = {
            "quoteExcerpt": "quote_excerpt",
            "whyOneSentence": "why_one_sentence",
            "howToFix": "how_to_fix",
        }
        normalized_weak_spot = dict(weak_spot)
        for source, target in nested_aliases.items():
            if source in normalized_weak_spot and target not in normalized_weak_spot:
                normalized_weak_spot[target] = normalized_weak_spot[source]
        data["weak_spot"] = normalized_weak_spot
    takeaway = data.get("gemini_takeaway")
    if isinstance(takeaway, dict):
        nested_aliases = {
            "structuralExplanation": "structural_explanation",
            "debateDynamic": "debate_dynamic",
        }
        normalized_takeaway = dict(takeaway)
        for source, target in nested_aliases.items():
            if source in normalized_takeaway and target not in normalized_takeaway:
                normalized_takeaway[target] = normalized_takeaway[source]
        data["gemini_takeaway"] = normalized_takeaway
    quote = data.get("gemini_quote")
    if isinstance(quote, dict):
        normalized_quote = dict(quote)
        if "quote" in normalized_quote and "text" not in normalized_quote:
            normalized_quote["text"] = normalized_quote["quote"]
        data["gemini_quote"] = normalized_quote
    return data


def _judge_summary_has_minimum_shape(summary: dict[str, Any]) -> bool:
    required = [
        "fatal_phrase",
        "turning_point",
    ]
    if not all(key in summary for key in required):
        return False
    if not any(key in summary for key in ["provisional_judgment", "reason_one_liner", "winner"]):
        return False
    return True


def _normalize_winner(summary: dict[str, Any]) -> dict[str, str]:
    raw = summary.get("winner")
    side = ""
    reason = ""
    if isinstance(raw, dict):
        side = _clean_text(raw.get("side") or raw.get("winner") or "")
        reason = _clean_text(raw.get("reason") or "")
    elif isinstance(raw, str):
        side = _clean_text(raw)
    side_lower = side.lower()
    if side_lower in {"a", "fighter a", "gpt"}:
        side = "A"
    elif side_lower in {"b", "fighter b", "claude"}:
        side = "B"
    elif side_lower in {"draw", "tie", "undecidable", "cannot decide", "引き分け", "互角", "五分"}:
        side = "Draw"
    else:
        side = _infer_winner_from_summary(summary, reason)
    if not reason:
        reason = _clean_text(summary.get("reason_one_liner") or summary.get("provisional_judgment") or "")
    if not reason:
        if side == "Draw":
            reason = "流れは動いたが、どちらも決定打を押し切れなかった。"
        else:
            reason = "押し込みは見えたが、最後の決め手を短くまとめ切れていない。"
    return {"side": side, "reason": _first_sentence(reason)}


PROPOSITION_VIOLATION_LABELS = {
    "命題逸脱",
    "主語の縮小",
    "時間軸ずらし",
    "条件すり替え",
    "問いの再発明",
}


def _infer_winner_from_summary(summary: dict[str, Any], reason: str) -> str:
    texts = [
        _clean_text(summary.get("reason_one_liner") or ""),
        _clean_text(summary.get("provisional_judgment") or ""),
        _clean_text(reason or ""),
        _clean_text(summary.get("full_rationale") or ""),
    ]
    combined = " ".join([text for text in texts if text])
    inferred = _infer_winner_from_text(combined)
    if inferred != "Draw":
        return inferred
    fatal = summary.get("fatal_phrase") if isinstance(summary.get("fatal_phrase"), dict) else {}
    weak_spot = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {}
    fatal_speaker = _clean_text(fatal.get("speaker") or "").upper()
    weak_speaker = _clean_text(weak_spot.get("speaker") or "").upper()
    if weak_speaker == "A" or fatal_speaker == "B":
        return "B"
    if weak_speaker == "B" or fatal_speaker == "A":
        return "A"
    flip = _clean_text(summary.get("flip_condition") or "")
    if "Aが戻る" in flip or "Aが返す" in flip:
        return "B"
    if "Bが戻る" in flip or "Bが返す" in flip:
        return "A"
    return "Draw"


def _infer_winner_from_text(text: str) -> str:
    lowered = str(text or "")
    if re.search(r"引き分け|互角|五分|決め切れない|決めきれない|cannot decide|undecidable|\bdraw\b|\btie\b", lowered, re.IGNORECASE):
        return "Draw"
    if re.search(r"\bA\b|Aの方|Aが|A優勢|Aが押した|Aが押し切|Aが守り切|Bが崩れ|Bが後退", lowered):
        return "A"
    if re.search(r"\bB\b|Bの方|Bが|B優勢|Bが押した|Bが押し切|Bが守り切|Aが崩れ|Aが後退", lowered):
        return "B"
    return "Draw"


def _normalize_reason_one_liner(summary: dict[str, Any], winner: dict[str, str]) -> str:
    value = _clean_text(summary.get("reason_one_liner") or summary.get("provisional_judgment") or winner.get("reason") or "")
    if value:
        return _first_sentence(value)
    side = winner.get("side") or "Draw"
    if side == "A":
        return "Aが最後まで押し返し、判定軸を握った。"
    if side == "B":
        return "Bが最後まで穴を残さず、相手の押し込みを止めた。"
    return "決定打は割れたが、流れは最後まで拮抗した。"


def _apply_major_violation_penalty(
    summary: dict[str, Any],
    winner: dict[str, str],
    reason_one_liner: str,
    turning_point: str,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
) -> dict[str, str]:
    side = winner.get("side") or "Draw"
    if side not in {"A", "B"}:
        return winner
    raw_weak = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {}
    weak_side = _clean_text(raw_weak.get("side") or weak_spot.get("side") or "")
    weak_label = _clean_text(raw_weak.get("label") or weak_spot.get("label") or "")
    if not weak_label:
        weak_label = _guess_weak_spot_label(
            " ".join(
                [
                    _clean_text(raw_weak.get("why_one_sentence") or raw_weak.get("why") or ""),
                    _clean_text(raw_weak.get("quote_excerpt") or raw_weak.get("text") or ""),
                    _clean_text(summary.get("reason_one_liner") or ""),
                    _clean_text(turning_point or ""),
                    _clean_text(fatal_phrase.get("text") or ""),
                ]
            )
        )
    if weak_side != side or weak_label not in PROPOSITION_VIOLATION_LABELS:
        return winner
    exposing_side = _detect_violation_exposer(summary, turning_point, fatal_phrase, weak_side)
    if exposing_side not in {"A", "B"} or exposing_side == side:
        return winner
    return {
        "side": exposing_side,
        "reason": _first_sentence(
            f"{exposing_side}は元の問いを守り、{side}の{weak_label}を明示的に暴いた。"
        ),
    }


def _detect_violation_exposer(
    summary: dict[str, Any],
    turning_point: str,
    fatal_phrase: dict[str, Any],
    violation_side: str,
) -> str:
    raw_weak = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {}
    texts = [
        _clean_text(summary.get("reason_one_liner") or ""),
        _clean_text(summary.get("provisional_judgment") or ""),
        _clean_text(turning_point or ""),
        _clean_text(fatal_phrase.get("text") or ""),
        _clean_text(fatal_phrase.get("reason") or ""),
        _clean_text(raw_weak.get("why_one_sentence") or raw_weak.get("why") or ""),
    ]
    combined = " ".join(texts)
    opposite = "B" if violation_side == "A" else "A" if violation_side == "B" else ""
    if not opposite:
        return ""
    if re.search(r"元の問い|命題|主語|短期|長期|昔のように|条件|一部の人間|一部の強い人|別の問い|問いに答えていない", combined):
        fatal_speaker = _clean_text(fatal_phrase.get("speaker") or "").upper()
        turning_side = _infer_side_from_text(turning_point)
        if fatal_speaker == opposite:
            return opposite
        if turning_side == opposite:
            return opposite
        if re.search(fr"{opposite}が[^。]*(固定|暴|突|指摘|守)", combined):
            return opposite
    return ""


def _normalize_turning_point(summary: dict[str, Any], winner: dict[str, str]) -> str:
    value = _clean_text(summary.get("turning_point") or "")
    if value and value != "未生成":
        return value
    fatal = summary.get("fatal_phrase") if isinstance(summary.get("fatal_phrase"), dict) else {}
    turn = fatal.get("turn") or 3
    try:
        turn_no = max(1, int(turn))
    except Exception:
        turn_no = 3
    if (winner.get("side") or "Draw") == "Draw":
        return f"Turn {turn_no}で流れは動いたが、どちらも決定打を最後まで押し切れなかった。"
    return f"Turn {turn_no}で流れが大きく傾き、その後の押し返しが勝敗を分けた。"


def _normalize_fatal_phrase(
    summary: dict[str, Any],
    fatal: dict[str, Any],
    winner: dict[str, str],
    turning_point: str,
    weak_spot: dict[str, str],
) -> dict[str, Any]:
    speaker = _clean_text(fatal.get("speaker") or "")
    text = _clean_text(fatal.get("text") or "")
    reason = _clean_text(fatal.get("reason") or "")
    turn = fatal.get("turn") or extract_turn_number_from_text(turning_point) or 3
    try:
        turn_no = max(1, int(turn))
    except Exception:
        turn_no = 3
    side = winner.get("side") or "Draw"
    winning_speaker = side if side in {"A", "B"} else "A/B"
    loser_speaker = _losing_side(winner)
    turning_side = _infer_side_from_text(turning_point)
    if text and text != "未生成":
        if _looks_like_meta_strategy_text(text) or _looks_like_meta_strategy_text(reason):
            text = ""
            reason = ""
        if side in {"A", "B"} and speaker in {"A", "B"} and speaker != winning_speaker:
            return {
                "turn": turn_no,
                "speaker": winning_speaker,
                "text": "この場面で相手の押し返しを止め、勝ち筋を守り切った。",
                "reason": f"{speaker}が流れを動かしても、最終的には{winning_speaker}が主導権を取り戻した。",
            }
        return {
            "turn": turn_no,
            "speaker": speaker or winning_speaker,
            "text": text,
            "reason": reason or ("最も流れを動かした応酬だった。" if side == "Draw" else "この一文が勝敗の傾きを決めた。"),
        }
    if side == "Draw":
        return {
            "turn": turn_no,
            "speaker": speaker or "A/B",
            "text": "単独の決定打はなかったが、この応酬が最も勝負を動かした。",
            "reason": _first_sentence(reason or weak_spot.get("why_one_sentence") or "流れは動いたが、どちらもここから決め切れなかった。"),
        }
    return {
        "turn": turn_no,
        "speaker": winning_speaker,
        "text": "この場面で相手の穴が最もはっきり見えた。",
        "reason": _first_sentence(
            reason
            or weak_spot.get("why_one_sentence")
            or (
                f"{loser_speaker}が流れを動かしかけても、{winning_speaker}が最後は押し返した。"
                if turning_side and turning_side != winning_speaker
                else "この場面で勝敗の傾きが固まった。"
            )
        ),
    }


def _normalize_confidence(value: Any) -> str:
    text = _clean_text(value or "")
    lowered = text.lower()
    if lowered in {"low", "medium", "high"}:
        return lowered.title()
    if text.isdigit():
        try:
            score = int(text)
        except Exception:
            score = 0
        if score >= 75:
            return "High"
        if score >= 45:
            return "Medium"
        return "Low"
    return "Medium"


def _normalize_momentum(
    value: Any,
    winner: dict[str, str],
    confidence: str,
    fatal_phrase: dict[str, Any],
    weak_spot: dict[str, str],
) -> dict[str, int]:
    if isinstance(value, dict):
        try:
            a = int(value.get("a"))
            b = int(value.get("b"))
            total = a + b
            if total > 0:
                a = max(0, min(100, int(round((a / total) * 100))))
                b = max(0, min(100, 100 - a))
                if winner.get("side") == "A" and a <= b:
                    return {"a": 55, "b": 45}
                if winner.get("side") == "B" and b <= a:
                    return {"a": 45, "b": 55}
                return {"a": a, "b": b}
        except Exception:
            pass
    side = winner.get("side") or "Draw"
    if side == "Draw":
        return {"a": 50, "b": 50}
    swing = 16 if confidence == "High" else 10 if confidence == "Medium" else 6
    inferred_side = side
    weak_speaker = _clean_text(weak_spot.get("speaker") or "").upper()
    fatal_speaker = _clean_text(fatal_phrase.get("speaker") or "").upper()
    if side == "Draw":
        if weak_speaker == "A" or fatal_speaker == "B":
            inferred_side = "B"
        elif weak_speaker == "B" or fatal_speaker == "A":
            inferred_side = "A"
    if inferred_side == "A":
        return {"a": 50 + swing, "b": 50 - swing}
    if inferred_side == "B":
        return {"a": 50 - swing, "b": 50 + swing}
    return {"a": 50, "b": 50}


def _apply_violation_momentum_boost(momentum: dict[str, int], winner: dict[str, str], weak_spot: dict[str, Any]) -> dict[str, int]:
    side = winner.get("side") or "Draw"
    if side not in {"A", "B"}:
        return momentum
    if _clean_text(weak_spot.get("label") or "") not in PROPOSITION_VIOLATION_LABELS:
        return momentum
    if _clean_text(weak_spot.get("side") or "") == _losing_side(winner):
        return {"a": 30, "b": 70} if side == "B" else {"a": 70, "b": 30}
    return momentum


def _normalize_gemini_takeaway(
    summary: dict[str, Any],
    winner: dict[str, str],
    reason_one_liner: str,
    momentum: dict[str, int],
    turning_point: str,
    weak_spot: dict[str, Any],
) -> dict[str, str]:
    raw = summary.get("gemini_takeaway")
    turning_side = _infer_side_from_text(turning_point)
    if isinstance(raw, dict):
        structural = _clean_text(raw.get("structural_explanation") or "")
        dynamic = _clean_text(raw.get("debate_dynamic") or "")
        quote = _clean_text(raw.get("quote") or "")
    side = winner.get("side") or "Draw"
    label = _clean_text(weak_spot.get("label") or "")
    winning_speaker = side if side in {"A", "B"} else "A/B"
    loser_speaker = _losing_side(winner)
    if side == "A":
        structural = (
            _first_sentence(raw.get("structural_explanation") or "")
            if isinstance(raw, dict)
            else ""
        ) or (
            f"{turning_point}でBが流れを揺らしても、Aは{label or '判定基準'}を守った。"
            if turning_side == "B"
            else f"{turning_point}でAが主導権を握り、{label or '判定基準'}を固定した。"
        )
        dynamic = (
            _first_sentence(raw.get("debate_dynamic") or "")
            if isinstance(raw, dict)
            else ""
        )
        if not dynamic or _text_favors_side(dynamic, "B"):
            dynamic = (
                f"しかし{loser_speaker}は決め手を押し切れず、最終的に{winning_speaker}が押し返した。"
                if turning_side == "B"
                else f"その後も{winning_speaker}が流れを保ち、{loser_speaker}は{label or '核心'}を返せなかった。"
            )
        quote = "「基準を握った側が、議論を支配する。」"
    elif side == "B":
        structural = (
            _first_sentence(raw.get("structural_explanation") or "")
            if isinstance(raw, dict)
            else ""
        ) or (
            f"{turning_point}でAが流れを揺らしても、Bは{label or '判定軸'}を崩さなかった。"
            if turning_side == "A"
            else f"{turning_point}でBが流れを動かし、{label or '判定軸'}を押し切った。"
        )
        dynamic = (
            _first_sentence(raw.get("debate_dynamic") or "")
            if isinstance(raw, dict)
            else ""
        )
        if not dynamic or _text_favors_side(dynamic, "A"):
            dynamic = (
                f"しかし{loser_speaker}は決め手を最後まで支え切れず、最終的に{winning_speaker}が押し切った。"
                if turning_side == "A"
                else f"その後も{winning_speaker}が圧を維持し、{loser_speaker}は{label or '弱点'}を修正し切れなかった。"
            )
        quote = "「きれいな理屈でも、穴があれば崩れる。」"
    else:
        structural = (
            _first_sentence(raw.get("structural_explanation") or "")
            if isinstance(raw, dict)
            else ""
        ) or "流れは動いたが、どちらも相手の核を最後まで崩し切れなかった。"
        dynamic = (
            _first_sentence(raw.get("debate_dynamic") or "")
            if isinstance(raw, dict)
            else ""
        ) or f"{turning_point}で勝負は揺れたが、その後も決定打が続かなかった。"
        quote = (_clean_text(raw.get("quote") or "") if isinstance(raw, dict) else "") or "「流れは揺れたが、決着は届かなかった。」"
    if reason_one_liner and reason_one_liner != "未生成" and not structural:
        structural = _first_sentence(reason_one_liner)
    if momentum.get("a") == momentum.get("b") and side != "Draw":
        dynamic = f"{turning_point}で傾きは出たが、押し込みは僅差だった。"
    if side in {"A", "B"} and not _text_favors_side(dynamic, side):
        dynamic = f"{turning_point}で揺れが出ても、最終的に{side}が主導権を保った。"
    return {
        "structural_explanation": _first_sentence(structural),
        "debate_dynamic": _first_sentence(dynamic),
        "quote": _clip_takeaway_quote(quote),
    }


def _clip_takeaway_quote(text: str) -> str:
    quote = _clean_text(text).strip("「」")
    if not quote:
        return "「議論の型を握った側が残る。」"
    if len(quote) > 20:
        quote = quote[:20].rstrip() + "…"
    return f"「{quote}」"


def _normalize_gemini_quote(
    summary: dict[str, Any],
    winner: dict[str, str],
    turning_point: str,
    weak_spot: dict[str, Any],
) -> dict[str, str]:
    raw = summary.get("gemini_quote")
    if isinstance(raw, dict):
        text = _clean_text(raw.get("text") or "")
        if text and not _looks_like_generic_gemini_quote(text) and _quote_aligns_with_winner(text, winner):
            clipped = _clip_gemini_quote(text)
            if _is_complete_gemini_quote(clipped):
                return {"text": clipped}
    rebuilt = _build_specific_gemini_quote(summary, winner, turning_point, weak_spot)
    return {"text": _clip_gemini_quote(rebuilt)}


def _clip_gemini_quote(text: str) -> str:
    quote = _clean_text(text).strip("「」")
    if not quote:
        quote = "流れを変えた一手が、勝負を決める。"
    if len(quote) <= 36:
        quote = quote
    elif len(quote) > 36:
        sentence = _first_sentence(quote).strip("「」")
        if sentence and len(sentence) <= 36:
            quote = sentence
        else:
            cut = _find_quote_cut_position(quote, 36)
            quote = quote[:cut].rstrip("、 ")
    if not re.search(r"[。！？]$", quote):
        quote = quote.rstrip("、 ")
        if not re.search(r"(た|ない|った|れる|した|見えた|動いた|崩れた|止まった|折れた|薄まった|立たなかった|守れなかった|逃げに見えた)$", quote):
            quote = _build_complete_quote_sentence(quote)
        if not re.search(r"[。！？]$", quote):
            quote = quote + "。"
    return f"「{quote}」"


def _find_quote_cut_position(text: str, max_len: int) -> int:
    if len(text) <= max_len:
        return len(text)
    candidates = []
    for marker in ["。", "、", "た", "ない", "った", "れる", "した", "見えた", "動いた", "崩れた", "止まった", "折れた", "薄まった", "立たなかった", "守れなかった"]:
        idx = text.rfind(marker, 0, max_len + 1)
        if idx >= 0:
            candidates.append(idx + len(marker))
    return max(candidates) if candidates else max_len


def _build_complete_quote_sentence(text: str) -> str:
    value = _clean_text(text)
    if not value:
        return "流れを変えた一手が、勝負を決めた。"
    if re.search(r"(動かな|止まっ|崩れ|折れ|薄まっ|逃げに見え|立たな|守れな)$", value):
        return value + "た。"
    if re.search(r"(語ったが|広げたが|変えた瞬間|言い換えた瞬間|答えないまま)$", value):
        return value + "、勝負が動いた。"
    return value + "。"


def _is_complete_gemini_quote(text: str) -> bool:
    quote = _clean_text(text).strip("「」")
    return bool(quote) and "…" not in quote and re.search(r"[。！？]$", quote)


def _looks_like_generic_gemini_quote(text: str) -> bool:
    quote = _clean_text(text)
    banned = [
        "基準を握った側が議論を支配する",
        "定義を握った側が勝つ",
        "ルールを作る側が有利",
        "whoever controls the definition wins",
        "whoever sets the rules wins",
    ]
    return any(phrase in quote for phrase in banned)


def _build_specific_gemini_quote(
    summary: dict[str, Any],
    winner: dict[str, str],
    turning_point: str,
    weak_spot: dict[str, Any],
) -> str:
    concepts = _extract_gemini_quote_concepts(summary, turning_point, weak_spot)
    primary = concepts[0] if concepts else ""
    secondary = concepts[1] if len(concepts) > 1 else ""
    label = _clean_text(weak_spot.get("label") or "")
    side = winner.get("side") or "Draw"

    if label == "定義の後退" and primary and secondary:
        return f"{primary}を広げた瞬間、{secondary}は折れた。"
    if label == "循環論法" and primary:
        return f"{primary}を言い換えた瞬間、穴が残った。"
    if label == "未応答" and primary:
        return f"{primary}に答えないまま、勝ち筋が止まった。"
    if label == "抽象逃避" and primary and secondary:
        return f"{primary}を語ったが、{secondary}は動かなかった。"
    if label == "条件追加の後手化" and primary:
        return f"{primary}を後から足すと、論理は逃げに見える。"
    if label == "評価基準のすり替え" and primary and secondary:
        return f"{primary}を変えた瞬間、{secondary}が崩れた。"
    if label == "論拠不足" and primary and secondary:
        return f"{primary}は出た。だが{secondary}は立たなかった。"
    if label == "一般化しすぎ" and primary and secondary:
        return f"{primary}を広げたせいで、{secondary}が薄まった。"

    if side == "Draw" and primary and secondary:
        return f"{primary}は揺れたが、{secondary}までは折れなかった。"
    if side == "A" and primary and secondary:
        return f"{primary}を守った瞬間、{secondary}が崩れた。"
    if side == "B" and primary and secondary:
        return f"{primary}を突いた瞬間、{secondary}が崩れた。"
    if primary and secondary:
        return f"{primary}は広がったが、{secondary}は動かなかった。"
    if primary:
        return f"{primary}だけでは、勝ち筋は動かない。"
    return "その試合の穴を突いた側が残った。"


def _extract_gemini_quote_concepts(summary: dict[str, Any], turning_point: str, weak_spot: dict[str, Any]) -> list[str]:
    sources = [
        _clean_text(((summary.get("fatal_phrase") or {}).get("text") if isinstance(summary.get("fatal_phrase"), dict) else "")),
        _clean_text(weak_spot.get("quote_excerpt") or ""),
        _clean_text(weak_spot.get("why_one_sentence") or ""),
        _clean_text(turning_point or ""),
        _clean_text(summary.get("reason_one_liner") or ""),
    ]
    concepts: list[str] = []
    for source in sources:
        for term in _extract_focus_terms(source):
            cleaned = term.strip()
            if not cleaned or cleaned in JP_STOPWORDS:
                continue
            if re.fullmatch(r"Turn|\d+|A|B|A/B", cleaned, re.IGNORECASE):
                continue
            if cleaned not in concepts:
                concepts.append(cleaned)
            if len(concepts) >= 4:
                return concepts
    return concepts


def _normalize_weak_spot(
    summary: dict[str, Any],
    winner: dict[str, str],
    turning_point: str,
    fatal: dict[str, Any],
) -> dict[str, Any]:
    raw = summary.get("weak_spot")
    contradiction = _clean_text(summary.get("contradiction_exposed") or summary.get("contradiction") or "")
    side = winner.get("side") or "Draw"
    if isinstance(raw, dict):
        speaker = _normalize_weak_spot_speaker(raw.get("speaker"), winner)
        side_value = _normalize_weak_spot_side(raw.get("side"), speaker, winner)
        coerced = False
        if side in {"A", "B"} and side_value == side:
            side_value = _default_weak_spot_side(winner)
            speaker = _default_weak_spot_speaker(winner)
            coerced = True
        label_source = " ".join(
            [
                _clean_text(raw.get("label") or ""),
                _clean_text(raw.get("why_one_sentence") or raw.get("why") or ""),
                _clean_text(raw.get("quote_excerpt") or raw.get("text") or raw.get("quote") or ""),
                contradiction,
                _clean_text(summary.get("provisional_judgment") or ""),
            ]
        ).strip()
        label = _normalize_weak_spot_label(label_source, side_value)
        why_source = _clean_text(raw.get("why_one_sentence") or raw.get("why") or "")
        why = _first_sentence(_default_weak_spot_why(side_value, label, contradiction) if coerced else (why_source or _default_weak_spot_why(side_value, label, contradiction)))
        if label or why:
            return {
                "side": side_value,
                "turn": _normalize_weak_spot_turn(raw.get("turn"), turning_point, fatal),
                "speaker": speaker,
                "label": label,
                "quote_excerpt": _normalize_weak_spot_excerpt(raw.get("quote_excerpt") or raw.get("text") or raw.get("quote") or "", contradiction, fatal),
                "why_one_sentence": why,
                "how_to_fix": _first_sentence(
                    _default_weak_spot_fix(side_value, label)
                    if coerced
                    else (_clean_text(raw.get("how_to_fix") or "") or _default_weak_spot_fix(side_value, label))
                ),
            }
    return {
        "side": _default_weak_spot_side(winner),
        "turn": _normalize_weak_spot_turn(None, turning_point, fatal),
        "speaker": _default_weak_spot_speaker(winner),
        "label": _normalize_weak_spot_label(contradiction or _clean_text(summary.get("provisional_judgment") or ""), _default_weak_spot_side(winner)),
        "quote_excerpt": _normalize_weak_spot_excerpt("", contradiction, fatal),
        "why_one_sentence": _default_weak_spot_why(_default_weak_spot_side(winner), _normalize_weak_spot_label(contradiction or _clean_text(summary.get("provisional_judgment") or ""), _default_weak_spot_side(winner)), contradiction),
        "how_to_fix": _default_weak_spot_fix(_default_weak_spot_side(winner), _normalize_weak_spot_label(contradiction or _clean_text(summary.get("provisional_judgment") or ""), _default_weak_spot_side(winner))),
    }


def _normalize_weak_spot_side(raw_side: Any, speaker: str, winner: dict[str, str]) -> str:
    side = _clean_text(raw_side or "").lower()
    if side in {"a", "fighter a"}:
        return "A"
    if side in {"b", "fighter b"}:
        return "B"
    if side in {"both", "a/b", "draw"}:
        return "both"
    if speaker == "A":
        return "A"
    if speaker == "B":
        return "B"
    return _default_weak_spot_side(winner)


def _normalize_weak_spot_speaker(raw_speaker: Any, winner: dict[str, str]) -> str:
    speaker = _clean_text(raw_speaker or "").upper()
    if speaker in {"A", "B", "A/B"}:
        return speaker
    return _default_weak_spot_speaker(winner)


def _normalize_weak_spot_turn(raw_turn: Any, turning_point: str, fatal: dict[str, Any]) -> int:
    turn = extract_turn_number_from_text(raw_turn)
    if turn:
        return turn
    turn = extract_turn_number_from_text(turning_point)
    if turn:
        return turn
    turn = extract_turn_number_from_text(fatal)
    return turn or 3


def _normalize_weak_spot_excerpt(raw_excerpt: str, contradiction: str, fatal: dict[str, Any]) -> str:
    excerpt = _clean_text(raw_excerpt or "")
    if excerpt:
        return _short_quote_excerpt(excerpt)
    contradiction_excerpt = _short_quote_excerpt(contradiction)
    if contradiction_excerpt:
        return contradiction_excerpt
    fatal_text = _clean_text(fatal.get("text") or "")
    if fatal_text:
        return _short_quote_excerpt(fatal_text)
    return "相手に最も刺された弱点がここで露出した。"


def _normalize_weak_spot_label(text: str, side: str) -> str:
    if side == "both":
        return "Why it stayed unresolved"
    return _guess_weak_spot_label(text)


def _default_weak_spot_why(side: str, label: str, contradiction: str) -> str:
    if contradiction:
        return _first_sentence(contradiction)
    if side == "both":
        return "A/Bともに相手の核を崩し切れず、流れを決め切る決定打が足りなかった。"
    if label == "命題逸脱":
        return f"{side}は元の問いの拘束語を外し、別の答えや別の条件へ逃がしてしまった。"
    if label == "主語の縮小":
        return f"{side}は人間一般の問いを一部の例外的人物へ縮め、命題の主語を守れなかった。"
    if label == "時間軸ずらし":
        return f"{side}は昔のように・短期という条件を守れず、別の時間軸へずらした。"
    if label == "条件すり替え":
        return f"{side}は元の条件を維持せず、別条件の一般論へ逃がした。"
    if label == "問いの再発明":
        return f"{side}は元の問いを別の問いへ作り変え、その命題に答え切れなかった。"
    return f"{side}は「{label}」を突かれたあとも修正できず、勝負を動かす材料を返せなかった。"


def _default_weak_spot_fix(side: str, label: str) -> str:
    mapping = {
        "命題逸脱": "元の問いを作り替えず、最初の命題の拘束語にそのまま答えるべきだった。",
        "主語の縮小": "人間一般の問いを一部の例外へ縮めず、普通の主体でも成立する根拠を出すべきだった。",
        "時間軸ずらし": "昔のように・短期という条件を守り、長期や別時間軸へ逃がさずに答えるべきだった。",
        "条件すり替え": "BOT増加環境など元の条件を外さず、その条件下で成否を示すべきだった。",
        "問いの再発明": "勝てるかを生き残れるかに変えず、元の問いに対する yes/no を維持するべきだった。",
        "反復": "同じ主張を繰り返す前に、新しい具体例か検証指標を一つ足すべきだった。",
        "ドリフト": "論題を広げる前に、最初の問いにそのまま答える一文を先に置くべきだった。",
        "定義の後退": "途中で定義を広げず、最初に置いた基準を最後まで守るべきだった。",
        "未応答": "自説を足す前に、相手の核心への返答を一文で先に済ませるべきだった。",
        "抽象逃避": "抽象語ではなく、その場で検証できる具体例か観測基準を出すべきだった。",
        "循環論法": "結論を言い換えるのではなく、結論を支える独立した根拠を追加すべきだった。",
        "弱い例示": "印象的な例より、相手の主張を直接崩す具体例を一つに絞るべきだった。",
        "論拠不足": "主張を重ねる前に、その主張を支える根拠か比較対象を先に出すべきだった。",
        "条件追加の後手化": "押し返された後ではなく、最初の段階で必要条件を先に明示すべきだった。",
        "評価基準のすり替え": "不利になってから基準を変えず、最初の評価軸に沿って戦うべきだった。",
        "具体性不足": "抽象的な方向性ではなく、相手が否定しにくい具体的な一場面を出すべきだった。",
        "一般化しすぎ": "大きな一般論へ飛ばず、まずこの命題で本当に言える範囲に絞るべきだった。",
        "Why it stayed unresolved": "片側を倒す前に、相手の核を崩す一手を明確に作るべきだった。",
    }
    return mapping.get(label, "一段抽象的な言い換えではなく、相手の核心を崩す具体例か基準を先に置くべきだった。")


def _default_weak_spot_side(winner: dict[str, str]) -> str:
    side = winner.get("side") or "Draw"
    if side == "A":
        return "B"
    if side == "B":
        return "A"
    return "both"


def _losing_side(winner: dict[str, str]) -> str:
    side = winner.get("side") or "Draw"
    if side == "A":
        return "B"
    if side == "B":
        return "A"
    return "A/B"


def _infer_side_from_text(text: Any) -> str:
    value = _clean_text(text or "")
    if not value:
        return ""
    inferred = _infer_winner_from_text(value)
    return inferred if inferred in {"A", "B"} else ""


def _text_favors_side(text: str, side: str) -> bool:
    if side not in {"A", "B"}:
        return True
    inferred = _infer_side_from_text(text)
    return not inferred or inferred == side


def _quote_aligns_with_winner(text: str, winner: dict[str, str]) -> bool:
    side = winner.get("side") or "Draw"
    if side == "Draw":
        return True
    lowered = _clean_text(text)
    if side == "A":
        return not re.search(r"Bが[^。]*?(押した|勝|支配|握|残った|押し切|守り切)", lowered)
    return not re.search(r"Aが[^。]*?(押した|勝|支配|握|残った|押し切|守り切)", lowered)


def _default_weak_spot_speaker(winner: dict[str, str]) -> str:
    side = winner.get("side") or "Draw"
    if side == "A":
        return "B"
    if side == "B":
        return "A"
    return "A/B"


def _guess_weak_spot_label(text: str) -> str:
    value = str(text or "")
    mapping = [
        ("命題逸脱", "命題逸脱"),
        ("命題から", "命題逸脱"),
        ("元の問いに答えていない", "命題逸脱"),
        ("主語の縮小", "主語の縮小"),
        ("一部の人間", "主語の縮小"),
        ("一部の強い人", "主語の縮小"),
        ("例外的な人", "主語の縮小"),
        ("時間軸ずらし", "時間軸ずらし"),
        ("昔のように", "時間軸ずらし"),
        ("長期で見れば", "時間軸ずらし"),
        ("短期ではなく長期", "時間軸ずらし"),
        ("長期なら", "時間軸ずらし"),
        ("長期へ", "時間軸ずらし"),
        ("短期の問い", "時間軸ずらし"),
        ("条件すり替え", "条件すり替え"),
        ("条件をすり替", "条件すり替え"),
        ("問いの再発明", "問いの再発明"),
        ("別の問い", "問いの再発明"),
        ("問いを作り変", "問いの再発明"),
        ("反復", "反復"),
        ("繰り返", "反復"),
        ("ドリフト", "ドリフト"),
        ("論点", "ドリフト"),
        ("ずら", "ドリフト"),
        ("定義", "定義の後退"),
        ("後退", "定義の後退"),
        ("未応答", "未応答"),
        ("答えていない", "未応答"),
        ("抽象", "抽象逃避"),
        ("一般論", "抽象逃避"),
        ("循環", "循環論法"),
        ("言い換え", "循環論法"),
        ("例", "弱い例示"),
        ("根拠", "論拠不足"),
        ("証拠", "論拠不足"),
        ("条件", "条件追加の後手化"),
        ("基準", "評価基準のすり替え"),
        ("具体", "具体性不足"),
        ("一般化", "一般化しすぎ"),
        ("広げ", "一般化しすぎ"),
    ]
    for needle, label in mapping:
        if needle in value:
            return label
    return "論拠不足"


def _short_quote_excerpt(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    sentence = _first_sentence(cleaned)
    if len(sentence) <= 48:
        return sentence
    return sentence[:48].rstrip() + "…"


def _first_sentence(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return "未生成"
    parts = re.split(r"(?<=[。.!?！？])\s*", cleaned)
    return parts[0].strip() if parts and parts[0].strip() else cleaned


def extract_turn_number_from_text(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    if isinstance(value, dict):
        turn = value.get("turn")
        if isinstance(turn, int):
            return turn
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    match = re.search(r"Turn\s*(\d+)", text, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None
    return None


def _normalize_turn_meta(
    meta: Any,
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    speech: str,
    latest_opponent: str = "",
) -> dict[str, str]:
    if isinstance(meta, dict):
        return {
            "phase": _clean_text(meta.get("phase") or ""),
            "target_issue": _clean_text(meta.get("target_issue") or ""),
            "attacked_weakness": _clean_text(meta.get("attacked_weakness") or ""),
            "new_issue": _clean_text(meta.get("new_issue") or ""),
            "collapse_signal": _clean_text(meta.get("collapse_signal") or ""),
            "finish_intent": _clean_text(meta.get("finish_intent") or ""),
            "end_match": _clean_text(meta.get("end_match") or ""),
        }
    mock_meta = _mock_turn_plan(speaker, cfg, turns, len(turns) + 1, latest_opponent, speech)
    return mock_meta


def _mock_turn_text(speaker: str, turn_no: int, topic: str, own_basis: str, opponent_basis: str) -> str:
    return f"{speaker} {turn_no} {topic} {own_basis} {opponent_basis}"


def _mock_summary(cfg: DebateConfig, turns: list[dict[str, Any]]) -> dict[str, Any]:
    pivot_turn = turns[2] if len(turns) > 2 else turns[-1]
    fatal_turn = turns[1] if len(turns) > 1 else turns[0]
    fatal_text = fatal_turn["b"]
    return _normalize_summary(
        {
            "winner": {
                "side": "B",
                "reason": "Aは命題を守ろうとしたが、Bが未解決条件を最後まで残した。",
            },
            "reason_one_liner": "Aは押し返したが、最後まで採用条件を閉じ切れず、Bが穴を残した。",
            "confidence": "Medium",
            "turning_point": f"Turn {pivot_turn['turn']}で、相手の直前主張を受けて新争点が追加され、議論が単純な賛否からルール争奪へ移った。",
            "fatal_phrase": {
                "turn": fatal_turn["turn"],
                "speaker": "B",
                "text": fatal_text,
                "reason": "決定打ではなく、Aが便益の存在から制度の正当化へ飛躍していた構造破綻を最初に露出させた発言だから。",
            },
            "weak_spot": {
                "speaker": "A",
                "label": "定義の後退",
                "why": "Aは強い命題を維持すると言いながら、途中で条件を足して射程を狭めた。",
            },
            "rule_expansion": "中盤で双方が自説を守るために評価条件を増やし、単一論点では勝てない構造へ広がった。",
            "rule_capture": "優勢側は『何を満たせば採用できるか』という判定規則を握り、相手をそのルールに従わせた。",
            "contradiction": "ラリー中盤で、一方は強い命題を掲げたまま、実際には条件付き後退でしか守れていないことが露出した。",
            "contradiction_exposed": "ラリー中盤で、一方は強い命題を掲げたまま、実際には条件付き後退でしか守れていないことが露出した。",
            "unresolved_residue": f"{cfg.topic}で実際に許容される導入条件の閾値が最後まで具体化されず、制度採用の運用基準が残った。",
            "provisional_judgment": "勝敗ではなく構造上の暫定評価として、Bの方が命題の輪郭と立証責任の位置を安定して保持した。",
            "full_rationale": "Bは最後まで未解決条件を残し、Aは命題の輪郭を守るために条件を足し続けた。見た瞬間に拾うべきポイントは、Winner と Fatal Phrase と Weak Spot で足りる。",
            "key_disagreement_top3": [
                "便益の存在と制度化の正当化を同一命題として扱ってよいか",
                "安全性の立証責任を誰がどこまで負うべきか",
                "条件付き導入への後退が命題修正なのか精緻化なのか",
            ],
        }
    )


def _compact_basis(text: str) -> str:
    first = re.split(r"[。\n]", text.strip())[0].strip()
    return first[:72] if first else text.strip()[:72]


def _append_transcript(transcript: str, turn_no: int, speaker: str, text: str) -> str:
    line = f"Turn {turn_no} {speaker}: {text}".strip()
    return f"{transcript}\n{line}".strip()


def _fallback_speech(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    latest_opponent: str = "",
) -> str:
    return _mock_sequential_turn(speaker, cfg, turns, turn_no, latest_opponent)


def _should_end_match(cfg: DebateConfig, turns: list[dict[str, Any]]) -> bool:
    if not turns:
        return False
    if len(turns) >= cfg.turn_count:
        return True
    min_finish_turn = min(max(3, cfg.turn_count), 5)
    if len(turns) < min_finish_turn:
        return False
    last = turns[-1]
    a_meta = (last.get("meta") or {}).get("a") or {}
    b_meta = (last.get("meta") or {}).get("b") or {}
    if a_meta.get("end_match") == "yes" and b_meta.get("end_match") == "yes":
        return True
    if len(turns) >= 2:
        prev = turns[-2]
        prev_a = ((prev.get("meta") or {}).get("a") or {}).get("new_issue") or ""
        prev_b = ((prev.get("meta") or {}).get("b") or {}).get("new_issue") or ""
        if prev_a and prev_a == a_meta.get("target_issue") and prev_b and prev_b == b_meta.get("target_issue"):
            if a_meta.get("finish_intent") == "finish" or b_meta.get("finish_intent") == "finish":
                return True
    return False


def _format_history(turns: list[dict[str, Any]]) -> str:
    if not turns:
        return "(none yet)"
    lines = []
    for turn in turns:
        lines.append(f"Turn {turn['turn']} A: {turn['a']}")
        lines.append(f"Turn {turn['turn']} B: {turn['b']}")
    return "\n".join(lines)


def _opponent_last_statement(speaker: str, turns: list[dict[str, Any]]) -> str:
    if not turns:
        return "(none yet)"
    last_turn = turns[-1]
    if speaker == "A":
        return last_turn.get("b") or "(none yet)"
    return last_turn.get("a") or "(none yet)"


def _mock_sequential_turn(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    latest_opponent: str = "",
) -> str:
    plan = _mock_turn_plan(speaker, cfg, turns, turn_no, latest_opponent)
    own_basis = _compact_basis(cfg.side_a if speaker == "A" else cfg.side_b)
    own_line = cfg.side_a if speaker == "A" else cfg.side_b
    issue_bank = _issue_bank(cfg.topic)
    target_detail = issue_bank.get(plan["target_issue"], f"{plan['target_issue']}が何を左右するか")
    new_issue_detail = issue_bank.get(plan["new_issue"], f"{plan['new_issue']}が結論をどう変えるか")
    weakness_effect = _weakness_effect(plan["attacked_weakness"])
    if turn_no == 1:
        if not turns:
            return _sanitize_fighter_speech(
                (
                f"まず言いたいのは『{own_basis}』という点だ。好みの話で終わらせず、{plan['new_issue']}を見ないと結論は決まらない。"
                f" {new_issue_detail}があるから、派手な反例だけ並べても話は片付かない。"
                f" まず押さえたいのは、{plan['target_issue']}や目先の見えやすさだけで判断すると土台を見失うということだ。"
                f" {own_line}という結論は、その土台まで見たときに一番筋が通る。"
                )
            )
    if turn_no == 2:
        lead = (
            f"相手は{plan['target_issue']}で押してきた。"
            if plan["target_issue"]
            else "相手は自分に有利な基準を先に置いて、そのまま話を決めようとしてきた。"
        )
        if speaker == "A":
            return _sanitize_fighter_speech(
                (
                f"{lead} でもそこには{plan['attacked_weakness']}弱さがある。{weakness_effect}から、そのまま乗るのは苦しい。"
                f" {own_line}の方がまだ筋が通るし、相手が頼っている前提はここで崩れる。"
                f" しかも{plan['new_issue']}まで見ると、相手の話は一気に窮屈になる。"
                )
            )
        return _sanitize_fighter_speech(
            (
            f"{lead} ただ、その初手は{plan['attacked_weakness']}。{weakness_effect}ので、見た目ほど強くない。"
            f" {own_line}の立場から見ると、相手の過大評価はここではっきり止まる。"
            f" しかも{plan['new_issue']}まで見ると、相手の優勢はだいぶ怪しい。"
            )
        )
    finish_line = _finish_line(plan, own_basis, own_line)
    openings = [
        f"相手がいま頼っているのは{plan['target_issue']}だ。",
        f"相手は{plan['target_issue']}が決め手だと言いたいんだろう。",
        f"また{plan['target_issue']}で押してきたけど、そこだけ見ても話は決まらない。",
    ]
    attacks = [
        f"でもそこには{plan['attacked_weakness']}弱さがある。{weakness_effect}から、その押し方は長く持たない。",
        f"苦しいのは{plan['attacked_weakness']}点だ。そこを突くと{weakness_effect}ので、相手の勢いは止まる。",
        f"その押し方は{plan['attacked_weakness']}。言い換えると、脚が一本折れたまま走ろうとしているようなものだ。",
    ]
    reinforcements_a = [
        f"だからこちらは『{own_basis}』という結論を守れる。{own_line}は、その弱点を踏まえてもまだ筋が通る。",
        f"こちらは話を戻しているだけじゃない。{own_line}の方が、相手の物差しでは拾えない部分まで説明できる。",
        f"{own_line}で見れば、相手の攻撃は物差しが一つしかなくて薄い。だからこちらの結論はまだ崩れない。",
    ]
    reinforcements_b = [
        f"こちらが言いたいのは単純で、{own_line}で見ると相手はまだ採用ラインを越えていないということだ。",
        f"反対と言っているだけじゃない。{own_line}で見ると、相手の基準は甘すぎる。",
        f"{own_basis}を守るなら、相手の説明の過剰さはここで止まる。そこまで見れば、相手はまだ届いていない。",
    ]
    new_issue_push = [
        f"さらに{plan['new_issue']}も見るべきだ。{new_issue_detail}が入ると、相手の説明はそのままでは持たない。",
        f"加えて{plan['new_issue']}が効く。{new_issue_detail}を無視すると、相手の話は急に薄く見える。",
        f"もう一つ言うなら{plan['new_issue']}だ。そこまで広げると、相手はさっきの説明だけでは逃げ切れない。",
    ]
    closings = [
        finish_line if plan["finish_intent"] == "finish" else f"要するに、相手は{plan['new_issue']}まで答えないと苦しい。そこを避けるなら、見えていた強さは見かけ倒しだったことになる。そこが一番きつい。",
        finish_line if plan["finish_intent"] == "finish" else f"これで相手は元の説明を繰り返すだけでは足りない。話を戻すだけなら、その場しのぎに見えてしまう。そこが苦しい。",
        finish_line if plan["finish_intent"] == "finish" else f"ここまで来ると、{plan['new_issue']}を無視した返しはただの逃げに見える。きれいに言い換えても、その穴は埋まらない。見た目だけでは持たない。",
    ]
    idx = (turn_no - 3) % 3
    if speaker == "A":
        return _sanitize_fighter_speech(f"{openings[idx]} {attacks[idx]} {reinforcements_a[idx]} {new_issue_push[idx]} {closings[idx]}")
    return _sanitize_fighter_speech(f"{openings[idx]} {attacks[idx]} {reinforcements_b[idx]} {new_issue_push[idx]} {closings[idx]}")


def _mock_turn_plan(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    latest_opponent: str = "",
    speech: str = "",
) -> dict[str, str]:
    issue_pool = _issue_pool(cfg.topic, speaker)
    prior_turn = turns[-1] if turns else None
    opponent_text = latest_opponent or (
        prior_turn.get("b") if speaker == "A" and prior_turn else prior_turn.get("a") if prior_turn else ""
    )
    prior_meta = ((prior_turn.get("meta") or {}).get("b") if speaker == "A" and prior_turn else (prior_turn.get("meta") or {}).get("a") if prior_turn else {}) or {}
    used_issues = {str(((turn.get("meta") or {}).get("a") or {}).get("new_issue") or "") for turn in turns}
    used_issues.update({str(((turn.get("meta") or {}).get("b") or {}).get("new_issue") or "") for turn in turns})
    target_issue = _clean_text(prior_meta.get("new_issue") or "") or _select_focus_term(opponent_text, issue_pool["reaction_terms"])
    attacked_weakness = issue_pool["weaknesses"][(turn_no - 1) % len(issue_pool["weaknesses"])]
    new_issue = _select_new_issue(issue_pool["new_issues"], used_issues)
    phase = "opening" if turn_no == 1 else "rebuttal" if turn_no == 2 else "rally"
    collapse_signal = _collapse_signal(turns, target_issue, attacked_weakness, turn_no)
    finish_intent = _finish_intent(turns, turn_no, collapse_signal)
    end_match = "yes" if finish_intent == "finish" and turn_no >= 5 else "no"
    return {
        "phase": phase,
        "target_issue": target_issue,
        "attacked_weakness": attacked_weakness,
        "new_issue": new_issue,
        "collapse_signal": collapse_signal,
        "finish_intent": finish_intent,
        "end_match": end_match,
    }


def _issue_pool(topic: str, speaker: str) -> dict[str, list[str]]:
    low = (topic or "").lower()
    if "金" in topic and "銀" in topic:
        if speaker == "A":
            return {
                "reaction_terms": ["中央銀行需要", "安全資産需要", "産業需要", "ボラティリティ", "保管コスト"],
                "weaknesses": ["価格の安さだけで質の違いを飛ばしている", "需要の持続性を短期価格と混同している", "資産の役割差を代替可能と見なしすぎている", "景気循環と通貨不安の局面差を潰している", "流動性と制度的需要の差を無視している"],
                "new_issues": ["中央銀行需要", "危機時流動性", "通貨不安ヘッジ", "実物保管コスト", "制度的採用"],
            }
        return {
            "reaction_terms": ["中央銀行需要", "安全資産需要", "通貨不安ヘッジ", "制度的採用", "危機時流動性"],
            "weaknesses": ["象徴的需要を実需より重く置きすぎている", "安全資産の看板だけで期待リターンを正当化している", "制度採用を将来期待で先取りしている", "ヘッジ機能と収益機能を混同している", "需給の柔軟性を見落としている"],
            "new_issues": ["産業需要", "価格弾力性", "太陽光需要", "供給制約の違い", "相対バリュエーション"],
        }
    if "戦争" in topic:
        if speaker == "A":
            return {
                "reaction_terms": ["抑止", "侵略", "国際法", "軍拡", "資源競争", "権威主義"],
                "weaknesses": ["規範目標と移行手段を混同している", "抑止の必要と軍拡の自己増殖を切り分けていない", "制度不在のまま理想だけを先取りしている", "短期安全保障と長期平和構築の時点を潰している", "相手の遵守インセンティブを説明していない"],
                "new_issues": ["国際法の強制力", "資源競争の管理", "戦後秩序の再建コスト", "協調安全保障の費用分担", "捕虜・民間人保護の執行"],
            }
        return {
            "reaction_terms": ["抑止", "侵略", "国際法", "軍拡", "資源競争", "権威主義"],
            "weaknesses": ["規範目標と移行手段を混同している", "抑止の必要と軍拡の自己増殖を切り分けていない", "制度不在のまま理想だけを先取りしている", "短期安全保障と長期平和構築の時点を潰している", "相手の遵守インセンティブを説明していない"],
            "new_issues": ["移行期間の抑止設計", "権威主義国家への執行力", "違反時の制裁能力", "軍事技術拡散", "安全保障ジレンマ"],
        }
    if "合理的" in topic or "意思決定" in topic:
        if speaker == "A":
            return {
                "reaction_terms": ["バイアス", "ヒューリスティック", "感情", "制度設計", "集団意思決定", "専門家判断"],
                "weaknesses": ["個人の認知限界と制度補正を混同している", "感情を非合理と短絡している", "合理性の定義が結果論に寄りすぎている", "個人判断と集団判断の水準を混ぜている", "時間制約下の合理性を静的基準で裁いている"],
                "new_issues": ["制度補正", "集団熟議の質", "専門家委任", "感情の情報価値", "限定合理性"],
            }
        return {
            "reaction_terms": ["バイアス", "ヒューリスティック", "感情", "制度設計", "集団意思決定", "専門家判断"],
            "weaknesses": ["個人の認知限界と制度補正を混同している", "感情を非合理と短絡している", "合理性の定義が結果論に寄りすぎている", "個人判断と集団判断の水準を混ぜている", "時間制約下の合理性を静的基準で裁いている"],
            "new_issues": ["バイアス補正の限界", "時間制約", "損失回避", "過信", "情報カスケード"],
        }
    return {
        "reaction_terms": ["評価基準", "安全性", "コスト", "実行条件", "副作用", "再現性"],
        "weaknesses": ["評価基準が閉じていない", "副作用の条件が曖昧なまま止めている", "費用対効果の比較軸を固定していない", "移行条件を後付けしている", "自説を修正する条件が不明なままだ"],
        "new_issues": ["検証指標", "停止条件", "移行コスト", "制度設計", "再評価ゲート"],
    }


def _issue_bank(topic: str) -> dict[str, str]:
    if "金" in topic and "銀" in topic:
        return {
            "中央銀行需要": "中央銀行が準備資産として買い続ける限り、景気循環が崩れても需要の底が抜けにくいこと",
            "安全資産需要": "景気後退や信用不安の局面で逃避資金が集まりやすいこと",
            "産業需要": "銀は太陽光や電子材料で実需が伸びるため、景気回復局面では価格を押し上げやすいこと",
            "価格弾力性": "銀は市場規模が小さいぶん資金流入時の値動きが大きくなりやすいこと",
            "危機時流動性": "危機局面では売りたい時に売れる厚い市場が長期保有の安心を支えること",
            "通貨不安ヘッジ": "通貨価値が揺れた時に保全先として機能するかが長期保有では重要なこと",
            "太陽光需要": "エネルギー転換が進むほど銀の実需が追加で積み上がること",
            "供給制約の違い": "副産物供給の多い銀は需要増に対して供給調整が遅れやすいこと",
            "相対バリュエーション": "金銀比価の歪みが修正される局面では銀の上昇幅が大きくなりやすいこと",
            "制度的採用": "準備資産や担保として制度に組み込まれるかが価格の粘着性を左右すること",
        }
    if "戦争" in topic:
        return {
            "抑止": "相手に攻撃コストを計算させて先制を思いとどまらせる仕組みが必要だということ",
            "国際法の強制力": "違反した国家に実際の不利益を与えられる執行力がなければ規範は空文化すること",
            "移行期間の抑止設計": "理想秩序へ移る途中で誰が安全保障を担うかを決めないと空白が生まれること",
            "資源競争の管理": "資源や物流の奪い合いを制度で抑えない限り戦争動機は残ること",
            "権威主義国家への執行力": "規範を拒む国家に対しても違反コストを課せるかが試されること",
            "戦後秩序の再建コスト": "戦争を止めても秩序再建に莫大な負担がかかるため予防制度の方が合理的なこと",
            "違反時の制裁能力": "合意破りに対して段階的かつ継続的な制裁を打てるかが抑止の実効性を決めること",
            "協調安全保障の費用分担": "平和維持のコストをどの国がどこまで持つかが制度の持続性を左右すること",
            "安全保障ジレンマ": "自衛の軍拡が相手には脅威と映り、相互に緊張を増幅すること",
            "軍事技術拡散": "先端兵器が広がるほど地域紛争が大規模化しやすくなること",
        }
    if "合理的" in topic or "意思決定" in topic:
        return {
            "バイアス": "人は損失回避や確証バイアスに引かれて判断を歪めやすいこと",
            "制度補正": "チェックリストや複数承認などで個人の偏りを削れること",
            "バイアス補正の限界": "補正制度があっても現場では時間不足や忖度で機能不全になること",
            "集団熟議の質": "良い議論は誤りを減らすが、悪い議論は同調圧力を増やすこと",
            "時間制約": "重要判断ほど締切圧力が強く、最適解より即答可能性が優先されること",
            "専門家委任": "複雑領域では専門家に委ねることで認知資源を節約できること",
            "損失回避": "人は利益より損失を過大評価し、撤退や挑戦の判断を歪めやすいこと",
            "感情の情報価値": "感情はノイズである一方で、危険や不公正への警報としても働くこと",
            "過信": "自分の予測精度を実力以上に見積もる癖が重要判断を狂わせること",
            "情報カスケード": "他人の判断に追随する連鎖が起きると、誤った合意でも修正しにくいこと",
        }
    return {
        "評価基準": "何をもって採否を決めるのかを固定しないと議論が漂流すること",
        "安全性": "副作用や事故コストを事前にどう管理するかが制度判断を左右すること",
        "コスト": "導入費と維持費の両方を見ないと総合判断を誤ること",
        "実行条件": "理想論ではなく現場で満たせる条件を置く必要があること",
        "副作用": "便益だけでなく副作用の発生条件も比較しなければならないこと",
        "再現性": "一度の成功例ではなく継続して同じ結果が出るかが重要なこと",
    }


def _weakness_effect(weakness: str) -> str:
    mapping = {
        "価格の安さだけで質の違いを飛ばしている": "価格の安い資産なら何でも長期保有に向くという雑な比較になる",
        "需要の持続性を短期価格と混同している": "長期保有で見るべき需給の粘着性が説明から抜け落ちる",
        "資産の役割差を代替可能と見なしすぎている": "安全資産と景気敏感資産を同じ物差しで扱う誤差が生まれる",
        "景気循環と通貨不安の局面差を潰している": "どの危機に強いのかという条件差が見えなくなる",
        "流動性と制度的需要の差を無視している": "市場が厚いことと制度に組み込まれていることを同じ話にしてしまう",
        "象徴的需要を実需より重く置きすぎている": "価格を支える実需の有無が置き去りになり、期待先行の議論になる",
        "安全資産の看板だけで期待リターンを正当化している": "守りの機能と増える資産かどうかが混線する",
        "制度採用を将来期待で先取りしている": "今の比較ではなく楽観シナリオ頼みの議論になる",
        "ヘッジ機能と収益機能を混同している": "守るための保有と増やすための保有が区別されなくなる",
        "需給の柔軟性を見落としている": "需要が伸びても供給で吸収される可能性を過小評価する",
        "規範目標と移行手段を混同している": "理想の終点とそこへ至る安全保障設計が一緒くたになる",
        "抑止の必要と軍拡の自己増殖を切り分けていない": "安全確保の話がそのまま無限の軍拡容認へ滑る",
        "制度不在のまま理想だけを先取りしている": "守られない規範を前提に政策判断してしまう",
        "短期安全保障と長期平和構築の時点を潰している": "いま必要な防衛と将来必要な制度改革が同じ速度で進む前提になる",
        "相手の遵守インセンティブを説明していない": "ルールを破る側がなぜ従うのかが空白のまま残る",
        "個人の認知限界と制度補正を混同している": "個人の弱さを制度改善でどこまで埋められるかが曖昧になる",
        "感情を非合理と短絡している": "警戒や倫理判断に必要な情報まで切り捨てることになる",
        "合理性の定義が結果論に寄りすぎている": "その時点で合理的だった判断まで事後結果だけで裁くことになる",
        "個人判断と集団判断の水準を混ぜている": "人間一般の限界と組織的補正の効果を同時に測れなくなる",
        "時間制約下の合理性を静的基準で裁いている": "現実の意思決定環境を無視した理想基準になる",
        "評価基準が閉じていない": "都合の悪い反例が出るたびに物差しを変えられてしまう",
        "副作用の条件が曖昧なまま止めている": "何を避けたいのかが曖昧で、停止判断の厳しさが測れない",
        "費用対効果の比較軸を固定していない": "便益とコストのどちらを重く見るかが毎回変わる",
        "移行条件を後付けしている": "反論を受けるたびに命題の輪郭が細っていく",
        "自説を修正する条件が不明なままだ": "相互検証ではなく一方的な保留宣言に近づく",
    }
    return mapping.get(weakness, "結論を動かす条件が見えず、議論が停止判断に寄ってしまう")


def _collapse_signal(
    turns: list[dict[str, Any]],
    target_issue: str,
    attacked_weakness: str,
    turn_no: int,
) -> str:
    if turn_no <= 2:
        return "none"
    if "後付け" in attacked_weakness or "修正" in attacked_weakness:
        return "proposition_retreat"
    if "評価基準" in attacked_weakness or "条件" in attacked_weakness:
        return "rule_blur"
    if len(turns) >= 2:
        last = turns[-1]
        prev = turns[-2]
        last_target = (((last.get("meta") or {}).get("a") or {}).get("target_issue") or "") + (((last.get("meta") or {}).get("b") or {}).get("target_issue") or "")
        prev_target = (((prev.get("meta") or {}).get("a") or {}).get("target_issue") or "") + (((prev.get("meta") or {}).get("b") or {}).get("target_issue") or "")
        if target_issue and last_target == prev_target:
            return "issue_loop"
    return "pressure"


def _finish_intent(turns: list[dict[str, Any]], turn_no: int, collapse_signal: str) -> str:
    if turn_no < 5:
        return "extend"
    if collapse_signal in {"proposition_retreat", "rule_blur", "issue_loop"}:
        return "finish"
    if turn_no >= 7:
        return "finish"
    return "push"


def _finish_line(plan: dict[str, str], own_basis: str, own_line: str) -> str:
    if plan["collapse_signal"] == "issue_loop":
        return (
            f"相手はもう{plan['target_issue']}の周辺を回るだけで、新しい立証を出せていない。"
            f" なら{own_line}を崩す材料は尽きている。"
        )
    if plan["collapse_signal"] == "proposition_retreat":
        return (
            f"相手は強い命題を掲げたまま、実際には条件付き後退でしか耐えていない。"
            f" それでは『{own_basis}』への反論にならない。だから{own_line}の方が残る。"
        )
    if plan["collapse_signal"] == "rule_blur":
        return (
            f"相手は基準を守ると言いながら、都合の悪い局面ではその基準自体を曖昧にしている。"
            f" なら{own_line}を止める根拠はもう残っていない。"
        )
    return (
        f"この時点で相手は{plan['target_issue']}を決め手にできていない。"
        f" むしろ{plan['new_issue']}まで見ると、残るのは{own_line}で、崩れたのは相手の説明だ。"
    )


META_STRATEGY_PATTERNS = [
    "次の一手",
    "この返し",
    "このラリー",
    "盤面",
    "戦略",
    "分析",
    "構造",
    "検証指標を入れる",
    "元の立場を使う",
    "崩しに行く",
    "採否の決定因子",
    "前提に盤面をずらす",
    "相手の最新",
    "勝ち筋",
    "ここを詰める",
]


def _looks_like_meta_strategy_text(text: str) -> bool:
    value = _clean_text(text or "")
    if not value:
        return False
    return any(pattern in value for pattern in META_STRATEGY_PATTERNS)


def _sanitize_fighter_speech(text: str) -> str:
    cleaned = _clean_text(text)
    replacements = {
        "ここで": "",
        "盤面": "話",
        "構造": "中身",
        "戦略": "主張",
        "分析": "話",
        "勝ち筋": "話",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("次の一手として", "")
    cleaned = cleaned.replace("この返しで", "")
    cleaned = cleaned.replace("このラリーは", "")
    cleaned = cleaned.replace("元の立場を使うと", "")
    cleaned = cleaned.replace("検証指標を入れる", "指標を見る")
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_focus_terms(text: str) -> list[str]:
    parts = re.findall(r"[A-Za-z]{3,}|[一-龥]{2,}|[ァ-ヶー]{2,}", text or "")
    out = []
    for part in parts:
        p = part.strip()
        if not p or p in JP_STOPWORDS:
            continue
        if p not in out:
            out.append(p)
    return out


def _select_focus_term(text: str, fallback_terms: list[str]) -> str:
    keywords = _extract_focus_terms(text)
    for word in keywords:
        for fallback in fallback_terms:
            if fallback in text and fallback not in JP_STOPWORDS:
                return fallback
        if word not in JP_STOPWORDS:
            return word
    return fallback_terms[0]


def _select_new_issue(candidates: list[str], used: set[str]) -> str:
    for issue in candidates:
        if issue and issue not in used:
            return issue
    return candidates[0]


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_gemini_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in response.get("candidates", []) if isinstance(response.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []) if isinstance(content.get("parts"), list) else []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "\n".join(parts).strip()


def _gemini_finish_reason(response: dict[str, Any]) -> str:
    candidates = response.get("candidates")
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        return _clean_text(candidates[0].get("finishReason") or "")
    return ""


def _extract_json_candidate(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""
    block = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if block:
        return block.group(1).strip()
    start_obj = text.find("{")
    end_obj = text.rfind("}")
    if start_obj >= 0 and end_obj > start_obj:
        return text[start_obj : end_obj + 1].strip()
    start_arr = text.find("[")
    end_arr = text.rfind("]")
    if start_arr >= 0 and end_arr > start_arr:
        return text[start_arr : end_arr + 1].strip()
    return ""


def _repair_json_candidate(candidate: str) -> str:
    repaired = str(candidate or "").strip()
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def _classify_provider_reason(message: str) -> str:
    text = str(message or "").lower()
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "401" in text or "403" in text or "auth" in text or "permission" in text:
        return "auth_error"
    if "404" in text or "not found" in text or "no model" in text:
        return "model_not_found"
    if "400" in text or "bad request" in text or "invalid argument" in text:
        return "bad_request"
    if "safety" in text or "blocked" in text:
        return "safety_block"
    if "empty text" in text or "empty_response" in text:
        return "empty_response"
    if "json" in text and "parse" in text:
        return "json_parse_error"
    if "schema" in text or "required summary keys" in text:
        return "schema_mismatch"
    if "http_error" in text or "network_error" in text or "provider_error" in text or "invalid_response_shape" in text:
        return "provider_error"
    return "unknown"


def _record_gemini_judge_debug(debug: dict[str, Any]) -> Path | None:
    payload = dict(debug)
    payload["saved_at"] = int(time.time())
    try:
        GEMINI_JUDGE_DEBUG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return GEMINI_JUDGE_DEBUG_PATH
    except Exception:
        return None


def _log_gemini_judge_event(status: str, debug: dict[str, Any]) -> None:
    summary = {
        "status": status,
        "reason": debug.get("reason", ""),
        "model": debug.get("model", GEMINI_MODEL),
        "status_code": debug.get("status_code"),
        "judge_payload_char_count": debug.get("judge_payload_char_count"),
        "transcript_char_count": debug.get("transcript_char_count"),
        "judge_prompt_char_count": debug.get("judge_prompt_char_count"),
        "latency_ms": debug.get("latency_ms"),
        "finish_reason": debug.get("finish_reason", ""),
        "provider_error": debug.get("provider_error", ""),
        "retry_count": debug.get("retry_count"),
        "attempt": debug.get("attempt"),
        "debug_path": debug.get("debug_path", ""),
    }
    print(f"[{status}] " + json.dumps(summary, ensure_ascii=False))


def _log_judge_stage(prefix: str, payload: dict[str, Any]) -> None:
    print(f"[{prefix}] " + json.dumps(payload, ensure_ascii=False))
