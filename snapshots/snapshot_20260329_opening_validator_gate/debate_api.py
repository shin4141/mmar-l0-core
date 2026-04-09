from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
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
GEMINI_MODEL = os.getenv("MMAR_DEBATE_GEMINI_MODEL", "").strip()
GEMINI_MODEL_CANDIDATES = [
    "models/gemini-2.5-flash",
    "models/gemini-flash-latest",
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-001",
]
_GEMINI_MODEL_CACHE: dict[str, str] = {}
REQUEST_TIMEOUT_S = 300
JUDGE_TIMEOUT_S = int(os.getenv("MMAR_DEBATE_JUDGE_TIMEOUT_S", "120"))
GEMINI_JUDGE_MAX_OUTPUT_TOKENS = int(os.getenv("MMAR_DEBATE_GEMINI_MAX_OUTPUT_TOKENS", "4096"))
GEMINI_JUDGE_PASS1_MAX_OUTPUT_TOKENS = int(os.getenv("MMAR_DEBATE_GEMINI_PASS1_MAX_OUTPUT_TOKENS", "512"))
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
    disable_live_judge: bool = False
    run_id: str = ""
    topic_hash: str = ""
    artifact_dir: str = ""
    port: str = ""
    build_sha: str = ""
    boot_at: str = ""
    created_at: str = ""
    session_id: str = ""
    route_signature: str = ""
    judge_provider: str = "gemini"
    fighter_a_model: str = ""
    fighter_b_model: str = ""
    judge_model: str = ""
    keyword: str = ""


class JudgeError(RuntimeError):
    def __init__(self, reason: str, message: str, *, debug: dict[str, Any] | None = None):
        super().__init__(message)
        self.reason = reason or "unknown"
        self.debug = debug or {}


def _compose_raw_reason(*parts: Any) -> str:
    values = [str(part).strip() for part in parts if str(part or "").strip()]
    return " | ".join(values)


JP_STOPWORDS = {
    "こと", "それ", "これ", "ため", "もの", "よう", "どこ", "どの", "その", "この", "あの",
    "そして", "しかし", "だから", "つまり", "直前", "主張", "議論", "制度", "導入", "限定", "常時",
    "評価", "条件", "安全", "立場", "相手", "自分", "要求", "論点", "反論", "理由", "可能", "必要",
    "基準", "定義", "ルール", "勝負", "支配", "議題", "優勢", "劣勢", "決定打", "決着",
}

FATAL_PHRASE_BANNED_TEXTS = {
    "この一文が勝敗の傾きを決めた。",
    "この試合の決め手だった。",
    "ここが分岐点だった。",
    "この場面で勝敗の傾きが固まった。",
    "最も流れを動かした応酬だった。",
}

GENERIC_WHY_TEXTS = {
    "強かったから。",
    "説得力があった。",
    "優勢になった。",
}

SURFACE_META_BANNED_PHRASES = [
    "相手の核心",
    "あなたの核心",
    "弱点は",
    "問題は一行",
    "話をずらしてる",
    "それは苦しい",
    "結論は一つ",
    "核心は一点",
    "論点はこうだ",
    "一刀両断",
]


