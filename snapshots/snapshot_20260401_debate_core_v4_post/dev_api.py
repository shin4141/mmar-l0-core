#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import hashlib
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    from debate_api import _call_gemini, ask_match_gemini, run_debate, run_live_judge
    from debate_core_v2 import run_debate_v2
    from debate_core_v3 import run_debate_v3
    from debate_core_v4 import run_debate_v4
    from debate_api_pure import run_debate as run_debate_pure
    from history_store import get_history_record, increment_history_metric, list_history_records, save_history_record
except ModuleNotFoundError:
    from tools.debate_api import _call_gemini, ask_match_gemini, run_debate, run_live_judge
    from tools.debate_core_v2 import run_debate_v2
    from tools.debate_core_v3 import run_debate_v3
    from tools.debate_core_v4 import run_debate_v4
    from tools.debate_api_pure import run_debate as run_debate_pure
    from tools.history_store import get_history_record, increment_history_metric, list_history_records, save_history_record


HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8787"))
BOOT_AT = datetime.now(timezone.utc).isoformat()
REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

def _git_sha_short() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO),
            text=True,
            timeout=2,
        )
        return out.strip() or "unknown"
    except Exception:
        return "unknown"


GIT_SHA = _git_sha_short()


def _topic_hash(topic: str) -> str:
    return hashlib.sha1(str(topic or "").strip().encode("utf-8")).hexdigest()[:12]