def run_debate(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = _normalize_config(payload)
    session = _session_runtime(cfg)
    debate, transcript, trace_entries = _run_debate_with_provider_fallbacks(cfg, session)
    judge_started_at = time.time()
    session.progress(
        stage="judge_summary",
        active_speakers=["judge"],
        active_providers={"judge": cfg.judge_provider},
    )
    debate["summary"] = _session_inline_judge_summary(cfg, debate.get("turns") or [], transcript, session.provider_statuses)
    session.append_elapsed_phase("judge_summary", judge_started_at)
    session.append_elapsed_phase("run_debate_total", session.phase_entries[0]["at"], completed_turns=len(debate.get("turns") or []))
    session.progress(
        stage="completed",
        extra={"completed_turns": len(debate.get("turns") or [])},
    )
    return _session_debate_response(cfg, session, debate, trace_entries)


def run_live_judge(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = _normalize_config(payload)
    turns = payload.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("missing_turns")
    transcript = str(payload.get("transcript") or "").strip()
    if not transcript:
        raise ValueError("missing_transcript")
    judge_started_at = time.time()
    session = _session_runtime(cfg)
    session.progress(
        stage="judge_summary",
        active_speakers=["judge"],
        active_providers={"judge": cfg.judge_provider},
    )
    summary, judge_status = _judge_summary_data(cfg, turns, transcript)
    user_pick = _clean_text(payload.get("user_pick") or "")
    user_reason = _clean_text(payload.get("user_reason") or "")
    winner_obj = summary.get("winner") if isinstance(summary.get("winner"), dict) else {}
    actual_winner = _clean_text(winner_obj.get("side") if isinstance(winner_obj, dict) else summary.get("winner") or "")
    if user_pick:
        summary["prediction_check"] = {
            "user_pick": user_pick,
            "user_reason": user_reason,
            "actual_winner": actual_winner,
            "match": user_pick == actual_winner,
        }
        summary["prediction_feedback"] = _build_prediction_feedback(
            user_pick,
            user_reason,
            actual_winner,
            _clean_text(summary.get("reason_one_liner") or ""),
            summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {},
        )
        summary["fairness_rewrite"] = _build_fairness_rewrite(
            user_pick,
            actual_winner,
            _clean_text(summary.get("reason_one_liner") or ""),
        )
    _apply_provider_status_delta(session.provider_statuses, "judge", judge_status)
    session.append_elapsed_phase("judge_summary", judge_started_at)
    session.progress(stage="completed", extra={"completed_turns": len(turns)})
    judge_info = session.provider_statuses.get("judge", {})
    judge_mode = str(judge_info.get("mode") or "")
    if judge_mode != "live":
        raw_reason = str(judge_info.get("raw_reason") or judge_info.get("reason") or "").strip()
        reason = str(judge_info.get("reason") or "judge failed").strip()
        error_text = f"Judge live failed: {reason}"
        if raw_reason and raw_reason != reason:
            error_text = f"{error_text} ({raw_reason})"
        return {
            "ok": False,
            "error": error_text,
            "mode": "judge-failed",
            "provider_statuses": session.provider_statuses,
            "artifact_phase_entries": session.phase_entries,
        }
    return {
        "ok": True,
        "session_id": cfg.session_id,
        "route_signature": cfg.route_signature,
        "mode": "live",
        "fighter_a_provider": cfg.fighter_a_provider,
        "fighter_b_provider": cfg.fighter_b_provider,
        "judge_provider": cfg.judge_provider,
        "fighter_a_model": cfg.fighter_a_model,
        "fighter_b_model": cfg.fighter_b_model,
        "judge_model": cfg.judge_model,
        "provider_statuses": session.provider_statuses,
        "summary": summary,
        "artifact_phase_entries": session.phase_entries,
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
    gemini_key = str(os.getenv("GEMINI_API_KEY") or "").strip()
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
    keyword = str(payload.get("keyword") or "").strip()
    turn_count_raw = payload.get("turn_count", payload.get("turnCount", 3))
    try:
        turn_count = int(turn_count_raw)
    except Exception:
        turn_count = 3
    turn_count = 5 if turn_count == 5 else 3
    mode = str(payload.get("mode") or "casual").strip().lower()
    if mode not in {"casual", "pro"}:
        mode = "casual"
    api_keys = payload.get("api_keys") if isinstance(payload.get("api_keys"), dict) else {}
    force_mock = bool(payload.get("_force_mock"))
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
    if force_mock:
        openai_key = ""
        anthropic_key = ""
        gemini_key = ""
    else:
        openai_key = str(api_keys.get("openai") or os.getenv("OPENAI_API_KEY") or "").strip()
        anthropic_key = str(api_keys.get("anthropic") or os.getenv("ANTHROPIC_API_KEY") or "").strip()
        gemini_key = str(os.getenv("GEMINI_API_KEY") or "").strip()
    artifact_meta = payload.get("_artifact_meta") if isinstance(payload.get("_artifact_meta"), dict) else {}
    disable_live_judge = bool(payload.get("_disable_live_judge")) or os.getenv("MMAR_DISABLE_LIVE_JUDGE", "").lower() == "true"
    if not topic or not side_a or not side_b:
        raise ValueError("missing_topic_or_positions")
    fighter_a_model = _resolve_provider_model(fighter_a_provider, openai_key, anthropic_key, gemini_key)
    fighter_b_model = _resolve_provider_model(fighter_b_provider, openai_key, anthropic_key, gemini_key)
    judge_provider = "gemini"
    judge_model = _resolve_provider_model(judge_provider, openai_key, anthropic_key, gemini_key)
    session_id = str(artifact_meta.get("run_id") or "")
    route_signature = _route_signature(
        topic_hash=str(artifact_meta.get("topic_hash") or ""),
        turn_count=turn_count,
        mode=mode,
        fighter_a_provider=fighter_a_provider,
        fighter_b_provider=fighter_b_provider,
        judge_provider=judge_provider,
        fighter_a_model=fighter_a_model,
        fighter_b_model=fighter_b_model,
        judge_model=judge_model,
        disable_live_judge=disable_live_judge,
    )
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
        disable_live_judge=disable_live_judge,
        run_id=str(artifact_meta.get("run_id") or ""),
        topic_hash=str(artifact_meta.get("topic_hash") or ""),
        artifact_dir=str(artifact_meta.get("artifact_dir") or ""),
        port=str(artifact_meta.get("port") or ""),
        build_sha=str(artifact_meta.get("build_sha") or ""),
        boot_at=str(artifact_meta.get("boot_at") or ""),
        created_at=str(artifact_meta.get("created_at") or ""),
        session_id=session_id,
        route_signature=route_signature,
        judge_provider=judge_provider,
        fighter_a_model=fighter_a_model,
        fighter_b_model=fighter_b_model,
        judge_model=judge_model,
        keyword=keyword,
    )


def _phase_entry(name: str, started_at: float, **extra: Any) -> dict[str, Any]:
    ended_at = time.time()
    return {
        "name": name,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": ended_at - started_at,
        **extra,
    }


def _append_phase_entry(phase_entries: list[dict[str, Any]], name: str, started_at: float, **extra: Any) -> None:
    phase_entries.append(_phase_entry(name, started_at, **extra))


def _session_metadata(cfg: DebateConfig) -> dict[str, Any]:
    return {
        "session_id": cfg.session_id,
        "route_signature": cfg.route_signature,
        "fighter_a_provider": cfg.fighter_a_provider,
        "fighter_b_provider": cfg.fighter_b_provider,
        "judge_provider": cfg.judge_provider,
        "fighter_a_model": cfg.fighter_a_model,
        "fighter_b_model": cfg.fighter_b_model,
        "judge_model": cfg.judge_model,
        "mode": cfg.mode,
        "topic_hash": cfg.topic_hash,
        "turn_count": cfg.turn_count,
    }


def _session_judge_meta(provider_statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    judge_info = provider_statuses.get("judge", provider_statuses.get("gemini", {}))
    return {
        "judge_mode": judge_info.get("mode", ""),
        "judge_reason": judge_info.get("reason", ""),
        "judge_raw_reason": judge_info.get("raw_reason", ""),
        "judge_stage": judge_info.get("judge_stage", ""),
        "judge_provider": judge_info.get("judge_provider", "gemini"),
        "judge_model": judge_info.get("judge_model", GEMINI_MODEL),
        "judge_request_variant": judge_info.get("judge_request_variant", ""),
        "judge_request_url": judge_info.get("judge_request_url", ""),
        "judge_request_body_shape": judge_info.get("judge_request_body_shape", ""),
        "judge_request_has_generation_config": bool(judge_info.get("judge_request_has_generation_config", False)),
        "judge_prompt_chars": int(judge_info.get("judge_prompt_chars", 0) or 0),
        "judge_prompt_preview": str(judge_info.get("judge_prompt_preview", "") or ""),
        "judge_raw_received": bool(judge_info.get("judge_raw_received", False)),
        "judge_parse_success": bool(judge_info.get("judge_parse_success", False)),
    }


def _session_debate_response(
    cfg: DebateConfig,
    session: _SessionRuntime,
    debate: dict[str, Any],
    trace_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    judge_meta = _session_judge_meta(session.provider_statuses)
    return {
        "ok": True,
        "run_id": cfg.run_id,
        "session_id": cfg.session_id,
        "route_signature": cfg.route_signature,
        "topic_hash": cfg.topic_hash,
        "artifact_bundle_dir": cfg.artifact_dir,
        "artifact_created_at": cfg.created_at,
        "fighter_a_provider": cfg.fighter_a_provider,
        "fighter_b_provider": cfg.fighter_b_provider,
        "judge_provider": cfg.judge_provider,
        "fighter_a_model": cfg.fighter_a_model,
        "fighter_b_model": cfg.fighter_b_model,
        "judge_model": cfg.judge_model,
        "mode": _derive_mode(session.provider_statuses),
        "warning": _build_warning(session.provider_statuses),
        "judge_meta": judge_meta,
        "output_meta": judge_meta,
        "provider_statuses": session.provider_statuses,
        "debate": debate,
        "artifact_trace_entries": trace_entries,
        "artifact_phase_entries": session.phase_entries,
    }


@dataclass
class _SessionRuntime:
    cfg: DebateConfig
    provider_statuses: dict[str, dict[str, Any]]
    phase_entries: list[dict[str, Any]]

    def mark_started(self, name: str, **extra: Any) -> float:
        started_at = time.time()
        self.phase_entries.append({"name": name, "at": started_at, **extra})
        return started_at

    def append_phase(self, name: str, started_at: float, **extra: Any) -> None:
        _append_phase_entry(self.phase_entries, name, started_at, **extra)

    def append_elapsed_phase(self, name: str, started_at: float, **extra: Any) -> None:
        self.phase_entries.append(_phase_entry(name, started_at, **extra))

    def progress(
        self,
        *,
        stage: str,
        turn: int | None = None,
        active_speakers: list[str] | None = None,
        active_providers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        _write_progress_checkpoint(
            self.cfg,
            stage=stage,
            phase_entries=self.phase_entries,
            provider_statuses=self.provider_statuses,
            turn=turn,
            active_speakers=active_speakers,
            active_providers=active_providers,
            extra=extra,
        )

    def speaker_progress(
        self,
        *,
        speaker: str,
        provider: str,
        turn: int,
        provider_call_index: int,
        request_phase: str,
        prompt: str,
        transcript: str,
        started_at: float,
        completed: bool,
    ) -> None:
        _write_speaker_progress_checkpoint(
            self.cfg,
            speaker=speaker,
            provider=provider,
            turn=turn,
            provider_call_index=provider_call_index,
            request_phase=request_phase,
            prompt=prompt,
            transcript=transcript,
            started_at=started_at,
            completed=completed,
        )


def _session_runtime(cfg: DebateConfig) -> _SessionRuntime:
    return _SessionRuntime(
        cfg=cfg,
        provider_statuses=_initial_provider_statuses(cfg),
        phase_entries=[],
    )


def _write_progress_checkpoint(
    cfg: DebateConfig,
    *,
    stage: str,
    phase_entries: list[dict[str, Any]],
    provider_statuses: dict[str, dict[str, str]],
    turn: int | None = None,
    active_speakers: list[str] | None = None,
    active_providers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    artifact_dir = _clean_text(cfg.artifact_dir)
    if not artifact_dir:
        return
    try:
        bundle_dir = Path(artifact_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        started_at = phase_entries[0].get("at") if phase_entries and isinstance(phase_entries[0], dict) else None
        elapsed = max(0.0, time.time() - float(started_at)) if started_at else None
        payload: dict[str, Any] = {
            "run_id": cfg.run_id,
            "topic": cfg.topic,
            "topic_hash": cfg.topic_hash,
            "artifact_bundle_dir": artifact_dir,
            "artifact_created_at": cfg.created_at,
            **_session_metadata(cfg),
            "stage": stage,
            "turn": turn,
            "active_speakers": list(active_speakers or []),
            "active_providers": dict(active_providers or {}),
            "provider_statuses": provider_statuses,
            "phase_entry_count": len(phase_entries),
            "last_phase_entry": phase_entries[-1] if phase_entries else {},
            "elapsed_seconds": elapsed,
        }
        if extra:
            payload.update(extra)
        (bundle_dir / "progress.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _write_speaker_progress_checkpoint(
    cfg: DebateConfig,
    *,
    speaker: str,
    provider: str,
    turn: int,
    provider_call_index: int,
    request_phase: str,
    prompt: str,
    transcript: str,
    started_at: float,
    completed: bool = False,
) -> None:
    artifact_dir = _clean_text(cfg.artifact_dir)
    if not artifact_dir:
        return
    try:
        bundle_dir = Path(artifact_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": cfg.run_id,
            "topic": cfg.topic,
            "topic_hash": cfg.topic_hash,
            "artifact_bundle_dir": artifact_dir,
            "artifact_created_at": cfg.created_at,
            **_session_metadata(cfg),
            "execution_stage": "provider_call",
            "turn": turn,
            "active_speaker": speaker,
            "active_provider": provider,
            "provider_call_index": provider_call_index,
            "provider_call_started_at": started_at,
            "elapsed_seconds": max(0.0, time.time() - started_at),
            "prompt_char_count": len(prompt or ""),
            "transcript_char_count": len(transcript or ""),
            "request_model": _speaker_request_model(cfg, speaker, provider),
            "request_phase": request_phase,
            "completed": completed,
        }
        (bundle_dir / f"speaker_progress_{speaker}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _timed_speaker_turn_data(
    *,
    speaker: str,
    provider: str,
    prompt: str,
    cfg: DebateConfig,
    session: _SessionRuntime,
    fallback_speech: str,
    turn_no: int,
    transcript: str,
    stage_label: str,
) -> tuple[dict[str, Any], float, float]:
    started_at = time.time()
    provider_call_index = (turn_no - 1) * 2 + (1 if speaker == "A" else 2)
    session.speaker_progress(
        speaker=speaker,
        provider=provider,
        turn=turn_no,
        provider_call_index=provider_call_index,
        request_phase=stage_label,
        prompt=prompt,
        transcript=transcript,
        started_at=started_at,
        completed=False,
    )
    data = _speaker_turn_data(
        speaker=speaker,
        provider=provider,
        prompt=prompt,
        cfg=cfg,
        fallback_speech=fallback_speech,
    )
    _apply_provider_status_delta(session.provider_statuses, provider, data.get("_provider_status"))
    ended_at = time.time()
    session.speaker_progress(
        speaker=speaker,
        provider=provider,
        turn=turn_no,
        provider_call_index=provider_call_index,
        request_phase=stage_label,
        prompt=prompt,
        transcript=transcript,
        started_at=started_at,
        completed=True,
    )
    return data, started_at, ended_at


def _finalize_fighter_output(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    text: str,
    latest_opponent: str,
    debug_trace: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    finalized = _sanitize_fighter_speech(text)
    if cfg.turn_count == 3 and turn_no == 3:
        a2_text = _clean_text((turns[1].get("a") if len(turns) > 1 else "") or "")
        b2_text = _clean_text((turns[1].get("b") if len(turns) > 1 else "") or "")
        advantage = _estimate_advantage(a2_text, b2_text)
        if advantage in {"A", "B"} and speaker != advantage:
            finalized = _remove_analogy(finalized)
    validation = _three_turn_validation_report(speaker, cfg, turns, turn_no, finalized, latest_opponent) if cfg.turn_count == 3 else {}
    alignment = _response_alignment_report(speaker, cfg, turn_no, finalized, latest_opponent) if cfg.turn_count == 3 else {}
    stage1_pass = bool(validation.get("three_turn_contract_pass", True)) if cfg.turn_count == 3 else True
    stage2_pass = bool(alignment.get("stage2_pass", True)) if cfg.turn_count == 3 else True
    if cfg.turn_count == 3 and turn_no >= 2 and (not stage1_pass or not stage2_pass):
        candidates: list[tuple[str, str, dict[str, Any], dict[str, Any], int]] = []

        def _candidate_score(candidate_validation: dict[str, Any], candidate_alignment: dict[str, Any]) -> int:
            return (
                (10 if candidate_validation.get("three_turn_contract_pass") else 0)
                + (6 if candidate_alignment.get("stage2_pass") else 0)
                + (3 if candidate_alignment.get("response_alignment_pass") else 0)
                + int(candidate_validation.get("density_score") or 0)
            )

        candidates.append(("current", finalized, validation, alignment, _candidate_score(validation, alignment)))

        repair_candidate = _sanitize_fighter_speech(_three_turn_repair_speech(speaker, cfg, turns, turn_no, latest_opponent))
        repair_validation = _three_turn_validation_report(speaker, cfg, turns, turn_no, repair_candidate, latest_opponent)
        repair_alignment = _response_alignment_report(speaker, cfg, turn_no, repair_candidate, latest_opponent)
        candidates.append(("repair", repair_candidate, repair_validation, repair_alignment, _candidate_score(repair_validation, repair_alignment)))

        grounded_candidate = _sanitize_fighter_speech(_three_turn_grounded_surface(speaker, cfg, turn_no, latest_opponent))
        grounded_validation = _three_turn_validation_report(speaker, cfg, turns, turn_no, grounded_candidate, latest_opponent)
        grounded_alignment = _response_alignment_report(speaker, cfg, turn_no, grounded_candidate, latest_opponent)
        candidates.append(("grounded", grounded_candidate, grounded_validation, grounded_alignment, _candidate_score(grounded_validation, grounded_alignment)))

        chosen_label, finalized, validation, alignment, _ = max(candidates, key=lambda item: item[4])
        debug_trace["finalize_candidates"] = [
            {
                "candidate_name": label,
                "stage1_pass": bool(candidate_validation.get("three_turn_contract_pass")),
                "stage2_pass": bool(candidate_alignment.get("stage2_pass")),
                "failures": list(candidate_validation.get("three_turn_failures", [])),
                "warnings": list(candidate_validation.get("three_turn_warnings", [])),
                "response_alignment_pass": bool(candidate_alignment.get("response_alignment_pass")),
                "density_score": int(candidate_validation.get("density_score") or 0),
                "selected": label == chosen_label,
                "text_preview": _clean_text(candidate_text)[:160],
            }
            for label, candidate_text, candidate_validation, candidate_alignment, _score in candidates
        ]
        stage1_pass = bool(validation.get("three_turn_contract_pass"))
        stage2_pass = bool(alignment.get("stage2_pass"))
        if chosen_label != "current":
            debug_trace["repair_triggered"] = True
            debug_trace["adopted_stage"] = "finalize-repair" if chosen_label == "repair" else "finalize-grounded-fallback"
    debug_trace["sanitize_applied"] = True
    debug_trace["keyword_used"] = _keyword_usage(finalized, cfg.keyword)
    debug_trace["keyword_bonus"] = _keyword_bonus(finalized, cfg.keyword)
    debug_trace["stage1_pass"] = stage1_pass
    debug_trace["stage2_pass"] = stage2_pass
    debug_trace["opponent_focus"] = alignment.get("opponent_focus", "")
    debug_trace["response_alignment_pass"] = alignment.get("response_alignment_pass", stage2_pass)
    debug_trace["route_name"] = debug_trace.get("adopted_stage") or "initial"
    if cfg.turn_count == 3:
        validation.update(
            {
                "keyword_used": debug_trace["keyword_used"],
                "keyword_bonus": debug_trace["keyword_bonus"],
                "stage1_pass": stage1_pass,
                "stage2_pass": stage2_pass,
                "opponent_focus": alignment.get("opponent_focus", ""),
                "response_alignment_pass": alignment.get("response_alignment_pass", stage2_pass),
            }
        )
    return finalized, validation


def _estimate_advantage(a2_text: str, b2_text: str) -> str:
    score_a = len(_clean_text(a2_text))
    score_b = len(_clean_text(b2_text))
    if score_a > score_b:
        return "A"
    if score_b > score_a:
        return "B"
    return "neutral"


def _remove_analogy(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return cleaned
    patterns = ("宝くじ", "ゲーム", "スポーツ", "仕事")
    sentences = re.split(r"(?<=[。.!?！？])\s*", cleaned)
    kept: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        if any(pattern in sentence for pattern in patterns):
            continue
        kept.append(sentence)
    stripped = "".join(kept).strip()
    if stripped:
        return stripped
    for pattern in patterns:
        cleaned = cleaned.replace(pattern, "")
    return cleaned.strip()


def _keyword_usage(text: str, keyword: str) -> bool:
    clean_keyword = _clean_text(keyword).lower()
    if not clean_keyword:
        return False
    return clean_keyword in _clean_text(text).lower()


def _keyword_bonus(text: str, keyword: str) -> int:
    clean_keyword = _clean_text(keyword).lower()
    cleaned_text = _clean_text(text)
    if not clean_keyword:
        return 0
    if clean_keyword not in cleaned_text.lower():
        return 0
    if len(cleaned_text) < 80:
        return 0
    if "ようなもの" in cleaned_text or "みたいな" in cleaned_text:
        return 2
    return 1


def _build_keyword_note(keyword: str, topic: str) -> str:
    clean_keyword = _clean_text(keyword)
    if not clean_keyword:
        return ""
    topic_hint = _clean_text(topic or "この議論")
    return f"Keyword note: 「{clean_keyword}」で言えば、この議論は{topic_hint}で何が決め手になるかを見極める話に近い。"


def _build_prediction_feedback(
    user_pick: str,
    user_reason: str,
    actual_winner: str,
    reason_one_liner: str,
    weak_spot: dict[str, Any],
) -> str:
    if not user_pick:
        return ""
    picked_reason = _clean_text(user_reason)
    actual = _clean_text(actual_winner or "")
    weak_label = _clean_text((weak_spot or {}).get("label") or "弱点")
    if user_pick == actual:
        if picked_reason:
            return f"あなたは「{picked_reason}」を見て勝ち筋を読めていた。実際にもその見立ては外れておらず、最後は{weak_label}の差が押し切りに効いた。"
        return f"勝者予想は当たり。最後は{weak_label}の差がそのまま判定に残った。"
    if picked_reason:
        return f"あなたが拾った「{picked_reason}」は途中の見どころとしては有効だったが、最終判定では{_first_sentence(reason_one_liner)}"
    return f"途中の印象は拾えていたが、最終判定では{_first_sentence(reason_one_liner)}"


def _build_fairness_rewrite(
    user_pick: str,
    actual_winner: str,
    reason_one_liner: str,
) -> str:
    if not user_pick:
        return ""
    if user_pick == actual_winner:
        return ""
    winner_side = actual_winner if actual_winner in {"A", "B"} else "勝者"
    return f"次に見るなら、『どちらが好きか』ではなく『どちらが最後に成立条件を残したか』に言い換えると、この判定軸はもっとフェアに追える。"


def _run_debate_with_provider_fallbacks(cfg: DebateConfig, session: _SessionRuntime) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    turns: list[dict[str, Any]] = []
    transcript = ""
    round_debug: list[dict[str, Any]] = []
    trace_entries: list[dict[str, Any]] = []
    provider_statuses = session.provider_statuses
    phase_entries = session.phase_entries
    session.mark_started("run_debate_start", turn_count=cfg.turn_count)
    session.progress(
        stage="run_debate_start",
        extra={"turn_count": cfg.turn_count},
    )
    for turn_no in range(1, cfg.turn_count + 1):
        stage_label = _stage_label(turn_no, cfg.turn_count)
        round_snapshot = _build_round_snapshot(turn_no, transcript, turns)
        prior_transcript = round_snapshot["text"]
        a_latest_opponent = _opponent_last_statement("A", turns)
        b_latest_opponent = _opponent_last_statement("B", turns)
        a_prompt = _speaker_prompt("A", cfg.fighter_a_provider, cfg, turns, prior_transcript, turn_no, stage_label)
        b_prompt = _speaker_prompt("B", cfg.fighter_b_provider, cfg, turns, prior_transcript, turn_no, stage_label)
        a_fallback = _fallback_speech("A", cfg, turns, turn_no, a_latest_opponent)
        b_fallback = _fallback_speech("B", cfg, turns, turn_no, b_latest_opponent)
        turn_phase_started_at = time.time()
        session.phase_entries.append({"name": "turn_phase_start", "at": turn_phase_started_at, "turn": turn_no})
        session.progress(
            stage="provider_call",
            turn=turn_no,
            active_speakers=["A", "B"],
            active_providers={"A": cfg.fighter_a_provider, "B": cfg.fighter_b_provider},
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            a_future = executor.submit(
                _timed_speaker_turn_data,
                speaker="A",
                provider=cfg.fighter_a_provider,
                prompt=a_prompt,
                cfg=cfg,
                session=session,
                fallback_speech=a_fallback,
                turn_no=turn_no,
                transcript=prior_transcript,
                stage_label=stage_label,
            )
            b_future = executor.submit(
                _timed_speaker_turn_data,
                speaker="B",
                provider=cfg.fighter_b_provider,
                prompt=b_prompt,
                cfg=cfg,
                session=session,
                fallback_speech=b_fallback,
                turn_no=turn_no,
                transcript=prior_transcript,
                stage_label=stage_label,
            )
            a_data, a_provider_started_at, a_provider_ended_at = a_future.result()
            b_data, b_provider_started_at, b_provider_ended_at = b_future.result()
        phase_entries.append(
            {
                "name": "provider_call",
                "turn": turn_no,
                "speaker": "A",
                "provider": cfg.fighter_a_provider,
                "provider_mode": a_data.get("_provider_mode") or "",
                "started_at": a_provider_started_at,
                "ended_at": a_provider_ended_at,
                "elapsed_seconds": a_provider_ended_at - a_provider_started_at,
                "phase_group": f"turn-{turn_no}",
            }
        )
        phase_entries.append(
            {
                "name": "provider_call",
                "turn": turn_no,
                "speaker": "B",
                "provider": cfg.fighter_b_provider,
                "provider_mode": b_data.get("_provider_mode") or "",
                "started_at": b_provider_started_at,
                "ended_at": b_provider_ended_at,
                "elapsed_seconds": b_provider_ended_at - b_provider_started_at,
                "phase_group": f"turn-{turn_no}",
            }
        )
        a_postprocess_started_at = time.time()
        a_initial_processing_started_at = time.time()
        a_initial_raw = _clean_text(a_data.get("speech") or a_fallback)
        a_initial_text = _sanitize_fighter_speech(a_initial_raw)
        a_text = a_initial_text
        a_validation = _three_turn_validation_report("A", cfg, turns, turn_no, a_text, a_latest_opponent) if cfg.turn_count == 3 else {}
        session.append_phase(
            "postprocess_initial_prepare",
            a_initial_processing_started_at,
            turn=turn_no,
            speaker="A",
        )
        a_debug_trace = {
            "provider_mode": a_data.get("_provider_mode") or "",
            "raw_provider_output_hash": hashlib.sha1(_clean_text(a_data.get("_provider_raw_output") or "").encode("utf-8")).hexdigest() if _clean_text(a_data.get("_provider_raw_output") or "") else "",
            "raw_provider_char_count": len(_clean_text(a_data.get("_provider_raw_speech") or "")),
            "raw_provider_has_banned_meta": _contains_banned_surface_meta(a_data.get("_provider_raw_speech") or "") or _looks_like_design_memo_speech(a_data.get("_provider_raw_speech") or ""),
            "sanitized_initial_text": a_initial_text,
            "initial_validation": dict(a_validation),
            "opening_validated": turn_no != 1,
            "opening_validation_failures": [],
            "retry_triggered": False,
            "repair_triggered": False,
            "adopted_stage": "initial",
        }
        if turn_no == 1:
            opening_ok, opening_failures = _is_valid_opening_speech(a_text)
            a_debug_trace["opening_validated"] = opening_ok
            a_debug_trace["opening_validation_failures"] = list(opening_failures)
            if not opening_ok:
                a_debug_trace["retry_triggered"] = True
                retry_prompt = _opening_retry_prompt(a_prompt, opening_failures)
                retry_started_at = time.time()
                retry_data = _speaker_turn_data(
                    speaker="A",
                    provider=cfg.fighter_a_provider,
                    prompt=retry_prompt,
                    cfg=cfg,
                    fallback_speech=_three_turn_repair_speech("A", cfg, turns, turn_no, a_latest_opponent),
                )
                _apply_provider_status_delta(provider_statuses, cfg.fighter_a_provider, retry_data.get("_provider_status"))
                session.append_phase(
                    "postprocess_opening_retry_provider_call",
                    retry_started_at,
                    turn=turn_no,
                    speaker="A",
                    provider=cfg.fighter_a_provider,
                    provider_mode=retry_data.get("_provider_mode") or "",
                )
                retry_post_started_at = time.time()
                retry_raw = _clean_text(retry_data.get("speech") or _three_turn_repair_speech("A", cfg, turns, turn_no, a_latest_opponent))
                retry_text = _sanitize_fighter_speech(retry_raw)
                retry_ok, retry_failures = _is_valid_opening_speech(retry_text)
                session.append_phase(
                    "postprocess_opening_retry_evaluate",
                    retry_post_started_at,
                    turn=turn_no,
                    speaker="A",
                )
                a_debug_trace["retry_provider_mode"] = retry_data.get("_provider_mode") or ""
                a_debug_trace["retry_raw_provider_output_hash"] = hashlib.sha1(_clean_text(retry_data.get("_provider_raw_output") or "").encode("utf-8")).hexdigest() if _clean_text(retry_data.get("_provider_raw_output") or "") else ""
                a_debug_trace["retry_raw_provider_char_count"] = len(_clean_text(retry_data.get("_provider_raw_speech") or ""))
                a_debug_trace["retry_raw_provider_has_banned_meta"] = _contains_banned_surface_meta(retry_data.get("_provider_raw_speech") or "") or _looks_like_design_memo_speech(retry_data.get("_provider_raw_speech") or "")
                a_debug_trace["retry_sanitized_text"] = retry_text
                a_debug_trace["opening_retry_validated"] = retry_ok
                a_debug_trace["opening_retry_failures"] = list(retry_failures)
                if retry_ok:
                    a_data = retry_data
                    a_text = retry_text
                    a_validation = _three_turn_validation_report("A", cfg, turns, turn_no, a_text, a_latest_opponent) if cfg.turn_count == 3 else {}
                    a_debug_trace["opening_validated"] = True
                    a_debug_trace["opening_validation_failures"] = []
                    a_debug_trace["adopted_stage"] = "opening-retry"
                else:
                    a_text = _three_turn_grounded_surface("A", cfg, turn_no, a_latest_opponent)
                    a_validation = _three_turn_validation_report("A", cfg, turns, turn_no, a_text, a_latest_opponent) if cfg.turn_count == 3 else {}
                    a_debug_trace["repair_triggered"] = True
                    a_debug_trace["repair_text"] = a_text
                    a_debug_trace["repair_validation"] = dict(a_validation)
                    a_debug_trace["adopted_stage"] = "opening-grounded"
        if (
            cfg.turn_count == 3
            and turn_no != 1
            and not a_validation.get("three_turn_contract_pass")
            and (a_data.get("_provider_mode") or "") != "live"
        ):
            a_debug_trace["retry_triggered"] = True
            retry_prompt = _three_turn_retry_prompt(a_prompt, a_validation.get("three_turn_failures") or [], turn_no)
            retry_started_at = time.time()
            retry_data = _speaker_turn_data(
                speaker="A",
                provider=cfg.fighter_a_provider,
                prompt=retry_prompt,
                cfg=cfg,
                fallback_speech=_three_turn_repair_speech("A", cfg, turns, turn_no, a_latest_opponent),
            )
            _apply_provider_status_delta(provider_statuses, cfg.fighter_a_provider, retry_data.get("_provider_status"))
            session.append_phase(
                "postprocess_retry_provider_call",
                retry_started_at,
                turn=turn_no,
                speaker="A",
                provider=cfg.fighter_a_provider,
                provider_mode=retry_data.get("_provider_mode") or "",
            )
            retry_post_started_at = time.time()
            retry_raw = _clean_text(retry_data.get("speech") or _three_turn_repair_speech("A", cfg, turns, turn_no, a_latest_opponent))
            retry_text = _sanitize_fighter_speech(retry_raw)
            retry_validation = _three_turn_validation_report("A", cfg, turns, turn_no, retry_text, a_latest_opponent)
            session.append_phase(
                "postprocess_retry_evaluate",
                retry_post_started_at,
                turn=turn_no,
                speaker="A",
            )
            a_debug_trace["retry_provider_mode"] = retry_data.get("_provider_mode") or ""
            a_debug_trace["retry_raw_provider_output_hash"] = hashlib.sha1(_clean_text(retry_data.get("_provider_raw_output") or "").encode("utf-8")).hexdigest() if _clean_text(retry_data.get("_provider_raw_output") or "") else ""
            a_debug_trace["retry_raw_provider_char_count"] = len(_clean_text(retry_data.get("_provider_raw_speech") or ""))
            a_debug_trace["retry_raw_provider_has_banned_meta"] = _contains_banned_surface_meta(retry_data.get("_provider_raw_speech") or "") or _looks_like_design_memo_speech(retry_data.get("_provider_raw_speech") or "")
            a_debug_trace["retry_sanitized_text"] = retry_text
            a_debug_trace["retry_validation"] = dict(retry_validation)
            if retry_validation.get("three_turn_contract_pass"):
                a_data = retry_data
                a_text = retry_text
                a_validation = retry_validation
                a_debug_trace["adopted_stage"] = "retry"
            if not a_validation.get("three_turn_contract_pass"):
                a_text = _three_turn_repair_speech("A", cfg, turns, turn_no, a_latest_opponent)
                a_validation = _three_turn_validation_report("A", cfg, turns, turn_no, a_text, a_latest_opponent)
                a_debug_trace["repair_triggered"] = True
                a_debug_trace["repair_text"] = a_text
                a_debug_trace["repair_validation"] = dict(a_validation)
                a_debug_trace["adopted_stage"] = "repair"
        a_meta_started_at = time.time()
        a_meta = _normalize_turn_meta(a_data.get("meta"), "A", cfg, turns, a_text, a_latest_opponent)
        session.append_phase(
            "postprocess_normalize_meta",
            a_meta_started_at,
            turn=turn_no,
            speaker="A",
        )
        if cfg.turn_count == 3:
            a_trace_started_at = time.time()
            a_meta.update(a_validation)
            a_meta.update(a_debug_trace)
            a_trace_entry = {
                "run_id": cfg.run_id,
                "topic_hash": cfg.topic_hash,
                "topic": cfg.topic,
                "turn": turn_no,
                "speaker": "A",
                "provider_mode": a_data.get("_provider_mode") or "",
                "raw_provider_speech": _clean_text(a_data.get("_provider_raw_speech") or ""),
                "sanitized_initial_text": a_initial_text,
                "initial_validation": a_debug_trace.get("initial_validation"),
                "opening_validated": a_debug_trace.get("opening_validated"),
                "opening_validation_failures": a_debug_trace.get("opening_validation_failures"),
                "retry_triggered": a_debug_trace.get("retry_triggered"),
                "repair_triggered": a_debug_trace.get("repair_triggered"),
                "sanitize_applied": a_debug_trace.get("sanitize_applied"),
                "adopted_stage": a_debug_trace.get("adopted_stage"),
                "route_name": a_debug_trace.get("route_name"),
                "final_text": a_text,
                "final_validation": dict(a_validation),
            }
            trace_entries.append(a_trace_entry)
            _append_three_turn_trace(a_trace_entry)
            session.append_phase(
                "postprocess_trace_record",
                a_trace_started_at,
                turn=turn_no,
                speaker="A",
            )
        a_visible_debug_started_at = time.time()
        a_visible_debug = _visible_context_debug(turn_no, "A", cfg.fighter_a_provider, round_snapshot, a_prompt)
        session.append_phase(
            "postprocess_visible_debug",
            a_visible_debug_started_at,
            turn=turn_no,
            speaker="A",
        )
        session.append_elapsed_phase("postprocess", a_postprocess_started_at, turn=turn_no, speaker="A")
        b_postprocess_started_at = time.time()
        b_initial_processing_started_at = time.time()
        b_initial_raw = _clean_text(b_data.get("speech") or b_fallback)
        b_initial_text = _sanitize_fighter_speech(b_initial_raw)
        b_text = b_initial_text
        b_validation = _three_turn_validation_report("B", cfg, turns, turn_no, b_text, b_latest_opponent) if cfg.turn_count == 3 else {}
        session.append_phase(
            "postprocess_initial_prepare",
            b_initial_processing_started_at,
            turn=turn_no,
            speaker="B",
        )
        b_debug_trace = {
            "provider_mode": b_data.get("_provider_mode") or "",
            "raw_provider_output_hash": hashlib.sha1(_clean_text(b_data.get("_provider_raw_output") or "").encode("utf-8")).hexdigest() if _clean_text(b_data.get("_provider_raw_output") or "") else "",
            "raw_provider_char_count": len(_clean_text(b_data.get("_provider_raw_speech") or "")),
            "raw_provider_has_banned_meta": _contains_banned_surface_meta(b_data.get("_provider_raw_speech") or "") or _looks_like_design_memo_speech(b_data.get("_provider_raw_speech") or ""),
            "sanitized_initial_text": b_initial_text,
            "initial_validation": dict(b_validation),
            "opening_validated": turn_no != 1,
            "opening_validation_failures": [],
            "retry_triggered": False,
            "repair_triggered": False,
            "adopted_stage": "initial",
        }
        if turn_no == 1:
            opening_ok, opening_failures = _is_valid_opening_speech(b_text)
            b_debug_trace["opening_validated"] = opening_ok
            b_debug_trace["opening_validation_failures"] = list(opening_failures)
            if not opening_ok:
                b_debug_trace["retry_triggered"] = True
                retry_prompt = _opening_retry_prompt(b_prompt, opening_failures)
                retry_started_at = time.time()
                retry_data = _speaker_turn_data(
                    speaker="B",
                    provider=cfg.fighter_b_provider,
                    prompt=retry_prompt,
                    cfg=cfg,
                    fallback_speech=_three_turn_repair_speech("B", cfg, turns, turn_no, b_latest_opponent, b_text),
                )
                _apply_provider_status_delta(provider_statuses, cfg.fighter_b_provider, retry_data.get("_provider_status"))
                session.append_phase(
                    "postprocess_opening_retry_provider_call",
                    retry_started_at,
                    turn=turn_no,
                    speaker="B",
                    provider=cfg.fighter_b_provider,
                    provider_mode=retry_data.get("_provider_mode") or "",
                )
                retry_post_started_at = time.time()
                retry_raw = _clean_text(retry_data.get("speech") or _three_turn_repair_speech("B", cfg, turns, turn_no, b_latest_opponent, b_text))
                retry_text = _sanitize_fighter_speech(retry_raw)
                retry_ok, retry_failures = _is_valid_opening_speech(retry_text)
                session.append_phase(
                    "postprocess_opening_retry_evaluate",
                    retry_post_started_at,
                    turn=turn_no,
                    speaker="B",
                )
                b_debug_trace["retry_provider_mode"] = retry_data.get("_provider_mode") or ""
                b_debug_trace["retry_raw_provider_output_hash"] = hashlib.sha1(_clean_text(retry_data.get("_provider_raw_output") or "").encode("utf-8")).hexdigest() if _clean_text(retry_data.get("_provider_raw_output") or "") else ""
                b_debug_trace["retry_raw_provider_char_count"] = len(_clean_text(retry_data.get("_provider_raw_speech") or ""))
                b_debug_trace["retry_raw_provider_has_banned_meta"] = _contains_banned_surface_meta(retry_data.get("_provider_raw_speech") or "") or _looks_like_design_memo_speech(retry_data.get("_provider_raw_speech") or "")
                b_debug_trace["retry_sanitized_text"] = retry_text
                b_debug_trace["opening_retry_validated"] = retry_ok
                b_debug_trace["opening_retry_failures"] = list(retry_failures)
                if retry_ok:
                    b_data = retry_data
                    b_text = retry_text
                    b_validation = _three_turn_validation_report("B", cfg, turns, turn_no, b_text, b_latest_opponent) if cfg.turn_count == 3 else {}
                    b_debug_trace["opening_validated"] = True
                    b_debug_trace["opening_validation_failures"] = []
                    b_debug_trace["adopted_stage"] = "opening-retry"
                else:
                    b_text = _three_turn_grounded_surface("B", cfg, turn_no, b_latest_opponent)
                    b_validation = _three_turn_validation_report("B", cfg, turns, turn_no, b_text, b_latest_opponent) if cfg.turn_count == 3 else {}
                    b_debug_trace["repair_triggered"] = True
                    b_debug_trace["repair_text"] = b_text
                    b_debug_trace["repair_validation"] = dict(b_validation)
                    b_debug_trace["adopted_stage"] = "opening-grounded"
        if (
            cfg.turn_count == 3
            and turn_no != 1
            and not b_validation.get("three_turn_contract_pass")
            and (b_data.get("_provider_mode") or "") != "live"
        ):
            b_debug_trace["retry_triggered"] = True
            retry_prompt = _three_turn_retry_prompt(b_prompt, b_validation.get("three_turn_failures") or [], turn_no)
            retry_started_at = time.time()
            retry_data = _speaker_turn_data(
                speaker="B",
                provider=cfg.fighter_b_provider,
                prompt=retry_prompt,
                cfg=cfg,
                fallback_speech=_three_turn_repair_speech("B", cfg, turns, turn_no, b_latest_opponent, b_text),
            )
            _apply_provider_status_delta(provider_statuses, cfg.fighter_b_provider, retry_data.get("_provider_status"))
            session.append_phase(
                "postprocess_retry_provider_call",
                retry_started_at,
                turn=turn_no,
                speaker="B",
                provider=cfg.fighter_b_provider,
                provider_mode=retry_data.get("_provider_mode") or "",
            )
            retry_post_started_at = time.time()
            retry_raw = _clean_text(retry_data.get("speech") or _three_turn_repair_speech("B", cfg, turns, turn_no, b_latest_opponent, b_text))
            retry_text = _sanitize_fighter_speech(retry_raw)
            retry_validation = _three_turn_validation_report("B", cfg, turns, turn_no, retry_text, b_latest_opponent)
            session.append_phase(
                "postprocess_retry_evaluate",
                retry_post_started_at,
                turn=turn_no,
                speaker="B",
            )
            b_debug_trace["retry_provider_mode"] = retry_data.get("_provider_mode") or ""
            b_debug_trace["retry_raw_provider_output_hash"] = hashlib.sha1(_clean_text(retry_data.get("_provider_raw_output") or "").encode("utf-8")).hexdigest() if _clean_text(retry_data.get("_provider_raw_output") or "") else ""
            b_debug_trace["retry_raw_provider_char_count"] = len(_clean_text(retry_data.get("_provider_raw_speech") or ""))
            b_debug_trace["retry_raw_provider_has_banned_meta"] = _contains_banned_surface_meta(retry_data.get("_provider_raw_speech") or "") or _looks_like_design_memo_speech(retry_data.get("_provider_raw_speech") or "")
            b_debug_trace["retry_sanitized_text"] = retry_text
            b_debug_trace["retry_validation"] = dict(retry_validation)
            if retry_validation.get("three_turn_contract_pass"):
                b_data = retry_data
                b_text = retry_text
                b_validation = retry_validation
                b_debug_trace["adopted_stage"] = "retry"
            if not b_validation.get("three_turn_contract_pass"):
                b_text = _three_turn_repair_speech("B", cfg, turns, turn_no, b_latest_opponent, b_text)
                b_validation = _three_turn_validation_report("B", cfg, turns, turn_no, b_text, b_latest_opponent)
                b_debug_trace["repair_triggered"] = True
                b_debug_trace["repair_text"] = b_text
                b_debug_trace["repair_validation"] = dict(b_validation)
                b_debug_trace["adopted_stage"] = "repair"
        if (
            cfg.turn_count == 3
            and turn_no == 2
            and _needs_short_stance_boost(cfg, "B")
            and b_validation.get("grounded_keyword_count", 0) < 2
        ):
            b_text = _three_turn_repair_speech("B", cfg, turns, turn_no, b_latest_opponent, b_text)
            b_validation = _three_turn_validation_report("B", cfg, turns, turn_no, b_text, b_latest_opponent)
            b_debug_trace["repair_triggered"] = True
            b_debug_trace["repair_text"] = b_text
            b_debug_trace["repair_validation"] = dict(b_validation)
            b_debug_trace["adopted_stage"] = "forced-b-turn2-repair"
        parity_failures = _three_turn_parity_failures(a_validation, b_validation) if cfg.turn_count == 3 else {"A": [], "B": []}
        if cfg.turn_count == 3 and turn_no != 1 and parity_failures.get("A"):
            a_alignment = _response_alignment_report("A", cfg, turn_no, a_text, a_latest_opponent)
            a_should_skip_parity_repair = (
                turn_no == 2
                and bool(a_alignment.get("stage2_pass"))
                and bool(a_alignment.get("response_alignment_pass"))
            )
            if not a_should_skip_parity_repair:
                repaired = _three_turn_repair_speech("A", cfg, turns, turn_no, a_latest_opponent)
                repaired_validation = _three_turn_validation_report("A", cfg, turns, turn_no, repaired, a_latest_opponent)
                if repaired_validation.get("three_turn_contract_pass") and repaired_validation.get("density_score", 0) >= a_validation.get("density_score", 0):
                    a_text = repaired
                    a_validation = repaired_validation
                    a_meta = _normalize_turn_meta(a_data.get("meta"), "A", cfg, turns, a_text, a_latest_opponent)
                    a_meta.update(a_validation)
                    a_debug_trace["repair_triggered"] = True
                    a_debug_trace["parity_failures"] = parity_failures.get("A")
                    a_debug_trace["repair_text"] = a_text
                    a_debug_trace["repair_validation"] = dict(a_validation)
                    a_debug_trace["adopted_stage"] = "parity-repair"
                    a_meta.update(a_debug_trace)
        if cfg.turn_count == 3 and turn_no != 1 and parity_failures.get("B"):
            repaired = _three_turn_repair_speech("B", cfg, turns, turn_no, b_latest_opponent, b_text)
            repaired_validation = _three_turn_validation_report("B", cfg, turns, turn_no, repaired, b_latest_opponent)
            if repaired_validation.get("three_turn_contract_pass") and repaired_validation.get("density_score", 0) >= b_validation.get("density_score", 0):
                b_text = repaired
                b_validation = repaired_validation
                b_debug_trace["repair_triggered"] = True
                b_debug_trace["parity_failures"] = parity_failures.get("B")
                b_debug_trace["repair_text"] = b_text
                b_debug_trace["repair_validation"] = dict(b_validation)
                b_debug_trace["adopted_stage"] = "parity-repair"
        a_text, a_validation = _finalize_fighter_output("A", cfg, turns, turn_no, a_text, a_latest_opponent, a_debug_trace)
        a_meta = _normalize_turn_meta(a_data.get("meta"), "A", cfg, turns, a_text, a_latest_opponent)
        if cfg.turn_count == 3:
            a_meta.update(a_validation)
            a_meta.update(a_debug_trace)
            a_trace_entry["sanitize_applied"] = a_debug_trace.get("sanitize_applied")
            a_trace_entry["adopted_stage"] = a_debug_trace.get("adopted_stage")
            a_trace_entry["route_name"] = a_debug_trace.get("route_name")
            a_trace_entry["final_text"] = a_text
            a_trace_entry["final_validation"] = dict(a_validation)
        b_text, b_validation = _finalize_fighter_output("B", cfg, turns, turn_no, b_text, b_latest_opponent, b_debug_trace)
        b_meta_started_at = time.time()
        b_meta = _normalize_turn_meta(b_data.get("meta"), "B", cfg, turns, b_text, b_latest_opponent)
        session.append_phase(
            "postprocess_normalize_meta",
            b_meta_started_at,
            turn=turn_no,
            speaker="B",
        )
        if cfg.turn_count == 3:
            b_trace_started_at = time.time()
            b_meta.update(b_validation)
            b_meta.update(b_debug_trace)
            b_trace_entry = {
                "run_id": cfg.run_id,
                "topic_hash": cfg.topic_hash,
                "topic": cfg.topic,
                "turn": turn_no,
                "speaker": "B",
                "provider_mode": b_data.get("_provider_mode") or "",
                "raw_provider_speech": _clean_text(b_data.get("_provider_raw_speech") or ""),
                "sanitized_initial_text": b_initial_text,
                "initial_validation": b_debug_trace.get("initial_validation"),
                "opening_validated": b_debug_trace.get("opening_validated"),
                "opening_validation_failures": b_debug_trace.get("opening_validation_failures"),
                "retry_triggered": b_debug_trace.get("retry_triggered"),
                "repair_triggered": b_debug_trace.get("repair_triggered"),
                "sanitize_applied": b_debug_trace.get("sanitize_applied"),
                "adopted_stage": b_debug_trace.get("adopted_stage"),
                "route_name": b_debug_trace.get("route_name"),
                "final_text": b_text,
                "final_validation": dict(b_validation),
            }
            trace_entries.append(b_trace_entry)
            _append_three_turn_trace(b_trace_entry)
            session.append_phase(
                "postprocess_trace_record",
                b_trace_started_at,
                turn=turn_no,
                speaker="B",
            )
        b_visible_debug_started_at = time.time()
        b_visible_debug = _visible_context_debug(turn_no, "B", cfg.fighter_b_provider, round_snapshot, b_prompt)
        session.append_phase(
            "postprocess_visible_debug",
            b_visible_debug_started_at,
            turn=turn_no,
            speaker="B",
        )
        session.append_elapsed_phase("postprocess", b_postprocess_started_at, turn=turn_no, speaker="B")
        session.append_elapsed_phase("turn_phase_total", turn_phase_started_at, turn=turn_no)

        transcript_append_started_at = time.time()
        transcript = _append_transcript(prior_transcript, turn_no, "A", a_text)
        transcript = _append_transcript(transcript, turn_no, "B", b_text)
        session.append_phase("postprocess_transcript_append", transcript_append_started_at, turn=turn_no)
        turns_append_started_at = time.time()
        round_debug.append(
            {
                "turn": turn_no,
                "snapshot_id": round_snapshot["snapshot_id"],
                "a": a_visible_debug,
                "b": b_visible_debug,
            }
        )
        turns.append(
            {
                "turn": turn_no,
                "stage_label": stage_label,
                "a": a_text,
                "b": b_text,
                "meta": {"a": a_meta, "b": b_meta},
            }
        )
        session.append_phase("postprocess_turn_record_append", turns_append_started_at, turn=turn_no)
        session.progress(
            stage="turn_completed",
            turn=turn_no,
            extra={"completed_turns": len(turns)},
        )
        if _should_end_match(cfg, turns):
            break

    debate = {
        "topic": cfg.topic,
        "keyword": cfg.keyword,
        "turn_count": len(turns),
        "run_id": cfg.run_id,
        "topic_hash": cfg.topic_hash,
        "artifact_bundle_dir": cfg.artifact_dir,
        "participants": {"a": _provider_label(cfg.fighter_a_provider), "b": _provider_label(cfg.fighter_b_provider), "judge": "Gemini"},
        "turns": turns,
        "round_debug": round_debug,
        "keyword_used_count": sum(
            1
            for turn in turns
            for speaker in ("a", "b")
            if bool(((turn.get("meta") or {}).get(speaker) or {}).get("keyword_used"))
        ),
        "keyword_used_turns": [
            f"Turn {turn.get('turn')} {speaker.upper()}"
            for turn in turns
            for speaker in ("a", "b")
            if bool(((turn.get("meta") or {}).get(speaker) or {}).get("keyword_used"))
        ],
        "keyword_bonus_total": sum(
            int(((turn.get("meta") or {}).get(speaker) or {}).get("keyword_bonus") or 0)
            for turn in turns
            for speaker in ("a", "b")
        ),
        "keyword_bonus_turns": [
            {
                "turn": turn.get("turn"),
                "speaker": speaker.upper(),
                "bonus": int(((turn.get("meta") or {}).get(speaker) or {}).get("keyword_bonus") or 0),
            }
            for turn in turns
            for speaker in ("a", "b")
            if int(((turn.get("meta") or {}).get(speaker) or {}).get("keyword_bonus") or 0) > 0
        ],
    }
    return debate, transcript, trace_entries


def _session_inline_judge_summary(
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    transcript: str,
    provider_statuses: dict[str, dict[str, str]],
) -> dict[str, Any]:
    fallback = _mock_summary(cfg, turns)
    judge_model_name = cfg.judge_model or (_resolve_gemini_model(cfg.gemini_key) if cfg.gemini_key else _default_gemini_model_name())
    if cfg.disable_live_judge:
        provider_statuses["judge"] = {
            **_provider_entry("mock", "judge disabled"),
            "judge_provider": cfg.judge_provider,
            "judge_model": judge_model_name,
            "judge_request_variant": "disabled",
            "judge_request_url": _gemini_generate_content_url(judge_model_name),
            "judge_request_body_shape": "disabled",
            "judge_request_has_generation_config": True,
            "judge_prompt_chars": 0,
            "judge_prompt_preview": "",
            "judge_stage": "disabled",
            "judge_raw_received": False,
            "judge_parse_success": False,
            "raw_reason": "",
        }
        _log_judge_stage("judge-disabled", {"reason": "disabled_for_live_fighters", "stage": "disabled"})
        if cfg.keyword and not sum(
            1
            for turn in turns
            for speaker in ("a", "b")
            if bool(((turn.get("meta") or {}).get(speaker) or {}).get("keyword_used"))
        ):
            keyword_note = _build_keyword_note(cfg.keyword, cfg.topic)
            fallback["keyword_note"] = keyword_note
            fallback["full_rationale"] = f"{_clean_text(fallback.get('full_rationale') or '')} {keyword_note}".strip()
        return fallback
    summary, judge_status = _judge_summary_data(cfg, turns, transcript)
    _apply_provider_status_delta(provider_statuses, "judge", judge_status)
    if cfg.keyword and not sum(
        1
        for turn in turns
        for speaker in ("a", "b")
        if bool(((turn.get("meta") or {}).get(speaker) or {}).get("keyword_used"))
    ):
        keyword_note = _build_keyword_note(cfg.keyword, cfg.topic)
        summary["keyword_note"] = keyword_note
        summary["full_rationale"] = f"{_clean_text(summary.get('full_rationale') or '')} {keyword_note}".strip()
    return summary


def _build_round_snapshot(turn_no: int, transcript: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    text = str(transcript or "")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    visible_turn_count = len(turns)
    return {
        "text": text,
        "hash": digest,
        "visible_turn_count": visible_turn_count,
        "snapshot_id": f"turn-{turn_no}-up-to-{visible_turn_count}-{digest[:10]}",
    }


def _visible_context_debug(
    turn_no: int,
    speaker: str,
    provider: str,
    round_snapshot: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    visible_text = str(round_snapshot.get("text") or "")
    same_turn_markers = [f"Turn {turn_no} A:", f"Turn {turn_no} B:"]
    return {
        "turn": turn_no,
        "speaker": speaker,
        "provider": provider,
        "visible_transcript_text": visible_text,
        "visible_transcript_hash": str(round_snapshot.get("hash") or ""),
        "visible_turn_count": int(round_snapshot.get("visible_turn_count") or 0),
        "same_turn_content_present": any(marker in visible_text for marker in same_turn_markers),
        "round_snapshot_id": str(round_snapshot.get("snapshot_id") or ""),
        "prompt_hash": hashlib.sha1(str(prompt or "").encode("utf-8")).hexdigest(),
        "context_char_count": len(visible_text),
    }


def _initial_provider_statuses(cfg: DebateConfig) -> dict[str, dict[str, str]]:
    return {
        "openai": {
            **_provider_entry("live-ready" if cfg.openai_key else "mock", "api key missing" if not cfg.openai_key else ""),
            "model": cfg.fighter_a_model if cfg.fighter_a_provider == "openai" else (cfg.fighter_b_model if cfg.fighter_b_provider == "openai" else OPENAI_MODEL),
        },
        "anthropic": {
            **_provider_entry("live-ready" if cfg.anthropic_key else "mock", "api key missing" if not cfg.anthropic_key else ""),
            "model": cfg.fighter_a_model if cfg.fighter_a_provider == "anthropic" else (cfg.fighter_b_model if cfg.fighter_b_provider == "anthropic" else ANTHROPIC_MODEL),
        },
        "gemini": {
            **_provider_entry("live-ready" if cfg.gemini_key else "mock", "api key missing" if not cfg.gemini_key else ""),
            "model": cfg.fighter_a_model if cfg.fighter_a_provider == "gemini" else (cfg.fighter_b_model if cfg.fighter_b_provider == "gemini" else cfg.judge_model),
        },
        "judge": {
            **_provider_entry("live-ready" if cfg.gemini_key else "mock", "api key missing" if not cfg.gemini_key else ""),
            "judge_provider": cfg.judge_provider,
            "judge_model": cfg.judge_model,
            "judge_stage": "provider_select",
            "judge_raw_received": False,
            "judge_parse_success": False,
        },
    }


def _provider_entry(mode: str, reason: str, raw_reason: str = "") -> dict[str, str]:
    entry = {"mode": mode, "reason": reason}
    if raw_reason:
        entry["raw_reason"] = raw_reason
    return entry


def _apply_provider_status_delta(
    provider_statuses: dict[str, dict[str, Any]],
    provider: str,
    delta: dict[str, Any] | None,
) -> None:
    if not delta:
        return
    current = dict(provider_statuses.get(provider, {}))
    current.update(delta)
    provider_statuses[provider] = current


def _normalize_fighter_provider(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"openai", "gpt", "gpt-5-mini", "gpt5", "gpt5mini"}:
        return "openai"
    if text in {"anthropic", "claude", "claude-sonnet", "claude-sonnet-4-5-20250929"}:
        return "anthropic"
    if text in {"gemini", "gemini-flash", "gemini-2.5-flash", "gemini25flash"}:
        return "gemini"
    raise ValueError("invalid_fighter_provider")


def _resolve_provider_model(provider: str, openai_key: str, anthropic_key: str, gemini_key: str) -> str:
    if provider == "openai":
        return OPENAI_MODEL
    if provider == "anthropic":
        return ANTHROPIC_MODEL
    if provider == "gemini":
        return _resolve_gemini_model(gemini_key) if gemini_key else _default_gemini_model_name()
    return ""


def _route_signature(
    *,
    topic_hash: str,
    turn_count: int,
    mode: str,
    fighter_a_provider: str,
    fighter_b_provider: str,
    judge_provider: str,
    fighter_a_model: str,
    fighter_b_model: str,
    judge_model: str,
    disable_live_judge: bool,
) -> str:
    raw = json.dumps(
        {
            "topic_hash": topic_hash,
            "turn_count": turn_count,
            "mode": mode,
            "fighter_a_provider": fighter_a_provider,
            "fighter_b_provider": fighter_b_provider,
            "judge_provider": judge_provider,
            "fighter_a_model": fighter_a_model,
            "fighter_b_model": fighter_b_model,
            "judge_model": judge_model,
            "disable_live_judge": disable_live_judge,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _provider_label(provider: str) -> str:
    if provider == "openai":
        return "GPT"
    if provider == "anthropic":
        return "Claude"
    if provider == "gemini":
        return "Gemini"
    return provider


def _speaker_request_model(cfg: DebateConfig, speaker: str, provider: str) -> str:
    if speaker == "A" and provider == cfg.fighter_a_provider and cfg.fighter_a_model:
        return cfg.fighter_a_model
    if speaker == "B" and provider == cfg.fighter_b_provider and cfg.fighter_b_model:
        return cfg.fighter_b_model
    if provider == "openai":
        return OPENAI_MODEL
    if provider == "anthropic":
        return ANTHROPIC_MODEL
    if provider == "gemini":
        return cfg.judge_model or _default_gemini_model_name()
    return ""


def _speaker_turn_data(
    speaker: str,
    provider: str,
    prompt: str,
    cfg: DebateConfig,
    fallback_speech: str,
) -> dict[str, Any]:
    fallback = {
        "speech": fallback_speech,
        "_provider_mode": "fallback",
        "_provider_raw_output": "",
        "_provider_raw_speech": fallback_speech,
    }
    key = _provider_key(cfg, provider)
    if not key:
        return {**fallback, "_provider_mode": "mock", "_provider_status": _provider_entry("mock", "api key missing")}
    try:
        model_name = _speaker_request_model(cfg, speaker, provider)
        if provider == "openai":
            raw = _call_openai(prompt, key, model_name=model_name)
        elif provider == "anthropic":
            raw = _call_anthropic(prompt, key, model_name=model_name)
        elif provider == "gemini":
            raw = _call_gemini(prompt, key, model_name=model_name)
        else:
            raise RuntimeError(f"unsupported_provider:{provider}")
        parsed = _parse_json_response(raw, fallback)
        parsed["_provider_mode"] = "live"
        parsed["_provider_raw_output"] = raw
        parsed["_provider_raw_speech"] = _clean_text(parsed.get("speech") or fallback_speech)
        parsed["_provider_status"] = _provider_entry("live", "")
        return parsed
    except Exception as e:
        raw_reason = str(e)
        reason = _classify_provider_reason(raw_reason)
        return {
            **fallback,
            "_provider_mode": "mock-fallback",
            "_provider_status": _provider_entry("mock-fallback", reason, raw_reason),
        }


def _judge_summary_data(
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    transcript: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fallback = _mock_summary(cfg, turns)
    judge_model_name = cfg.judge_model or (_resolve_gemini_model(cfg.gemini_key) if cfg.gemini_key else _default_gemini_model_name())
    _log_judge_stage(
        "judge-provider",
        {
            "provider": "gemini",
            "model": judge_model_name,
            "request_url": _gemini_generate_content_url(judge_model_name),
            "selected": True,
            "api_key_present": bool(cfg.gemini_key),
        },
    )
    if not cfg.gemini_key:
        _log_judge_stage("judge-fallback", {"reason": "api key missing", "stage": "provider_select"})
        return fallback, {
            **_provider_entry("mock", "api key missing"),
            "judge_provider": "gemini",
            "judge_model": judge_model_name,
            "judge_request_variant": "contents_with_generation_config",
            "judge_request_url": _gemini_generate_content_url(judge_model_name),
            "judge_request_body_shape": "contents+generationConfig",
            "judge_request_has_generation_config": True,
            "judge_prompt_chars": 0,
            "judge_prompt_preview": "",
            "judge_stage": "provider_select",
            "judge_raw_received": False,
            "judge_parse_success": False,
            "raw_reason": "",
        }
    judge_prompt_pass1 = _judge_pass1_prompt(cfg, turns, transcript)
    judge_metrics_pass1 = _judge_metrics(transcript, judge_prompt_pass1)
    try:
        try:
            print("[DEBUG] entering judge_pass1")
            judge_raw_pass1, judge_debug_pass1 = _call_gemini_match_chat(
                judge_prompt_pass1,
                cfg.gemini_key,
                timeout_s=JUDGE_PASS1_TIMEOUT_S,
                retries=GEMINI_JUDGE_PASS1_RETRIES,
                max_output_tokens=GEMINI_JUDGE_PASS1_MAX_OUTPUT_TOKENS,
                debug_context={**judge_metrics_pass1, "pass_label": "judge_pass1"},
                error_cls=JudgeError,
                response_mime_type="application/json",
                thinking_budget=0,
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
            judge_status = {
                    "judge_provider": "gemini",
                    "judge_model": judge_debug_pass1.get("model", judge_model_name),
                    "judge_request_variant": judge_debug_pass1.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": judge_debug_pass1.get("request_url", _gemini_generate_content_url(judge_model_name)),
                    "judge_request_body_shape": judge_debug_pass1.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(judge_debug_pass1.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                    "judge_prompt_preview": str(judge_debug_pass1.get("judge_prompt_preview", "") or ""),
                    "judge_stage": "judge_pass1",
                    "judge_raw_received": bool(str(judge_raw_pass1 or "").strip()),
                    "judge_parse_success": True,
                    "raw_reason": "",
                }
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
            judge_status = {
                    "judge_provider": "gemini",
                    "judge_model": exc.debug.get("model", judge_model_name),
                    "judge_request_variant": exc.debug.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": exc.debug.get("request_url", _gemini_generate_content_url(judge_model_name)),
                    "judge_request_body_shape": exc.debug.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(exc.debug.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(exc.debug.get("judge_prompt_char_count", 0) or 0),
                    "judge_prompt_preview": str(exc.debug.get("judge_prompt_preview", "") or ""),
                    "judge_stage": "judge_pass1",
                    "judge_raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                    "judge_parse_success": False,
                    "raw_reason": _compose_raw_reason(exc.debug.get("provider_error", ""), exc.debug.get("raw_body", ""), str(exc)),
                }
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
                response_mime_type="application/json",
                thinking_budget=0,
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
            judge_status = {
                    "judge_provider": "gemini",
                    "judge_model": judge_debug_pass2.get("model", judge_model_name),
                    "judge_request_variant": judge_debug_pass2.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": judge_debug_pass2.get("request_url", _gemini_generate_content_url(judge_model_name)),
                    "judge_request_body_shape": judge_debug_pass2.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(judge_debug_pass2.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                    "judge_prompt_preview": str(judge_debug_pass1.get("judge_prompt_preview", "") or ""),
                    "judge_stage": "judge_pass2",
                    "judge_raw_received": bool(str(judge_raw_pass2 or "").strip()),
                    "judge_parse_success": True,
                    "raw_reason": "",
                }
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
            judge_status = {
                    "judge_provider": "gemini",
                    "judge_model": exc.debug.get("model", judge_model_name),
                    "judge_request_variant": exc.debug.get("request_variant", "contents_with_generation_config"),
                    "judge_request_url": exc.debug.get("request_url", _gemini_generate_content_url(judge_model_name)),
                    "judge_request_body_shape": exc.debug.get("request_body_shape", "contents+generationConfig"),
                    "judge_request_has_generation_config": bool(exc.debug.get("request_has_generation_config", True)),
                    "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                    "judge_prompt_preview": str(judge_debug_pass1.get("judge_prompt_preview", "") or ""),
                    "judge_stage": "judge_pass2",
                    "judge_raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                    "judge_parse_success": False,
                    "raw_reason": _compose_raw_reason(exc.debug.get("provider_error", ""), exc.debug.get("raw_body", ""), str(exc)),
                }
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
            },
            turns,
        )
        judge_status = {
                **_provider_entry("live", ""),
                "judge_provider": "gemini",
                "judge_model": judge_debug_pass2.get("model", judge_model_name),
                "judge_request_variant": judge_debug_pass2.get("request_variant", "contents_with_generation_config"),
                "judge_request_url": judge_debug_pass2.get("request_url", _gemini_generate_content_url(judge_model_name)),
                "judge_request_body_shape": judge_debug_pass2.get("request_body_shape", "contents+generationConfig"),
                "judge_request_has_generation_config": bool(judge_debug_pass2.get("request_has_generation_config", True)),
                "judge_prompt_chars": int(judge_debug_pass1.get("judge_prompt_char_count", 0) or 0),
                "judge_prompt_preview": str(judge_debug_pass1.get("judge_prompt_preview", "") or ""),
                "judge_stage": "judge_pass2",
                "judge_raw_received": bool(str(judge_raw_pass2 or "").strip()),
                "judge_parse_success": True,
                "raw_reason": "",
            }
        _record_gemini_judge_debug(
            {
                "status": "live",
                "reason": "",
                "model": judge_debug_pass2.get("model", judge_model_name),
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
        return summary, judge_status
    except JudgeError as exc:
        judge_status = {
                **_provider_entry("mock-fallback", exc.reason),
                "judge_provider": "gemini",
                "judge_model": exc.debug.get("model", judge_model_name),
                "judge_request_variant": exc.debug.get("request_variant", "contents_with_generation_config"),
                "judge_request_url": exc.debug.get("request_url", _gemini_generate_content_url(judge_model_name)),
                "judge_request_body_shape": exc.debug.get("request_body_shape", "contents+generationConfig"),
                "judge_request_has_generation_config": bool(exc.debug.get("request_has_generation_config", True)),
                "judge_prompt_chars": int(exc.debug.get("judge_prompt_char_count", 0) or 0),
                "judge_prompt_preview": str(exc.debug.get("judge_prompt_preview", "") or ""),
                "judge_stage": str(exc.debug.get("pass_label", "") or "judge_pass1"),
                "judge_raw_received": bool(str(exc.debug.get("raw_text") or "").strip()),
                "judge_parse_success": False,
                "raw_reason": _compose_raw_reason(exc.debug.get("provider_error", ""), exc.debug.get("raw_body", ""), str(exc)),
            }
        debug = {
            "status": "mock-fallback",
            "reason": exc.reason,
            "exception_message": str(exc),
            "stack_trace": traceback.format_exc(),
            "model": exc.debug.get("model", judge_model_name),
            "prompt_chars": len(judge_prompt_pass1),
            **judge_metrics_pass1,
            **exc.debug,
        }
        path = _record_gemini_judge_debug(debug)
        _log_gemini_judge_event("mock-fallback", {**debug, "debug_path": str(path) if path else ""})
        _log_judge_stage("judge-fallback", {"reason": exc.reason, "stage": exc.debug.get("pass_label", ""), "debug_path": str(path) if path else ""})
        return fallback, judge_status
    except Exception as exc:
        reason = _classify_provider_reason(str(exc))
        judge_status = {
                **_provider_entry("mock-fallback", reason),
                "judge_provider": "gemini",
                "judge_model": judge_model_name,
                "judge_request_variant": "contents_with_generation_config",
                "judge_request_url": _gemini_generate_content_url(judge_model_name),
                "judge_request_body_shape": "contents+generationConfig",
                "judge_request_has_generation_config": True,
                "judge_prompt_chars": int(judge_metrics_pass1.get("judge_prompt_char_count", 0) or 0),
                "judge_prompt_preview": _prompt_preview(judge_prompt_pass1),
                "judge_stage": "",
                "judge_raw_received": False,
                "judge_parse_success": False,
                "raw_reason": _compose_raw_reason(str(exc)),
            }
        debug = {
            "status": "mock-fallback",
            "reason": reason,
            "exception_message": str(exc),
            "stack_trace": traceback.format_exc(),
            "model": judge_model_name,
            "prompt_chars": len(judge_prompt_pass1),
            **judge_metrics_pass1,
            "provider_error": str(exc),
        }
        path = _record_gemini_judge_debug(debug)
        _log_gemini_judge_event("mock-fallback", {**debug, "debug_path": str(path) if path else ""})
        _log_judge_stage("judge-fallback", {"reason": reason, "stage": "", "debug_path": str(path) if path else ""})
        return fallback, judge_status


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
    opponent_last = _opponent_last_statement(speaker, turns)
    proposition_lock_block = _proposition_lock_prompt_block(cfg)
    opening_contract_block = _opening_contract_prompt_block(cfg, speaker, turn_no)
    three_turn_block = _three_turn_prompt_block(cfg, turn_no)
    return (
        f"You are {role_name} in a structured debate prototype.\n"
        "TOPIC LOCK:\n"
        f"- Stay strictly within the given topic: {cfg.topic}.\n"
        "- Do NOT introduce concepts or terminology from unrelated domains.\n"
        "TOPIC ANCHOR:\n"
        "- You MUST use at least one core term from the topic in every turn.\n"
        f"- Prefer domain-specific terms directly related to: {cfg.topic}.\n"
        "ANTI-DRIFT:\n"
        "- Do NOT introduce generic business or product terms unless they are explicitly part of the topic.\n"
        "- Avoid concepts like cost optimization, switching cost, SaaS, or platform strategies unless directly relevant.\n"
        "TURN RULES:\n"
        "- Turn 1: Begin with a clear claim and one key reason.\n"
        "- Turn 2: Directly respond to the opponent's core point in natural language.\n"
        "- Turn 3: Conclude your position clearly.\n"
        "MINIMUM DEVELOPMENT:\n"
        "- Each response must include at least:\n"
        "  (1) one concrete example or observation,\n"
        "  (2) one causal explanation,\n"
        "  (3) one clear conclusion sentence.\n"
        "- Turn 1 must include one concrete example and one sentence that anticipates the opponent's likely attack.\n"
        "- Turn 2 must explicitly explain why the opponent's argument fails.\n"
        "- Turn 3 must end with a decisive conclusion, not an unfinished thought.\n"
        "- Turn 3: You must end with a decisive conclusion that clearly states why the opponent fails and why your position holds.\n"
        "STRICT PROHIBITIONS:\n"
        "- Do NOT output meta-discourse such as '受け取った', '受け取り', or '相手の発言なし'.\n"
        "- Do NOT narrate the debate or describe turns.\n"
        f"Topic: {cfg.topic}\n"
        f"Your position: {own_position}\n"
        f"Opponent position: {opposing_position}\n"
        f"Current round: Turn {turn_no} / {cfg.turn_count}\n"
        f"Stage label: {stage_label}\n"
        "Goal: win the exchange by attacking the opponent's latest core and keeping your own line standing.\n"
        "Core failure rule: generic explanation, both-sides language, burden restatement without a concrete hit, or neutral closing counts as failure.\n"
        "Requirements:\n"
        "- Respond entirely in natural Japanese.\n"
        "- Return strict JSON only.\n"
        "- Schema: {\"speech\":\"...\",\"move\":\"opening|rebuttal|rally|finish\",\"meta\":{\"phase\":\"opening|rebuttal|rally\",\"finish_intent\":\"push|finish|extend\",\"end_match\":\"yes|no\",\"opening_contract\":{\"claim_scope\":\"...\",\"comparison_axis\":\"...\",\"acceptance_condition\":\"...\",\"anti_reframe_guard\":\"...\",\"exception_policy\":\"...\",\"burden_target\":\"...\"}}}\n"
        "- meta is hidden scaffold only. Speech must not contain planning, judging, structure labels, or third-person commentary about the debate.\n"
        "- Do not begin or end the speech with labels like はい, いいえ, 結論:, 賛成, or 反対.\n"
        "- Keep at least one topic-specific concrete noun visible in every turn.\n"
        "- Same-claim paraphrase is prohibited. Each turn must react to the opponent's immediate previous claim.\n"
        "- Use only one very short receive line for the opponent's last move. Do not summarize it at length.\n"
        f"{proposition_lock_block}"
        "- Write a dense sequential debate response. In Japanese, target 300 to 800 characters.\n"
        f"{three_turn_block}"
        f"{opening_contract_block}"
        "- Do not use formulas such as 'Turn 1でAは...' or 'Turn 2でBは...'.\n"
        "- Do not quote the opponent at length. If quotation is necessary, use only a very short phrase.\n"
        "- Prefer topic-grounded burdens such as cost, safety, responsibility, implementation, or observed examples over abstract debate scaffolding.\n"
        "- Avoid recurring scaffolds such as 補助線, 本体, 検証指標, 骨組み, 停止条件, 移行コスト, 成り立つライン, 条件を閉じ切る.\n"
        "- If you use an analogy, make it natural and tied to the topic rather than a stock metaphor.\n"
        f"{_mode_prompt_rules(cfg.mode)}"
        "- If there is no opponent statement yet, open by stating your own thesis and two concrete supports.\n"
        "- If opponent logic collapses, attempt to finish the debate.\n"
        "- If you say the opponent collapses, attach one reason.\n"
        "- Set meta.end_match=yes only when you believe the exchange should stop now because of collapse, decisive rebuttal, proposition retreat, or issue loop.\n"
        "- If the opponent changed the proposition, call it out explicitly.\n"
        "- If the opponent shifts burden of proof or breaks its own definition, attack that structure.\n"
        f"{_speaker_role_rules(provider, speaker)}"
        "- Do not mention being an AI or the JSON schema.\n"
        f"Opponent last statement:\n{opponent_last}\n"
        f"Transcript so far:\n{transcript or '(none yet)'}\n"
        "OPTIONAL SIGNAL:\n"
        "- You may incorporate the keyword if it helps your argument.\n"
        "- If used, do it naturally in one short phrase.\n"
        "- If it does not fit, ignore it.\n"
        f"Keyword: {cfg.keyword or '(none)'}\n"
    )


def _three_turn_prompt_block(cfg: DebateConfig, turn_no: int) -> str:
    if cfg.turn_count != 3:
        return ""
    topic = _clean_text(cfg.topic or "")
    dignity_topic = "命" in topic and "値段" in topic and "許され" in topic
    short_payload = _needs_short_stance_boost(cfg, "A") or _needs_short_stance_boost(cfg, "B")
    if turn_no == 1:
        base = (
            "- 3-turn mode.\n"
            "- Turn 1 = claim first: clear stance first, then two topic-specific concrete supports.\n"
            "- Do not begin with evaluation language, proof-criteria language, or opponent reference.\n"
            "- Turn 1 must show one causal chain and one concrete example.\n"
            "- Turn 1 must preempt one likely opponent attack in one short sentence.\n"
        )
        if short_payload:
            base += "- If your stated position is short, replace it with a topic-grounded claim instead of bare はい/いいえ.\n"
        if dignity_topic:
            base += (
                "- This topic is about pricing human life: ground the opening in insurance, compensation, medical resources, safety regulation, triage, cost-effectiveness, dignity, or public policy.\n"
                "- Do not use generic scaffolding like 補助線, 本体, 検証指標, 骨組み, 停止条件, 移行コスト.\n"
            )
        return base
    if turn_no == 2:
        base = (
            "- Turn 2 = rebuttal.\n"
            "- Include exactly these moves: one short receive of the opponent core, one concrete rebuttal, one push for your side.\n"
            "- Do not spend the turn only re-announcing burden or comparison axis.\n"
        )
        if short_payload:
            base += "- If your stated position is short, the concrete rebuttal must name at least one topic noun, example, market, policy, or operational detail.\n"
        if dignity_topic:
            base += (
                "- Stay inside the topic of pricing human life and use concrete policy or compensation examples instead of generic debate scaffolding.\n"
            )
        return base
    base = (
        "- Turn 3 = closing.\n"
        "- Close the existing battlefield: explain why your side remains, why the opponent fails, and end with one short closing punch.\n"
        "- Do not open a new battlefield or end neutrally.\n"
    )
    if dignity_topic:
        base += (
            "- Closing must still be grounded in life valuation, public policy, compensation, triage, or dignity; avoid generic abstract wrappers.\n"
        )
    return base


def _grounding_keywords_for_cfg(cfg: DebateConfig) -> list[str]:
    topic = _clean_text(cfg.topic or "")
    if "sora" in topic.lower() and "動画サービス" in topic and ("手を出すべきでなかった" in topic or "手を出すべきだった" in topic):
        return [
            "SORA",
            "撤退",
            "動画サービス",
            "事業",
            "事業判断",
            "技術投資",
            "収益",
            "収益性",
            "配信",
            "運営コスト",
            "差別化",
            "OpenAI",
            "GPT",
            "戦略",
            "権利処理",
            "配信インフラ",
        ]
    if "命" in topic and "値段" in topic and "許され" in topic:
        return [
            "命",
            "値段",
            "価格",
            "金額",
            "救命",
            "医療資源",
            "保険",
            "補償",
            "損害賠償",
            "安全規制",
            "費用対効果",
            "倫理",
            "尊厳",
            "トリアージ",
            "公共政策",
            "事故防止",
            "配分",
            "逸失利益",
            "VSL",
        ]
    generic = []
    for source in [cfg.topic, cfg.side_a, cfg.side_b]:
        for token in _extract_focus_terms(source):
            if len(token) >= 2 and token not in generic:
                generic.append(token)
    return generic[:10]


def _topic_issue_candidates(cfg: DebateConfig) -> list[str]:
    topic = _clean_text(cfg.topic or "")
    terms = [term for term in _extract_focus_terms(topic) if len(term) >= 2][:3]
    anchor = "・".join(terms[:2]) if len(terms) >= 2 else (terms[0] if terms else "この命題")
    low = topic.lower()
    if "原発" in topic or "電力" in topic or "再エネ" in topic:
        return [
            f"{anchor}で安定供給を本当に維持できるか",
            f"{anchor}の事故・廃炉・燃料コストを誰が負担するか",
            f"{anchor}を再エネや蓄電でどこまで代替できるか",
        ]
    if "教育" in topic or "学校" in topic or "授業" in topic:
        return [
            f"{anchor}で学習効果が本当に上がるか",
            f"{anchor}が教師の評価や指導をどう変えるか",
            f"{anchor}で依存や格差が広がらないか",
        ]
    if "医療" in topic or "病院" in topic:
        return [
            f"{anchor}で治療の質が実際に上がるか",
            f"{anchor}の責任と安全性を誰が担保するか",
            f"{anchor}で現場負担と費用がどう変わるか",
        ]
    if "ai" in low or "生成" in topic:
        return [
            f"{anchor}で何が自動化され何が残るか",
            f"{anchor}の誤答や依存コストを誰が引き受けるか",
            f"{anchor}を他の手段で代替できるか",
        ]
    return [
        f"{anchor}で実際に何が良くなるか",
        f"{anchor}の副作用や失敗コストを誰が負担するか",
        f"{anchor}を他の手段で代替できるか",
    ]


def _banned_three_turn_template_phrases(cfg: DebateConfig) -> list[str]:
    topic = _clean_text(cfg.topic or "")
    common = ["だからはい", "だからいいえ"]
    if "sora" in topic.lower() and "動画サービス" in topic and ("手を出すべきでなかった" in topic or "手を出すべきだった" in topic):
        return common + [
            "先に押さえたいのは補助線じゃなく本体だ",
            "周辺条件ばかり膨らませると",
            "検証指標",
            "話の骨組み",
            "停止条件",
            "移行コスト",
            "補助線",
            "本体",
        ]
    if "命" in topic and "値段" in topic and "許され" in topic:
        return common + [
            "先に押さえたいのは補助線じゃなく本体だ",
            "周辺条件ばかり膨らませると",
            "検証指標",
            "話の骨組み",
            "停止条件",
            "移行コスト",
            "立場を支える条件まで見ると",
            "ここまで来ると",
            "空白はごまかせない",
            "補助線",
            "本体",
        ]
    return common


def _topic_grounding_report(cfg: DebateConfig, speech: str) -> dict[str, Any]:
    cleaned = _clean_text(speech)
    keywords = _grounding_keywords_for_cfg(cfg)
    grounded_hits = [keyword for keyword in keywords if keyword and keyword in cleaned]
    banned_hits = [phrase for phrase in _banned_three_turn_template_phrases(cfg) if phrase and phrase in cleaned]
    bare_tokens = 0
    for token in ["はい", "いいえ", "だからはい", "だからいいえ"]:
        bare_tokens += cleaned.count(token)
    return {
        "grounded_keywords": grounded_hits,
        "grounded_keyword_count": len(dict.fromkeys(grounded_hits)),
        "banned_template_phrases": banned_hits,
        "banned_template_phrase_count": len(banned_hits),
        "bare_stance_tokens": bare_tokens,
    }


def _normalized_topic_evaluation_basis(topic: str) -> dict[str, str]:
    cleaned = _clean_text(topic).rstrip("。")
    proposition = cleaned
    topic_core = cleaned.rstrip("？?")
    is_question = topic_core.endswith("か") or "どちらが" in cleaned or "正しいか" in cleaned
    if topic_core.endswith("か"):
        proposition = f"{topic_core[:-1]}という主張は成立するか"
    elif "どちらが" in cleaned:
        proposition = f"{cleaned}を、主張の成立条件で比べる"
    elif "正しいか" in cleaned:
        proposition = cleaned.replace("正しいか", "という主張は成立するか")
    evaluation_axis = "論理の成立条件・前提の妥当性・因果の成立" if is_question else "評価基準"
    comparison_unit = "主張の成立" if is_question else "命題そのもの"
    return {
        "topic_proposition": proposition,
        "evaluation_axis": evaluation_axis,
        "comparison_unit": comparison_unit,
        "is_question_like": "yes" if is_question else "no",
    }


def _build_opening_contract(cfg: DebateConfig, speech: str = "") -> dict[str, str]:
    side_text = _clean_text(cfg.side_a or speech)
    basis = _compact_basis(side_text)
    topic_basis = _normalized_topic_evaluation_basis(cfg.topic)
    reaction_terms = _issue_pool(cfg.topic, "A")["reaction_terms"]
    comparison_axis = topic_basis["evaluation_axis"]
    if topic_basis["is_question_like"] != "yes":
        comparison_axis = next(
            (
                term
                for term in reaction_terms
                if term and term in " ".join([cfg.topic, cfg.side_a, speech])
            ),
            reaction_terms[0] if reaction_terms else "採用条件",
        )
        comparison_axis = comparison_axis if comparison_axis and comparison_axis != "論点" else "採用条件"
    claim_scope = _build_complete_quote_sentence(
        f"{basis}という主張が、{comparison_axis}の範囲でどこまで成立するかを争点にする"
    )
    acceptance_condition = _build_complete_quote_sentence(
        f"{comparison_axis}で{basis}が崩れずに残るなら、この立場は成立すると先に固定する"
    )
    anti_reframe_guard = _build_complete_quote_sentence(
        "時間軸のずらし、主語の縮小、別基準への逃避、問いの再発明は反論ではなく reframe とみなす"
    )
    exception_policy = _build_complete_quote_sentence(
        "単発の例外や印象論だけでは崩れたとみなさず、採用条件そのものを壊す反例だけを致命傷とみなす"
    )
    burden_target = _build_complete_quote_sentence(
        f"Aは{comparison_axis}と採用条件を先に閉じ、Bはその必要条件が本当に崩れることを示す責任を負う"
    )
    return {
        "claim_scope": claim_scope,
        "comparison_axis": comparison_axis,
        "acceptance_condition": acceptance_condition,
        "anti_reframe_guard": anti_reframe_guard,
        "exception_policy": exception_policy,
        "burden_target": burden_target,
    }


def _build_proposition_lock(cfg: DebateConfig) -> dict[str, Any]:
    topic = _clean_text(cfg.topic)
    topic_basis = _normalized_topic_evaluation_basis(topic)
    comparison_topic = "より" in topic or "どちら" in topic
    subject = topic.split("は", 1)[0].strip("「」『』") if "は" in topic else topic
    predicate = topic.split("は", 1)[1].strip("？?。 ") if "は" in topic else topic
    comparison_unit = topic_basis["comparison_unit"]
    evaluation_axis = topic_basis["evaluation_axis"] if topic_basis["is_question_like"] == "yes" else (_issue_pool(cfg.topic, "A")["reaction_terms"][0] if _issue_pool(cfg.topic, "A")["reaction_terms"] else "評価基準")
    time_scope = "general_present"
    quantifier_scope = "general_rule"
    exception_policy = "極限例外だけで一般命題を書き換えない"
    means_vs_essence_lock = "essence_over_means"
    proof_burden_shape = (
        "両者とも、自分の主張が成立する条件、前提の妥当性、因果の成立を示し、相手側はその不成立を示す"
        if topic_basis["is_question_like"] == "yes"
        else "賛成側は命題が一般に成立する採用条件を示し、反対側はその必要条件の不成立を示す"
    )
    forbidden_reframes = [
        "条件だけへ逃げる",
        "例外だけで一般命題を上書きする",
        "時間軸をずらす",
        "比較軸を変える",
    ]
    if topic_basis["is_question_like"] == "yes":
        means_vs_essence_lock = "proposition_validity"
        forbidden_reframes.extend(["印象比較へ逃げる", "人気や便益だけで主張成立を置き換える"])
    if comparison_topic and topic_basis["is_question_like"] == "yes":
        means_vs_essence_lock = "comparison_validity"
        forbidden_reframes = [
            "比較対象そのものを別の対象へすり替える",
            "長期保有という時間軸を別の時間軸へずらす",
            "比較命題を人気や印象だけの話へ落とす",
        ]

    if "愛" in topic and "金" in topic:
        comparison_unit = "愛そのもの"
        evaluation_axis = "本質成立"
        means_vs_essence_lock = "love_itself_not_conditions"
        forbidden_reframes = ["恋愛の条件や環境だけへ逃げる", "維持コストを愛そのものへすり替える", "手段を本質の証明にする"]
    elif "復讐" in topic and "許される" in topic:
        comparison_unit = "一般規範"
        evaluation_axis = "一般的許容原則"
        quantifier_scope = "general_rule"
        exception_policy = "極限例外は一般規範を自動では上書きしない"
        means_vs_essence_lock = "general_rule_not_edge_exception"
        forbidden_reframes = ["極限例外だけで一般原則を塗り替える", "感情理解を規範許容へすり替える"]
    elif "嘘" in topic and "許される" in topic:
        comparison_unit = "一般規範"
        evaluation_axis = "一般的許容原則"
        quantifier_scope = "general_rule"
        exception_policy = "人命保護のような例外があっても一般規範を自動では上書きしない"
        means_vs_essence_lock = "general_rule_not_edge_exception"
        forbidden_reframes = ["救命のような例外だけで一般原則を塗り替える", "便宜上の必要を許容原則へすり替える"]
    elif "陰謀論" in topic and "真実" in topic:
        comparison_unit = "陰謀論と呼ばれていた集合"
        evaluation_axis = "当時のラベルと事後検証"
        time_scope = "labeled_at_time_of_claim"
        quantifier_scope = "existential_within_labeled_set"
        means_vs_essence_lock = "labeled_set_not_posthoc_relabel"
        forbidden_reframes = ["証明後にラベルを外して別集合にする", "今も陰謀論かどうかへ問いを変える"]
    elif "どちらが" in topic and ("悪い" in topic or "体に" in topic):
        comparison_unit = "主要健康被害"
        evaluation_axis = "直接害と長期被害"
        means_vs_essence_lock = "direct_harm_not_market_conditions"
        forbidden_reframes = ["違法市場や周辺条件だけへ逃げる", "普及母数だけで対象自体の害を上書きする"]
    elif "パチンコ" in topic and "三店方式" in topic and ("知っている" in topic or "知っているか" in topic):
        comparison_unit = "制度運用上の認識"
        evaluation_axis = "周知性と形式論の区別"
        means_vs_essence_lock = "knowledge_not_formal_approval"
        forbidden_reframes = ["知っていることを公認と同一視する", "形式論だけで運用上の認識から逃げる", "黙認と周知の違いを消す"]
    elif "sora" in topic.lower() and "動画サービス" in topic and ("手を出すべきでなかった" in topic or "手を出すべきだった" in topic):
        comparison_unit = "動画事業の適合性"
        evaluation_axis = "技術投資とサービス運営の適合性"
        means_vs_essence_lock = "product_sprawl_not_core_advantage"
        forbidden_reframes = ["単発ニュースをそのまま全戦略の成否へ飛ばす", "モデル技術と動画配信事業を同一視する", "撤退報道だけで収益構造の検討を飛ばす"]
    elif "命" in topic and "値段" in topic and "許され" in topic:
        comparison_unit = "尊厳と配分実務の区別"
        evaluation_axis = "価格化と序列化の分離可能性"
        means_vs_essence_lock = "dignity_not_compensation_proxy"
        forbidden_reframes = ["補償実務をそのまま命の価値と同一視する", "配分技術を尊厳の序列化へ短絡する", "価格禁止だけで現実の配分責任から逃げる"]
    elif "神" in topic and ("存在" in topic or "いる" in topic):
        comparison_unit = "存在命題"
        evaluation_axis = "説明力と存在根拠の区別"
        means_vs_essence_lock = "existence_not_explanatory_label"
        forbidden_reframes = ["説明の便利さを存在証明へすり替える", "分からなさをそのまま実在へ飛ばす"]

    if re.search(r"(長期|将来|生涯)", topic):
        time_scope = "long_term"
    elif re.search(r"(短期|今|現時点|現在)", topic):
        time_scope = "short_term_present"
    if re.search(r"(一つでも|あるか)", topic):
        quantifier_scope = "existential"

    return {
        "claim_subject": subject or topic,
        "claim_predicate": predicate or topic,
        "comparison_unit": comparison_unit,
        "evaluation_axis": evaluation_axis,
        "time_scope": time_scope,
        "quantifier_scope": quantifier_scope,
        "exception_policy": exception_policy,
        "means_vs_essence_lock": means_vs_essence_lock,
        "proof_burden_shape": proof_burden_shape,
        "forbidden_reframes": forbidden_reframes,
    }


def _proposition_lock_prompt_block(cfg: DebateConfig) -> str:
    lock = _build_proposition_lock(cfg)
    forbidden = ", ".join(lock.get("forbidden_reframes") or [])
    return (
        "- Locked proposition for this match:\n"
        f"- claim_subject: {lock['claim_subject']}\n"
        f"- claim_predicate: {lock['claim_predicate']}\n"
        f"- comparison_unit: {lock['comparison_unit']}\n"
        f"- evaluation_axis: {lock['evaluation_axis']}\n"
        f"- time_scope: {lock['time_scope']}\n"
        f"- quantifier_scope: {lock['quantifier_scope']}\n"
        f"- means_vs_essence_lock: {lock['means_vs_essence_lock']}\n"
        f"- proof_burden_shape: {lock['proof_burden_shape']}\n"
        f"- forbidden_reframes: {forbidden}\n"
        "- Both sides must argue the same locked proposition. Do not quietly switch to conditions, exceptions, means, or a different time scope unless you are explicitly attacking that as a reframe.\n"
    )


def _opening_contract_prompt_block(cfg: DebateConfig, speaker: str, turn_no: int) -> str:
    if speaker != "A" or turn_no != 1:
        return ""
    contract = _build_opening_contract(cfg)
    return (
        "- For A Turn 1, opening_contract is meta only.\n"
        "- Do not surface labels such as 見たい筋, 焦点, 比較軸, 採用条件, or anti-reframe guard in speech.\n"
        f"- Hidden comparison axis for meta only: {contract['comparison_axis']}\n"
        f"- Hidden acceptance condition for meta only: {contract['acceptance_condition']}\n"
        "- If you return meta.opening_contract, keep it aligned with the actual speech.\n"
    )


def _mode_prompt_rules(mode: str) -> str:
    if mode == "pro":
        return (
            "- Debate mode: Pro.\n"
            "- Use structured reasoning, definitions, and evidence when helpful.\n"
        )
    return (
        "- Debate mode: Casual.\n"
        "- Write in normal conversational Japanese.\n"
        "- Prefer concrete examples and one natural analogy over abstract commentary.\n"
        "- Be direct; do not sound academic or neutral.\n"
        "- Do NOT use technical jargon, model names, or scientific terminology.\n"
        "- Use plain everyday language that a high school student can understand.\n"
        "- If giving examples, describe them simply without naming specific scientific terms.\n"
    )


def _speaker_role_rules(provider: str, speaker: str) -> str:
    turn1_opening_rule = (
        "- Turn 1: Even without opponent input, you must state your own position and give at least two reasons.\n"
        if speaker == "B"
        else ""
    )
    if provider == "openai":
        return (
            turn1_opening_rule
            + "- GPT role: breaker.\n"
            "- Hit the opponent's immediate premise, then advance your case in the same turn.\n"
            "- Use metaphor only when it sharpens the hit.\n"
        )
    if provider == "anthropic":
        return (
            turn1_opening_rule
            + "- Claude role: closer.\n"
            "- Test one required condition and press the finish if it fails.\n"
        )
    return turn1_opening_rule


def _judge_prompt(cfg: DebateConfig, turns: list[dict[str, Any]], transcript: str) -> str:
    # KEEP: thin compatibility wrapper for judge tests and live judge entry.
    return _judge_pass1_prompt(cfg, turns, transcript)


def _judge_pass1_prompt(cfg: DebateConfig, turns: list[dict[str, Any]], transcript: str) -> str:
    topic_basis = _normalized_topic_evaluation_basis(cfg.topic)
    return (
        "You are a debate judge.\n"
        "Respond with one JSON object only. No markdown, no prose, no code fences.\n"
        f"Evaluate this match as: {topic_basis['topic_proposition']}.\n"
        "Judge by the logical validity of the claim, the plausibility of its premises, and whether the causal links actually hold.\n"
        "Use this exact schema:\n"
        "{"
        "\"winner\":{\"side\":\"A|B|Draw\",\"reason\":\"20字以内\"},"
        "\"reason_one_liner\":\"80字以内の日本語1文\","
        "\"confidence\":\"Low|Medium|High\","
        "\"turning_point_turn\":\"1|2|3|4|5\""
        "}\n"
        "Keep every field short.\n"
        "Judge the winner once and summarize why in one sentence.\n"
        "Debate transcript:\n"
        f"{transcript}\n"
    )


def _judge_pass2_prompt(cfg: DebateConfig, turns: list[dict[str, Any]], transcript: str, pass1: dict[str, Any]) -> str:
    winner = pass1.get("winner") if isinstance(pass1.get("winner"), dict) else {}
    topic_basis = _normalized_topic_evaluation_basis(cfg.topic)
    return (
        "You are Judge Gemini Pass2 for a debate structure extraction UI.\n"
        "Respond with one JSON object only. No markdown, no prose, no code fences.\n"
        f"Topic: {cfg.topic}\n"
        f"Locked evaluation form: {topic_basis['topic_proposition']}\n"
        f"Evaluate by: {topic_basis['evaluation_axis']}\n"
        f"Side A position: {cfg.side_a}\n"
        f"Side B position: {cfg.side_b}\n"
        "Use Pass1 as fixed baseline. Do not change the winner.\n"
        "Respond entirely in natural Japanese.\n"
        "Use this exact JSON schema:\n"
        "{"
        "\"fatal_phrase\":{\"turn\":1,\"speaker\":\"A|B|A/B\",\"text\":\"25字以内\",\"reason\":\"40字以内\"},"
        "\"weak_spot\":{\"side\":\"A|B|both\",\"turn\":1,\"speaker\":\"A|B|A/B\",\"label\":\"12字以内\",\"quote_excerpt\":\"25字以内\",\"why_one_sentence\":\"40字以内\",\"how_to_fix\":\"40字以内\"},"
        "\"flip_condition\":\"40字以内\","
        "\"gemini_takeaway\":{\"structural_explanation\":\"50字以内\",\"debate_dynamic\":\"50字以内\"},"
        "\"gemini_quote\":{\"text\":\"16字以内\"}"
        "}\n"
        "- Keep every field short and concrete.\n"
        "- Weak Spot is mandatory.\n"
        "- Fatal Phrase is the earliest line where the winning structure became visible.\n"
        "- Diagnose the losing side in weak_spot when the match is not Draw.\n"
        "- Do not contradict Pass1.\n"
        f"Pass1 winner: {_clean_text(winner.get('side') or '')}\n"
        f"Pass1 reason: {_clean_text(pass1.get('reason_one_liner') or '')}\n"
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


def _prompt_preview(prompt: str, limit: int = 200) -> str:
    text = str(prompt or "").strip().replace("\n", "\\n")
    return text[:limit]


def _default_gemini_model_name() -> str:
    return GEMINI_MODEL or GEMINI_MODEL_CANDIDATES[0]


def _list_gemini_generate_models(api_key: str) -> list[str]:
    query = parse.urlencode({"key": api_key})
    url = f"https://generativelanguage.googleapis.com/v1beta/models?{query}"
    req = request.Request(url, headers={}, method="GET")
    with request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
        payload = json.loads(response.read().decode("utf-8"))
    models = []
    for item in payload.get("models", []) if isinstance(payload.get("models"), list) else []:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" in methods and isinstance(item.get("name"), str):
            models.append(item["name"])
    return models


def _resolve_gemini_model(api_key: str) -> str:
    key = _clean_text(api_key)
    if not key:
        return _default_gemini_model_name()
    cached = _GEMINI_MODEL_CACHE.get(key)
    if cached:
        return cached
    models = _list_gemini_generate_models(key)
    preferred = [model for model in [GEMINI_MODEL, *GEMINI_MODEL_CANDIDATES] if model]
    for model in preferred:
        if model in models:
            _GEMINI_MODEL_CACHE[key] = model
            return model
    chosen = models[0] if models else _default_gemini_model_name()
    _GEMINI_MODEL_CACHE[key] = chosen
    return chosen


def _gemini_generate_content_url(model_name: str | None = None) -> str:
    resolved = model_name or _default_gemini_model_name()
    return f"https://generativelanguage.googleapis.com/v1beta/{resolved}:generateContent"


def _format_momentum(value: Any) -> str:
    if isinstance(value, dict):
        return f"A {value.get('a', '?')} / B {value.get('b', '?')}"
    return _clean_text(value or "")


def _call_openai(prompt: str, api_key: str, *, model_name: str | None = None) -> str:
    payload = {"model": model_name or OPENAI_MODEL, "input": prompt}
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


def _call_anthropic(prompt: str, api_key: str, *, model_name: str | None = None) -> str:
    payload = {
        "model": model_name or ANTHROPIC_MODEL,
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


def _call_gemini(prompt: str, api_key: str, *, model_name: str | None = None) -> str:
    model_name = model_name or _resolve_gemini_model(api_key)
    query = parse.urlencode({"key": api_key})
    url = f"{_gemini_generate_content_url(model_name)}?{query}"
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
    response_mime_type: str | None = None,
    thinking_budget: int | None = None,
) -> tuple[str, dict[str, Any]]:
    print("[DEBUG] using _call_gemini_match_chat")
    print("[DEBUG] prompt_chars:", len(prompt))
    model_name = _resolve_gemini_model(api_key)
    last_error: Exception | None = None
    current_max_output_tokens = max_output_tokens
    context = dict(debug_context or {})
    pass_label = str(context.get("pass_label") or "")
    for attempt in range(1, retries + 2):
        response, payload = _call_gemini_generate_content(
            prompt,
            api_key,
            model_name=model_name,
            temperature=0.15,
            max_output_tokens=current_max_output_tokens,
            timeout_s=timeout_s,
            response_mime_type=response_mime_type,
            thinking_budget=thinking_budget,
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
                "request_url": _gemini_generate_content_url(model_name),
                "request_variant": "contents_with_generation_config",
                "request_body_shape": "contents+generationConfig",
                "request_has_generation_config": True,
                "model": model_name,
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
            "request_url": _gemini_generate_content_url(model_name),
            "request_variant": "contents_with_generation_config",
            "request_body_shape": "contents+generationConfig",
            "request_has_generation_config": True,
            "model": model_name,
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
    model_name: str,
    temperature: float,
    max_output_tokens: int,
    timeout_s: int,
    response_mime_type: str | None = None,
    thinking_budget: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    query = parse.urlencode({"key": api_key})
    url = f"{_gemini_generate_content_url(model_name)}?{query}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    if response_mime_type:
        payload["generationConfig"]["responseMimeType"] = response_mime_type
    if thinking_budget is not None:
        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": thinking_budget}
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


def _normalize_summary(summary: dict[str, Any], turns: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
    try:
        turning_point = _normalize_turning_point(summary, winner, turns or [])
    except Exception:
        turning_point = {"turn": fatal_turn or 3, "summary": f"Turn {fatal_turn or 3}で流れが動いた。", "quote_excerpt": ""}
    try:
        weak_spot = _normalize_weak_spot(summary, winner, turning_point, fatal, turns or [])
    except Exception:
        weak_spot = {
            "side": _default_weak_spot_side(winner),
            "turn": fatal_turn or extract_turn_number_from_text(turning_point) or 3,
            "speaker": _default_weak_spot_speaker(winner),
            "label": "論拠不足",
            "quote_excerpt": "",
            "why_one_sentence": _default_weak_spot_why(_default_weak_spot_side(winner), "論拠不足", ""),
            "how_to_fix": _default_weak_spot_fix(_default_weak_spot_side(winner), "論拠不足"),
        }
    try:
        fatal_phrase = _normalize_fatal_phrase(summary, fatal, winner, turning_point, weak_spot, turns or [])
    except Exception:
        fatal_phrase = {
            "turn": extract_turn_number_from_text(turning_point) or fatal_turn or 3,
            "speaker": winner.get("side") if winner.get("side") in {"A", "B"} else "A/B",
            "text": "",
            "quote": "",
            "reason": _first_sentence(reason_one_liner),
        }
    debug_flags = _judge_specificity_debug(summary, turning_point, fatal_phrase, weak_spot)
    winner = _apply_major_violation_penalty(summary, winner, reason_one_liner, turning_point, weak_spot, fatal_phrase)
    reason_one_liner = _normalize_reason_one_liner(summary, winner)
    try:
        weak_spot = _normalize_weak_spot(summary, winner, turning_point, fatal, turns or [])
    except Exception:
        pass
    try:
        fatal_phrase = _normalize_fatal_phrase(summary, fatal, winner, turning_point, weak_spot, turns or [])
    except Exception:
        pass
    opening_debug = _evaluate_opening_contract_debug(turns or [], summary, weak_spot)
    fairness_debug = _evaluate_fairness_axes(summary, winner, reason_one_liner, turning_point, weak_spot, fatal_phrase, opening_debug)
    winner = _apply_fairness_winner_adjustment(winner, fairness_debug, reason_one_liner)
    reason_one_liner = _normalize_reason_one_liner(summary, winner)
    try:
        weak_spot = _normalize_weak_spot(summary, winner, turning_point, fatal, turns or [])
    except Exception:
        pass
    try:
        fatal_phrase = _normalize_fatal_phrase(summary, fatal, winner, turning_point, weak_spot, turns or [])
    except Exception:
        pass
    opening_debug = _evaluate_opening_contract_debug(turns or [], summary, weak_spot)
    fairness_debug = _evaluate_fairness_axes(summary, winner, reason_one_liner, turning_point, weak_spot, fatal_phrase, opening_debug)
    momentum = _normalize_momentum(summary.get("momentum"), winner, confidence, fatal_phrase, weak_spot)
    momentum = _apply_violation_momentum_boost(momentum, winner, weak_spot)
    try:
        gemini_takeaway = _normalize_gemini_takeaway(summary, winner, reason_one_liner, momentum, turning_point, weak_spot)
    except Exception:
        gemini_takeaway = {
            "structural_explanation": _first_sentence(reason_one_liner),
            "debate_dynamic": _stringify_turning_point(turning_point) or "流れは動いたが、決定打は簡潔に残らなかった。",
            "quote": "「議論の型を握った側が残る。」",
        }
    try:
        gemini_quote = _normalize_gemini_quote(summary, winner, turning_point, weak_spot, turns or [], fatal_phrase)
    except Exception:
        gemini_quote = {
            "text": "「その試合の穴を突いた側が残った。」",
            "quote": "",
            "source_turn": 0,
            "source_side": "",
            "match_confidence": 0.0,
            "debug_source": "generated_fallback",
        }
    decision_timeline = _normalize_decision_timeline(summary, winner, reason_one_liner, turning_point, weak_spot, fatal_phrase, turns or [])
    fatal_phrase["role"] = "decisive_lock"
    reason_one_liner, turning_point, weak_spot, fatal_phrase, gemini_quote = _separate_summary_card_roles(
        summary,
        winner,
        reason_one_liner,
        turning_point,
        weak_spot,
        fatal_phrase,
        gemini_quote,
    )
    winner, reason_one_liner, turning_point, weak_spot, fatal_phrase, axis_tags = _rewrite_cards_with_structural_axes(
        winner,
        reason_one_liner,
        turning_point,
        weak_spot,
        fatal_phrase,
        fairness_debug,
        opening_debug,
    )
    winner, reason_one_liner, turning_point, weak_spot, fatal_phrase, gemini_takeaway, gemini_quote = _naturalize_summary_surfaces(
        winner,
        reason_one_liner,
        turning_point,
        weak_spot,
        fatal_phrase,
        gemini_takeaway,
        gemini_quote,
    )
    return {
        "winner": winner,
        "why_role": "verdict_summary",
        "winner_axis_tag": axis_tags["winner"],
        "why_axis_tag": axis_tags["why"],
        "reason_one_liner": reason_one_liner,
        "confidence": confidence,
        "momentum": momentum,
        "turning_point": turning_point,
        "fatal_phrase": fatal_phrase,
        "first_crack": decision_timeline["first_crack"],
        "clincher": decision_timeline["clincher"],
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
        "frame_owner": fairness_debug["frame_owner"],
        "frame_survival": fairness_debug["frame_survival"],
        "burden_closure": fairness_debug["burden_closure"],
        "parasitic_rebuttal": fairness_debug["parasitic_rebuttal"],
        "parasitic_rebuttal_reason": fairness_debug["parasitic_rebuttal_reason"],
        "residue_owner": fairness_debug["residue_owner"],
        "burden_shift_detected": fairness_debug["burden_shift_detected"],
        "definition_drift_owner": fairness_debug["definition_drift_owner"],
        "proposition_lock": opening_debug["proposition_lock"],
        "opening_contract": opening_debug["opening_contract"],
        "opening_axis_locked": opening_debug["opening_axis_locked"],
        "opening_acceptance_locked": opening_debug["opening_acceptance_locked"],
        "drift_from_opening_contract": opening_debug["drift_from_opening_contract"],
        "legitimate_elaboration": opening_debug["legitimate_elaboration"],
        "reframe_attempt_detected": opening_debug["reframe_attempt_detected"],
        "reframe_detected": opening_debug["reframe_detected"],
        "reframe_type": opening_debug["reframe_type"],
        "reframe_severity": opening_debug["reframe_severity"],
        "reframe_owner": opening_debug["reframe_owner"],
        "key_disagreement_top3": disagreements,
        "reused_template_flags": debug_flags["reused_template_flags"],
        "direct_quote_found": debug_flags["direct_quote_found"],
        "turning_point_quote_found": debug_flags["turning_point_quote_found"],
        "first_crack_turn": decision_timeline["first_crack"].get("turn") or 0,
        "first_crack_quote": decision_timeline["first_crack"].get("quote") or "",
        "decisive_lock_turn": fatal_phrase.get("turn") or 0,
        "decisive_lock_quote": fatal_phrase.get("quote") or "",
        "clincher_turn": decision_timeline["clincher"].get("turn") or 0,
        "clincher_quote": decision_timeline["clincher"].get("quote") or "",
    }


def _summary_role_overlap_key(text: Any) -> str:
    value = _clean_text(text or "").lower()
    value = re.sub(r"[「」『』（）()\[\]【】\s。、，,.;:!！?？・/\\\-]+", "", value)
    return value


def _summary_role_overlaps(left: Any, right: Any) -> bool:
    a = _summary_role_overlap_key(left)
    b = _summary_role_overlap_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 8 and shorter in longer


def _build_turning_point_frame_shift_summary(turning_point: Any, weak_spot: dict[str, Any], fatal_phrase: dict[str, Any]) -> str:
    turn_no = extract_turn_number_from_text(turning_point) or extract_turn_number_from_text(weak_spot.get("turn")) or extract_turn_number_from_text(fatal_phrase.get("turn")) or 3
    focus = _clean_text(
        weak_spot.get("label")
        or weak_spot.get("quote_excerpt")
        or fatal_phrase.get("quote")
        or fatal_phrase.get("reason")
        or ""
    ).strip("「」")
    if focus:
        return f"Turn {turn_no}で争点が{_first_sentence(focus)}へ移り、試合の見方が変わった。"
    return f"Turn {turn_no}で議論の軸が動き、押し引きよりもルールの奪い合いが前面に出た。"


def _build_decisive_hit_reason(
    winner: dict[str, str],
    fatal_phrase: dict[str, Any],
    weak_spot: dict[str, Any],
) -> str:
    role = _clean_text(fatal_phrase.get("structural_role") or "")
    label = _clean_text(weak_spot.get("label") or "")
    if label:
        return _first_sentence(f"{label}を一撃で露出し、勝敗の傾きを固定した。")
    if role == "definition_lock":
        return "定義の逃げ道を塞ぎ、その場で勝ち筋を固定した。"
    if role == "rule_capture":
        return "判定基準を握り、その後の返答を全部守勢に回した。"
    if role == "burden_shift":
        return "立証責任を押し返し、相手だけが説明を背負う形にした。"
    if winner.get("side") in {"A", "B"}:
        return f"{winner['side']}の勝ち筋がこの一文で具体化し、その後の反撃幅を狭めた。"
    return "この一文で争点が固定され、決着の向きが見えた。"


def _build_first_crack_reason(winner: dict[str, str], weak_spot: dict[str, Any]) -> str:
    loser = _losing_side(winner)
    weak_label = _clean_text(weak_spot.get("label") or "")
    if loser in {"A", "B"} and weak_label:
        return f"{loser}の「{weak_label}」が最初に露出し、その後の押し込みの起点になった。"
    if loser in {"A", "B"}:
        return f"{loser}の核に最初のヒビが入り、その後の反論が通りやすくなった。"
    return "ここで最初のヒビが入り、試合の流れに傷が残った。"


def _build_clincher_reason(winner: dict[str, str], quote: str, turning_point: Any) -> str:
    side = winner.get("side") or ""
    if side in {"A", "B"}:
        return f"{side}が最後に逃げ道を塞ぎ、逆転余地をほぼ消した。"
    if quote:
        return "最後の一文で、残っていた逃げ道が塞がれた。"
    return f"{_stringify_turning_point(turning_point) or '終盤の一押し'}が、そのまま締めになった。"


def _axis_label_from_reframe_type(reframe_type: str) -> str:
    mapping = {
        "means_for_essence": "Means for essence",
        "exception_for_general_rule": "Exception escape",
        "general_for_exception": "Generalization shift",
        "time_shift": "Time shift",
        "proof_threshold_shift": "Proof threshold shift",
        "comparison_axis_shift": "Axis shift",
        "scope_substitution": "Scope substitution",
    }
    return mapping.get(_clean_text(reframe_type or ""), "Reframe")


def _rewrite_cards_with_structural_axes(
    winner: dict[str, str],
    why: str,
    turning_point: dict[str, Any],
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
    fairness_debug: dict[str, Any],
    opening_debug: dict[str, Any],
) -> tuple[dict[str, str], str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    winner_out = dict(winner or {})
    turning = dict(turning_point or {})
    weak = dict(weak_spot or {})
    fatal = dict(fatal_phrase or {})
    why_out = _first_sentence(why)
    axis_tags = {
        "winner": "",
        "why": "",
        "turning": "",
        "weak": "",
        "fatal": "",
    }

    reframe_detected = bool(opening_debug.get("reframe_detected"))
    reframe_owner = _clean_text(opening_debug.get("reframe_owner") or "")
    reframe_type = _clean_text(opening_debug.get("reframe_type") or "")
    proposition_lock = opening_debug.get("proposition_lock") or {}
    claim_subject = _clean_text(proposition_lock.get("claim_subject") or "")
    claim_predicate = _clean_text(proposition_lock.get("claim_predicate") or "")
    comparison_topic = "より" in claim_subject or "どちら" in claim_subject or "より" in claim_predicate or "どちら" in claim_predicate
    drift = bool(opening_debug.get("drift_from_opening_contract"))
    legitimate = bool(opening_debug.get("legitimate_elaboration"))
    frame_survival = _clean_text(fairness_debug.get("frame_survival") or "")
    residue_owner = _clean_text(fairness_debug.get("residue_owner") or "")
    burden_shift_owner = _clean_text(fairness_debug.get("burden_shift_detected") or "")
    burden_closure = fairness_debug.get("burden_closure") or {}

    if comparison_topic and reframe_detected and reframe_owner == "B":
        axis_tags = {key: "Comparison validity" for key in axis_tags}
        if winner_out.get("side") == "A":
            winner_out["reason"] = _first_sentence(
                "Aは比較軸を一貫して扱い、Bは条件差を持ち込んだが、その接続でAの成立条件を崩し切れなかった。"
            )
            why_out = _first_sentence(
                "Aは長期保有の比較軸を保ったまま具体条件を積み、Bの反証は条件差の提示にとどまって比較命題の反転まで届かなかった。"
            )
            weak["side"] = "B"
            weak["speaker"] = "B"
            weak["label"] = "比較軸の接続不足"
            weak["why_one_sentence"] = _first_sentence(
                "Bは流動性や保有主体の差を出したが、それがなぜ比較命題そのものを反転させるかを閉じ切れなかった。"
            )
            weak["role"] = "failure_exposure"
            weak["axis_tag"] = "Comparison validity"
            turning["summary"] = _first_sentence(
                f"Turn {extract_turn_number_from_text(turning.get('turn')) or weak.get('turn') or fatal.get('turn') or 2}で、比較軸の内側でどちらが条件差を接続できるかが勝負になった。"
            )
            turning["axis_tag"] = "Comparison validity"
            fatal["reason"] = _first_sentence(
                "この一文で比較軸の内側にある条件差が整理され、Bの反証が反転条件まで届いていないことが見えた。"
            )
            fatal["axis_tag"] = "Comparison validity"
        elif winner_out.get("side") == "B":
            winner_out["reason"] = _first_sentence(
                "Bは比較軸を一貫して扱い、条件差を具体でつなぎ切ってAの成立条件を崩した。"
            )
            why_out = _first_sentence(
                "Bは長期保有の比較軸を外さずに条件差を具体化し、Aの主張が成り立つ前提を反証で閉じた。"
            )
        return winner_out, why_out, turning, weak, fatal, axis_tags

    if reframe_detected and reframe_owner == "B":
        label = _axis_label_from_reframe_type(reframe_type)
        axis_tags = {key: label for key in axis_tags}
        winner_out["reason"] = _first_sentence(
            f"Bは{label.lower()}で問いを別物へずらしたが、固定された proposition の中でAの必要条件を壊したわけではない。"
        )
        why_out = _first_sentence(
            f"Aは proposition lock を守り、Bの{label.lower()}は lock 外の押し込みとして扱う。"
        )
        weak["side"] = "B"
        weak["speaker"] = "B"
        weak["label"] = {
            "means_for_essence": "手段の本質化",
            "exception_for_general_rule": "例外逃避",
            "general_for_exception": "一般化のすり替え",
            "time_shift": "時間軸ずらし",
            "proof_threshold_shift": "立証閾値ずらし",
            "comparison_axis_shift": "比較軸ずらし",
            "scope_substitution": "問いの再発明",
        }.get(reframe_type, "問いの再発明")
        weak["why_one_sentence"] = _first_sentence(
            f"Bは{weak['label']}で proposition lock の外へ逃げ、Aの主張そのものには答えていない。"
        )
        weak["role"] = "failure_exposure"
        weak["axis_tag"] = label
        turning["summary"] = _first_sentence(
            f"Turn {extract_turn_number_from_text(turning.get('turn')) or extract_turn_number_from_text(turning) or weak.get('turn') or fatal.get('turn') or 2}でBの{weak['label']}が露出し、争点が lock の内外へ分かれた。"
        )
        turning["axis_tag"] = label
        fatal["reason"] = _first_sentence(
            f"この一文でBの{weak['label']}が露出し、lock 外の押し込みでは勝ち切れないことが固定した。"
        )
        fatal["axis_tag"] = label
        return winner_out, why_out, turning, weak, fatal, axis_tags

    if drift:
        axis_tags = {key: "Contract drift" for key in axis_tags}
        winner_out["reason"] = _first_sentence(
            "Aは最初に置いた筋を守れず、押し返されたあとで条件を足したぶん勝ち筋が細った。"
        )
        why_out = _first_sentence(
            "Aは最初に置いた見方と成立ラインの外へ出て、あとから守りを足したように見えた。"
        )
        weak["side"] = "A"
        weak["speaker"] = "A"
        weak["label"] = "Contract drift"
        weak["why_one_sentence"] = _first_sentence(
            "Aは主張の範囲をあとから動かし、精密化より後付け防御に見える返しになった。"
        )
        weak["axis_tag"] = "Contract drift"
        turning["summary"] = _first_sentence(
            f"Turn {extract_turn_number_from_text(turning.get('turn')) or weak.get('turn') or fatal.get('turn') or 3}でAが最初の筋から外れ、争点が後付けの条件かどうかへ移った。"
        )
        turning["axis_tag"] = "Contract drift"
        fatal["reason"] = _first_sentence(
            "この一文でAの条件追加が後付けに見え、そこで勝ち筋の弱さがはっきりした。"
        )
        fatal["axis_tag"] = "Contract drift"
        return winner_out, why_out, turning, weak, fatal, axis_tags

    if frame_survival == "A_frame_survived" and burden_closure.get("B") != "closed":
        axis_tags["winner"] = "Frame survival"
        axis_tags["why"] = "Frame survival"
        winner_out["reason"] = _first_sentence("Aの最初のフレームが最後まで残り、Bは必要条件を壊し切れなかった。")
        why_out = _first_sentence("Aは最初の問いと約束を守り切り、Bはその内側で崩すだけの根拠を閉じられなかった。")
    elif frame_survival == "B_frame_survived" and burden_closure.get("B") == "closed":
        axis_tags["winner"] = "Frame survival"
        axis_tags["why"] = "Frame survival"
        winner_out["reason"] = _first_sentence("Bは対抗フレームを立て、その内側でAの必要条件を実際に壊した。")
        why_out = _first_sentence("Bは最初の問いを外さずに対抗フレームを維持し、Aの成立ライン不成立を閉じた。")

    if residue_owner == "B":
        weak["axis_tag"] = weak.get("axis_tag") or "Residue"
        if not _summary_role_overlaps(weak.get("why_one_sentence"), "B側の残差"):
            weak["why_one_sentence"] = _first_sentence("最後に残った未解決条件はB側の責任で、A不利へ短絡できない。")
    if burden_shift_owner in {"A", "B"}:
        label = "Burden shift"
        if burden_shift_owner == _clean_text(weak.get("side") or ""):
            weak["axis_tag"] = weak.get("axis_tag") or label
        if not turning.get("axis_tag"):
            turning["axis_tag"] = label
    if legitimate and not drift and not why_out:
        why_out = _first_sentence("Aは最初の contract を守った範囲で精密化し、後退ではなく補強として残した。")
    return winner_out, why_out, turning, weak, fatal, axis_tags


def _closing_sentence_score(sentence: str, support_terms: list[str]) -> int:
    normalized = _clean_text(sentence or "")
    score = _score_quote_candidate(normalized, support_terms)
    if re.search(r"(つまり|だから|結局|最後に|それでも|要するに|以上|残らない|逃げられない|閉じる|確定する)", normalized):
        score += 5
    if re.search(r"[。！？]$", normalized):
        score += 2
    return score


def _extract_best_sentence_for_turn(turns: list[dict[str, Any]], turn_no: int, speaker: str, *hints: str) -> tuple[str, float]:
    speech = _extract_turn_speech(turns, turn_no, speaker)
    if not speech:
        return "", 0.0
    sentences = _split_quote_candidates(speech)
    hint_terms = _quote_hint_terms(*hints)
    ranked = sorted(
        (
            (sentence, _closing_sentence_score(sentence, hint_terms))
            for sentence in sentences
            if not _is_banned_placeholder_quote(sentence)
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[0] if ranked else ("", 0.0)


def _normalize_decision_timeline(
    summary: dict[str, Any],
    winner: dict[str, str],
    reason_one_liner: str,
    turning_point: Any,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
    turns: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    winner_side = _normalize_speaker_code(winner.get("side") or "")
    decisive_turn = extract_turn_number_from_text(fatal_phrase.get("turn")) or extract_turn_number_from_text(turning_point) or 3
    weak_turn = _normalize_weak_spot_turn(weak_spot.get("turn"), turning_point, fatal_phrase)
    first_turn = min([value for value in [weak_turn, extract_turn_number_from_text(turning_point), decisive_turn] if value], default=decisive_turn)
    first_quote = ""
    first_speaker = winner_side or _normalize_speaker_code(fatal_phrase.get("speaker") or "") or "A"
    if turns and first_turn and first_turn < decisive_turn and first_speaker in {"A", "B"}:
        quote, score = _extract_best_sentence_for_turn(
            turns,
            first_turn,
            first_speaker,
            weak_spot.get("quote_excerpt") or "",
            weak_spot.get("why_one_sentence") or "",
            reason_one_liner,
            fatal_phrase.get("quote") or "",
        )
        if quote and score >= 5:
            first_quote = quote
    if not first_quote:
        first_quote = _clean_text(weak_spot.get("quote_excerpt") or "") or _clean_text((turning_point or {}).get("quote_excerpt") if isinstance(turning_point, dict) else "")
        if not first_quote:
            first_quote = _clean_text(fatal_phrase.get("quote") or fatal_phrase.get("text") or "")
            first_turn = decisive_turn
            first_speaker = _normalize_speaker_code(fatal_phrase.get("speaker") or "") or first_speaker
    first_quote = _ensure_self_contained_quote(
        first_quote,
        turns,
        first_turn,
        first_speaker,
        weak_spot.get("why_one_sentence") or "",
        weak_spot.get("label") or "",
        reason_one_liner,
    )
    first_crack = {
        "turn": int(first_turn or decisive_turn or 3),
        "speaker": first_speaker if first_speaker in {"A", "B"} else (_normalize_speaker_code(fatal_phrase.get("speaker") or "") or "A"),
        "quote": first_quote,
        "reason": _build_first_crack_reason(winner, weak_spot),
        "role": "first_crack",
    }

    clincher_turn = 0
    clincher_quote = ""
    clincher_speaker = winner_side or _normalize_speaker_code(fatal_phrase.get("speaker") or "")
    if turns and clincher_speaker in {"A", "B"}:
        max_turn = max(int(turn.get("turn") or 0) for turn in turns) if turns else decisive_turn
        for candidate_turn in range(max_turn, max(decisive_turn, 1) - 1, -1):
            quote, score = _extract_best_sentence_for_turn(
                turns,
                candidate_turn,
                clincher_speaker,
                fatal_phrase.get("reason") or "",
                reason_one_liner,
                weak_spot.get("why_one_sentence") or "",
                _stringify_turning_point(turning_point),
            )
            if quote and score >= 7:
                clincher_turn = candidate_turn
                clincher_quote = quote
                break
    if clincher_turn and clincher_turn < decisive_turn:
        clincher_turn = 0
        clincher_quote = ""
    if clincher_quote and _summary_role_overlap_key(clincher_quote) == _summary_role_overlap_key(fatal_phrase.get("quote") or fatal_phrase.get("text") or ""):
        clincher_turn = 0
        clincher_quote = ""
    clincher = {
        "turn": clincher_turn,
        "speaker": clincher_speaker if clincher_turn else "",
        "quote": clincher_quote,
        "reason": _build_clincher_reason(winner, clincher_quote, turning_point) if clincher_turn else "",
        "role": "clincher",
    }
    return {"first_crack": first_crack, "clincher": clincher}


def _build_distinct_gemini_framing(
    winner: dict[str, str],
    reason_one_liner: str,
    turning_point: Any,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
    gemini_quote: dict[str, Any],
) -> str:
    role = _clean_text(gemini_quote.get("framing_role") or gemini_quote.get("structural_role") or "")
    evidence = _clean_text(gemini_quote.get("evidence_quote") or gemini_quote.get("quote") or "").strip("「」")
    weak_label = _clean_text(weak_spot.get("label") or "")
    turning_summary = _stringify_turning_point(turning_point)
    if "実証例" in reason_one_liner and "全面否定" in reason_one_liner:
        return "実証例が一つ出た時点で、全面否定はもう維持できない。"
    if role == "definition_lock":
        return "相手があとから定義をずらす余地を消し、問いそのものを固定した。"
    if role == "rule_capture":
        return "判定基準を先に握り、その後の反論を全部その基準で裁ける形にした。"
    if role == "burden_shift":
        return "答える責任を相手側に固定し、自分は問いをずらさずに押し切った。"
    if role == "counterexample_land":
        return "一般論では逃げられない反例を置き、相手の採用条件そのものを壊した。"
    if role == "drift_exposure":
        return "相手が条件を後ろへずらした瞬間を捉え、勝ち筋の逃げを可視化した。"
    if weak_label:
        return _build_complete_quote_sentence(f"{weak_label}が露出した時点で、{_side_phrase(_opposite_side(winner.get('side') or '')) or '相手側'}の理屈は守勢に回った")
    if evidence:
        return _build_complete_quote_sentence(f"{_first_sentence(evidence)}が、この試合の決着構図をそのまま示した")
    if turning_summary:
        return _build_complete_quote_sentence(turning_summary)
    return _build_complete_quote_sentence(reason_one_liner)


def _separate_summary_card_roles(
    summary: dict[str, Any],
    winner: dict[str, str],
    reason_one_liner: str,
    turning_point: Any,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
    gemini_quote: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    why = _first_sentence(reason_one_liner)
    turning = dict(turning_point or {})
    fatal = dict(fatal_phrase or {})
    weak = dict(weak_spot or {})
    gemini = dict(gemini_quote or {})
    contradiction = _clean_text(summary.get("contradiction_exposed") or summary.get("contradiction") or "")

    fatal["role"] = _clean_text(fatal.get("role") or "decisive_hit")
    turning["role"] = _clean_text(turning.get("role") or "frame_shift")
    weak["role"] = _clean_text(weak.get("role") or "failure_exposure")
    gemini["framing_role"] = _clean_text(gemini.get("framing_role") or gemini.get("structural_role") or "decisive_frame")

    if _summary_role_overlaps(fatal.get("reason"), why):
        fatal["reason"] = _build_decisive_hit_reason(winner, fatal, weak)

    if _summary_role_overlaps(turning.get("summary"), why) or _summary_role_overlaps(turning.get("summary"), fatal.get("reason")):
        turning["summary"] = _build_turning_point_frame_shift_summary(turning, weak, fatal)

    weak_why = _clean_text(weak.get("why_one_sentence") or "")
    fatal_reason = _clean_text(fatal.get("reason") or "")
    if (
        weak_why
        and (
            _summary_role_overlap_key(weak_why) == _summary_role_overlap_key(why)
            or _summary_role_overlap_key(weak_why) == _summary_role_overlap_key(fatal_reason)
        )
    ):
        weak["why_one_sentence"] = _default_weak_spot_why(
            _clean_text(weak.get("side") or _default_weak_spot_side(winner)),
            _clean_text(weak.get("label") or "論拠不足"),
            contradiction,
        )

    framing = _clean_text(gemini.get("framing_text") or gemini.get("text") or "")
    if (
        _summary_role_overlaps(framing, why)
        or _summary_role_overlaps(framing, fatal.get("reason"))
        or _summary_role_overlaps(framing, turning.get("summary"))
    ):
        distinct = _build_distinct_gemini_framing(winner, why, turning, weak, fatal, gemini)
        gemini["framing_text"] = _clip_gemini_quote(distinct)
        gemini["text"] = gemini["framing_text"]
        if not _clean_text(gemini.get("framing_reason") or ""):
            gemini["framing_reason"] = "試合全体の構造読解として、一撃や転換とは別に言い直した。"
        gemini["pick_reason"] = _clean_text(gemini.get("framing_reason") or gemini.get("pick_reason") or "")

    return why, turning, weak, fatal, gemini


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


def _side_phrase(side: str) -> str:
    if side == "A":
        return "A"
    if side == "B":
        return "B"
    return "両者"


def _opposite_side(side: str) -> str:
    if side == "A":
        return "B"
    if side == "B":
        return "A"
    return ""


def _fairness_text_blob(
    summary: dict[str, Any],
    reason_one_liner: str,
    turning_point: Any,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
) -> str:
    parts = [
        _clean_text(reason_one_liner),
        _stringify_turning_point(turning_point),
        _clean_text((turning_point or {}).get("quote_excerpt") if isinstance(turning_point, dict) else ""),
        _clean_text(summary.get("provisional_judgment") or ""),
        _clean_text(summary.get("contradiction_exposed") or summary.get("contradiction") or ""),
        _clean_text(fatal_phrase.get("text") or ""),
        _clean_text(fatal_phrase.get("reason") or ""),
        _clean_text(weak_spot.get("label") or ""),
        _clean_text(weak_spot.get("quote_excerpt") or ""),
        _clean_text(weak_spot.get("why_one_sentence") or ""),
        _clean_text(summary.get("unresolved_residue") or ""),
    ]
    return " ".join([part for part in parts if part])


def _infer_frame_owner(
    summary: dict[str, Any],
    winner: dict[str, str],
    reason_one_liner: str,
    turning_point: Any,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
) -> str:
    text = _fairness_text_blob(summary, reason_one_liner, turning_point, weak_spot, fatal_phrase)
    weak_side = _clean_text(weak_spot.get("side") or "")
    weak_label = _clean_text(weak_spot.get("label") or "")
    if weak_side in {"A", "B"} and weak_label in PROPOSITION_VIOLATION_LABELS:
        owner = _opposite_side(weak_side)
        if owner:
            return owner
    for side in ("A", "B"):
        if re.search(fr"{side}が[^。]*(元の問い|命題|基準|定義|採用条件).*(固定|守|維持|戻|握|壊していない|残った)", text):
            return side
    if winner.get("side") in {"A", "B"} and re.search(r"(元の問い|命題|定義|採用条件|基準)", text):
        return winner["side"]
    return "A"


def _detect_burden_shift_owner(
    summary: dict[str, Any],
    weak_spot: dict[str, Any],
    turning_point: Any,
    fatal_phrase: dict[str, Any],
) -> str:
    weak_label = _clean_text(weak_spot.get("label") or "")
    weak_side = _clean_text(weak_spot.get("side") or "")
    if weak_side in {"A", "B"} and weak_label in PROPOSITION_VIOLATION_LABELS:
        return weak_side
    text = _fairness_text_blob(summary, "", turning_point, weak_spot, fatal_phrase)
    if re.search(r"(問いをずら|別の問い|条件を後から足|命題から逃|定義を広げ|定義を縮め|長期で答え|主語を縮め)", text):
        if weak_side in {"A", "B"}:
            return weak_side
        inferred = _infer_side_from_text(text)
        if inferred in {"A", "B"}:
            return inferred
    return ""


def _detect_parasitic_rebuttal(
    winner: dict[str, str],
    summary: dict[str, Any],
    reason_one_liner: str,
    turning_point: Any,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
) -> tuple[bool, str]:
    raw_weak = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {}
    side = winner.get("side") or ""
    loser = _opposite_side(side)
    if side not in {"A", "B"}:
        side = "B" if re.search(r"\bB\b", _fairness_text_blob(summary, reason_one_liner, turning_point, weak_spot, fatal_phrase)) else side
    text = _fairness_text_blob(summary, reason_one_liner, turning_point, weak_spot, fatal_phrase)
    explicit_parasitic = bool(
        re.search(r"(独自の採用条件を立てていない|自分の採用条件を(出していない|示していない|閉じていない)|反論成立なのかは示していない|寄生反論)", text)
    )
    attack_only = bool(re.search(r"(答えていない|論拠不足|根拠不足|未応答|穴|弱い|足りない|疑い)", text))
    owns_frame = bool(re.search(fr"{side}が[^。]*(基準|定義|命題|問い|採用条件|立証責任|検証可能性|分類).*(固定|守|握|戻|立て)", text))
    if fatal_phrase.get("speaker") == side and re.search(r"(基準|定義|命題|問い|検証可能性|採用条件)", _clean_text(fatal_phrase.get("text") or "") + _clean_text(fatal_phrase.get("reason") or "")):
        owns_frame = True
    weak_side = _clean_text(raw_weak.get("side") or weak_spot.get("side") or "")
    if explicit_parasitic and side in {"A", "B"}:
        return True, f"{side} attacked the opponent's holes without establishing a counter-frame or burden standard."
    if side == "B" and weak_side == loser and attack_only and not owns_frame and re.search(r"(だけ|ばかり|しか|寄生反論)", text):
        return True, "B attacked A's holes without establishing a counter-frame or burden standard."
    return False, ""


def _infer_frame_survival(
    frame_owner: str,
    winner: dict[str, str],
    burden_shift_owner: str,
    weak_spot: dict[str, Any],
) -> str:
    weak_side = _clean_text(weak_spot.get("side") or "")
    if frame_owner == "A":
        if burden_shift_owner == "A" or (weak_side == "A" and _clean_text(weak_spot.get("label") or "") in PROPOSITION_VIOLATION_LABELS):
            return "A_frame_broken"
        if winner.get("side") == "A":
            return "A_frame_survived"
        return "A_contested"
    if frame_owner == "B":
        if burden_shift_owner == "B" or (weak_side == "B" and _clean_text(weak_spot.get("label") or "") in PROPOSITION_VIOLATION_LABELS):
            return "B_frame_broken"
        if winner.get("side") == "B":
            return "B_frame_survived"
        return "B_contested"
    return "contested"


def _infer_residue_owner(summary: dict[str, Any], weak_spot: dict[str, Any], winner: dict[str, str]) -> str:
    unresolved = _clean_text(summary.get("unresolved_residue") or "")
    weak_side = _clean_text(weak_spot.get("side") or "")
    if re.search(r"Aが[^。]*(未解決|答えていない|残った)", unresolved):
        return "A"
    if re.search(r"Bが[^。]*(未解決|答えていない|残った)", unresolved):
        return "B"
    if re.search(r"B[^。]*(採用条件|基準|条件)[^。]*(示し切れず|示していない|閉じていない|残差)", unresolved):
        return "B"
    if re.search(r"A[^。]*(採用条件|基準|条件)[^。]*(示し切れず|示していない|閉じていない|残差)", unresolved):
        return "A"
    if weak_side in {"A", "B"}:
        return weak_side
    if winner.get("side") in {"A", "B"} and re.search(r"(未解決|残差|詰め切れていない)", unresolved):
        return _opposite_side(winner["side"]) or "shared"
    return "shared"


def _infer_burden_closure(
    winner: dict[str, str],
    frame_owner: str,
    frame_survival: str,
    weak_spot: dict[str, Any],
    parasitic_rebuttal: bool,
    burden_shift_owner: str,
    residue_owner: str,
) -> dict[str, str]:
    result = {"A": "open", "B": "open"}
    for side in ("A", "B"):
        if weak_spot.get("side") == side:
            result[side] = "open"
    if frame_survival == "A_frame_survived":
        result["A"] = "closed"
    if frame_survival == "B_frame_survived":
        result["B"] = "closed"
    if winner.get("side") in {"A", "B"} and not parasitic_rebuttal and burden_shift_owner != winner.get("side"):
        result[winner["side"]] = "closed"
    if residue_owner in {"A", "B"}:
        result[residue_owner] = "open"
    return result


def _evaluate_fairness_axes(
    summary: dict[str, Any],
    winner: dict[str, str],
    reason_one_liner: str,
    turning_point: Any,
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
    opening_debug: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_turning = summary.get("turning_point") if summary.get("turning_point") is not None else turning_point
    raw_weak = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else weak_spot
    raw_fatal = summary.get("fatal_phrase") if isinstance(summary.get("fatal_phrase"), dict) else fatal_phrase
    fairness_text = _fairness_text_blob(summary, reason_one_liner, raw_turning, raw_weak, raw_fatal)
    frame_owner = _infer_frame_owner(summary, winner, reason_one_liner, raw_turning, raw_weak, raw_fatal)
    burden_shift_owner = _detect_burden_shift_owner(summary, raw_weak, raw_turning, raw_fatal)
    parasitic_rebuttal, parasitic_reason = _detect_parasitic_rebuttal(winner, summary, reason_one_liner, raw_turning, raw_weak, raw_fatal)
    frame_survival = _infer_frame_survival(frame_owner, winner, burden_shift_owner, raw_weak)
    residue_owner = _infer_residue_owner(summary, raw_weak, winner)
    burden_closure = _infer_burden_closure(
        winner,
        frame_owner,
        frame_survival,
        raw_weak,
        parasitic_rebuttal,
        burden_shift_owner,
        residue_owner,
    )
    opening_debug = opening_debug or {}
    definition_drift_owner = ""
    if _clean_text(raw_weak.get("label") or "") in {"定義の後退", "主語の縮小", "時間軸ずらし", "条件すり替え", "問いの再発明", "命題逸脱"}:
        definition_drift_owner = _clean_text(raw_weak.get("side") or "")
    if opening_debug.get("drift_from_opening_contract") and not definition_drift_owner:
        definition_drift_owner = "A"
    if opening_debug.get("reframe_attempt_detected") and burden_shift_owner not in {"A", "B"}:
        burden_shift_owner = "B"
    return {
        "frame_owner": frame_owner,
        "frame_survival": frame_survival,
        "burden_closure": burden_closure,
        "parasitic_rebuttal": parasitic_rebuttal,
        "parasitic_rebuttal_reason": parasitic_reason,
        "residue_owner": residue_owner,
        "burden_shift_detected": burden_shift_owner,
        "definition_drift_owner": definition_drift_owner,
        "opening_axis_locked": bool(opening_debug.get("opening_axis_locked")),
        "opening_acceptance_locked": bool(opening_debug.get("opening_acceptance_locked")),
        "drift_from_opening_contract": bool(opening_debug.get("drift_from_opening_contract")),
        "legitimate_elaboration": bool(opening_debug.get("legitimate_elaboration")),
        "reframe_attempt_detected": bool(opening_debug.get("reframe_attempt_detected")),
        "reframe_detected": bool(opening_debug.get("reframe_detected")),
        "reframe_type": _clean_text(opening_debug.get("reframe_type") or ""),
        "reframe_severity": _clean_text(opening_debug.get("reframe_severity") or ""),
        "reframe_owner": _clean_text(opening_debug.get("reframe_owner") or ""),
        "_structural_signal": bool(re.search(r"(基準|定義|命題|問い|採用条件|立証責任|検証可能性|時間軸|主語|条件)", fairness_text)),
    }


def _apply_fairness_winner_adjustment(
    winner: dict[str, str],
    fairness: dict[str, Any],
    reason_one_liner: str,
) -> dict[str, str]:
    side = winner.get("side") or "Draw"
    if side not in {"A", "B"}:
        return winner
    frame_owner = fairness.get("frame_owner") or ""
    frame_survival = fairness.get("frame_survival") or ""
    residue_owner = fairness.get("residue_owner") or ""
    burden_shift_owner = fairness.get("burden_shift_detected") or ""
    burden_closure = fairness.get("burden_closure") or {}
    parasitic_rebuttal = bool(fairness.get("parasitic_rebuttal"))
    structural_signal = bool(fairness.get("_structural_signal"))
    opening_axis_locked = bool(fairness.get("opening_axis_locked"))
    opening_acceptance_locked = bool(fairness.get("opening_acceptance_locked"))
    drift_from_opening_contract = bool(fairness.get("drift_from_opening_contract"))
    reframe_attempt_detected = bool(fairness.get("reframe_attempt_detected"))
    reframe_detected = bool(fairness.get("reframe_detected"))
    reframe_owner = fairness.get("reframe_owner") or ""
    if side == "B":
        if reframe_detected and reframe_owner == "B":
            return {
                "side": "A",
                "reason": _first_sentence("Bは問いを条件や例外の側へずらしたが、固定された命題の中でAの必要条件を壊したわけではない。"),
            }
        if opening_axis_locked and opening_acceptance_locked and not drift_from_opening_contract and reframe_attempt_detected:
            return {
                "side": "A",
                "reason": _first_sentence("Aは初手で比較軸と採用条件を固定したまま残り、Bは問いをずらしただけでは必要条件を壊せなかった。"),
            }
        if parasitic_rebuttal or burden_shift_owner == "B":
            return {
                "side": "A",
                "reason": _first_sentence("Aのフレームが残り、Bは寄生反論だけでは必要条件を壊し切れなかった。"),
            }
        if structural_signal and frame_owner == "A" and frame_survival == "A_frame_survived" and burden_closure.get("B") != "closed":
            return {
                "side": "A",
                "reason": _first_sentence("Aが最初の基準を維持し、Bはその必要条件を実際には壊せなかった。"),
            }
        if residue_owner == "B":
            return {
                "side": "A",
                "reason": _first_sentence("最後に残った未解決条件はB側の責任で、A不利へは倒せない。"),
            }
    if side == "A":
        if drift_from_opening_contract and opening_axis_locked and opening_acceptance_locked:
            return {
                "side": "B",
                "reason": _first_sentence("Aは初手で固定した採用条件の外へ逃げ、後から条件を足して主張範囲を守ろうとした。"),
            }
        if parasitic_rebuttal and frame_owner == "B":
            return {
                "side": "B",
                "reason": _first_sentence("Bのフレームが残り、Aは寄生反論だけでは必要条件を壊し切れなかった。"),
            }
        if structural_signal and frame_owner == "B" and frame_survival == "B_frame_survived" and burden_closure.get("B") == "closed":
            return {
                "side": "B",
                "reason": _first_sentence("Bが対抗フレームを立て、その中でAの必要条件を壊した。"),
            }
        if burden_shift_owner == "A" and residue_owner == "A":
            return {
                "side": "B",
                "reason": _first_sentence("Aは問いの責任を守れず、残差もA側に残った。"),
            }
    return winner


def _opening_contract_from_turns(turns: list[dict[str, Any]], cfg: DebateConfig | None = None) -> dict[str, str]:
    if turns:
        first_meta = ((turns[0].get("meta") or {}).get("a") or {})
        raw_contract = first_meta.get("opening_contract")
        if isinstance(raw_contract, dict):
            contract = {
                key: _clean_text(raw_contract.get(key) or "")
                for key in (
                    "claim_scope",
                    "comparison_axis",
                    "acceptance_condition",
                    "anti_reframe_guard",
                    "exception_policy",
                    "burden_target",
                )
            }
            if any(contract.values()):
                return contract
        if cfg and _clean_text(turns[0].get("a") or ""):
            return _build_opening_contract(cfg, _clean_text(turns[0].get("a") or ""))
    if cfg:
        return _build_opening_contract(cfg)
    return {
        "claim_scope": "",
        "comparison_axis": "",
        "acceptance_condition": "",
        "anti_reframe_guard": "",
        "exception_policy": "",
        "burden_target": "",
    }


def _proposition_lock_from_turns(turns: list[dict[str, Any]], cfg: DebateConfig | None = None) -> dict[str, Any]:
    if turns:
        for speaker_key in ("a", "b"):
            first_meta = ((turns[0].get("meta") or {}).get(speaker_key) or {})
            raw_lock = first_meta.get("proposition_lock")
            if isinstance(raw_lock, dict) and any(_clean_text(v) for v in raw_lock.values() if not isinstance(v, list)):
                return {
                    "claim_subject": _clean_text(raw_lock.get("claim_subject") or ""),
                    "claim_predicate": _clean_text(raw_lock.get("claim_predicate") or ""),
                    "comparison_unit": _clean_text(raw_lock.get("comparison_unit") or ""),
                    "evaluation_axis": _clean_text(raw_lock.get("evaluation_axis") or ""),
                    "time_scope": _clean_text(raw_lock.get("time_scope") or ""),
                    "quantifier_scope": _clean_text(raw_lock.get("quantifier_scope") or ""),
                    "exception_policy": _clean_text(raw_lock.get("exception_policy") or ""),
                    "means_vs_essence_lock": _clean_text(raw_lock.get("means_vs_essence_lock") or ""),
                    "proof_burden_shape": _clean_text(raw_lock.get("proof_burden_shape") or ""),
                    "forbidden_reframes": [str(x).strip() for x in raw_lock.get("forbidden_reframes") or [] if str(x).strip()],
                }
    if cfg:
        return _build_proposition_lock(cfg)
    return {
        "claim_subject": "",
        "claim_predicate": "",
        "comparison_unit": "",
        "evaluation_axis": "",
        "time_scope": "",
        "quantifier_scope": "",
        "exception_policy": "",
        "means_vs_essence_lock": "",
        "proof_burden_shape": "",
        "forbidden_reframes": [],
    }


def _detect_proposition_reframe(text: str, proposition_lock: dict[str, Any]) -> dict[str, Any]:
    cleaned = _clean_text(text)
    if not cleaned:
        return {"reframe_detected": False, "reframe_type": "", "reframe_severity": "low"}
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    quantifier_scope = _clean_text(proposition_lock.get("quantifier_scope") or "")
    time_scope = _clean_text(proposition_lock.get("time_scope") or "")
    evaluation_axis = _clean_text(proposition_lock.get("evaluation_axis") or "")

    if lock_type == "comparison_validity":
        allowed_comparison_axes = [
            "価格",
            "需要",
            "ボラティリティ",
            "流動性",
            "保有主体",
            "中央銀行",
            "準備資産",
            "実需",
            "安全資産",
            "保管",
            "担保",
            "市場規模",
            "長期保有",
        ]
        explicit_shift_markers = [
            "別の問い",
            "そもそも問うべきは",
            "本題は",
            "ではなく",
            "人気の有無",
            "印象",
        ]
        if any(token in cleaned for token in allowed_comparison_axes) and not any(marker in cleaned for marker in explicit_shift_markers):
            return {"reframe_detected": False, "reframe_type": "", "reframe_severity": "low"}

    if lock_type == "love_itself_not_conditions" and re.search(r"(環境|きっかけ|会う機会|時間を買う|条件を整える|維持費|余裕を買う)", cleaned):
        return {"reframe_detected": True, "reframe_type": "means_for_essence", "reframe_severity": "high"}
    if lock_type == "general_rule_not_edge_exception" and re.search(r"(例外|極限状況|家族を守るなら|一度だけなら|非常時なら)", cleaned):
        return {"reframe_detected": True, "reframe_type": "exception_for_general_rule", "reframe_severity": "high"}
    if quantifier_scope in {"general_rule", "existential_within_labeled_set"} and re.search(r"(例外|一部でも|たまたま一件|一つでもあれば)", cleaned):
        return {"reframe_detected": True, "reframe_type": "exception_for_general_rule", "reframe_severity": "medium"}
    if quantifier_scope == "existential" and re.search(r"(常に|一般に|原則として|全面的に)", cleaned):
        return {"reframe_detected": True, "reframe_type": "general_for_exception", "reframe_severity": "medium"}
    if time_scope in {"general_present", "short_term_present", "labeled_at_time_of_claim"} and re.search(r"(長期|将来|後から見れば|事後的には|今ではなく将来)", cleaned):
        return {"reframe_detected": True, "reframe_type": "time_shift", "reframe_severity": "high" if time_scope == "labeled_at_time_of_claim" else "medium"}
    if evaluation_axis and evaluation_axis not in cleaned and re.search(r"(別の基準|比較すべきは.+ではなく|本題は.+ではなく|価値全体|条件全体)", cleaned):
        return {"reframe_detected": True, "reframe_type": "comparison_axis_shift", "reframe_severity": "medium"}
    if re.search(r"(完全証明|少しでも疑い|絶対に|100%|一切の例外なく)", cleaned):
        return {"reframe_detected": True, "reframe_type": "proof_threshold_shift", "reframe_severity": "medium"}
    if re.search(r"(別の問い|問いを変える|そもそも問うべきは|本題は.+ではなく)", cleaned):
        return {"reframe_detected": True, "reframe_type": "scope_substitution", "reframe_severity": "high"}
    return {"reframe_detected": False, "reframe_type": "", "reframe_severity": "low"}


def _opening_contract_term_hits(contract: dict[str, str], text: str) -> tuple[bool, bool]:
    cleaned = _clean_text(text)
    if not cleaned:
        return False, False
    axis = _clean_text(contract.get("comparison_axis") or "")
    axis_hit = bool(axis and axis in cleaned)
    acceptance_hit = bool(
        _clean_text(contract.get("acceptance_condition") or "")
        and any(term in cleaned for term in [axis, "採用条件", "条件", "基準", "成立", "崩れ", "維持"])
    )
    return axis_hit, acceptance_hit


def _detect_opening_contract_drift(text: str, contract: dict[str, str]) -> dict[str, Any]:
    cleaned = _clean_text(text)
    if not cleaned:
        return {
            "drift_from_opening_contract": False,
            "legitimate_elaboration": False,
            "definition_drift": False,
            "scope_narrowing": False,
            "scope_expansion": False,
        }
    narrowing = bool(re.search(r"(少なくとも|今回に限れば|一部では|限定すれば|例外的には|短期なら|ここでは|せめて)", cleaned))
    expansion = bool(re.search(r"(広く言えば|本質的には|全体として|もっと広い価値|そもそも比較すべきは)", cleaned))
    redefinition = bool(re.search(r"(ここで言う.+とは|定義し直すと|呼び方の問題|主語を縮め|主語を広げ|時間軸をずら)", cleaned))
    axis_hit, acceptance_hit = _opening_contract_term_hits(contract, cleaned)
    drift = bool(redefinition or narrowing or expansion) and not (axis_hit and acceptance_hit and not redefinition)
    return {
        "drift_from_opening_contract": drift,
        "legitimate_elaboration": bool((axis_hit or acceptance_hit) and not drift),
        "definition_drift": bool(drift and redefinition),
        "scope_narrowing": bool(drift and narrowing),
        "scope_expansion": bool(drift and expansion),
    }


def _detect_reframe_attempt(text: str, contract: dict[str, str]) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if re.search(r"(別の問い|問いを変え|比較すべきは.+ではなく|本題は.+ではなく|短期ではなく長期|主語を縮め|主語を広げ|条件をすり替|もっと広い価値)", cleaned):
        return True
    guard = _clean_text(contract.get("anti_reframe_guard") or "")
    return bool(guard and re.search(r"(時間軸|主語|別基準|問いの再発明|reframe)", guard) and re.search(r"(長期|短期|主語|別基準|別の問い)", cleaned))


def _evaluate_opening_contract_debug(
    turns: list[dict[str, Any]],
    summary: dict[str, Any],
    weak_spot: dict[str, Any],
) -> dict[str, Any]:
    contract = _opening_contract_from_turns(turns)
    proposition_lock = _proposition_lock_from_turns(turns)
    has_contract = bool(_clean_text(contract.get("comparison_axis") or "") and _clean_text(contract.get("acceptance_condition") or ""))
    a_later_meta = [((turn.get("meta") or {}).get("a") or {}) for turn in turns[1:]]
    b_later_meta = [((turn.get("meta") or {}).get("b") or {}) for turn in turns[1:]]
    drift = any(bool(meta.get("drift_from_opening_contract")) for meta in a_later_meta)
    legitimate = any(bool(meta.get("legitimate_elaboration")) for meta in a_later_meta) or (bool(a_later_meta) and not drift)
    reframe_attempt = any(bool(meta.get("reframe_attempt_detected")) for meta in b_later_meta)
    reframe_type = next((_clean_text(meta.get("reframe_type") or "") for meta in b_later_meta if _clean_text(meta.get("reframe_type") or "")), "")
    reframe_severity = next((_clean_text(meta.get("reframe_severity") or "") for meta in b_later_meta if _clean_text(meta.get("reframe_severity") or "")), "low")
    reframe_owner = "B" if reframe_attempt else ""
    weak_label = _clean_text(weak_spot.get("label") or "")
    weak_side = _clean_text(weak_spot.get("side") or "")
    if weak_side == "B" and weak_label in {"問いの再発明", "時間軸ずらし", "条件すり替え", "評価基準のすり替え"}:
        reframe_attempt = True
        reframe_owner = "B"
        if not reframe_type:
            reframe_type = "scope_substitution"
        if reframe_severity == "low":
            reframe_severity = "medium"
    if has_contract and weak_side == "A" and weak_label in {"定義の後退", "主語の縮小", "時間軸ずらし", "条件すり替え", "条件追加の後手化", "評価基準のすり替え"}:
        drift = True
        legitimate = False
    return {
        "proposition_lock": proposition_lock,
        "opening_contract": contract,
        "opening_axis_locked": has_contract,
        "opening_acceptance_locked": has_contract,
        "drift_from_opening_contract": drift,
        "legitimate_elaboration": legitimate,
        "reframe_attempt_detected": reframe_attempt,
        "reframe_detected": reframe_attempt,
        "reframe_type": reframe_type,
        "reframe_severity": reframe_severity,
        "reframe_owner": reframe_owner,
    }


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


def _normalize_quote_text(value: str) -> str:
    return re.sub(r"[「」\"'\s、。,.!?！？]", "", _clean_text(value or ""))


def _split_quote_candidates(text: str) -> list[str]:
    cleaned = _clean_text(text or "")
    if not cleaned:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])\s*", cleaned) if part.strip()]
    if not sentences:
        sentences = [cleaned]
    candidates = [sentence for sentence in sentences if 12 <= len(sentence) <= 120]
    if 12 <= len(cleaned) <= 120 and cleaned not in candidates:
        candidates.insert(0, cleaned)
    return candidates


def _extract_turn_speech(turns: list[dict[str, Any]], turn_no: int, speaker: str) -> str:
    speaker_value = _normalize_speaker_code(speaker)
    if turn_no < 1 or speaker_value not in {"A", "B"}:
        return ""
    for turn in turns:
        if int(turn.get("turn") or 0) != turn_no:
            continue
        return _clean_text(turn.get("a") if speaker_value == "A" else turn.get("b"))
    return ""


def _normalize_speaker_code(value: Any) -> str:
    text = _clean_text(value or "")
    lowered = text.lower()
    if lowered in {"a", "fighter a", "side a"}:
        return "A"
    if lowered in {"b", "fighter b", "side b"}:
        return "B"
    if lowered in {"a/b", "both", "draw"}:
        return "A/B"
    return ""


def _is_banned_placeholder_quote(text: str) -> bool:
    value = _clean_text(text or "")
    if not value:
        return True
    if value in FATAL_PHRASE_BANNED_TEXTS:
        return True
    if _looks_like_meta_strategy_text(value):
        return True
    if _contains_banned_surface_meta(value):
        return True
    if value.startswith("この一文") or value.startswith("この試合") or value.startswith("ここが分岐点"):
        return True
    return False


def _is_generic_why(text: str) -> bool:
    value = _clean_text(text or "")
    if not value or value in GENERIC_WHY_TEXTS:
        return True
    return bool(re.fullmatch(r"(強かったから|説得力があった|優勢になった)(。)?", value))


def _quote_hint_terms(*texts: str) -> list[str]:
    terms: list[str] = []
    for text in texts:
        for term in _extract_focus_terms(_clean_text(text or "")):
            value = term.strip()
            if not value or value in JP_STOPWORDS or len(value) <= 1:
                continue
            if value not in terms:
                terms.append(value)
    return terms[:8]


def _score_quote_candidate(sentence: str, hint_terms: list[str]) -> int:
    score = 0
    normalized = _clean_text(sentence)
    if _contains_banned_surface_meta(normalized) or _looks_like_meta_strategy_text(normalized):
        score -= 12
    for term in hint_terms:
        if term and term in normalized:
            score += 3
    if re.search(r"(定義|条件|反例|矛盾|逃げ|広げ|後退|基準|証拠|検証|命題)", normalized):
        score += 2
    if _is_self_contained_quote(normalized):
        score += 4
    if 18 <= len(normalized) <= 104:
        score += 2
    if re.search(r"[。！？]$", normalized):
        score += 1
    return score


def _is_self_contained_quote(text: str) -> bool:
    value = _clean_text(text or "").strip("「」")
    if not value:
        return False
    if len(value) < 8:
        return False
    if re.fullmatch(r"[A-Za-z0-9一-龥ァ-ヶー]+", value):
        return False
    if re.search(r"(は当時|で？|で\?$|とは。?$|だけ。?$|のみ。?$|つまり。?$)$", value):
        return False
    if re.search(r"(は|が|を|に|へ|で|と|も|だけ|のみ|こそ|なら|まで|から|より|や)$", value):
        return False
    if re.search(r"(。|！|!|？|\?)$", value):
        return True
    return bool(
        re.search(
            r"(だ|である|ない|た|ている|している|された|できる|できない|になる|ならない|見える|残る|崩れる|止まる|動く|違う|揺れる|足りない|十分だ|必要だ|証拠にはならない|守れない)$",
            value,
        )
    )


def _ensure_self_contained_quote(
    quote: str,
    turns: list[dict[str, Any]],
    turn_no: int,
    speaker: str,
    *hints: str,
) -> str:
    cleaned = _clean_text(quote or "")
    if cleaned and _is_self_contained_quote(cleaned):
        return cleaned
    matched, _ = _find_matching_transcript_quote(turns, turn_no, speaker, cleaned, *hints)
    if matched and _is_self_contained_quote(matched):
        return matched
    extracted, _ = _extract_transcript_quote(turns, turn_no, speaker, cleaned, *hints)
    if extracted and _is_self_contained_quote(extracted):
        return extracted
    return cleaned if _is_self_contained_quote(cleaned) else ""


def _infer_structural_role(*texts: Any) -> str:
    value = " ".join(_clean_text(text or "") for text in texts if _clean_text(text or ""))
    mapping = [
        (r"命題逸脱|主語の縮小|時間軸ずらし|条件すり替え|問いの再発明|元の問い", "drift_exposure"),
        (r"定義|定義の後退|主観的経験|定義は逃げ", "definition_lock"),
        (r"反例|具体例|その例", "counterexample_land"),
        (r"立証|証拠|検証|論拠不足|証明", "burden_shift"),
        (r"分類|カテゴリ|陰謀論|仮説", "category_reframe"),
        (r"ルール|基準|採用ライン|判定軸", "rule_capture"),
    ]
    for pattern, label in mapping:
        if re.search(pattern, value):
            return label
    return "decisive_frame"


def _build_pick_reason(role: str, quote: str, *reasons: Any) -> str:
    reason_text = _first_sentence(" ".join(_clean_text(value or "") for value in reasons if _clean_text(value or "")))
    templates = {
        "drift_exposure": "この一文が、相手の問いずらしや条件後退をその場で露出した。",
        "definition_lock": "この一文が、議論の定義を固定して相手の逃げ道を閉じた。",
        "counterexample_land": "この一文が、相手の一般論を具体例で折った。",
        "burden_shift": "この一文が、立証責任を相手へ固定し直した。",
        "category_reframe": "この一文が、議論の分類枠を入れ替えて結論の読みを変えた。",
        "rule_capture": "この一文が、判定基準そのものを握った。",
        "decisive_frame": "この一文が、勝敗を決めた構造を最短で示していた。",
    }
    return _first_sentence(reason_text if not _is_generic_why(reason_text) else templates.get(role, templates["decisive_frame"]))


def _looks_like_thin_framing_reason(text: str) -> bool:
    value = _clean_text(text or "")
    if not value:
        return True
    if _is_generic_why(value):
        return True
    if len(value) < 14:
        return True
    if re.fullmatch(r"[AB]が(押した|上回った|優勢だった|残った)(。)?", value):
        return True
    focus_terms = [term for term in _extract_focus_terms(value) if len(term.strip()) >= 2 and term.strip() not in JP_STOPWORDS]
    return len(focus_terms) < 2


def _extract_transcript_quote(
    turns: list[dict[str, Any]],
    turn_no: int,
    speaker: str,
    *hints: str,
) -> tuple[str, float]:
    speech = _extract_turn_speech(turns, turn_no, speaker)
    if not speech:
        return "", 0.0
    sentences = _split_quote_candidates(speech)
    if not sentences:
        return "", 0.0
    hint_terms = _quote_hint_terms(*hints)
    ranked = sorted(
        ((sentence, _score_quote_candidate(sentence, hint_terms)) for sentence in sentences if not _is_banned_placeholder_quote(sentence)),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        return "", 0.0
    viable = [item for item in ranked if item[1] > 0]
    if not viable:
        return "", 0.0
    best, score = viable[0]
    return best, float(score)


def _find_matching_transcript_quote(
    turns: list[dict[str, Any]],
    turn_no: int,
    speaker: str,
    preferred_text: str,
    *hints: str,
) -> tuple[str, float]:
    speech = _extract_turn_speech(turns, turn_no, speaker)
    if not speech:
        return "", 0.0
    candidates = _split_quote_candidates(speech)
    preferred = _normalize_quote_text(preferred_text)
    if preferred:
        for candidate in candidates:
            normalized = _normalize_quote_text(candidate)
            if normalized and (preferred in normalized or normalized in preferred):
                return candidate, 1.0
    return _extract_transcript_quote(turns, turn_no, speaker, preferred_text, *hints)


def _normalize_turning_point(summary: dict[str, Any], winner: dict[str, str], turns: list[dict[str, Any]]) -> dict[str, Any]:
    raw = summary.get("turning_point")
    value = _stringify_turning_point(raw)
    fatal = summary.get("fatal_phrase") if isinstance(summary.get("fatal_phrase"), dict) else {}
    weak_spot = summary.get("weak_spot") if isinstance(summary.get("weak_spot"), dict) else {}
    turn = extract_turn_number_from_text(raw) or fatal.get("turn") or weak_spot.get("turn") or 3
    try:
        turn_no = max(1, int(turn))
    except Exception:
        turn_no = 3
    issue = _clean_text(weak_spot.get("quote_excerpt") or weak_spot.get("label") or fatal.get("text") or "")
    speaker = _normalize_speaker_code((raw or {}).get("speaker") if isinstance(raw, dict) else "") or _normalize_speaker_code(fatal.get("speaker") or "") or _normalize_speaker_code(winner.get("side") or "")
    quote_excerpt, _ = _find_matching_transcript_quote(
        turns,
        turn_no,
        speaker if speaker in {"A", "B"} else (_normalize_speaker_code(fatal.get("speaker") or "") or _normalize_speaker_code(winner.get("side") or "") or "A"),
        _clean_text((raw or {}).get("quote_excerpt") if isinstance(raw, dict) else ""),
        value,
        issue,
        summary.get("reason_one_liner") or "",
    )
    if value and value != "未生成":
        return {"turn": turn_no, "summary": value, "quote_excerpt": quote_excerpt}
    if (winner.get("side") or "Draw") == "Draw":
        summary_text = (
            f"Turn {turn_no}で「{issue}」が争点として浮いたが、どちらも決め切れなかった。"
            if issue
            else f"Turn {turn_no}で流れは動いたが、どちらも決定打を最後まで押し切れなかった。"
        )
        return {"turn": turn_no, "summary": summary_text, "quote_excerpt": quote_excerpt}
    if quote_excerpt:
        return {"turn": turn_no, "summary": f"Turn {turn_no}で「{quote_excerpt}」が決定的な論点として前に出た。", "quote_excerpt": quote_excerpt}
    if issue:
        return {"turn": turn_no, "summary": f"Turn {turn_no}で「{issue}」が勝敗を分ける論点として前に出た。", "quote_excerpt": ""}
    return {"turn": turn_no, "summary": f"Turn {turn_no}で流れが大きく傾き、その後の押し返しが勝敗を分けた。", "quote_excerpt": ""}


def _normalize_fatal_phrase(
    summary: dict[str, Any],
    fatal: dict[str, Any],
    winner: dict[str, str],
    turning_point: str,
    weak_spot: dict[str, str],
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    speaker = _clean_text(fatal.get("speaker") or "")
    text = _extract_fatal_text(fatal)
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
    if _looks_like_meta_strategy_text(text) or _looks_like_meta_strategy_text(reason):
        text = ""
        reason = ""
    target_speaker = speaker if speaker in {"A", "B"} else (winning_speaker if winning_speaker in {"A", "B"} else "A")
    matched_quote, _ = _find_matching_transcript_quote(
        turns,
        turn_no,
        target_speaker,
        text,
        reason,
        weak_spot.get("quote_excerpt") or "",
        weak_spot.get("why_one_sentence") or "",
        summary.get("reason_one_liner") or "",
    )
    final_quote = _ensure_self_contained_quote(
        matched_quote or text,
        turns,
        turn_no,
        target_speaker,
        reason,
        weak_spot.get("quote_excerpt") or "",
        weak_spot.get("why_one_sentence") or "",
        summary.get("reason_one_liner") or "",
    )
    structural_role = _infer_structural_role(
        weak_spot.get("label") or "",
        weak_spot.get("why_one_sentence") or "",
        reason,
        final_quote,
        summary.get("reason_one_liner") or "",
    )
    pick_reason = _build_pick_reason(
        structural_role,
        final_quote,
        reason,
        weak_spot.get("why_one_sentence") or "",
        summary.get("reason_one_liner") or "",
    )
    if text and _is_banned_placeholder_quote(text):
        text = ""
    if text and text != "未生成":
        if side in {"A", "B"} and speaker in {"A", "B"} and speaker != winning_speaker:
            return {
                "turn": turn_no,
                "speaker": winning_speaker,
                "text": final_quote or _fatal_backfill_excerpt(weak_spot),
                "quote": final_quote or _fatal_backfill_excerpt(weak_spot),
                "reason": _first_sentence(weak_spot.get("why_one_sentence") or f"{speaker}の一撃はあったが、最終的には{winning_speaker}が押し返した。"),
                "structural_role": structural_role,
                "pick_reason": pick_reason,
            }
        return {
            "turn": turn_no,
            "speaker": speaker or winning_speaker,
            "text": final_quote,
            "quote": final_quote,
            "reason": _first_sentence(reason if not _is_generic_why(reason) else (weak_spot.get("why_one_sentence") or "")),
            "structural_role": structural_role,
            "pick_reason": pick_reason,
        }
    if side == "Draw":
        return {
            "turn": turn_no,
            "speaker": speaker or "A/B",
            "text": final_quote or "",
            "quote": final_quote or "",
            "reason": _first_sentence(reason if not _is_generic_why(reason) else (weak_spot.get("why_one_sentence") or "流れは動いたが、どちらもここから決め切れなかった。")),
            "structural_role": structural_role,
            "pick_reason": pick_reason,
        }
    return {
        "turn": turn_no,
        "speaker": winning_speaker,
        "text": final_quote or "",
        "quote": final_quote or "",
        "reason": _first_sentence(
            (reason if not _is_generic_why(reason) else "")
            or weak_spot.get("why_one_sentence")
            or (
                f"{loser_speaker}が流れを動かしかけても、{winning_speaker}が最後は押し返した。"
                if turning_side and turning_side != winning_speaker
                else "この場面で勝敗の傾きが固まった。"
            )
        ),
        "structural_role": structural_role,
        "pick_reason": pick_reason,
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
    turning_point: Any,
    weak_spot: dict[str, Any],
) -> dict[str, str]:
    raw = summary.get("gemini_takeaway")
    turning_point_text = _stringify_turning_point(turning_point)
    turning_side = _infer_side_from_text(turning_point_text)
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
            f"{turning_point_text}でBが流れを揺らしても、Aは{label or '判定基準'}を守った。"
            if turning_side == "B"
            else f"{turning_point_text}でAが主導権を握り、{label or '判定基準'}を固定した。"
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
            f"{turning_point_text}でAが流れを揺らしても、Bは{label or '判定軸'}を崩さなかった。"
            if turning_side == "A"
            else f"{turning_point_text}でBが流れを動かし、{label or '判定軸'}を押し切った。"
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
        ) or f"{turning_point_text}で勝負は揺れたが、その後も決定打が続かなかった。"
        quote = (_clean_text(raw.get("quote") or "") if isinstance(raw, dict) else "") or "「流れは揺れたが、決着は届かなかった。」"
    if reason_one_liner and reason_one_liner != "未生成" and not structural:
        structural = _first_sentence(reason_one_liner)
    if momentum.get("a") == momentum.get("b") and side != "Draw":
        dynamic = f"{turning_point_text}で傾きは出たが、押し込みは僅差だった。"
    if side in {"A", "B"} and not _text_favors_side(dynamic, side):
        dynamic = f"{turning_point_text}で揺れが出ても、最終的に{side}が主導権を保った。"
    return {
        "structural_explanation": _first_sentence(structural),
        "debate_dynamic": _first_sentence(dynamic),
        "quote": _clip_takeaway_quote(quote),
    }


def _extract_fatal_text(fatal: dict[str, Any]) -> str:
    return _clean_text(
        fatal.get("text")
        or fatal.get("quote_excerpt")
        or fatal.get("quote")
        or fatal.get("excerpt")
        or fatal.get("raw_text")
        or ""
    )


def _fatal_backfill_excerpt(weak_spot: dict[str, Any]) -> str:
    excerpt = _clean_text(weak_spot.get("quote_excerpt") or "")
    if excerpt and excerpt != "ここで一番効いた穴が露出した。":
        return excerpt
    return ""


def _stringify_turning_point(value: Any) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        for key in ("text", "summary", "explanation", "reason", "why", "value"):
            text = _clean_text(value.get(key) or "")
            if text:
                return text
    return ""


def _judge_specificity_debug(
    summary: dict[str, Any],
    turning_point: Any,
    fatal_phrase: dict[str, Any],
    weak_spot: dict[str, Any],
) -> dict[str, Any]:
    flags: list[str] = []
    direct_quote_found = bool(_clean_text(fatal_phrase.get("quote") or fatal_phrase.get("text") or ""))
    turning_point_quote_found = bool(
        _clean_text(
            ((turning_point or {}).get("quote_excerpt") or _stringify_turning_point(turning_point))
            if isinstance(turning_point, dict)
            else turning_point
        )
    )
    if not direct_quote_found:
        flags.append("fatal_phrase_missing_direct_quote")
    if not turning_point_quote_found:
        flags.append("turning_point_template")
    if not _clean_text(weak_spot.get("quote_excerpt") or ""):
        flags.append("weak_spot_missing_quote_excerpt")
    return {
        "reused_template_flags": flags,
        "direct_quote_found": direct_quote_found,
        "turning_point_quote_found": turning_point_quote_found,
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
    turning_point: Any,
    weak_spot: dict[str, Any],
    turns: list[dict[str, Any]],
    fatal_phrase: dict[str, Any],
) -> dict[str, Any]:
    winner_side = winner.get("side") or "Draw"
    support_terms = _quote_hint_terms(
        summary.get("reason_one_liner") or "",
        fatal_phrase.get("quote") or fatal_phrase.get("text") or "",
        fatal_phrase.get("reason") or "",
        weak_spot.get("label") or "",
        weak_spot.get("quote_excerpt") or "",
        weak_spot.get("why_one_sentence") or "",
        _stringify_turning_point(turning_point),
    )

    def pack_quote(
        text: str,
        quote: str,
        source_turn: int,
        source_side: str,
        confidence: float,
        debug_source: str,
    ) -> dict[str, Any]:
        resolved_speaker = source_side if source_side in {"A", "B"} else _normalize_speaker_code(fatal_phrase.get("speaker") or "") or "A"
        framing_seed = _build_specific_gemini_quote(
            summary,
            winner,
            _stringify_turning_point(turning_point),
            weak_spot,
            quote or text,
            source_side,
        )
        if debug_source == "generated_fallback":
            anchored_quote = ""
            display_text = _build_complete_quote_sentence(_clean_text(text or framing_seed or "").strip("「」"))
        else:
            anchored_quote = _clean_text(quote or "")
            if not anchored_quote:
                anchored_quote = _ensure_self_contained_quote(
                    text,
                    turns,
                    source_turn or 0,
                    resolved_speaker,
                    summary.get("reason_one_liner") or "",
                    fatal_phrase.get("reason") or "",
                    weak_spot.get("quote_excerpt") or "",
                    weak_spot.get("why_one_sentence") or "",
                    _stringify_turning_point(turning_point),
                )
            display_text = _build_complete_quote_sentence(_clean_text(framing_seed or text or anchored_quote).strip("「」"))
        consistent, consistency_reason = _gemini_quote_verdict_consistency(
            display_text or anchored_quote or quote or text,
            winner,
            source_side,
            support_terms,
            summary.get("reason_one_liner") or "",
            fatal_phrase,
            weak_spot,
            turning_point,
        )
        structural_role = _infer_structural_role(
            summary.get("reason_one_liner") or "",
            fatal_phrase.get("reason") or "",
            weak_spot.get("label") or "",
            weak_spot.get("why_one_sentence") or "",
            display_text or anchored_quote or quote or text,
        )
        framing_text = _clip_gemini_quote(display_text or framing_seed or text)
        evidence_quote = anchored_quote
        framing_reason = _build_pick_reason(
            structural_role,
            evidence_quote or text,
            summary.get("reason_one_liner") or "",
            fatal_phrase.get("reason") or "",
            weak_spot.get("why_one_sentence") or "",
        )
        return {
            "framing_text": framing_text,
            "framing_role": structural_role,
            "framing_reason": framing_reason,
            "evidence_quote": evidence_quote,
            "evidence_turn": source_turn,
            "evidence_side": source_side,
            "evidence_match_confidence": round(confidence, 3),
            "debug_source": debug_source,
            "verdict_consistency": consistent,
            "consistency_reason": consistency_reason,
            "text": framing_text,
            "quote": evidence_quote,
            "source_turn": source_turn,
            "source_side": source_side,
            "match_confidence": round(confidence, 3),
            "structural_role": structural_role,
            "pick_reason": framing_reason,
        }

    raw = summary.get("gemini_quote")
    if isinstance(raw, dict):
        text = _clean_text(raw.get("text") or "")
        source_turn = extract_turn_number_from_text(raw.get("source_turn") or raw.get("turn") or fatal_phrase.get("turn"))
        source_side = _clean_text(raw.get("source_side") or raw.get("side") or fatal_phrase.get("speaker") or "").upper()
        matched, confidence = _find_matching_transcript_quote(
            turns,
            source_turn or extract_turn_number_from_text(fatal_phrase.get("turn")) or 0,
            source_side if source_side in {"A", "B"} else _clean_text(fatal_phrase.get("speaker") or "").upper(),
            text,
            weak_spot.get("quote_excerpt") or "",
            weak_spot.get("why_one_sentence") or "",
            summary.get("reason_one_liner") or "",
        )
        if matched and not _looks_like_generic_gemini_quote(matched):
            packed = pack_quote(
                matched,
                matched,
                source_turn or extract_turn_number_from_text(fatal_phrase.get("turn")) or 0,
                source_side if source_side in {"A", "B"} else _clean_text(fatal_phrase.get("speaker") or "").upper(),
                confidence,
                "raw_transcript_match",
            )
            if packed["verdict_consistency"]:
                return packed
    anchor_candidate: dict[str, Any] | None = None
    fatal_quote = _clean_text(fatal_phrase.get("quote") or fatal_phrase.get("text") or "")
    fatal_turn = extract_turn_number_from_text(fatal_phrase.get("turn"))
    fatal_side = _clean_text(fatal_phrase.get("speaker") or "").upper()
    if fatal_quote:
        packed = pack_quote(fatal_quote, fatal_quote, fatal_turn or 0, fatal_side, 0.95, "fatal_reuse")
        if packed["verdict_consistency"]:
            anchor_candidate = packed
    weak_quote = _clean_text(weak_spot.get("quote_excerpt") or "")
    weak_turn = _normalize_weak_spot_turn(weak_spot.get("turn"), turning_point, fatal_phrase)
    weak_side = _clean_text(weak_spot.get("speaker") or weak_spot.get("side") or "").upper()
    if weak_quote and weak_quote != "ここで一番効いた穴が露出した。" and anchor_candidate is None:
        packed = pack_quote(weak_quote, weak_quote, weak_turn, weak_side if weak_side in {"A", "B"} else "", 0.75, "weak_spot_reuse")
        if packed["verdict_consistency"]:
            anchor_candidate = packed
    turning_quote = _clean_text((turning_point or {}).get("quote_excerpt") if isinstance(turning_point, dict) else "")
    turning_turn = extract_turn_number_from_text(turning_point) or weak_turn or fatal_turn or 0
    turning_side = _infer_side_from_text(turning_quote or _stringify_turning_point(turning_point))
    if turning_quote and anchor_candidate is None:
        packed = pack_quote(turning_quote, turning_quote, turning_turn, turning_side, 0.7, "turning_point_reuse")
        if packed["verdict_consistency"]:
            anchor_candidate = packed
    fallback_turn = extract_turn_number_from_text(turning_point) or fatal_turn or _normalize_weak_spot_turn(weak_spot.get("turn"), turning_point, fatal_phrase)
    fallback_side = fatal_side if fatal_side in {"A", "B"} else _clean_text(winner.get("side") or "").upper()
    quote, confidence = _extract_transcript_quote(
        turns,
        fallback_turn or 0,
        fallback_side if fallback_side in {"A", "B"} else "A",
        weak_spot.get("quote_excerpt") or "",
        weak_spot.get("why_one_sentence") or "",
        summary.get("reason_one_liner") or "",
    )
    if quote and anchor_candidate is None:
        packed = pack_quote(
            quote,
            quote,
            fallback_turn or 0,
            fallback_side if fallback_side in {"A", "B"} else "A",
            confidence,
            "transcript_fallback",
        )
        if packed["verdict_consistency"]:
            anchor_candidate = packed
    rebuilt = _build_specific_gemini_quote(summary, winner, _stringify_turning_point(turning_point), weak_spot)
    generated = pack_quote(
        rebuilt,
        "",
        0,
        "",
        0.0,
        "generated_fallback",
    )
    generated["verdict_consistency"] = True
    if anchor_candidate:
        generated["evidence_quote"] = anchor_candidate.get("evidence_quote", anchor_candidate.get("quote", ""))
        generated["evidence_turn"] = anchor_candidate.get("evidence_turn", anchor_candidate.get("source_turn", 0))
        generated["evidence_side"] = anchor_candidate.get("evidence_side", anchor_candidate.get("source_side", ""))
        generated["evidence_match_confidence"] = anchor_candidate.get("evidence_match_confidence", anchor_candidate.get("match_confidence", 0.0))
        generated["quote"] = generated["evidence_quote"]
        generated["source_turn"] = generated["evidence_turn"]
        generated["source_side"] = generated["evidence_side"]
        generated["match_confidence"] = generated["evidence_match_confidence"]
        generated["debug_source"] = "generated_with_anchor"
    return generated


def _gemini_quote_verdict_consistency(
    text: str,
    winner: dict[str, str],
    source_side: str,
    support_terms: list[str],
    reason_one_liner: str,
    fatal_phrase: dict[str, Any],
    weak_spot: dict[str, Any],
    turning_point: Any,
) -> tuple[bool, str]:
    side = winner.get("side") or "Draw"
    normalized = _clean_text(text or "")
    if not normalized:
        return False, "empty_quote"
    if text and not _is_self_contained_quote(normalized):
        return False, "quote_fragment_not_self_contained"
    if side not in {"A", "B"}:
        return True, "draw_or_unknown_winner"
    if not _quote_aligns_with_winner(normalized, winner):
        return False, "quote_reads_against_locked_winner"
    if source_side in {"A", "B"} and source_side != side:
        return False, "quote_source_side_opposes_locked_winner"
    overlap = 0
    for term in support_terms:
        if term and term in normalized:
            overlap += 1
    if overlap >= 2:
        return True, "supported_by_why_fatal_weak"
    if _text_favors_side(reason_one_liner, side) and _text_favors_side(normalized, side):
        return True, "winner_aligned_sentence"
    if any(
        term and term in normalized
        for term in [
            _clean_text(fatal_phrase.get("reason") or ""),
            _clean_text(weak_spot.get("label") or ""),
            _clean_text(weak_spot.get("why_one_sentence") or ""),
            _stringify_turning_point(turning_point),
        ]
    ):
        return True, "aligned_with_decisive_frame"
    return False, "insufficient_verdict_alignment"


def _clip_gemini_quote(text: str) -> str:
    quote = _clean_text(text).strip("「」")
    if not quote:
        quote = "流れを変えた一手が、勝負を決める。"
    if len(quote) <= 64:
        quote = quote
    elif len(quote) > 64:
        sentence = _first_sentence(quote).strip("「」")
        if sentence and len(sentence) <= 72:
            quote = sentence
        else:
            cut = _find_quote_cut_position(quote, 72)
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
    if re.search(r"[。！？]$", value):
        return value
    if re.search(r"(動かな|止まっ|崩れ|折れ|薄まっ|逃げに見え|立たな|守れな)$", value):
        return value + "た。"
    if re.search(r"(語ったが|広げたが|変えた瞬間|言い換えた瞬間|答えないまま)$", value):
        return value + "、勝負が動いた。"
    return value + "。"


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
    evidence_quote: str = "",
    evidence_side: str = "",
) -> str:
    reason_one_liner = _clean_text(summary.get("reason_one_liner") or "")
    if reason_one_liner and not _looks_like_thin_framing_reason(reason_one_liner):
        return _build_complete_quote_sentence(reason_one_liner)
    fatal_reason = _clean_text(((summary.get("fatal_phrase") or {}).get("reason") if isinstance(summary.get("fatal_phrase"), dict) else ""))
    if fatal_reason and not _looks_like_thin_framing_reason(fatal_reason):
        return _build_complete_quote_sentence(fatal_reason)
    concepts = _extract_gemini_quote_concepts(summary, turning_point, weak_spot)
    primary = concepts[0] if concepts else ""
    secondary = concepts[1] if len(concepts) > 1 else ""
    label = _clean_text(weak_spot.get("label") or "")
    side = winner.get("side") or "Draw"
    evidence = _clean_text(evidence_quote or "").strip("「」")
    evidence_focus = _extract_focus_terms(evidence)[:2] if evidence else []
    if not primary and evidence_focus:
        primary = evidence_focus[0]
    if not secondary and len(evidence_focus) > 1:
        secondary = evidence_focus[1]
    if not secondary and evidence and len(evidence) <= 28:
        secondary = evidence

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
    if evidence and side in {"A", "B"} and evidence_side == side:
        if primary and secondary:
            return f"{primary}を軸に据えたことで、{secondary}まで勝ち筋として閉じた。"
        if primary:
            return f"{primary}を押し出したことで、この試合の勝ち筋が一文で閉じた。"

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
    turns: list[dict[str, Any]],
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
        turn_value = _normalize_weak_spot_turn(raw.get("turn"), turning_point, fatal)
        if label or why:
            return {
                "side": side_value,
                "turn": turn_value,
                "speaker": speaker,
                "label": label,
                "quote_excerpt": _normalize_weak_spot_excerpt(raw.get("quote_excerpt") or raw.get("text") or raw.get("quote") or "", contradiction, fatal, turns, turn_value, speaker, why, label),
                "why_one_sentence": why,
                "how_to_fix": _first_sentence(
                    _default_weak_spot_fix(side_value, label)
                    if coerced
                    else (_clean_text(raw.get("how_to_fix") or "") or _default_weak_spot_fix(side_value, label))
                ),
            }
    turn_value = _normalize_weak_spot_turn(None, turning_point, fatal)
    speaker_value = _default_weak_spot_speaker(winner)
    label_value = _normalize_weak_spot_label(contradiction or _clean_text(summary.get("provisional_judgment") or ""), _default_weak_spot_side(winner))
    why_value = _default_weak_spot_why(_default_weak_spot_side(winner), label_value, contradiction)
    return {
        "side": _default_weak_spot_side(winner),
        "turn": turn_value,
        "speaker": speaker_value,
        "label": label_value,
        "quote_excerpt": _normalize_weak_spot_excerpt("", contradiction, fatal, turns, turn_value, speaker_value, why_value, label_value),
        "why_one_sentence": why_value,
        "how_to_fix": _default_weak_spot_fix(_default_weak_spot_side(winner), label_value),
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
    speaker = _normalize_speaker_code(raw_speaker or "")
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


def _normalize_weak_spot_excerpt(raw_excerpt: str, contradiction: str, fatal: dict[str, Any], turns: list[dict[str, Any]], turn_no: int, speaker: str, why: str, label: str) -> str:
    excerpt = _clean_text(raw_excerpt or "")
    if excerpt:
        matched, _ = _find_matching_transcript_quote(turns, turn_no, speaker if speaker in {"A", "B"} else _clean_text(fatal.get("speaker") or "").upper(), excerpt, why, label, contradiction)
        if matched:
            return _short_quote_excerpt(matched)
        return _short_quote_excerpt(excerpt)
    contradiction_excerpt = _short_quote_excerpt(contradiction)
    matched, _ = _extract_transcript_quote(turns, turn_no, speaker if speaker in {"A", "B"} else _clean_text(fatal.get("speaker") or "").upper() or "A", contradiction, why, label, _clean_text(fatal.get("text") or ""))
    if matched:
        return _short_quote_excerpt(matched)
    if contradiction_excerpt:
        return contradiction_excerpt
    fatal_text = _clean_text(fatal.get("text") or "")
    if fatal_text:
        return _short_quote_excerpt(fatal_text)
    return "ここで一番効いた穴が露出した。"


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
        "未応答": "自説を足す前に、相手の前提への返答を一文で先に済ませるべきだった。",
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
    return mapping.get(label, "一段抽象的な言い換えではなく、相手の前提を崩す具体例か基準を先に置くべきだった。")


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
    if isinstance(text, dict):
        value = _stringify_turning_point(text)
    else:
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
) -> dict[str, Any]:
    contract = _opening_contract_from_turns(turns, cfg)
    if isinstance(meta, dict):
        normalized: dict[str, Any] = {
            "phase": _clean_text(meta.get("phase") or ""),
            "target_issue": _clean_text(meta.get("target_issue") or ""),
            "attacked_weakness": _clean_text(meta.get("attacked_weakness") or ""),
            "new_issue": _clean_text(meta.get("new_issue") or ""),
            "collapse_signal": _clean_text(meta.get("collapse_signal") or ""),
            "finish_intent": _clean_text(meta.get("finish_intent") or ""),
            "end_match": _clean_text(meta.get("end_match") or ""),
        }
        proposition_lock = _proposition_lock_from_turns(turns, cfg)
        if speaker == "A" and not turns:
            normalized["opening_contract"] = _build_opening_contract(cfg, speech)
            normalized["proposition_lock"] = proposition_lock
        elif speaker == "A":
            normalized.update(_detect_opening_contract_drift(speech, contract))
        reframe = _detect_proposition_reframe(speech, proposition_lock)
        normalized.update(reframe)
        if speaker == "B" and turns:
            normalized["reframe_attempt_detected"] = _detect_reframe_attempt(speech, contract) or bool(reframe["reframe_detected"])
        if cfg.turn_count == 3:
            normalized.update(_three_turn_density_debug(speech, len(turns) + 1, latest_opponent))
        return normalized
    mock_meta = _mock_turn_plan(speaker, cfg, turns, len(turns) + 1, latest_opponent, speech)
    proposition_lock = _proposition_lock_from_turns(turns, cfg)
    if speaker == "A" and not turns:
        mock_meta["opening_contract"] = _build_opening_contract(cfg, speech)
        mock_meta["proposition_lock"] = proposition_lock
    elif speaker == "A":
        mock_meta.update(_detect_opening_contract_drift(speech, contract))
    reframe = _detect_proposition_reframe(speech, proposition_lock)
    mock_meta.update(reframe)
    if speaker == "B" and turns:
        mock_meta["reframe_attempt_detected"] = _detect_reframe_attempt(speech, contract) or bool(reframe["reframe_detected"])
    if cfg.turn_count == 3:
        mock_meta.update(_three_turn_density_debug(speech, len(turns) + 1, latest_opponent))
    return mock_meta


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
        },
        turns,
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
    if cfg.turn_count == 3:
        return _three_turn_repair_speech(speaker, cfg, turns, turn_no, latest_opponent)
    return _mock_sequential_turn(speaker, cfg, turns, turn_no, latest_opponent)


def _three_turn_issue_anchor(cfg: DebateConfig, index: int = 0) -> str:
    candidates = _topic_issue_candidates(cfg)
    if candidates:
        idx = min(max(index, 0), len(candidates) - 1)
        return _clean_text(candidates[idx])
    return _clean_text(cfg.topic or "この命題")


def _needs_short_stance_boost(cfg: DebateConfig, speaker: str) -> bool:
    side_text = _clean_text(cfg.side_a if speaker == "A" else cfg.side_b)
    focus_terms = [term for term in _extract_focus_terms(side_text) if len(term) >= 2]
    return len(side_text) <= 16 or len(focus_terms) <= 1


def _short_stance_topic_hook(cfg: DebateConfig) -> tuple[str, str]:
    topic = _clean_text(cfg.topic or "")
    low = topic.lower()
    if "ai" in low or "感情" in topic:
        return (
            "強化学習ロボの報酬変化、自己モデル、主観性、ホームオスタシスの代替可能性",
            "録音された泣き声と、本当に泣いている主体は同じではない",
        )
    if "教育" in topic or "大学" in topic or "オンライン" in topic:
        return (
            "実験実習、臨床、ゼミ、キャンパスの公共財、地方大学街への影響",
            "手術を全部オンラインで済ませるようなものだ",
        )
    if "制服" in topic or "高校" in topic:
        return (
            "ブランド格差、いじめ、通学時の識別、家計負担、快適性",
            "交差点から信号を外すようなものだ",
        )
    return (
        _three_turn_issue_anchor(cfg, 0),
        "土台のない橋を走らせるようなものだ",
    )


def _topic_lane(topic: str) -> str:
    cleaned = _clean_text(topic)
    low = cleaned.lower()
    if any(token in cleaned for token in ["宇宙", "神", "存在", "物理", "進化", "確率", "知性", "生命"]) or "alien" in low:
        return "science"
    if any(token in cleaned for token in ["SaaS", "価格", "成長", "市場", "プロダクト", "事業", "動画サービス", "銀", "金", "長期保有"]):
        return "product"
    if any(token in cleaned for token in ["法律", "倫理", "政策", "制度", "軍縮", "抑止", "教育", "原発", "制服", "導入"]):
        return "social"
    return "general"


def _topic_lane_terms(topic: str, latest_opponent: str = "", own_line: str = "") -> list[str]:
    out: list[str] = []
    for source in [latest_opponent, topic, own_line]:
        for term in _extract_focus_terms(source):
            if len(term) < 2 or term in JP_STOPWORDS or term in out:
                continue
            out.append(term)
            if len(out) >= 4:
                return out
    return out


def _a_turn2_structured_rebuttal(
    own_line: str,
    opponent_focus: str,
    concrete_example: str,
    causal_line: str,
) -> str:
    return _sanitize_fighter_speech(
        f"相手の核は、{opponent_focus}がこの命題を崩すという点だ。"
        f" だが{concrete_example}"
        f" {causal_line}"
        f" だから{own_line}"
    )


def _topic_grounded_short_claim(cfg: DebateConfig, speaker: str) -> str:
    topic = _clean_text(cfg.topic or "").rstrip("？?。")
    own_line = _clean_text(cfg.side_a if speaker == "A" else cfg.side_b)
    yes_like = own_line in {"はい", "賛成", "導入すべき", "維持すべき", "必要だ"}
    no_like = own_line in {"いいえ", "反対", "導入すべきではない", "維持すべきではない", "不要だ"}
    if "存在する" in topic and own_line in {"いない", "存在しない"}:
        return f"{topic.replace('存在する', '存在しない')}。"
    if "存在する" in topic and own_line in {"いる", "存在する"}:
        return f"{topic}。"
    if "終わりか" in topic:
        subject = topic.split("は", 1)[0].strip()
        if subject and own_line in {"終わりつつある", "終わっていない", "終わりではない"}:
            return f"{subject}は{own_line}。"
    if not topic:
        return f"{own_line}。"
    if yes_like:
        return f"{topic}。"
    if no_like:
        if topic.endswith("か"):
            return f"{topic[:-1]}とは言えない。"
        return f"{topic}とは言えない。"
    if topic.endswith("か"):
        if 2 <= len(own_line) <= 24 and not any(mark in own_line for mark in "。！？?!"):
            return f"{own_line}。"
        if any(token in own_line for token in ["ない", "ではない", "いない", "不要"]):
            return f"{topic[:-1]}とは言えない。"
        return f"{topic[:-1]}。"
    if "は" in topic and len(own_line) <= 16:
        subject = topic.split("は", 1)[0].strip()
        if subject:
            return f"{subject}は{own_line}。"
    return f"{own_line}。"


def _short_stance_opening_surface(
    cfg: DebateConfig,
    speaker: str,
    own_line: str,
    topic: str,
    short_hook: str,
    concrete: str,
) -> str:
    proposition = _topic_grounded_short_claim(cfg, speaker)
    lane = _topic_lane(topic)
    lane_terms = _topic_lane_terms(topic, own_line=own_line)
    if lane == "science":
        primary_term = lane_terms[0] if lane_terms else "観測証拠"
        secondary_term = lane_terms[1] if len(lane_terms) > 1 else "探索範囲"
        support_reason = f"{primary_term}がまだ決定打になっておらず、{secondary_term}にも空白が残るからだ。"
        attack_preempt = "相手は可能性や観測空白だけで押してくるだろうが、それだけでは一般命題は立たない。"
    elif lane == "product":
        primary_term = lane_terms[0] if lane_terms else "市場の継続需要"
        secondary_term = lane_terms[1] if len(lane_terms) > 1 else "切替コスト"
        support_reason = f"{primary_term}と{secondary_term}が、その結論を左右する現実条件だからだ。"
        attack_preempt = "相手は一時的な追い風や悲観だけを強調するだろうが、採用条件まで見ないと結論は決まらない。"
    elif lane == "social":
        primary_term = lane_terms[0] if lane_terms else "制度運用"
        secondary_term = lane_terms[1] if len(lane_terms) > 1 else "実装条件"
        support_reason = f"{primary_term}と{secondary_term}を現場で回せるかが、そのまま命題の成否を決めるからだ。"
        attack_preempt = "相手は理念や単発の例外から崩そうとするだろうが、制度全体の運用条件を越える反証にはなりにくい。"
    else:
        primary_term = lane_terms[0] if lane_terms else "現実条件"
        secondary_term = lane_terms[1] if len(lane_terms) > 1 else "採用条件"
        support_reason = f"{primary_term}と{secondary_term}が、この立場の採用条件を左右するからだ。"
        attack_preempt = "相手は抽象論だけで押すだろうが、現実条件がつながらない限り結論は動かない。"
    if speaker == "A":
        return _sanitize_fighter_speech(
            f"{proposition}"
            f" 理由は、{support_reason}"
            f" 例えば{concrete}"
            f" こうした具体が残るなら、生産性や観測や制度運用の条件がまだつながっており、こちらの結論は崩れない。"
            f" {attack_preempt}"
        )
    return _sanitize_fighter_speech(
        f"{proposition}"
        f" 理由は、{support_reason}"
        f" 例えば{concrete}"
        f" その具体から需要や実装や観測の条件まで因果が伸びるなら、相手の結論だけを先に確定することはできない。"
        f" {attack_preempt}"
    )


def _education_limited_rebuttal(cfg: DebateConfig, own_line: str) -> str:
    return _sanitize_fighter_speech(
        "相手の核は、生成AIを常時置けば個別最適化と反復学習が進むという点だ。"
        " だが初等教育では、宿題の自力判定、学習ログの信頼、教師の評価負荷、クラス運用の乱れがすぐ壁になる。"
        " 例えば作文や計算ドリルを常時AIに寄せると、家庭差で使い方が割れ、提出物の真正性確認まで教師が背負う。"
        f" その現場負担を越えられない限り、{own_line}"
    )


def _three_turn_grounded_surface(
    speaker: str,
    cfg: DebateConfig,
    turn_no: int,
    latest_opponent: str = "",
) -> str:
    proposition_lock = _build_proposition_lock(cfg)
    own_line = _three_turn_resolution_line(cfg.side_a if speaker == "A" else cfg.side_b, speaker, proposition_lock)
    own_line = _clean_text(own_line)
    contract = _build_opening_contract(cfg, cfg.side_a if speaker == "A" else cfg.side_b)
    issue_primary = _three_turn_issue_anchor(cfg, 0)
    issue_secondary = _three_turn_issue_anchor(cfg, 1)
    concrete = _three_turn_concrete_support(speaker, proposition_lock, min(turn_no, 2 if turn_no == 2 else 1 if turn_no == 1 else 2))
    opponent_focus = _select_focus_term(latest_opponent, [issue_primary, issue_secondary]) if latest_opponent else issue_primary
    topic = _clean_text(cfg.topic or "")
    lane = _topic_lane(topic)
    lane_terms = _topic_lane_terms(topic, latest_opponent, own_line)
    lane_term_a = lane_terms[0] if lane_terms else issue_primary
    lane_term_b = lane_terms[1] if len(lane_terms) > 1 else issue_secondary
    short_stance = _needs_short_stance_boost(cfg, speaker)
    short_hook, short_metaphor = _short_stance_topic_hook(cfg)
    if turn_no == 1:
        if speaker == "A":
            if "原発" in topic or "電力" in topic or "再エネ" in topic:
                return _sanitize_fighter_speech(
                    "私は原発維持を支持する。"
                    " 原発は短期の安定供給と低炭素の基幹電源としてまだ価値があり、LNG輸入増と電力価格高騰だけで穴埋めする方が家計と産業の負担は重い。"
                    " さらに安全規制、廃炉積立、賠償枠、最終処分の計画を現実に積み上げれば、維持の根拠はまだ残る。"
                    " 灯りを消す前に、代わりの発電所と金庫を先に用意できるなら維持の理由は残る。"
                    f" だから{own_line}"
                )
            if short_stance:
                return _short_stance_opening_surface(cfg, speaker, own_line, topic, short_hook, concrete)
            return _sanitize_fighter_speech(
                f"私は{own_line}。{concrete} {issue_primary}を見ても、この立場を崩す材料はまだ足りない。だから{own_line}"
            )
        if short_stance:
            return _short_stance_opening_surface(cfg, speaker, own_line, topic, short_hook, concrete)
        return _sanitize_fighter_speech(
            f"私は{own_line}。{concrete} この命題を通すにはまだ足りないものがある。"
        )
    if turn_no == 2:
        if speaker == "A":
            if lane == "science":
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{lane_term_a}や{lane_term_b}の観測は局所的な器用さや適応を示しても、火や金属加工や共同作業まで連続して立証していない。",
                    "だからその具体例から一般命題までは伸びず、こちらの立場は崩れない。",
                )
            if lane == "social":
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{lane_term_a}や{lane_term_b}の現場を見ても、制度や運用を左右する具体条件はまだ詰め切れていない。",
                    "だから単発の懸念や例外から全体の制度判断までは飛べず、こちらの主張の方が残る。",
                )
            if lane == "product":
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{lane_term_a}や{lane_term_b}の具体例は一部の機能や運用を示すだけで、採用条件そのものを固定した証拠にはなっていない。",
                    "だから相手の具体例から市場全体の結論へは伸びず、こちらの命題の方が残る。",
                )
            if short_stance:
                return _a_turn2_structured_rebuttal(
                    own_line,
                    opponent_focus,
                    f"{short_hook}まで具体に置くと、相手は一番重い現実条件を崩せていない。",
                    "だからその押し方だけでは命題は倒れず、こちらの立場を維持できる。",
                )
            return _a_turn2_structured_rebuttal(
                own_line,
                opponent_focus,
                _three_turn_concrete_support("A", proposition_lock, 2),
                "だからその具体例だけでは命題は倒れず、こちらの主張を押し返せる。",
            )
        if ("教育" in topic or "初等教育" in topic) and "生成" in topic:
            return _education_limited_rebuttal(cfg, own_line)
        if "原発" in topic or "電力" in topic or "再エネ" in topic:
            return _sanitize_fighter_speech(
                "あなたは実行条件を整えれば維持できると言う。だがその前提は崩れている。"
                " 福島第一の廃炉・賠償は長期の公的負担を残し、六ヶ所再処理や最終処分場もなお未決のままだ。"
                " 事故・廃炉・核廃棄物のコストを最後に誰が引き受けるのかが閉じない限り、便益だけを理由に維持は選べない。"
                " 壊れかけの橋に保険をかけても橋そのものは直らない。"
                f" だから{own_line}"
            )
        if "saas" in topic.lower():
            return _sanitize_fighter_speech(
                "相手の核は、垂直統合とAIでSaaSは再成長できるという点だ。"
                " だがVeevaやProcoreのような勝ち筋は、vertical SaaSの深い業界運用、長い導入期間、重い切替コストに支えられた例外であって、汎用SaaS全体の再成長をそのまま保証しない。"
                " CACは上がり、PLGだけで伸びる領域は狭まり、APIやデータ独自性もSalesforceやServiceNow、クラウド基盤に吸収されれば価格競争へ戻る。"
                f" だから局所的な成功例から市場全体の命題は立たず、{own_line}"
            )
        if short_stance:
            return _sanitize_fighter_speech(
                f"相手の核は{issue_primary}だ。"
                f" だが{_three_turn_concrete_support('B', proposition_lock, 2)}"
                f" {short_hook}だけではまだ命題は立たない。"
                f" {short_metaphor}。"
                f" そこを越えられない限り、{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手の核は「{opponent_focus}」だ。"
            f" だが{_three_turn_concrete_support('B', proposition_lock, 2)}"
            f" そこが抜けたままでは、{own_line}"
        )
    if speaker == "A":
        if "原発" in topic or "電力" in topic or "再エネ" in topic:
            return _sanitize_fighter_speech(
                "最後に残るのは、事故・廃炉・燃料コストを誰が負担するかを制度で閉じられるかという一点だ。"
                " 相手は負担の存在を言うが、火力依存による電気代高騰、LNG輸入増、CO2の積み増しという別の負担を軽く見ている。"
                " 独立積立、保険プール、発電事業者の厳格負担、送電と代替電源の併設まで含めて条件を法制化できるなら、維持は単なる先送りではない。"
                " 壊れかけた橋なら渡るのをやめるか、補強して通すかの違いであって、村の灯りごと消す話ではない。"
                " 金庫を先に作れるなら、原発維持はまだ合理的だ。"
                f" だから{own_line}"
            )
        if short_stance:
            return _sanitize_fighter_speech(
                f"最後に残るのは{issue_secondary}だ。"
                f" {short_hook}まで並べても相手は決め手を作れていない。"
                f" {short_metaphor}。"
                f" だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"最後に残るのは「{issue_secondary}」だ。{_three_turn_concrete_support('A', proposition_lock, 2)} だから{own_line}"
        )
    if "原発" in topic or "電力" in topic or "再エネ" in topic:
        return _sanitize_fighter_speech(
            "最後まで消えないのは、原発の事故・廃炉・核廃棄物の負担を未来に誰が引き受けるのかという一点だ。"
            " 福島の後始末、最終処分場の未決着、老朽炉の延命コストを見れば、相手は便益を語っても負担の出口を示せていない。"
            " 再エネ・蓄電・送電強化の組み合わせと比べてなお維持が必要だと立証できない限り、原発維持は未来への賭けを続ける話になる。"
            " バケツを増やしても穴の空いたダムは止まらない。"
            f" だから{own_line}"
        )
    if lane == "science":
        return _sanitize_fighter_speech(
            f"相手の核は、{opponent_focus}を積めば{topic or 'この命題'}が立つという点だ。"
            f" しかし{lane_term_a}や{lane_term_b}の観測だけでは、進化経路や物理制約を越えてその一般化は成立しない。"
            f" だから論題としての断定はまだできず、{own_line}"
        )
    if lane == "product":
        return _sanitize_fighter_speech(
            f"相手の核は、{opponent_focus}が残るから{topic or 'この命題'}は立つという点だ。"
            f" しかし{lane_term_a}や{lane_term_b}の具体例は一部の機能や局面を示すだけで、運用統合や採用条件の穴までは埋めていない。"
            f" だから命題全体の優位は固定できず、{own_line}"
        )
    if short_stance:
        return _sanitize_fighter_speech(
            f"最後まで消えないのは{issue_secondary}の負担だ。"
            f" {short_hook}を現実に並べると、相手の立場はまだ足りない。"
            f" {short_metaphor}。"
            f" だから{own_line}"
        )
    return _sanitize_fighter_speech(
        f"最後まで消えないのは「{issue_secondary}」の負担だ。{_three_turn_concrete_support('B', proposition_lock, 2)} だから{own_line}"
    )


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


def _opponent_last_statement(speaker: str, turns: list[dict[str, Any]]) -> str:
    if not turns:
        return "(none yet)"
    last_turn = turns[-1]
    if speaker == "A":
        return last_turn.get("b") or "(none yet)"
    return last_turn.get("a") or "(none yet)"


# FREEZE: legacy mock-only surface. Keep isolated from live prompt assembly and do not
# reintroduce its generic scaffold into _speaker_prompt or live 3-turn text generation.
def _mock_opening_surface(
    speaker: str,
    own_line: str,
    contract: dict[str, str],
    plan: dict[str, str],
    target_detail: str,
    new_issue_detail: str,
    proposition_lock: dict[str, Any],
) -> str:
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    topic = _clean_text(proposition_lock.get("claim_subject") or "")
    if speaker == "A":
        if lock_type == "love_itself_not_conditions":
            options = [
                f"金で動かせるのは会う機会や暮らしの余裕までで、気持ちそのものじゃない。だから{own_line}",
                f"この話で見たいのは関係の周辺条件じゃなく、愛情そのものが買えるかどうかだ。{own_line}",
                f"{own_line}。金で整うのは舞台までで、肝心の気持ちは札束で命令できない。",
            ]
            guard = "環境の話だけで押し切るなら、別の問いに滑ってしまう。"
        elif lock_type == "general_rule_not_edge_exception":
            options = [
                f"極端な場面を先に積むより、まず一般に許せる行為かで見たい。{own_line}",
                f"{own_line}。例外の話より先に、ふつうの社会で通していい原則かどうかを見たい。",
                f"まず問われるのは『追い詰められた時もある』ではなく、原則として許せるかだ。{own_line}",
            ]
            guard = "極限例だけで全体のルールを塗り替えるのは飛びすぎる。"
        elif lock_type == "labeled_set_not_posthoc_relabel":
            options = [
                f"見たいのは、後から名前を付け替える話じゃない。陰謀論扱いされたものの中に本当に当たりがあったかで、答えは{own_line}",
                f"{own_line}。あとから『それは陰謀論じゃなかった』と整理し直す前に、当時どう扱われていたかをそのまま見たい。",
                f"ここで争いたいのは、今の呼び名じゃなく当時陰謀論とされた集合だ。だから{own_line}",
            ]
            guard = "証明後に別ラベルへ逃がすなら、最初の問いが消える。"
        elif lock_type == "direct_harm_not_market_conditions":
            options = [
                f"周辺事情を足す前に、まず体そのものに何が起きるかで比べたい。{own_line}",
                f"{own_line}。流行り方や市場の話より先に、吸った時の害そのもので見た方が筋が通る。",
                f"ここで見たいのは売れ方じゃなく、体に入った時のダメージだ。だから{own_line}",
            ]
            guard = "周辺条件ばかり積むと、比べる対象そのものがぼやける。"
        elif lock_type == "existence_not_explanatory_label":
            options = [
                f"分からない場所に名前を置くことと、本当に存在することは同じじゃない。だから{own_line}",
                f"{own_line}。説明がつきそうだという感触だけで、実在まで飛ぶのは早い。",
                f"ここで見たいのは説明の便利さじゃなく、存在すると言えるだけの根拠があるかどうかだ。{own_line}",
            ]
            guard = "説明の穴埋めをそのまま実在の証明にすると、話が先走る。"
        else:
            options = [
                f"話を広げる前に、いま問われている{topic or '争点'}そのものを見るなら{own_line}",
                f"{own_line}。周辺条件をいくつも積む前に、まず命題そのものが立つかで見たい。",
                f"ここで先に押さえたいのは補助線じゃなく本体だ。だから{own_line}",
            ]
            guard = "周辺条件ばかり膨らませると、肝心の問いが見えなくなる。"
        opening = options[(len(own_line) + len(topic)) % len(options)]
        return f"{opening} {guard}"
    if lock_type == "love_itself_not_conditions":
        options = [
            f"{own_line}。気持ちだけを真空パックみたいに切り出すより、関係を成立させる条件ごと見た方が現実に近い。",
            f"先に言うと{own_line}。会う時間も安心も継続も全部コストに支えられるなら、条件と本体を完全には切れない。",
            f"{own_line}。愛情だけ聖域みたいに扱っても、実際には関係を保つ土台がなければ続かない。",
        ]
    elif lock_type == "general_rule_not_edge_exception":
        options = [
            f"{own_line}。原則だけで切ると、法も救済も届かない場面を説明できない。",
            f"先に言っておくと{own_line}。規範は平時だけで試されるわけじゃなく、壊れた状況でどこまで持つかも問われる。",
            f"{own_line}。一般論だけきれいに守っても、現実の破局に答えられなければ立場としては弱い。",
        ]
    elif lock_type == "labeled_set_not_posthoc_relabel":
        options = [
            f"{own_line}。後から当たった一件を拾っても、陰謀論というラベル全体の信頼までは救えない。",
            f"先に言うと{own_line}。たまに当たった例があっても、それで陰謀論一般の精度まで正当化はできない。",
            f"{own_line}。事後に当たった話と、ふだん陰謀論が当てるかどうかは別に見ないと危ない。",
        ]
    elif lock_type == "direct_harm_not_market_conditions":
        options = [
            f"{own_line}。いま分かっている害だけで安心するのは早く、未知の長期リスクまで含めて見る必要がある。",
            f"先に言えば{own_line}。既知の毒性だけで比べると、まだ積み上がっていない長期被害を見落とす。",
            f"{own_line}。『今は軽く見える』だけで済ませると、時間がたってからしか分からない危険を拾えない。",
        ]
    elif lock_type == "existence_not_explanatory_label":
        options = [
            f"{own_line}。世界の説明が欲しいことと、そこに本当に神がいることは別に見ないといけない。",
            f"先に言うと{own_line}。説明しにくい部分へ名前を置いても、そのまま実在の裏付けにはならない。",
            f"{own_line}。説明力があるように見えることと、存在が確かめられることは同じじゃない。",
        ]
    else:
        options = [
            f"{own_line}。一つの見えやすい点だけで切ると、肝心の条件が抜け落ちる。",
            f"先に言えば{own_line}。表面だけで早く決めるより、何が本当に立場を支えるかまで見たい。",
            f"{own_line}。見えやすい材料だけでなく、土台になっている条件まで数えたい。",
        ]
    return options[(len(own_line) + len(plan.get("target_issue") or "")) % len(options)]


def _three_turn_concrete_support(
    speaker: str,
    proposition_lock: dict[str, Any],
    turn_no: int,
) -> str:
    focus_terms = [
        term
        for term in _extract_focus_terms(
            _clean_text(proposition_lock.get("claim_subject") or "")
            or _clean_text(proposition_lock.get("claim_predicate") or "")
        )
        if len(term) >= 2
    ][:2]
    focus = "と".join(focus_terms) if len(focus_terms) >= 2 else (focus_terms[0] if focus_terms else "この命題")
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    if lock_type == "love_itself_not_conditions":
        if turn_no == 1:
            return "高価な贈り物や快適な暮らしは好意のきっかけにはなっても、相手の自発的な愛着そのものを命令する力までは持たない。"
        if speaker == "A":
            return "住環境や時間の余裕を整えられても、そこから先の選好や献身まで自動で発生するわけではない。"
        return "会う時間、安心、継続的な接触が揃わなければ感情は育ちにくく、その土台は現実には金で大きく左右される。"
    if lock_type == "general_rule_not_edge_exception":
        if turn_no == 1:
            return "私的報復を認めれば、どこまでが報復でどこからが過剰かの線引きが当事者の怒りに委ねられやすい。"
        if speaker == "A":
            return "怒りが理解できることと、報復を制度の外で許可することは別で、その境界を崩すと暴力の連鎖が止まりにくい。"
        return "虐殺や国家崩壊のように制度が実質機能しない場面では、一般原則だけでは救済の空白を説明しきれない。"
    if lock_type == "labeled_set_not_posthoc_relabel":
        if turn_no == 1:
            return "ウォーターゲートやMKウルトラのように、当初は荒唐無稽と退けられながら後から事実だと分かった事例が実際にある。"
        if speaker == "A":
            return "当時は陰謀論として扱われていたのに後で裏付けが出た例がある以上、ラベルだけで最初から全部を虚偽と処理はできない。"
        return "一部に当たりがあっても、陰謀論の大半が再現不能な推測であることまで正当化はできない。"
    if lock_type == "direct_harm_not_market_conditions":
        if turn_no == 1:
            return "紙タバコは燃焼でタールや一酸化炭素を直接取り込み、肺がんや心血管疾患の長期データが厚い。"
        if speaker == "A":
            return "未知のリスクがあるとしても、既知の重い長期被害が積み上がっている紙タバコの不利までは消えない。"
        return "電子タバコは香料エアロゾルや金属粒子の長期吸入データがまだ薄く、見えていない被害を軽く見積もれない。"
    if lock_type == "knowledge_not_formal_approval":
        if turn_no == 1:
            return "営業の継続年数、景品交換所の配置、取り締まり実務の安定を見れば、現場が存在自体を知らないとは考えにくい。"
        if speaker == "A":
            return "形式上は別法人でも、同じ地域で長期に同じ換金動線が維持されるなら、運用を把握していないと説明しにくい。"
        return "知っていることと公認していることは別で、違法性を正面から認めないために制度上の距離を残している可能性がある。"
    if lock_type == "product_sprawl_not_core_advantage":
        if turn_no == 1:
            return "SORAの撤退報道が示すのは、生成モデルの強さだけでは動画サービスの運営を支えきれず、配信インフラ・権利処理・継続投資まで抱える事業は別の勝負だという点だ。"
        if speaker == "A":
            return "動画サービスはモデル開発よりも、権利処理、配信基盤、作品供給、収益化の設計が重く、GPTの優位だけで差別化しにくい。"
        return "SORA級の生成技術を持つなら、動画編集支援や制作ツールまで含めた新しい体験で差別化でき、撤退報道だけで戦略失敗とは決め切れない。"
    if lock_type == "dignity_not_compensation_proxy":
        if turn_no == 1:
            return "保険金、損害賠償、交通安全のVSL、医療資源配分のように、現実の制度はすでに人命に関わる判断を金額や費用対効果で扱っている。"
        if speaker == "A":
            return "数字を置くこと自体が尊厳の否定なのではなく、低所得や障害をそのまま価値の低さへ結びつける補償設計こそ問題だ。"
        return "年収や逸失利益で補償額が変わる実務では、金額換算がそのまま『どの命を軽く扱うか』へ滑りやすく、トリアージや保険の現場で弱者不利を招きやすい。"
    if lock_type == "existence_not_explanatory_label":
        if turn_no == 1:
            return "宇宙の秩序や意識の起源に説明力があるとしても、その説明がそのまま存在証明に変わるわけではない。"
        if speaker == "A":
            return "自然主義だけで意識や価値の根を説明し切れないなら、神仮説には少なくとも競合上の強みが残る。"
        return "説明が欲しい場所に便利な仮説を置くことと、実在を確かめることは同じ手続きではない。"
    if turn_no == 1:
        return f"{focus}で何が良くなり、何が重くなるのかを代替策まで含めて比べないと、この命題の強さは見えない。"
    if speaker == "A":
        return f"{focus}の便益が本当に残るかという点では、相手はまだこちらの採用条件を崩していない。"
    return f"{focus}の副作用と失敗時の負担という点では、相手はまだ採用条件を閉じ切れていない。"


def _three_turn_resolution_line(
    raw: str,
    speaker: str,
    proposition_lock: dict[str, Any],
) -> str:
    raw = _clean_text(raw)
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    if lock_type == "product_sprawl_not_core_advantage":
        if speaker == "A":
            return "GPTは動画サービスに手を出すべきではなかった。"
        return "撤退報道だけでGPTの動画サービス参入判断を誤りとまでは言えない。"
    if lock_type == "dignity_not_compensation_proxy":
        if speaker == "A":
            return "人の命に値段をつけることは、制度運用の範囲でなら許される。"
        return "人の命に値段をつけることは、尊厳の序列化につながる以上許されない。"
    if lock_type == "love_itself_not_conditions":
        if speaker == "A":
            return "愛は金では買えない。"
        return "愛は条件まで含めれば金で買える。"
    if lock_type == "knowledge_not_formal_approval":
        if speaker == "A":
            return "警察はパチンコの換金の実態を知っている。"
        return "警察が換金の実態を知っているとまでは言えない。"
    if lock_type == "general_rule_not_edge_exception":
        if speaker == "A":
            return "復讐は原則として許されない。"
        return "復讐が許される場面は残る。"
    if lock_type == "labeled_set_not_posthoc_relabel":
        if speaker == "A":
            return "陰謀論の中に真実が含まれることはある。"
        return "陰謀論の中に真実があるとしても、それで全体は正当化されない。"
    if lock_type == "direct_harm_not_market_conditions":
        if speaker == "A":
            return "体に悪いのは紙タバコの方だ。"
        return "全体として体に悪いのは電子タバコの方だと見る余地がある。"
    if lock_type == "existence_not_explanatory_label":
        if speaker == "A":
            return "神は存在すると見る根拠がまだ残る。"
        return "神の存在はなお立証されていない。"
    basis = _compact_basis(raw)
    if basis:
        if re.search(r"[。！？!?]$", basis):
            return basis
        return f"{basis}。"
    return "以上から、この立場が残る。"


def _final_sentence(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?])", _clean_text(text)) if part.strip()]
    return parts[-1] if parts else _clean_text(text)


def _first_sentence(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?])", _clean_text(text)) if part.strip()]
    return parts[0] if parts else _clean_text(text)


def _has_long_overlap(a: str, b: str, min_len: int = 20) -> bool:
    a = _clean_text(a)
    b = _clean_text(b)
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    for size in range(min_len, len(shorter) + 1):
        for idx in range(0, len(shorter) - size + 1):
            if shorter[idx : idx + size] in longer:
                return True
    return False


def _has_opponent_reference_in_first_sentence(speech: str, latest_opponent: str) -> bool:
    first = _first_sentence(speech)
    if any(token in first for token in ["相手", "君", "あなた", "その話", "その立て方"]):
        return True
    opponent_terms = [term for term in _extract_focus_terms(latest_opponent)[:8] if len(term) >= 2]
    return any(term in first for term in opponent_terms)


# FREEZE: legacy pre-restore scaffold kept only as historical reference during local
# cleanup. Current live path must stay on _three_turn_grounded_surface instead.
def _three_turn_opening_surface(
    speaker: str,
    own_line: str,
    proposition_lock: dict[str, Any],
) -> str:
    own_line = _three_turn_resolution_line(own_line, speaker, proposition_lock)
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    if speaker == "A":
        if lock_type == "knowledge_not_formal_approval":
            return _sanitize_fighter_speech(
                f"問いたいのは公認かどうかじゃなく、現場がその仕組みの存在を把握しているかどうかだ。{_three_turn_concrete_support('A', proposition_lock, 1)} その把握を前提にしないと、全国で同じ換金動線が長年維持された理由を説明できない。だから{own_line}"
            )
        if lock_type == "product_sprawl_not_core_advantage":
            return _sanitize_fighter_speech(
                f"SORAの撤退報道が本当なら、GPTが動画サービスに踏み込む判断は筋が悪かった。{_three_turn_concrete_support('A', proposition_lock, 1)} 動画事業はモデルの派手さより、配信インフラ、権利処理、作品供給、運営コストを回し続けられるかで決まる。OpenAIの強みは生成モデルと開発者基盤にあり、そこから離れて総合動画サービスまで抱えると投資が分散しやすい。撤退が示すのは一時の失敗ではなく、事業の重さと戦略のずれだ。だから{own_line}"
            )
        if lock_type == "dignity_not_compensation_proxy":
            return _sanitize_fighter_speech(
                f"命に値段をつけることが直ちに人命軽視になるわけではない。{_three_turn_concrete_support('A', proposition_lock, 1)} 保険、損害賠償、事故防止、公共政策では、値付けを拒めば医療資源や安全規制をどう配るか決められない。問題は価格化そのものより、低所得者や障害者を安く扱う補償設計を放置することだ。そこを分けて管理できるなら、尊厳と実務は両立する。だから{own_line}"
            )
        if lock_type == "love_itself_not_conditions":
            return _sanitize_fighter_speech(
                f"金で整えられるのは会う機会や暮らしの余裕までで、愛情そのものじゃない。{_three_turn_concrete_support('A', proposition_lock, 1)} そこで相手の自発的な選好まで動かせると示せない限り、『買える』までは届かない。だから{own_line}"
            )
        if lock_type == "general_rule_not_edge_exception":
            return _sanitize_fighter_speech(
                f"ここで見たいのは極端な一場面より、原則として許せる行為かどうかだ。{_three_turn_concrete_support('A', proposition_lock, 1)} 例外を出すだけで原則が崩れるわけではなく、一般に認める理由まで示せないと立場は残らない。だから{own_line}"
            )
        if lock_type == "labeled_set_not_posthoc_relabel":
            return _sanitize_fighter_speech(
                f"後から名前を付け替える前に、陰謀論扱いされたものの中に事実があったかで見たい。{_three_turn_concrete_support('A', proposition_lock, 1)} 当時のラベルのまま検証しても真実が混じると示せるなら、この命題は立つ。だから{own_line}"
            )
        if lock_type == "direct_harm_not_market_conditions":
            return _sanitize_fighter_speech(
                f"比べたいのは市場やイメージじゃなく、体そのものに起きる害だ。{_three_turn_concrete_support('A', proposition_lock, 1)} 未知の不安を足しても、既知の長期被害を上回る材料が出ない限り紙タバコの重さは残る。だから{own_line}"
            )
        if lock_type == "existence_not_explanatory_label":
            return _sanitize_fighter_speech(
                f"問いたいのは説明の便利さじゃなく、本当に存在すると言えるだけの根拠があるかどうかだ。{_three_turn_concrete_support('A', proposition_lock, 1)} 自然主義の説明だけで不足が残るなら、神仮説の優位はまだ消えない。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"見たいのは補助線ではなく命題そのものだ。{_three_turn_concrete_support('A', proposition_lock, 1)} その核を崩す具体材料が出ない限り、この立場は残る。だから{own_line}"
        )
    if lock_type == "knowledge_not_formal_approval":
        return _sanitize_fighter_speech(
            f"知っていることをそのまま公認と同じにすると話が飛ぶ。{_three_turn_concrete_support('B', proposition_lock, 1)} だから{own_line}"
        )
    if lock_type == "product_sprawl_not_core_advantage":
        return _sanitize_fighter_speech(
            f"SORAの撤退報道が出ても、それだけでGPTが動画サービスに手を出すべきでなかったとはまだ言えない。{_three_turn_concrete_support('B', proposition_lock, 1)} 動画生成モデルを持つ企業が制作支援から配信まで試すのは自然な拡張で、撤退が事実でも戦略全体ではなく実行形態の問題かもしれない。GPTの基盤と生成技術を動画体験へ伸ばす余地まで否定するには、まだ材料が足りない。だから{own_line}"
        )
    if lock_type == "dignity_not_compensation_proxy":
        return _sanitize_fighter_speech(
            f"補償や政策で数字を使うことと、人の命に値札を貼ってよいことは同じじゃない。{_three_turn_concrete_support('B', proposition_lock, 1)} 保険や医療資源の配分で一度価格を置けば、その数字は『誰を先に救うか』『誰の命を安く見るか』という序列へ変わりやすい。そこを止める制度を示せないなら、価格化は人命の尊厳を削る方向へ流れる。だから{own_line}"
        )
    if lock_type == "love_itself_not_conditions":
        return _sanitize_fighter_speech(
            f"愛情だけを切り離すと現実の関係が消える。{_three_turn_concrete_support('B', proposition_lock, 1)} だから{own_line}"
        )
    if lock_type == "general_rule_not_edge_exception":
        return _sanitize_fighter_speech(
            f"一般論だけで切ると、制度が壊れた場面を説明しきれない。{_three_turn_concrete_support('B', proposition_lock, 1)} だから{own_line}"
        )
    if lock_type == "labeled_set_not_posthoc_relabel":
        return _sanitize_fighter_speech(
            f"一部の当たりを見つけても、それで陰謀論一般の信頼までは回復しない。{_three_turn_concrete_support('B', proposition_lock, 1)} だから{own_line}"
        )
    if lock_type == "direct_harm_not_market_conditions":
        return _sanitize_fighter_speech(
            f"今見えている害だけで決めるのは早い。{_three_turn_concrete_support('B', proposition_lock, 1)} しかも未知の長期被害は後からしか見えない以上、現在のデータだけで軽いと断定はできない。だから{own_line}"
        )
    if lock_type == "existence_not_explanatory_label":
        return _sanitize_fighter_speech(
            f"説明したい気持ちと存在証明は別だ。{_three_turn_concrete_support('B', proposition_lock, 1)} だから{own_line}"
        )
    return _sanitize_fighter_speech(
        f"見えやすい一点だけで決めると条件が抜け落ちる。{_three_turn_concrete_support('B', proposition_lock, 1)} だから{own_line}"
    )


# FREEZE: legacy pre-restore scaffold kept only as historical reference during local
# cleanup. Current live path must stay on _three_turn_grounded_surface instead.
def _three_turn_rebuttal_surface(
    speaker: str,
    own_line: str,
    proposition_lock: dict[str, Any],
) -> str:
    own_line = _three_turn_resolution_line(own_line, speaker, proposition_lock)
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    focus_issue = _topic_issue_candidates(DebateConfig(
        topic=_clean_text(proposition_lock.get("claim_subject") or proposition_lock.get("claim_predicate") or ""),
        side_a=own_line if speaker == "A" else "",
        side_b=own_line if speaker == "B" else "",
        turn_count=3,
        mode="casual",
        fighter_a_provider="openai",
        fighter_b_provider="openai",
        openai_key="",
        anthropic_key="",
        gemini_key="",
        disable_live_judge=True,
        artifact_dir="",
    ))[0]
    if lock_type == "product_sprawl_not_core_advantage":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"相手は『SORAの撤退だけで参入失敗とは言えない』『実行形態の問題かもしれない』と言うが、そこでは動画サービスの重さを軽く見積もっている。{_three_turn_concrete_support('A', proposition_lock, 2)} 動画はモデル性能だけで勝てる市場ではなく、配信インフラ、権利処理、作品供給、継続課金まで一体で回せないと収益にならない。撤退報道を単発の試行錯誤に矮小化しても、OpenAIが本来強い開発者基盤から離れて総合運営まで抱える無理は消えない。以上から、撤退は戦略判断のずれを示しており、GPTは動画サービスに手を出すべきではなかった。"
            )
        return _sanitize_fighter_speech(
            f"相手は『配信インフラや権利処理が重いから参入判断そのものが誤りだ』と言うが、それは難しさの列挙であって撤退の意味を狭く読みすぎている。{_three_turn_concrete_support('B', proposition_lock, 2)} 動画サービスは最初から完成形で勝負するだけではなく、制作支援、編集、配信補助のどこから入るかで戦略が変わる。SORAの撤退報道が事実でも、それだけでGPT全体の動画展開を否定するのは飛躍で、相手は失敗の範囲を必要以上に広げている。以上から、撤退報道だけでGPTの動画サービス参入判断を誤りとまでは言えない。"
        )
    if lock_type == "dignity_not_compensation_proxy":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"相手は値段を置いた瞬間に序列化が始まると言うが、そこで混ざっているのは価格化そのものと補償設計の欠陥だ。{_three_turn_concrete_support('A', proposition_lock, 2)} 交通事故の賠償や保険金が収入連動で歪むなら直すべきは基準であって、事故防止や救命の費用対効果まで捨てる理由にはならない。医療資源や安全規制の配分には比較が必要で、価格化を全面否定すると別の形の恣意的な切り捨てが残る。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手は設計を直せばいいと言うが、その答えでは足りない。{_three_turn_concrete_support('B', proposition_lock, 2)} 現実の保険、損害賠償、トリアージでは、金額や効率を前に出した瞬間に高収入者や回復可能性の高い人が優先されやすい。価格化を許したまま『ここから先は尊厳に触れない』という線を、相手は医療資源配分や公共政策の現場で示せていない。だから{own_line}"
        )
    if lock_type == "love_itself_not_conditions":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"相手が押しているのは関係を回す条件であって、愛を買えるかという本題ではない。{_three_turn_concrete_support('A', proposition_lock, 2)} それでも残るのは{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手は気持ちだけを切り出すが、現実の愛は条件なしでは続かない。{_three_turn_concrete_support('B', proposition_lock, 2)} だから{own_line}"
        )
    if lock_type == "knowledge_not_formal_approval":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"相手は公認かどうかへ論点をずらすが、ここで問われているのは知っているかどうかだ。{_three_turn_concrete_support('A', proposition_lock, 2)} それでも残るのは{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手は周知性から直ちに認識まで飛ぶが、形式上の距離を保つ運用なら知っていても認めない構造はありうる。{_three_turn_concrete_support('B', proposition_lock, 2)} だから{own_line}"
        )
    if lock_type == "general_rule_not_edge_exception":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"相手の例外は理解できても、それだけで一般原則はひっくり返らない。{_three_turn_concrete_support('A', proposition_lock, 2)} だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手の原則論は平時には通っても、制度が壊れた場面の答えになっていない。{_three_turn_concrete_support('B', proposition_lock, 2)} だから{own_line}"
        )
    if lock_type == "labeled_set_not_posthoc_relabel":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"後から『それは陰謀論じゃなかった』と言い換えるのは逃げだ。{_three_turn_concrete_support('A', proposition_lock, 2)} だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"当たり例を拾っても、陰謀論一般の精度までは救えない。{_three_turn_concrete_support('B', proposition_lock, 2)} だから{own_line}"
        )
    if lock_type == "direct_harm_not_market_conditions":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"未知の危険を言っても、既知の重い長期被害がある側の不利は消えない。{_three_turn_concrete_support('A', proposition_lock, 2)} しかも禁煙外来や疫学調査で積み上がった被害の厚みは、まだ薄い長期推定だけではひっくり返らない。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手は既知の被害だけで決めようとするが、未知の長期リスクを軽く見積もる理由はない。{_three_turn_concrete_support('B', proposition_lock, 2)} まだ見えていない慢性被害が後から立ち上がるなら、今あるデータの厚みだけで安全側を断定するのは早い。だから{own_line}"
        )
    if lock_type == "existence_not_explanatory_label":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"相手は立証の厳しさを上げるが、それだけで対立仮説が勝ったことにはならない。{_three_turn_concrete_support('A', proposition_lock, 2)} だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"相手は説明力を前に出すが、便利な説明と実在は同じじゃない。{_three_turn_concrete_support('B', proposition_lock, 2)} だから{own_line}"
        )
    if speaker == "A":
        return _sanitize_fighter_speech(
            f"相手は{focus_issue}を軽く見ている。{_three_turn_concrete_support('A', proposition_lock, 2)} その点を崩せていない以上、{own_line}"
        )
    return _sanitize_fighter_speech(
        f"相手は{focus_issue}でかかる負担を曖昧にしたままだ。{_three_turn_concrete_support('B', proposition_lock, 2)} そこが抜ける限り、{own_line}"
    )


# FREEZE: legacy pre-restore scaffold kept only as historical reference during local
# cleanup. Current live path must stay on _three_turn_grounded_surface instead.
def _three_turn_closing_surface(
    speaker: str,
    own_line: str,
    proposition_lock: dict[str, Any],
) -> str:
    own_line = _three_turn_resolution_line(own_line, speaker, proposition_lock)
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    focus_issue = _topic_issue_candidates(DebateConfig(
        topic=_clean_text(proposition_lock.get("claim_subject") or proposition_lock.get("claim_predicate") or ""),
        side_a=own_line if speaker == "A" else "",
        side_b=own_line if speaker == "B" else "",
        turn_count=3,
        mode="casual",
        fighter_a_provider="openai",
        fighter_b_provider="openai",
        openai_key="",
        anthropic_key="",
        gemini_key="",
        disable_live_judge=True,
        artifact_dir="",
    ))[1]
    if lock_type == "dignity_not_compensation_proxy":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"最後に残るのは、人命の尊厳を守りたいからこそ配分の基準を隠してはいけないという点だ。相手は価格化を禁じれば序列化を防げると言うが、医療資源、保険、事故防止の現場では何かを選ぶ責任自体は消えない。ならば費用対効果や補償基準を公開し、弱い立場の人が不利にならないよう修正できる形の方がまだましだ。人命を雑に扱うのではなく、救命と公共政策の判断を可視化するために値段を使うなら許される。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"締めで残るのは、値段を置いた瞬間に人命の比較が始まり、その比較が弱い立場の人を不利にするという現実だ。相手は公共政策や救命のために価格化が必要だと言うが、現実の補償、保険、トリアージではその数字が『誰を先に救うか』『誰の命を安く見るか』に直結してきた。尊厳と価格を分けられる制度設計を一つでも示せない限り、この値付けは人の命を守る手段ではなく序列化の装置になる。だから{own_line}"
        )
    if lock_type == "knowledge_not_formal_approval":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"最後まで残るのは、形式上の距離があっても長年同じ換金動線が維持されるなら現場が存在自体を知らないとは言えないという点だ。相手は公認かどうかへ逃げたが、本題の『知っているか』は崩していない。景品交換所の配置や選択的摘発まで通して見ると、知らないでは説明がつかない。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"締めで効くのは、知っていることと公認していることを混ぜると制度上の距離が消えるという点だ。相手は周知性を積んだが、それだけで公権力の認識まで断定はできない。形式論と運用上の認識を分けない限り、この結論は早すぎる。だから{own_line}"
        )
    if lock_type == "love_itself_not_conditions":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"最後まで残るのは、金が動かせるのは条件までで愛情そのものではないという点だ。相手は関係の環境を語ったが、本題の『買える』までは届いていない。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"最後に効くのは、愛を条件から切り離した相手の立て方が現実の関係と噛み合っていないことだ。愛は環境・継続・安心と切れず、そこを握れるなら{own_line}"
        )
    if lock_type == "general_rule_not_edge_exception":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"ここで残るのは、極端な例を積んでも一般原則は自動では崩れないという点だ。相手は例外の圧力を出したが、原則として許す理由までは作れていない。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"締めで見るべきなのは、きれいな原則論だけでは破局の場面を説明できないことだ。相手は平時の規範を守っただけで、制度が壊れた時の空白を埋めていない。だから{own_line}"
        )
    if lock_type == "labeled_set_not_posthoc_relabel":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"最後まで残るのは、後からラベルを付け替えても当時の評価は消えないという点だ。陰謀論扱いされた集合の中に真実が混じっていた以上、{own_line}"
            )
        return _sanitize_fighter_speech(
            f"結局、当たり例を拾っても陰謀論一般の信頼までは立たない。相手は例外の存在を示しただけで、陰謀論という方法全体を救えていない。だから{own_line}"
        )
    if lock_type == "direct_harm_not_market_conditions":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"締めで残るのは、既知の長期被害が厚い側を上回る材料が相手から出ていないことだ。未知の危険は否定しないが、それだけで紙タバコの重さは消えない。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"最後に押さえたいのは、今見えている害だけで全体比較を終わらせるのが早いことだ。未知の長期リスクを軽く扱う限り、相手の断定はまだ立たない。だから{own_line}"
        )
    if lock_type == "existence_not_explanatory_label":
        if speaker == "A":
            return _sanitize_fighter_speech(
                f"ここで残るのは、自然主義だけで説明し切れない部分がまだ大きいことだ。相手は存在証明のハードルを上げたが、神仮説の説明上の優位までは崩せていない。だから{own_line}"
            )
        return _sanitize_fighter_speech(
            f"最後に見るべきなのは、説明が欲しいことと実在を認めることは別だという点だ。相手は説明の魅力を語ったが、存在を裏付ける証拠までは渡していない。だから{own_line}"
        )
    if speaker == "A":
        return _sanitize_fighter_speech(
            f"最後まで残るのは{focus_issue}で相手がこちらを崩せなかったことだ。そこで差が埋まらない以上、{own_line}"
        )
    return _sanitize_fighter_speech(
        f"結局、{focus_issue}の負担が相手の説明では処理されていない。そこが残る限り、{own_line}"
    )


def _three_turn_density_debug(
    speech: str,
    turn_no: int,
    latest_opponent: str = "",
) -> dict[str, Any]:
    cleaned = _clean_text(speech)
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", cleaned) if part.strip()]
    char_count = len(cleaned)
    sentence_count = len(sentences)
    concrete_terms = _extract_focus_terms(cleaned)
    has_concrete_support = any(len(term) >= 2 for term in concrete_terms[:8]) and char_count >= 80
    opponent_terms = set(_extract_focus_terms(latest_opponent)[:8]) if latest_opponent else set()
    overlap = any(term in cleaned for term in opponent_terms if len(term) >= 2)
    has_counter = bool(latest_opponent) and (
        any(token in cleaned for token in ["相手", "でも", "しかし", "ただ", "一方で", "そこを"]) or overlap
    )
    if turn_no == 1:
        role_complete = sentence_count >= 2 and has_concrete_support
    elif turn_no == 2:
        role_complete = sentence_count >= 2 and has_concrete_support and has_counter
    else:
        role_complete = sentence_count >= 2 and has_concrete_support and any(token in cleaned for token in ["だから", "結局", "最後", "残る"])
    density_score = char_count + sentence_count * 24 + (30 if has_concrete_support else 0) + (20 if has_counter else 0)
    return {
        "sentence_count": sentence_count,
        "char_count": char_count,
        "has_concrete_support": has_concrete_support,
        "has_counter_to_opponent": has_counter,
        "turn_role_complete": role_complete,
        "density_score": density_score,
        "three_turn_contract_pass": role_complete and char_count >= 90,
    }


def _looks_like_skeleton_three_turn_opening(speech: str) -> bool:
    cleaned = _clean_text(speech)
    if not cleaned:
        return True
    thin_patterns = [
        r"^周辺条件をいくつも積む前に",
        r"^まず命題そのものが立つかで見たい",
        r"^この話で見たいのは",
        r"^まず比べたいのは",
        r"^周辺条件ばかり膨らませると",
        r"^先に争点を絞ると",
    ]
    if any(re.search(pattern, cleaned) for pattern in thin_patterns):
        if len(cleaned) < 150:
            return True
        if not any(token in cleaned for token in ["具体", "データ", "長期", "事例", "全国", "MKウルトラ", "肺がん", "一酸化炭素", "換金", "接触機会"]):
            return True
    return False


def _has_self_stance_reference(cfg: DebateConfig, speaker: str, speech: str) -> bool:
    own_line = cfg.side_a if speaker == "A" else cfg.side_b
    own_terms = [term for term in _extract_focus_terms(own_line) if len(term) >= 2][:6]
    cleaned = _clean_text(speech)
    if any(term in cleaned for term in own_terms):
        return True
    return any(
        token in cleaned
        for token in [
            "こちらの立場は崩れない",
            "この命題の方が残る",
            "この立場の方が残る",
            "こちらの命題は残る",
            "したがって",
            "だから",
            "結論として",
            "と言える",
            "が妥当だ",
            "は成立する",
            "は成立しない",
            "とは言えない",
        ]
    )


def _has_acceptance_condition_signal(speech: str) -> bool:
    cleaned = _clean_text(speech)
    return any(token in cleaned for token in ["なら", "限り", "以上", "までは", "ここで見る", "問うのは", "残るのは", "本題", "だから"])


def _has_closing_punch_signal(speech: str) -> bool:
    cleaned = _clean_text(speech)
    return any(token in cleaned for token in ["だから", "結局", "最後", "残る", "ここまで来ると", "それでも", "結論として"])


def _response_alignment_report(
    speaker: str,
    cfg: DebateConfig,
    turn_no: int,
    speech: str,
    latest_opponent: str = "",
) -> dict[str, Any]:
    cleaned = _clean_text(speech)
    opponent_terms = [term for term in _extract_focus_terms(latest_opponent) if len(term) >= 2][:6]
    overlap_terms = [term for term in opponent_terms if term in cleaned]
    opponent_focus = overlap_terms[0] if overlap_terms else (opponent_terms[0] if opponent_terms else _three_turn_issue_anchor(cfg, 0))
    density = _three_turn_density_debug(speech, turn_no, latest_opponent)
    grounding = _topic_grounding_report(cfg, speech)
    abstract_skeleton = any(
        phrase in cleaned
        for phrase in [
            "まだ届いていない",
            "一番重い具体物",
            "土台のない橋",
            "副作用と失敗時の負担",
        ]
    )
    if turn_no == 1:
        stage2_pass = True
        response_alignment_pass = True
    else:
        response_alignment_pass = bool(overlap_terms) or _has_opponent_reference_in_first_sentence(speech, latest_opponent)
        stage2_pass = (
            response_alignment_pass
            and (density.get("has_concrete_support") or grounding.get("grounded_keyword_count", 0) >= 2)
            and not abstract_skeleton
        )
    return {
        "opponent_focus": opponent_focus,
        "opponent_terms": opponent_terms,
        "opponent_overlap_terms": overlap_terms,
        "response_alignment_pass": response_alignment_pass,
        "stage2_pass": stage2_pass,
    }


def _three_turn_validation_report(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    speech: str,
    latest_opponent: str = "",
) -> dict[str, Any]:
    debug = _three_turn_density_debug(speech, turn_no, latest_opponent)
    grounding = _topic_grounding_report(cfg, speech)
    topic = _clean_text(cfg.topic or "")
    sora_video_topic = (
        "sora" in topic.lower()
        and "動画サービス" in topic
        and ("手を出すべきでなかった" in topic or "手を出すべきだった" in topic)
    )
    failures: list[str] = []
    warnings: list[str] = []
    cleaned = _clean_text(speech)
    char_min = 140 if turn_no in {1, 2} else 100
    sentence_min = 3
    if debug["sentence_count"] < sentence_min:
        failures.append("too few sentences")
    if debug["char_count"] < char_min:
        failures.append("too short")
    if not _has_self_stance_reference(cfg, speaker, speech):
        failures.append("missing self stance")
    if _contains_banned_surface_meta(speech) or _looks_like_design_memo_speech(speech):
        failures.append("contains surface meta")
    if grounding["grounded_keyword_count"] and grounding["grounded_keyword_count"] < 3:
        warnings.append("insufficient topic grounding")
    if grounding["banned_template_phrase_count"]:
        failures.append("contains banned template phrasing")
    if grounding["bare_stance_tokens"]:
        failures.append("contains bare stance token")
    if re.search(r"(だからはい|だからいいえ|(^|[。！？!?\\s])はい|(^|[。！？!?\\s])いいえ)\\s*$", cleaned):
        failures.append("ends with bare stance suffix")
    if turn_no == 1:
        if not debug["has_concrete_support"]:
            failures.append("opening lacks concrete support")
        if not _has_acceptance_condition_signal(speech):
            failures.append("opening lacks acceptance condition")
        if _looks_like_skeleton_three_turn_opening(speech):
            failures.append("skeleton opening")
        if sora_video_topic and grounding["grounded_keyword_count"] < 4:
            failures.append("opening lacks topic-grounded opening")
        if sora_video_topic:
            cleaned = _clean_text(speech)
            if cleaned.startswith(("だからはい", "だからいいえ", "先に押さえたい", "周辺条件ばかり")):
                failures.append("opening starts with banned generic scaffold")
            if not any(token in cleaned for token in ["SORA", "撤退", "動画サービス", "OpenAI", "GPT"]):
                failures.append("opening missing case anchor")
    elif turn_no == 2:
        if not debug["has_counter_to_opponent"]:
            failures.append("rebuttal missing direct counter")
        if not debug["has_concrete_support"]:
            failures.append("rebuttal lacks concrete support")
        if not any(token in _clean_text(speech) for token in ["それでも", "だから", "残る", "本題", "結局"]):
            warnings.append("rebuttal missing self restate")
        prior_same_side = ""
        if turns:
            latest_turn = turns[-1] if turns else {}
            prior_same_side = _clean_text(latest_turn.get("a" if speaker == "A" else "b") or "")
        if latest_opponent and not _has_opponent_reference_in_first_sentence(speech, latest_opponent):
            warnings.append("rebuttal first sentence missing opponent reference")
        if prior_same_side:
            if _first_sentence(speech) == _first_sentence(prior_same_side):
                warnings.append("rebuttal repeats prior first sentence")
            if _final_sentence(speech) == _final_sentence(prior_same_side):
                warnings.append("rebuttal repeats prior last sentence")
            if _has_long_overlap(speech, prior_same_side, 20):
                warnings.append("rebuttal reuses long prior span")
    else:
        if not _has_closing_punch_signal(speech):
            failures.append("closing lacks punch")
        if not debug["has_counter_to_opponent"]:
            failures.append("closing missing opponent collapse")
        if not any(token in _clean_text(speech) for token in ["残る", "立たない", "届いていない", "崩れている", "消えない", "断定はできない", "とは限らない"]):
            failures.append("closing missing self-win reason")
    b3_contract_pass = False
    if turn_no == 3 and speaker == "B":
        has_decisive_conclusion = any(
            token in cleaned
            for token in ["結論", "したがって", "よって", "以上で終結", "まだ終わっていない", "存在すると判断する", "金の方が長期保有に向いている"]
        )
        states_opponent_failure = any(
            token in cleaned
            for token in ["失敗", "不十分", "成立しない", "一般化は失敗", "反証が成立していない", "その主張は失敗する"]
        )
        holds_own_position = any(
            token in cleaned
            for token in ["私の立場", "こちらの立場", "まだ終わっていない", "存在する", "金の方が長期保有に向いている", "結論"]
        )
        if has_decisive_conclusion and states_opponent_failure and holds_own_position:
            demoted = {"closing lacks punch", "closing missing self-win reason", "missing self stance"}
            warnings.extend([item for item in failures if item in demoted and item not in warnings])
            failures = [item for item in failures if item not in demoted]
            b3_contract_pass = True
    fatal_failures = {
        "contains surface meta",
        "too short",
        "too few sentences",
        "contains banned template phrasing",
        "contains bare stance token",
        "ends with bare stance suffix",
    }
    if turn_no == 2 and speaker == "A" and "too short" in failures:
        receives_opponent = bool(latest_opponent) and (
            _has_opponent_reference_in_first_sentence(speech, latest_opponent)
            or "相手の核" in cleaned
            or "相手" in _first_sentence(speech)
        )
        has_concrete_or_observation = bool(debug["has_concrete_support"] or grounding["grounded_keyword_count"] >= 1)
        has_causal_push = any(
            token in cleaned
            for token in ["だから", "そのため", "ゆえに", "結果として", "なので", "以上", "通らない", "崩れる", "伸びず"]
        )
        has_self_push = _has_self_stance_reference(cfg, speaker, speech) and any(
            token in cleaned
            for token in ["こちらの立場", "この命題", "この立場", "残る", "崩れない", "成立する", "妥当", "と言える", "だから", "したがって"]
        )
        if receives_opponent and has_concrete_or_observation and has_causal_push and has_self_push:
            failures = [item for item in failures if item != "too short"]
            warnings.append("too short")
    debug["three_turn_contract_pass"] = (
        (debug["turn_role_complete"] or b3_contract_pass)
        and not any(item in fatal_failures for item in failures)
    )
    debug["three_turn_failures"] = failures
    debug["three_turn_warnings"] = warnings
    debug["three_turn_speaker"] = speaker
    debug["three_turn_mode"] = cfg.turn_count == 3
    debug.update(grounding)
    return debug


def _three_turn_retry_prompt(prompt: str, failures: list[str], turn_no: int) -> str:
    if not failures:
        return prompt
    failure_text = ", ".join(failures)
    return (
        f"{prompt}\n"
        "Rewrite because the previous draft failed the 3-turn speaking contract.\n"
        f"Missing requirements: {failure_text}.\n"
        f"For Turn {turn_no}, produce a denser answer with concrete support, direct engagement, and a complete role.\n"
        "Use at least 3 sentences.\n"
        "Include one concrete noun, case, or evidentiary hook.\n"
        "Do not shorten. Do not output a skeleton. Do not stop at axis restatement.\n"
        "Avoid generic debate scaffolding such as 補助線, 本体, 検証指標, 骨組み, 停止条件, 移行コスト.\n"
        "Stay grounded in the actual topic rather than generic yes/no framing.\n"
        "Keep natural Japanese and return strict JSON only.\n"
    )


def _is_valid_opening_speech(text: str) -> tuple[bool, list[str]]:
    cleaned = _clean_text(text)
    failures: list[str] = []
    if len(cleaned) < 180:
        failures.append("opening too short")
    if not any(token in cleaned for token in ["理由", "なぜなら", "だから", "そのため", "結果として", "ので"]):
        failures.append("opening lacks causal explanation")
    if "例えば" not in cleaned:
        failures.append("opening lacks concrete example")
    if cleaned.startswith(("得する。", "損する。", "理由は", "まだ切れない", "この命題")):
        failures.append("opening starts with weak generic scaffold")
    return not failures, failures


def _opening_retry_prompt(prompt: str, failures: list[str]) -> str:
    failure_text = ", ".join(failures) if failures else "opening too weak"
    return (
        f"{prompt}\n"
        "Rewrite the opening because the previous Turn 1 draft was too weak to start a real debate.\n"
        f"Missing requirements: {failure_text}.\n"
        "Turn 1 must contain: one decisive thesis sentence, one causal chain, one concrete example, and one short preemption of the opponent's likely attack.\n"
        "Do not output a generic explanation, a bare claim, or an abstract yes/no answer.\n"
        "Do not open with lines like『理由は〜まだ切れない』or any weak generic scaffold.\n"
        "Keep natural Japanese and return strict JSON only.\n"
    )


# FREEZE: current repair lane entrypoint. Keep narrow and repair-only; do not expand it
# back into a general live generation surface.
def _three_turn_repair_speech(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    latest_opponent: str = "",
    current_text: str = "",
) -> str:
    topic = _clean_text(cfg.topic or "")
    if (
        speaker == "B"
        and turn_no == 2
        and _needs_short_stance_boost(cfg, "B")
    ):
        own_line = _clean_text(cfg.side_b or "その立場は立たない。")
        own_line_naked = re.sub(r"^(はい|いいえ)[。．!\s]*", "", own_line).strip()
        if not own_line_naked:
            own_line_naked = own_line
        opponent_line = _clean_text(latest_opponent or "")
        topic_terms = _extract_focus_terms(topic)
        opponent_terms = [term for term in _extract_focus_terms(opponent_line) if term not in JP_STOPWORDS]
        own_terms = [term for term in _extract_focus_terms(own_line) if term not in JP_STOPWORDS]
        concrete_terms: list[str] = []
        for term in opponent_terms + topic_terms + own_terms:
            if len(term) < 2:
                continue
            if term in concrete_terms:
                continue
            concrete_terms.append(term)
            if len(concrete_terms) >= 4:
                break
        concrete_a = concrete_terms[0] if concrete_terms else (topic_terms[0] if topic_terms else "具体例")
        concrete_b = concrete_terms[1] if len(concrete_terms) > 1 else (topic_terms[1] if len(topic_terms) > 1 else own_terms[0] if own_terms else "現場")
        if "金" in topic and "銀" in topic:
            return _sanitize_fighter_speech(
                "相手の核は、銀の方が長期保有で有利だという点だ。"
                " だが中央銀行の準備資産運用では、LBMA水準の流動性、COMEXを含む市場の厚み、保管と担保の実務がまず問われる。"
                " 銀は太陽光や電子部品の需要で価格が振れやすく、決済と担保で使う資産としては金ほど安定しない。"
                " だから長期保有の優位は固定できず、金より銀の方が長期保有に向いているとは言えない。"
            )
        current = _sanitize_fighter_speech(current_text or "")
        if current:
            patched = current
            if not _has_opponent_reference_in_first_sentence(patched, latest_opponent):
                opponent_core = _first_sentence(latest_opponent).rstrip("。")
                if opponent_core:
                    patched = f"相手の核は、{opponent_core}という点だ。 {patched}"
            if not _three_turn_density_debug(patched, turn_no, latest_opponent).get("has_concrete_support"):
                patched = f"{patched} {concrete_a}や{concrete_b}のような具体例では、条件がずれれば同じ結論はそのまま通らない。"
            if not any(token in _clean_text(patched) for token in ["だから", "そのため", "ゆえに", "通らない", "成立しない", "一般化できず"]):
                patched = f"{patched} だから相手の前提は一般化できず、この論点だけでは断定は成立しない。"
            if not _has_self_stance_reference(cfg, speaker, patched):
                patched = f"{patched} したがって、{own_line_naked}というこちらの立場は残る。"
            return _sanitize_fighter_speech(patched)
        opponent_core = opponent_line.split("。")[0].strip() if opponent_line else ""
        if opponent_core:
            opening = f"相手の核は、{opponent_core}という点だ。"
        else:
            opening = "相手の核は、その前提を一般化して押し切れるという点だ。"
        support = (
            f" だが{concrete_a}や{concrete_b}のような具体例では、"
            f"{concrete_a}の条件と{concrete_b}の条件がずれれば同じ結論はそのまま通らない。"
        )
        causal = (
            f" だから相手の前提は一般化できず、この論点だけでは断定は成立しない。"
            f" 相手の具体から一般命題までをつなぐ因果がまだ足りない。"
        )
        closing = f" したがって、{own_line_naked}というこちらの否定はそのまま残る。"
        return _sanitize_fighter_speech(opening + support + causal + closing)
    return _three_turn_grounded_surface(speaker, cfg, turn_no, latest_opponent)


def _append_three_turn_trace(entry: dict[str, Any]) -> None:
    try:
        path = Path("/tmp/mmar_three_turn_trace.jsonl")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def _three_turn_parity_failures(a_debug: dict[str, Any], b_debug: dict[str, Any]) -> dict[str, list[str]]:
    out = {"A": [], "B": []}
    if not a_debug or not b_debug:
        return out
    if int(a_debug.get("char_count") or 0) + 15 < int(b_debug.get("char_count") or 0):
        out["A"].append("char parity behind B")
    if int(b_debug.get("char_count") or 0) + 15 < int(a_debug.get("char_count") or 0):
        out["B"].append("char parity behind A")
    if int(a_debug.get("sentence_count") or 0) < int(b_debug.get("sentence_count") or 0):
        out["A"].append("sentence parity behind B")
    if int(b_debug.get("sentence_count") or 0) < int(a_debug.get("sentence_count") or 0):
        out["B"].append("sentence parity behind A")
    if not a_debug.get("has_concrete_support") and b_debug.get("has_concrete_support"):
        out["A"].append("missing concrete support parity")
    if not b_debug.get("has_concrete_support") and a_debug.get("has_concrete_support"):
        out["B"].append("missing concrete support parity")
    if int(a_debug.get("density_score") or 0) + 20 < int(b_debug.get("density_score") or 0):
        out["A"].append("density parity behind B")
    if int(b_debug.get("density_score") or 0) + 20 < int(a_debug.get("density_score") or 0):
        out["B"].append("density parity behind A")
    a_chars = max(1, int(a_debug.get("char_count") or 0))
    b_chars = max(1, int(b_debug.get("char_count") or 0))
    shorter = min(a_chars, b_chars)
    longer = max(a_chars, b_chars)
    if longer and (shorter / longer) < 0.60:
        if a_chars < b_chars:
            out["A"].append("length ratio behind B")
        elif b_chars < a_chars:
            out["B"].append("length ratio behind A")
    return out


def _mock_rebuttal_surface(
    speaker: str,
    own_line: str,
    opponent_line: str,
    plan: dict[str, str],
    proposition_lock: dict[str, Any],
    turn_no: int,
) -> str:
    lock_type = _clean_text(proposition_lock.get("means_vs_essence_lock") or "")
    idx = max(0, (turn_no - 2) % 3)
    if lock_type == "love_itself_not_conditions":
        if speaker == "A":
            options = [
                f"相手が言っているのは環境や継続の話で、問われている愛そのものとは別だ。そこを一緒にすると、問い自体がずれる。だから{own_line}",
                f"相手の話は『関係を続ける条件』には触れていても、『愛を買えるか』への答えにはなっていない。そこを混ぜると別の勝負になる。だから{own_line}",
                f"会う機会や安心を金で整えられることまでは否定しない。でもそこから先の気持ちまで自動で手に入るわけじゃない。だから{own_line}",
            ]
        else:
            options = [
                f"相手は愛情だけを切り離して語るけど、現実の関係は時間も余裕も継続も要る。成立条件を丸ごと外すと、きれいでも空中戦になる。だから{own_line}",
                f"『気持ちは買えない』だけで止めると、関係がどう成立し維持されるかが抜ける。そこを無視した純化は現実とかみ合わない。だから{own_line}",
                f"愛情を聖域みたいに扱うと、実際にそれを支える条件が見えなくなる。条件から切り離せない以上、{own_line}",
            ]
        return options[idx]
    if lock_type == "general_rule_not_edge_exception":
        if speaker == "A":
            options = [
                f"その反例が成り立つとしても、それで原則がひっくり返るわけじゃない。極端な一場面を一般ルールにするのは飛びすぎだ。だから{own_line}",
                f"相手が持ち出したのは例外の圧力であって、普段の規範を支える理由ではない。そこを混ぜると、何でもありに近づく。だから{own_line}",
                f"追い詰められた場面の感情を理解することと、それを原則として許すことは別だ。そこを分けるなら{own_line}",
            ]
        else:
            options = [
                f"原則だけで切ると、法も救済も壊れた場面を説明できない。現実に規範が試される地点まで見るなら{own_line}",
                f"きれいな一般論は立っていても、破局の場面で何を許すかを空白にしたままでは足りない。そこまで含めると{own_line}",
                f"相手は普段のルールを語っているけど、現実にはその外側で判断を迫られる。そこを切り捨てると議論が軽くなる。だから{own_line}",
            ]
        return options[idx]
    if lock_type == "labeled_set_not_posthoc_relabel":
        if speaker == "A":
            options = [
                f"『当たった時点でもう陰謀論じゃない』と言い換えるのは後出しだ。最初に陰謀論扱いされたものの中に事実があったか、そこから逃げると話が変わる。だから{own_line}",
                f"相手はラベルを後から付け替えている。でもこの話で見るべきなのは、当時どう呼ばれていたかと、その中に事実が混じっていたかだ。だから{own_line}",
                f"後から分類を入れ替えると、最初の問いは消える。陰謀論扱いされた集合の中に当たりがあったかで見るなら{own_line}",
            ]
        else:
            options = [
                f"一件当たった話があっても、陰謀論というラベル全体の信頼性は回復しない。例外で全体を正当化するのは広げすぎだ。だから{own_line}",
                f"相手は『当たった例もある』で押してくるけど、それだけでは陰謀論一般の精度にはならない。ラベル全体の評価で見るなら{own_line}",
                f"たまたま拾えた事例と、陰謀論がまともな手がかりになることは別だ。そこを混ぜないなら{own_line}",
            ]
        return options[idx]
    if lock_type == "direct_harm_not_market_conditions":
        if speaker == "A":
            options = [
                f"違法市場や未知リスクの話を足しても、いま分かっている直接害の差は消えない。対象そのものの毒性で見れば{own_line}",
                f"相手は周辺条件を広げてくるけど、比べているのは体に入った時のダメージだ。そこを外さないなら{own_line}",
                f"未知の部分があることは認めても、それで既知の長期被害まで軽くはならない。土台の差を見るなら{own_line}",
            ]
        else:
            options = [
                f"既知の害だけで決めると、まだ積み上がっていない長期リスクを見落とす。未知だから軽いとは言えない。そこまで含めるなら{own_line}",
                f"相手は今見えている害を強く出すけど、将来分かるリスクまで無視していい理由にはならない。長期で見るなら{own_line}",
                f"『今のデータでは重い』と『全体として悪い』は同じじゃない。未知の長期被害まで勘定に入れるなら{own_line}",
            ]
        return options[idx]
    if lock_type == "existence_not_explanatory_label":
        if speaker == "A":
            options = [
                f"相手は『立証できない』で止めるけど、それだけでは説明力の差までは消えない。世界の秩序や意識の起源まで含めて見るなら{own_line}",
                f"分からない場所に名前を置くだけだと言い切るには、説明の競争として何が残るかをまだ数え切れていない。そこまで見ると{own_line}",
                f"証明の厳しさを上げるだけでは、相手は存在を否定したことにならない。説明として何が一番無理なく立つかで見れば{own_line}",
            ]
        else:
            options = [
                f"世界を説明したい気持ちは分かるが、説明が欲しいことと神が実在することは別だ。そこを飛ばすなら{own_line}",
                f"秩序や意識の起源に触れても、それだけで存在証明にはならない。分からなさをそのまま実在へ飛ばさないなら{own_line}",
                f"相手は説明力を前に出すけど、説明に便利な仮説であることと本当にいることは同じじゃない。だから{own_line}",
            ]
        return options[idx]
    if speaker == "A":
        options = [
            f"相手は{plan['target_issue'] or '見えやすい一点'}を決め手にしたいんだろうけど、こちらが置いた話の骨組みまでは崩せていない。だから{own_line}",
            f"{opponent_line or '相手の話'}は耳ざわりはいいけど、{plan['target_issue'] or 'その材料'}だけでは立場をひっくり返す条件までは届いていない。そこまで見ると{own_line}",
            f"相手は{plan['target_issue'] or '一番目立つ材料'}で押してくるが、土台の条件までは動かせていない。なら{own_line}",
        ]
    else:
        options = [
            f"相手は{plan['target_issue'] or '結論'}を残したいんだろうけど、肝心の条件を自分で閉じ切れていない。そこを突くと{own_line}",
            f"{opponent_line or '相手の話'}だけでは、{plan['target_issue'] or 'その一点'}から先の決め手が足りない。立場を支える条件まで見ると{own_line}",
            f"相手は{plan['target_issue'] or '骨組み'}を守れているように見せるけど、抜けている条件が残る。そこを認めるなら{own_line}",
        ]
    return options[idx]


# FREEZE: legacy mock path. Keep available for mock-only execution and tests, but do not
# route live prompt generation back through this scaffold.
def _mock_sequential_turn(
    speaker: str,
    cfg: DebateConfig,
    turns: list[dict[str, Any]],
    turn_no: int,
    latest_opponent: str = "",
) -> str:
    if cfg.turn_count == 3:
        return _three_turn_grounded_surface(speaker, cfg, turn_no, latest_opponent)
    plan = _mock_turn_plan(speaker, cfg, turns, turn_no, latest_opponent)
    own_basis = _compact_basis(cfg.side_a if speaker == "A" else cfg.side_b)
    own_line = cfg.side_a if speaker == "A" else cfg.side_b
    opponent_line = latest_opponent or _opponent_last_statement(speaker, turns)
    proposition_lock = _build_proposition_lock(cfg)
    issue_bank = _issue_bank(cfg.topic)
    target_detail = issue_bank.get(plan["target_issue"], f"{plan['target_issue']}が何を左右するか")
    new_issue_detail = issue_bank.get(plan["new_issue"], f"{plan['new_issue']}が結論をどう変えるか")
    weakness_effect = _weakness_effect(plan["attacked_weakness"])
    if turn_no == 1:
        if not turns:
            if speaker == "A":
                contract = _build_opening_contract(cfg, own_line)
                return _sanitize_fighter_speech(
                    _mock_opening_surface("A", own_line, contract, plan, target_detail, new_issue_detail, proposition_lock)
                )
            return _sanitize_fighter_speech(
                _mock_opening_surface(
                    "B",
                    own_line,
                    _build_opening_contract(cfg, own_line),
                    plan,
                    target_detail,
                    new_issue_detail,
                    proposition_lock,
                )
            )
    if turn_no == 2:
        return _sanitize_fighter_speech(
            _mock_rebuttal_surface(speaker, own_line, opponent_line, plan, proposition_lock, turn_no)
        )
    finish_line = _finish_line(plan, own_basis, own_line)
    base = _mock_rebuttal_surface(speaker, own_line, opponent_line, plan, proposition_lock, turn_no)
    if plan["finish_intent"] == "finish":
        closing = finish_line
    else:
        if speaker == "A":
            closing_options = [
                f"相手は話を広げるほど、最初に置いた形から離れていく。{new_issue_detail}まで見ると、そのずれはさらに目立つ。",
                f"ここまで来ると、相手は言い換えを増やすほど土台が薄くなる。{plan['new_issue']}を含めて見直すと、押し返したつもりの部分も弱い。",
                f"返しを重ねても、こちらが先に置いた芯までは折れていない。とくに{plan['new_issue']}の地点で相手はまだ答え切れていない。",
            ]
        else:
            closing_options = [
                f"ここまで来ると、相手は結論を残したいだけで支える材料が足りない。{new_issue_detail}まで視野に入れると、その空白はごまかせない。",
                f"言い換えは増えても、相手の立場を最後まで立たせる支柱が足りない。{plan['new_issue']}の説明が薄いままなのが痛い。",
                f"相手はまだ決め手を出せておらず、押し返したように見えても土台が浮いている。{new_issue_detail}を数えると、その不安定さははっきりする。",
            ]
        closing = closing_options[(turn_no - 3) % len(closing_options)]
    return _sanitize_fighter_speech(f"{base} {closing}")


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


# FREEZE: issue pool is retained only for repair/mock planning. Do not reuse it as a
# live prompt scaffold source without an explicit text-lane decision.
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


# FREEZE: issue bank is retained only for repair/mock planning. Do not feed it back into
# live prompt assembly without an explicit text-lane decision.
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


def _contains_banned_surface_meta(text: str) -> bool:
    value = _clean_text(text or "")
    if not value:
        return False
    return any(phrase in value for phrase in SURFACE_META_BANNED_PHRASES)


def _looks_like_design_memo_speech(text: str) -> bool:
    value = _clean_text(text or "")
    if not value:
        return False
    return any(token in value for token in ["評価基準", "採用条件", "比較軸", "一般原則", "reframe", "contract", "proposition lock"])


def _naturalize_surface_text(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    substitutions = [
        (r"^相手の核心[:：]\s*", ""),
        (r"^あなたの核心[:：]\s*", ""),
        (r"^弱点は[:：]?\s*", ""),
        (r"^論点はこうだ[:：]?\s*", ""),
        (r"^問題は一行[:：]?\s*", ""),
        (r"^結論は一つ[:：]?\s*", ""),
        (r"^核心は一点[:：]?\s*", ""),
        (r"相手の核心", "相手の前提"),
        (r"あなたの核心", "君の前提"),
        (r"弱点は", "その立て方では"),
        (r"弱点", "穴"),
        (r"核心", "要所"),
        (r"話をずらしてる", "論点がずれている"),
        (r"それは苦しい", "そのままでは通らない"),
        (r"結論は一つ", "残る結論はこれだ"),
        (r"核心は一点", "要点は一つだ"),
        (r"論点はこうだ", "問題になるのはここだ"),
        (r"一刀両断", "ここで崩れる"),
        (r"opening contract", "最初の約束"),
        (r"proposition lock", "最初の問い"),
        (r"comparison axis", "最初に置いた見方"),
        (r"acceptance condition", "最初に置いた成立ライン"),
        (r"lock 外", "問いの外"),
        (r"means for essence", "条件論へのすり替え"),
        (r"exception escape", "例外逃げ"),
        (r"time shift", "時間軸ずらし"),
        (r"scope substitution", "問いのすり替え"),
        (r"burden shift", "立証責任ずらし"),
        (r"frame survival", "最初の筋の維持"),
        (r"contract 外", "最初に置いた筋から外れ"),
        (r"contract の外", "最初に置いた筋の外"),
        (r"drift", "後付けのずれ"),
        (r"reframe", "別の話へのずれ"),
        (r"評価基準[:：]?\s*", ""),
        (r"採用条件", "成り立つライン"),
        (r"比較軸", "見たい筋"),
        (r"一般原則", "ふつうのルール"),
        (r"結論は明快だ。?", ""),
    ]
    for pattern, replacement in substitutions:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"^まずこの話は", "この話で問われるのは", cleaned)
    cleaned = re.sub(r"^まず言いたいのは", "先に言っておくと", cleaned)
    cleaned = re.sub(r"^こちらが言いたいのは単純で、", "", cleaned)
    cleaned = re.sub(r"^要するに、", "", cleaned)
    cleaned = re.sub(r"([。！？])\1+", r"\1", cleaned)
    cleaned = re.sub(r"Aは\s*最初の問い\s*を守り、Bの(.+?)は\s*問いの外の押し込みとして扱う。", r"Aは最初の問いを守り、Bの\1は決め手にならなかった。", cleaned)
    cleaned = re.sub(r"Bは\s*最初の問い\s*を守り、Aの(.+?)は\s*問いの外の押し込みとして扱う。", r"Bは最初の問いを守り、Aの\1は決め手にならなかった。", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" 　")
    return cleaned


def _naturalize_summary_surfaces(
    winner: dict[str, Any],
    reason_one_liner: str,
    turning_point: dict[str, Any],
    weak_spot: dict[str, Any],
    fatal_phrase: dict[str, Any],
    gemini_takeaway: dict[str, Any],
    gemini_quote: dict[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    winner = {**winner, "reason": _naturalize_surface_text(winner.get("reason") or "")}
    reason_one_liner = _naturalize_surface_text(reason_one_liner)
    turning_point = {
        **turning_point,
        "summary": _naturalize_surface_text(turning_point.get("summary") or ""),
    }
    weak_spot = {
        **weak_spot,
        "why_one_sentence": _naturalize_surface_text(weak_spot.get("why_one_sentence") or ""),
        "how_to_fix": _naturalize_surface_text(weak_spot.get("how_to_fix") or ""),
    }
    fatal_phrase = {
        **fatal_phrase,
        "reason": _naturalize_surface_text(fatal_phrase.get("reason") or ""),
        "pick_reason": _naturalize_surface_text(fatal_phrase.get("pick_reason") or ""),
    }
    gemini_takeaway = {
        **gemini_takeaway,
        "structural_explanation": _naturalize_surface_text(gemini_takeaway.get("structural_explanation") or ""),
        "debate_dynamic": _naturalize_surface_text(gemini_takeaway.get("debate_dynamic") or ""),
    }
    gemini_quote = {
        **gemini_quote,
        "text": _naturalize_surface_text(gemini_quote.get("text") or ""),
        "framing_text": _naturalize_surface_text(gemini_quote.get("framing_text") or ""),
        "framing_reason": _naturalize_surface_text(gemini_quote.get("framing_reason") or ""),
        "pick_reason": _naturalize_surface_text(gemini_quote.get("pick_reason") or ""),
    }
    return winner, reason_one_liner, turning_point, weak_spot, fatal_phrase, gemini_takeaway, gemini_quote


def _strip_stance_meta_leakage(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    substitutions = [
        (r"^(はい|いいえ)[。:：\s]+", ""),
        (r"^(結論|結論は|結論として)[。:：\s]+", ""),
        (r"^(賛成|反対)(です|だ|です。|だ。)?[:：\s]+", ""),
        (r"(だから|よって)?(はい|いいえ)[。:：\s]*$", ""),
        (r"(結論|結論は|結論として)[:：\s]*$", ""),
        (r"(賛成|反対)(です|だ)?[。:：\s]*$", ""),
        (r"反リフレーム[:：]\s*", ""),
        (r"受入条件[:：]\s*", ""),
        (r"見たい筋（([^）]+)）[:：]\s*", r"見たい筋は「\1」です。 "),
    ]
    for pattern, replacement in substitutions:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" 　")
    return cleaned


def _repair_incomplete_sentence_ending(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    trailing_repairs = [
        (r"以上、?$", "以上だ。"),
        (r"限り、?$", "限り、この立場は崩れない。"),
        (r"だから、?$", "だからこの立場を取る。"),
        (r"したがって、?$", "したがってこの結論を維持する。"),
        (r"そこで、?$", "そこで立場は変わらない。"),
        (r"その点で、?$", "その点で相手の説明は足りない。"),
        (r"とはいえ、?$", "とはいえ結論は変わらない。"),
    ]
    for pattern, replacement in trailing_repairs:
        if re.search(pattern, cleaned):
            cleaned = re.sub(pattern, replacement, cleaned)
            break
    if re.search(r"[、,]\s*$", cleaned):
        cleaned = re.sub(r"[、,]\s*$", "。", cleaned)
    if cleaned and cleaned[-1] not in "。！？!?":
        cleaned += "。"
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" 　")
    return cleaned


def _sanitize_fighter_speech(text: str) -> str:
    cleaned = _naturalize_surface_text(text)
    cleaned = _strip_stance_meta_leakage(cleaned)
    label_prefix = r"(?:受け取りました|受け取り|受け|相手主張|相手|反論|押し|締め|最後の一撃)"
    label_repairs = [
        (r"^受け取りました[:：]\s*", ""),
        (r"^受け取る[:：]\s*", ""),
        (r"^受け取る[。.]\s*", ""),
        (r"^受け[:：]\s*", ""),
        (r'^受け取りました[:：]\s*([「『"].*)$', r"\1"),
        (rf"^(?:{label_prefix})(?:[:：]|[。.]|\s)+(?:なし[。.]?\s*)?", ""),
        (r"^次の一手(?:は|として)?[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^見たい筋(?:は|として)?[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^評価モード[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^討論として[:：]?\s*([^。！？!?]+)[。！？!?]\s*", ""),
        (r"^相手[:：]\s*([^。！？!?]+?)(?:と主張|と言う|としている)\s*", r"相手は\1と主張している。 "),
    ]
    for pattern, replacement in label_repairs:
        while True:
            updated = re.sub(pattern, replacement, cleaned)
            if updated == cleaned:
                break
            cleaned = updated
    cleaned = re.sub(r"\s*(?:受け取り[:：]?\s*なし|受け取りなし|受け[:：]\s*なし)(?:[。.]?\s*)$", "", cleaned)
    replacements = {
        "ここで": "",
        "盤面": "話",
        "構造": "中身",
        "戦略": "主張",
        "分析": "話",
        "勝ち筋": "話",
        "成り立つライン": "立場の条件",
        "閉じ切れていない": "まだ処理されていない",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("次の一手として", "")
    cleaned = cleaned.replace("この返しで", "")
    cleaned = cleaned.replace("このラリーは", "")
    cleaned = cleaned.replace("押し:", "")
    cleaned = cleaned.replace("押し：", "")
    cleaned = cleaned.replace("最後の一撃:", "")
    cleaned = cleaned.replace("最後の一撃：", "")
    cleaned = cleaned.replace("元の立場を使うと", "")
    cleaned = cleaned.replace("検証指標を入れる", "指標を見る")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _strip_stance_meta_leakage(cleaned)
    cleaned = _repair_incomplete_sentence_ending(cleaned)
    return _naturalize_surface_text(cleaned)


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
    if any(token in text for token in ["network_error", "nodename nor servname", "couldn't connect", "connection reset", "connection refused", "socket", "ssl", "dns", "temporary failure in name resolution"]):
        return "provider_error"
    if "model" in text and any(token in text for token in ["not found", "does not exist", "no model", "not available", "unsupported", "access", "permission", "not authorized", "forbidden"]):
        return "model_access_error"
    if "404" in text or "not found" in text or "no model" in text:
        return "model_not_found"
    if "401" in text or "403" in text or "auth" in text or "authentication" in text or "api key" in text:
        return "auth_error"
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