def _artifact_common(*, run_id: str, topic: str, topic_hash: str) -> dict[str, str]:
    return {
        "run_id": run_id,
        "topic": topic,
        "topic_hash": topic_hash,
        "port": str(PORT),
        "build_sha": GIT_SHA,
        "boot_at": BOOT_AT,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _public_live_debate_failed(request_payload: dict[str, object], response_payload: dict[str, object]) -> bool:
    provider_statuses = response_payload.get("provider_statuses")
    if not isinstance(provider_statuses, dict):
        return True
    fighter_providers = [
        str(request_payload.get("fighter_a_provider") or "openai").strip() or "openai",
        str(request_payload.get("fighter_b_provider") or "openai").strip() or "openai",
    ]
    for provider in fighter_providers:
        info = provider_statuses.get(provider)
        if not isinstance(info, dict) or str(info.get("mode") or "") != "live":
            return True
    return False


def _public_live_failure_payload(request_payload: dict[str, object], response_payload: dict[str, object]) -> dict[str, object]:
    provider_statuses = response_payload.get("provider_statuses")
    fighter_providers = [
        str(request_payload.get("fighter_a_provider") or "openai").strip() or "openai",
        str(request_payload.get("fighter_b_provider") or "openai").strip() or "openai",
    ]
    failure_parts = []
    if isinstance(provider_statuses, dict):
        for provider in fighter_providers:
            info = provider_statuses.get(provider) or {}
            mode = str(info.get("mode") or "")
            reason = str(info.get("reason") or info.get("raw_reason") or "").strip()
            label = provider.upper()
            if reason:
                failure_parts.append(f"{label}: {mode} ({reason})")
            else:
                failure_parts.append(f"{label}: {mode or 'unknown'}")
    error_text = "Live debate failed"
    if failure_parts:
        error_text = f"{error_text}: {'; '.join(failure_parts)}"
    return {
        "ok": False,
        "error": error_text,
        "failure_reason": error_text,
        "mode": "live-failed",
        "provider_statuses": provider_statuses,
        "run_id": response_payload.get("run_id", ""),
        "session_id": response_payload.get("session_id", ""),
        "route_signature": response_payload.get("route_signature", ""),
        "topic_hash": response_payload.get("topic_hash", ""),
        "artifact_bundle_dir": response_payload.get("artifact_bundle_dir", ""),
        "artifact_created_at": response_payload.get("artifact_created_at", ""),
        "fighter_a_provider": response_payload.get("fighter_a_provider", ""),
        "fighter_b_provider": response_payload.get("fighter_b_provider", ""),
        "judge_provider": response_payload.get("judge_provider", ""),
        "fighter_a_model": response_payload.get("fighter_a_model", ""),
        "fighter_b_model": response_payload.get("fighter_b_model", ""),
        "judge_model": response_payload.get("judge_model", ""),
    }


def _provider_preflight(payload: dict) -> dict:
    api_keys = payload.get("api_keys") if isinstance(payload.get("api_keys"), dict) else {}
    selected = []
    for provider in (
        str(payload.get("fighter_a_provider") or payload.get("fighterAProvider") or "openai").strip().lower(),
        str(payload.get("fighter_b_provider") or payload.get("fighterBProvider") or "gemini").strip().lower(),
    ):
        if provider and provider not in selected:
            selected.append(provider)

    checks: dict[str, dict[str, str | bool]] = {}
    hard_failures: list[str] = []

    if "anthropic" in selected:
        checks["anthropic"] = {"ok": False, "state": "disabled", "message": "Claude disabled"}
        hard_failures.append("Claude disabled")

    if "openai" in selected:
        openai_key = str(api_keys.get("openai") or os.getenv("OPENAI_API_KEY") or "").strip()
        if not openai_key:
            checks["openai"] = {"ok": False, "state": "missing", "message": "OpenAI key missing"}
            hard_failures.append("OpenAI key missing")
        else:
            checks["openai"] = {"ok": True, "state": "ready", "message": ""}

    if "gemini" in selected:
        gemini_key = str(os.getenv("GEMINI_API_KEY") or "").strip()
        if not gemini_key:
            checks["gemini"] = {"ok": False, "state": "missing", "message": "Gemini key missing"}
            hard_failures.append("Gemini key missing")
        else:
            try:
                _call_gemini('{"speech":"ok"}', gemini_key)
                checks["gemini"] = {"ok": True, "state": "ready", "message": ""}
            except Exception as exc:
                raw = str(exc)
                message = "Gemini key invalid" if "API_KEY_INVALID" in raw or "API key not valid" in raw else "Gemini unavailable"
                state = "invalid" if message == "Gemini key invalid" else "unavailable"
                checks["gemini"] = {"ok": False, "state": state, "message": message}
                hard_failures.append(message)

    return {
        "ok": not hard_failures,
        "checks": checks,
        "error": hard_failures[0] if hard_failures else "",
    }


def _write_bundle_json(bundle_dir: Path, name: str, payload: dict) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _repair_validation_payload(result: dict) -> list[dict]:
    turns = (((result or {}).get("debate") or {}).get("turns") or [])
    out: list[dict] = []
    for turn in turns:
        meta = (turn or {}).get("meta") or {}
        for speaker in ("a", "b"):
            speaker_meta = (meta.get(speaker) or {})
            out.append(
                {
                    "turn": turn.get("turn"),
                    "speaker": speaker.upper(),
                    "run_id": ((result or {}).get("run_id") or ""),
                    "topic_hash": ((result or {}).get("topic_hash") or ""),
                    "provider_mode": speaker_meta.get("provider_mode", ""),
                    "retry_triggered": bool(speaker_meta.get("retry_triggered", False)),
                    "repair_triggered": bool(speaker_meta.get("repair_triggered", False)),
                    "adopted_stage": speaker_meta.get("adopted_stage", ""),
                    "initial_validation": speaker_meta.get("initial_validation", {}),
                    "retry_validation": speaker_meta.get("retry_validation", {}),
                    "repair_validation": speaker_meta.get("repair_validation", {}),
                    "final_validation": {
                        "three_turn_contract_pass": speaker_meta.get("three_turn_contract_pass"),
                        "three_turn_failures": speaker_meta.get("three_turn_failures", []),
                        "sentence_count": speaker_meta.get("sentence_count"),
                        "char_count": speaker_meta.get("char_count"),
                    },
                }
            )
    return out


def _consistency_report(result: dict) -> dict:
    debate = (result or {}).get("debate") or {}
    turns = debate.get("turns") or []
    run_id = str((result or {}).get("run_id") or "")
    topic_hash = str((result or {}).get("topic_hash") or "")
    report = {
        "run_id": run_id,
        "topic": debate.get("topic", ""),
        "topic_hash": topic_hash,
        "turns": [],
        "same_run_topic_hash_mismatch_count": 0,
    }
    for turn in turns:
        meta = (turn.get("meta") or {})
        report["turns"].append(
            {
                "turn": turn.get("turn"),
                "a_len": len(str(turn.get("a") or "")),
                "b_len": len(str(turn.get("b") or "")),
                "a_topic_hash": topic_hash,
                "b_topic_hash": topic_hash,
                "a_run_id": run_id,
                "b_run_id": run_id,
            }
        )
    return report


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Private-Network", "true")


def _external_origin(handler: BaseHTTPRequestHandler) -> str:
    forwarded_proto = handler.headers.get("X-Forwarded-Proto", "").strip()
    proto = forwarded_proto or "http"
    request_host = handler.headers.get("Host", f"127.0.0.1:{PORT}")
    return f"{proto}://{request_host}"


def _safe_static_path(path: str) -> Path | None:
    candidate = unquote(path or "/")
    if candidate == "/":
        candidate = "/mmar/apps/debate/debate.html"
    resolved = (REPO / candidate.lstrip("/")).resolve()
    try:
        resolved.relative_to(REPO)
    except ValueError:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict) -> None:
        started_at = datetime.now(timezone.utc).isoformat()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("X-Build-SHA", GIT_SHA)
        _cors_headers(self)
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True
        finished_at = datetime.now(timezone.utc).isoformat()
        self._last_send_json_timing = {
            "response_write_start": started_at,
            "response_write_end": finished_at,
            "response_write_bytes": len(body),
        }

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/api/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "boot_at": BOOT_AT,
                    "build_sha": GIT_SHA,
                    "api_base": _external_origin(self),
                    "env": {
                        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
                        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
                        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
                    },
                },
            )
            return
        if path == "/api/history/list":
            query = parse_qs(parsed_url.query or "")
            sort = str(query.get("sort", ["recent"])[0] or "recent")
            items = list_history_records(sort=sort)
            self._send_json(200, {"ok": True, "items": items})
            return
        if path.startswith("/api/history/"):
            record_id = path.removeprefix("/api/history/").strip()
            record = get_history_record(record_id)
            if not record:
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            self._send_json(200, {"ok": True, "item": record})
            return
        static_path = _safe_static_path(path)
        if static_path:
            body = static_path.read_bytes()
            content_type, _ = mimetypes.guess_type(str(static_path))
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Build-SHA", GIT_SHA)
            _cors_headers(self)
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/debate", "/api/debate_pure", "/api/debate_v2", "/api/debate_v3", "/api/debate_v4", "/api/ask_match", "/api/history/save", "/api/provider_preflight", "/api/judge"} and not path.startswith("/api/history/view/") and not path.startswith("/api/history/like/"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(size)
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                self._send_json(400, {"ok": False, "error": "invalid_payload"})
                return
            if path == "/api/provider_preflight":
                self._send_json(200, _provider_preflight(payload))
                return
            if path == "/api/judge":
                server_phase_entries = []
                request_received_at = datetime.now(timezone.utc).isoformat()
                topic = str(payload.get("topic") or "").strip()
                run_id = uuid.uuid4().hex[:12]
                topic_hash = _topic_hash(topic or "judge")
                bundle_dir = Path(f"/tmp/mmar_judge_bundle_{run_id}")
                common = _artifact_common(run_id=run_id, topic=topic or "judge", topic_hash=topic_hash)
                request_payload = {
                    **payload,
                    "_artifact_meta": {
                        **common,
                        "artifact_dir": str(bundle_dir),
                    },
                }
                request_write_started_at = time.time()
                _write_bundle_json(bundle_dir, "request.json", request_payload)
                server_phase_entries.append(
                    {
                        "name": "bundle_write_request",
                        "started_at": request_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                judge_started_at = datetime.now(timezone.utc).isoformat()
                result = run_live_judge(request_payload)
                judge_finished_at = datetime.now(timezone.utc).isoformat()
                status = 200 if result.get("ok") else 502
                response_payload = {
                    **result,
                    "run_id": run_id,
                    "topic_hash": topic_hash,
                    "artifact_bundle_dir": str(bundle_dir),
                    "artifact_created_at": common["created_at"],
                }
                response_write_started_at = time.time()
                _write_bundle_json(bundle_dir, "response.json", response_payload)
                server_phase_entries.append(
                    {
                        "name": "bundle_write_response",
                        "started_at": response_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                phase_timing_write_started_at = time.time()
                _write_bundle_json(
                    bundle_dir,
                    "phase_timings.json",
                    {
                        **common,
                        "session_id": response_payload.get("session_id", ""),
                        "route_signature": response_payload.get("route_signature", ""),
                        "fighter_a_provider": response_payload.get("fighter_a_provider", ""),
                        "fighter_b_provider": response_payload.get("fighter_b_provider", ""),
                        "judge_provider": response_payload.get("judge_provider", ""),
                        "fighter_a_model": response_payload.get("fighter_a_model", ""),
                        "fighter_b_model": response_payload.get("fighter_b_model", ""),
                        "judge_model": response_payload.get("judge_model", ""),
                        "request_received_at": request_received_at,
                        "judge_start": judge_started_at,
                        "judge_end": judge_finished_at,
                        "phase_entries": result.get("artifact_phase_entries", []),
                        "server_phase_entries": server_phase_entries,
                    },
                )
                server_phase_entries.append(
                    {
                        "name": "bundle_write_phase_timings",
                        "started_at": phase_timing_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                _write_bundle_json(
                    bundle_dir,
                    "server_phase_timings.json",
                    {
                        **common,
                        "server_phase_entries": server_phase_entries,
                    },
                )
                self._send_json(status, response_payload)
                return
            if path in {"/api/debate", "/api/debate_pure", "/api/debate_v2", "/api/debate_v3", "/api/debate_v4"}:
                if os.getenv("READ_ONLY_DEMO", "").lower() == "true":
                    self._send_json(403, {"ok": False, "error": "read-only demo"})
                    return
                server_phase_entries = []
                request_received_at = datetime.now(timezone.utc).isoformat()
                topic = str(payload.get("topic") or payload.get("side_a") or payload.get("sideA") or "").strip()
                run_id = uuid.uuid4().hex[:12]
                topic_hash = _topic_hash(topic)
                bundle_dir = Path(f"/tmp/mmar_run_bundle_{run_id}")
                common = _artifact_common(run_id=run_id, topic=topic, topic_hash=topic_hash)
                # Canonical dev API should stay transport-stable even if the UI
                # is holding real provider keys in local state.
                safe_api_keys = {"openai": "", "anthropic": "", "gemini": ""}
                request_payload = {
                    **payload,
                    "api_keys": safe_api_keys,
                    "_force_mock": path == "/api/debate_pure",
                    "_disable_live_judge": True,
                    "_artifact_meta": {
                        **common,
                        "artifact_dir": str(bundle_dir),
                    },
                }
                request_write_started_at = time.time()
                _write_bundle_json(bundle_dir, "request.json", request_payload)
                server_phase_entries.append(
                    {
                        "name": "bundle_write_request",
                        "started_at": request_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                run_debate_started_at = datetime.now(timezone.utc).isoformat()
                try:
                    if path == "/api/debate_pure":
                        result = run_debate_pure(request_payload)
                    elif path == "/api/debate_v2":
                        result = run_debate_v2(request_payload)
                    elif path == "/api/debate_v3":
                        result = run_debate_v3(request_payload)
                    elif path == "/api/debate_v4":
                        result = run_debate_v4(request_payload)
                    else:
                        result = run_debate(request_payload)
                except Exception as exc:
                    run_debate_finished_at = datetime.now(timezone.utc).isoformat()
                    progress = {}
                    speaker_progress = {}
                    progress_path = bundle_dir / "progress.json"
                    if progress_path.exists():
                        try:
                            progress = json.loads(progress_path.read_text(encoding="utf-8"))
                        except Exception:
                            progress = {}
                    for speaker in ["A", "B"]:
                        speaker_path = bundle_dir / f"speaker_progress_{speaker}.json"
                        if speaker_path.exists():
                            try:
                                speaker_progress[speaker] = json.loads(speaker_path.read_text(encoding="utf-8"))
                            except Exception:
                                speaker_progress[speaker] = {}
                    active_speaker = None
                    active_provider = None
                    provider_call_index = None
                    provider_call_started_at = None
                    prompt_char_count = None
                    transcript_char_count = None
                    request_model = None
                    request_phase = None
                    latest_active = None
                    latest_started = -1.0
                    for speaker, info in speaker_progress.items():
                        if not isinstance(info, dict) or info.get("completed"):
                            continue
                        started = float(info.get("provider_call_started_at") or 0.0)
                        if started >= latest_started:
                            latest_started = started
                            latest_active = (speaker, info)
                    if latest_active:
                        active_speaker, info = latest_active
                        active_provider = info.get("active_provider")
                        provider_call_index = info.get("provider_call_index")
                        provider_call_started_at = info.get("provider_call_started_at")
                        prompt_char_count = info.get("prompt_char_count")
                        transcript_char_count = info.get("transcript_char_count")
                        request_model = info.get("request_model")
                        request_phase = info.get("request_phase")
                    response_payload = {
                        "ok": False,
                        "error": f"live_execution_failed:{type(exc).__name__}:{str(exc)}",
                        "failure_reason": f"{type(exc).__name__}:{str(exc)}",
                        "mode": "live-failed",
                        "provider_statuses": progress.get("provider_statuses", {}),
                        "run_id": run_id,
                        "session_id": run_id,
                        "route_signature": str(progress.get("route_signature") or ""),
                        "topic_hash": topic_hash,
                        "artifact_bundle_dir": str(bundle_dir),
                        "artifact_created_at": common["created_at"],
                        "fighter_a_provider": request_payload.get("fighter_a_provider", ""),
                        "fighter_b_provider": request_payload.get("fighter_b_provider", ""),
                        "judge_provider": "gemini",
                        "fighter_a_model": progress.get("fighter_a_model", ""),
                        "fighter_b_model": progress.get("fighter_b_model", ""),
                        "judge_model": progress.get("judge_model", ""),
                        "execution_stage": progress.get("stage", "unknown"),
                        "execution_turn": progress.get("turn"),
                        "execution_active_speakers": progress.get("active_speakers", []),
                        "execution_active_providers": progress.get("active_providers", {}),
                        "elapsed_seconds": progress.get("elapsed_seconds"),
                        "active_speaker": active_speaker,
                        "active_provider": active_provider,
                        "provider_call_index": provider_call_index,
                        "provider_call_started_at": provider_call_started_at,
                        "prompt_char_count": prompt_char_count,
                        "transcript_char_count": transcript_char_count,
                        "request_model": request_model,
                        "request_phase": request_phase,
                        "last_completed_checkpoint": progress.get("stage", "unknown"),
                        "speaker_progress": speaker_progress,
                    }
                    _write_bundle_json(bundle_dir, "response.json", response_payload)
                    _write_bundle_json(
                        bundle_dir,
                        "phase_timings.json",
                        {
                            **common,
                            "request_received_at": request_received_at,
                            "run_debate_start": run_debate_started_at,
                            "run_debate_end": run_debate_finished_at,
                            "session_id": run_id,
                            "route_signature": str(progress.get("route_signature") or ""),
                            "fighter_a_provider": progress.get("fighter_a_provider", request_payload.get("fighter_a_provider", "")),
                            "fighter_b_provider": progress.get("fighter_b_provider", request_payload.get("fighter_b_provider", "")),
                            "judge_provider": progress.get("judge_provider", "gemini"),
                            "fighter_a_model": progress.get("fighter_a_model", ""),
                            "fighter_b_model": progress.get("fighter_b_model", ""),
                            "judge_model": progress.get("judge_model", ""),
                            "phase_entries": [],
                            "server_phase_entries": server_phase_entries,
                            "progress": progress,
                            "speaker_progress": speaker_progress,
                            "exception": {
                                "type": type(exc).__name__,
                                "message": str(exc),
                            },
                        },
                    )
                    self._send_json(502, response_payload)
                    return
                run_debate_finished_at = datetime.now(timezone.utc).isoformat()
                response_assembly_started_at = time.time()
                response_payload = {
                    **result,
                    "run_id": run_id,
                    "topic_hash": topic_hash,
                    "artifact_bundle_dir": str(bundle_dir),
                    "artifact_created_at": common["created_at"],
                }
                response_status = 200
                if (
                    path not in {"/api/debate_pure", "/api/debate_v2", "/api/debate_v3", "/api/debate_v4"}
                    and not bool(request_payload.get("_allow_mock_fallback"))
                    and _public_live_debate_failed(request_payload, response_payload)
                ):
                    response_payload = _public_live_failure_payload(request_payload, response_payload)
                    response_status = 502
                server_phase_entries.append(
                    {
                        "name": "response_payload_assembly",
                        "started_at": response_assembly_started_at,
                        "ended_at": time.time(),
                    }
                )
                response_write_started_at = time.time()
                _write_bundle_json(bundle_dir, "response.json", response_payload)
                server_phase_entries.append(
                    {
                        "name": "bundle_write_response",
                        "started_at": response_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                phase_timing_write_started_at = time.time()
                _write_bundle_json(
                    bundle_dir,
                    "phase_timings.json",
                    {
                        **common,
                        "session_id": response_payload.get("session_id", ""),
                        "route_signature": response_payload.get("route_signature", ""),
                        "fighter_a_provider": response_payload.get("fighter_a_provider", ""),
                        "fighter_b_provider": response_payload.get("fighter_b_provider", ""),
                        "judge_provider": response_payload.get("judge_provider", ""),
                        "fighter_a_model": response_payload.get("fighter_a_model", ""),
                        "fighter_b_model": response_payload.get("fighter_b_model", ""),
                        "judge_model": response_payload.get("judge_model", ""),
                        "request_received_at": request_received_at,
                        "run_debate_start": run_debate_started_at,
                        "run_debate_end": run_debate_finished_at,
                        "phase_entries": result.get("artifact_phase_entries", []),
                        "server_phase_entries": server_phase_entries,
                    },
                )
                server_phase_entries.append(
                    {
                        "name": "bundle_write_phase_timings",
                        "started_at": phase_timing_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                raw_outputs_write_started_at = time.time()
                _write_bundle_json(
                    bundle_dir,
                    "raw_model_outputs.json",
                    {
                        **common,
                        "entries": result.get("artifact_trace_entries", []),
                    },
                )
                server_phase_entries.append(
                    {
                        "name": "bundle_write_raw_model_outputs",
                        "started_at": raw_outputs_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                repair_write_started_at = time.time()
                _write_bundle_json(
                    bundle_dir,
                    "repair_validation.json",
                    {
                        **common,
                        "entries": _repair_validation_payload(response_payload),
                    },
                )
                server_phase_entries.append(
                    {
                        "name": "bundle_write_repair_validation",
                        "started_at": repair_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                normalized_write_started_at = time.time()
                _write_bundle_json(
                    bundle_dir,
                    "normalized_turns.json",
                    {
                        **common,
                        "turns": ((result.get("debate") or {}).get("turns") or []),
                    },
                )
                server_phase_entries.append(
                    {
                        "name": "bundle_write_normalized_turns",
                        "started_at": normalized_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                consistency_write_started_at = time.time()
                _write_bundle_json(
                    bundle_dir,
                    "consistency_report.json",
                    {
                        **common,
                        **_consistency_report(response_payload),
                    },
                )
                server_phase_entries.append(
                    {
                        "name": "bundle_write_consistency_report",
                        "started_at": consistency_write_started_at,
                        "ended_at": time.time(),
                    }
                )
                _write_bundle_json(
                    bundle_dir,
                    "server_phase_timings.json",
                    {
                        **common,
                        "server_phase_entries": server_phase_entries,
                    },
                )
                print(
                    "[dev_api] result "
                    + json.dumps(
                        {
                            "run_id": run_id,
                            "topic_hash": topic_hash,
                            "bundle_dir": str(bundle_dir),
                            "mode": response_payload.get("mode"),
                            "provider_statuses": response_payload.get("provider_statuses"),
                            "warning": response_payload.get("warning", ""),
                        },
                        ensure_ascii=False,
                    )
                )
                self._send_json(response_status, response_payload)
                if getattr(self, "_last_send_json_timing", None):
                    _write_bundle_json(
                        bundle_dir,
                        "response_write_timing.json",
                        {
                            **common,
                            **self._last_send_json_timing,
                        },
                    )
                return
            if path == "/api/history/save":
                saved = save_history_record(payload)
                print(
                    "[dev_api] history_save "
                    + json.dumps(
                        {
                            "saved_id": saved.get("saved_id"),
                            "deduped": saved.get("deduped", False),
                            "topic": payload.get("topic", ""),
                        },
                        ensure_ascii=False,
                    )
                )
                self._send_json(200, {"ok": True, **saved})
                return
            if path.startswith("/api/history/view/"):
                record_id = path.removeprefix("/api/history/view/").strip()
                record = increment_history_metric(record_id, "views")
                if not record:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, {"ok": True, "item": record})
                return
            if path.startswith("/api/history/like/"):
                record_id = path.removeprefix("/api/history/like/").strip()
                record = increment_history_metric(record_id, "likes")
                if not record:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, {"ok": True, "item": record})
                return
            result = ask_match_gemini(payload)
            print(
                "[dev_api] ask_match "
                + json.dumps(
                    {
                        "ok": result.get("ok"),
                        "provider_status": result.get("provider_status"),
                        "error": result.get("error", ""),
                    },
                    ensure_ascii=False,
                )
            )
            self._send_json(200, result)
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})


def main() -> int:
    _load_dotenv(ENV_PATH)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[dev_api] listening on http://{HOST}:{PORT}")
    print(f"[dev_api] GET  /api/health")
    print(f"[dev_api] GET  /api/history/list")
    print(f"[dev_api] GET  /api/history/{{id}}")
    print(f"[dev_api] POST /api/debate")
    print(f"[dev_api] POST /api/ask_match")
    print(f"[dev_api] POST /api/history/save")
    print(f"[dev_api] POST /api/history/view/{{id}}")
    print(f"[dev_api] POST /api/history/like/{{id}}")
    print(
        "[dev_api] env "
        + json.dumps(
            {
                "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
                "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
                "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
            },
            ensure_ascii=False,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
