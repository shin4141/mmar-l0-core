#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import hashlib
import secrets
import time
import uuid
from html import unescape
from urllib import error as urllib_error
from urllib import request as urllib_request
from http import cookies
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    from debate_api import _call_gemini, _normalize_localized_view_cache, _normalize_summary, LocalizeError, ask_match_gemini, build_battle_from_x_url, localize_battle_record, run_debate, run_live_judge
    from debate_core_v2 import run_debate_v2
    from debate_core_v3 import run_debate_v3
    from debate_core_v4 import run_debate_v4
    from debate_api_pure import run_debate as run_debate_pure
    from history_store import (
        import_history_snapshot,
        history_env_tag,
        history_store_id,
        get_history_record,
        get_run_record,
        increment_history_metric,
        increment_run_metric,
        archive_run,
        list_published_run_ids,
        list_history_records,
        list_run_records,
        log_metric_event,
        metric_event_counts,
        promote_run_to_history,
        remove_run_from_history,
        restore_run,
        run_lifecycle_state,
        save_history_record,
        save_run_record,
        soft_delete_run,
    )
    from published_store import (
        count_published_cards,
        get_published_card,
        increment_published_metric,
        list_published_card_ids,
        list_published_cards,
        publish_record,
        published_store_id,
        published_store_meta,
        unpublish_record,
    )
except ModuleNotFoundError:
    from tools.debate_api import _call_gemini, _normalize_localized_view_cache, _normalize_summary, LocalizeError, ask_match_gemini, build_battle_from_x_url, localize_battle_record, run_debate, run_live_judge
    from tools.debate_core_v2 import run_debate_v2
    from tools.debate_core_v3 import run_debate_v3
    from tools.debate_core_v4 import run_debate_v4
    from tools.debate_api_pure import run_debate as run_debate_pure
    from tools.history_store import (
        import_history_snapshot,
        history_env_tag,
        history_store_id,
        get_history_record,
        get_run_record,
        increment_history_metric,
        increment_run_metric,
        archive_run,
        list_published_run_ids,
        list_history_records,
        list_run_records,
        log_metric_event,
        metric_event_counts,
        promote_run_to_history,
        remove_run_from_history,
        restore_run,
        run_lifecycle_state,
        save_history_record,
        save_run_record,
        soft_delete_run,
    )
    from tools.published_store import (
        count_published_cards,
        get_published_card,
        increment_published_metric,
        list_published_card_ids,
        list_published_cards,
        publish_record,
        published_store_id,
        published_store_meta,
        unpublish_record,
    )


HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8787"))
BOOT_AT = datetime.now(timezone.utc).isoformat()
REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / ".env"
ADMIN_SYNC_ORIGIN = str(os.getenv("MMAR_ADMIN_SYNC_ORIGIN") or "").strip().rstrip("/")
ADMIN_SYNC_TOKEN = str(os.getenv("MMAR_ADMIN_SYNC_TOKEN") or "").strip()
X_OEMBED_URL = "https://publish.x.com/oembed"


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


def _normalize_x_post_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    host = (parsed.netloc or "").strip().lower()
    if host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return ""
    path = parsed.path or ""
    if "/status/" not in path:
        return ""
    parts = [segment for segment in path.split("/") if segment]
    try:
        status_index = parts.index("status")
    except ValueError:
        return ""
    if status_index < 1 or status_index + 1 >= len(parts):
        return ""
    screen_name = parts[status_index - 1]
    status_id = parts[status_index + 1]
    if not screen_name or not status_id.isdigit():
        return ""
    return f"https://x.com/{screen_name}/status/{status_id}"


def _x_oembed_log(event: str, **payload: object) -> None:
    safe_payload = {key: value for key, value in payload.items()}
    print("[x-oembed] " + json.dumps({"event": event, **safe_payload}, ensure_ascii=False))


def _truncate_debug_text(value: str, limit: int = 280) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def _extract_x_media_url(post_url: str) -> str:
    normalized = _normalize_x_post_url(post_url)
    if not normalized:
        return ""
    request = urllib_request.Request(
        normalized,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "MMAR/1.0 (+https://mmar-debate-preview.onrender.com)",
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=6) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        _x_oembed_log(
            "media_url_error",
            normalized_url=normalized,
            error_type=type(exc).__name__,
            error_message=_truncate_debug_text(str(exc or "")),
        )
        return ""
    match = re.search(
        r'(https://pbs\.twimg\.com/(?:media|amplify_video_thumb)[^"\'\s>]+)',
        body,
        flags=re.IGNORECASE,
    )
    media_url = unescape(str(match.group(1) if match else "").strip())
    _x_oembed_log(
        "media_url",
        normalized_url=normalized,
        found=bool(media_url),
        media_url=_truncate_debug_text(media_url, limit=180),
    )
    return media_url


def _fetch_x_oembed(post_url: str) -> dict[str, object]:
    normalized = _normalize_x_post_url(post_url)
    _x_oembed_log("normalize", source_url=str(post_url or ""), normalized_url=normalized)
    if not normalized:
        raise ValueError("invalid_x_post_url")
    request_url = (
        f"{X_OEMBED_URL}?url={quote(normalized, safe='')}"
        "&omit_script=1&dnt=true&maxwidth=550"
    )
    request = urllib_request.Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MMAR/1.0 (+https://mmar-debate-preview.onrender.com)",
        },
        method="GET",
    )
    _x_oembed_log("request", normalized_url=normalized, request_url=request_url)
    try:
        with urllib_request.urlopen(request, timeout=6) as response:
            status = int(getattr(response, "status", 200) or 200)
            body = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        _x_oembed_log(
            "http_error",
            normalized_url=normalized,
            request_url=request_url,
            upstream_status=int(exc.code or 0),
            body_preview=_truncate_debug_text(body),
            error_type=type(exc).__name__,
        )
        raise RuntimeError(f"x_oembed_http_{int(exc.code or 0)}")
    except urllib_error.URLError as exc:
        _x_oembed_log(
            "url_error",
            normalized_url=normalized,
            request_url=request_url,
            reason=_truncate_debug_text(str(getattr(exc, "reason", exc) or "")),
            error_type=type(exc).__name__,
        )
        raise RuntimeError("x_oembed_network")
    except TimeoutError as exc:
        _x_oembed_log(
            "timeout",
            normalized_url=normalized,
            request_url=request_url,
            error_type=type(exc).__name__,
        )
        raise RuntimeError("x_oembed_timeout")
    except Exception as exc:
        _x_oembed_log(
            "exception",
            normalized_url=normalized,
            request_url=request_url,
            error_type=type(exc).__name__,
            error_message=_truncate_debug_text(str(exc or "")),
        )
        raise
    _x_oembed_log(
        "response",
        normalized_url=normalized,
        request_url=request_url,
        upstream_status=status,
        body_preview=_truncate_debug_text(body),
    )
    payload = json.loads(body or "{}")
    html = str(payload.get("html") or "").strip()
    if not html:
        _x_oembed_log(
            "missing_html",
            normalized_url=normalized,
            request_url=request_url,
            upstream_status=status,
            payload_keys=sorted(payload.keys()),
        )
        raise RuntimeError("x_oembed_missing_html")
    return {
        "ok": True,
        "url": normalized,
        "html": html,
        "media_url": _extract_x_media_url(normalized),
        "cache_age": str(payload.get("cache_age") or "").strip(),
        "provider_name": str(payload.get("provider_name") or "").strip(),
    }


GIT_SHA = _git_sha_short()
ADMIN_COOKIE_NAME = "mmar_admin_session"
ADMIN_SESSIONS: dict[str, dict[str, str]] = {}
ADMIN_DATA_SORT_KEYS = {"views", "opens", "shares", "saves"}
ADMIN_X_EMBED_STATUSES = {"success", "x_forbidden", "invalid", "temporary_error", "missing_html"}


def _configured_admin_password() -> str:
    return str(os.getenv("MMAR_ADMIN_PASSWORD") or "").strip()


def _public_battle_from_x_error(exc: Exception) -> tuple[int, str]:
    reason = _classify_x_import_reason(exc)
    if reason in {"invalid_x_url", "invalid_payload"}:
        return 400, reason
    if reason == "missing_xai_key":
        return 503, reason
    if reason == "provider_401":
        return 502, reason
    if reason == "provider_403":
        return 502, reason
    if reason == "provider_429":
        return 502, reason
    if reason == "provider_5xx":
        return 502, reason
    if reason == "timeout":
        return 504, reason
    return 502, reason


def _sanitize_admin_x_embed_payload(payload: dict) -> dict[str, str]:
    status = str(payload.get("x_embed_status") or "").strip()
    if status not in ADMIN_X_EMBED_STATUSES:
        status = "temporary_error"
    html = str(payload.get("x_embed_html") or "").strip()
    if status != "success" or "twitter-tweet" not in html:
        html = ""
    media_url = str(payload.get("x_embed_media_url") or "").strip()
    if not media_url.startswith(("https://", "http://")):
        media_url = ""
    source_url = str(payload.get("x_embed_source_url") or "").strip()
    checked_at = str(payload.get("x_embed_checked_at") or datetime.now(timezone.utc).isoformat()).strip()
    error_code = str(payload.get("x_embed_error") or "").strip()
    return {
        "x_embed_status": status,
        "x_embed_html": html,
        "x_embed_media_url": media_url,
        "x_embed_source_url": source_url,
        "x_embed_checked_at": checked_at,
        "x_embed_error": error_code,
    }


def _requested_experience_mode(payload: dict) -> str:
    raw = str(payload.get("experience_mode") or payload.get("experienceMode") or "").strip().lower()
    if raw in {"battle", "debate"}:
        return raw
    if any(str(payload.get(key) or "").strip() for key in ("source_type", "source_url", "source_image", "source_summary")):
        return "battle"
    return "debate"


def _public_battle_run_forbidden(payload: dict) -> bool:
    return history_env_tag() == "public" and _requested_experience_mode(payload) == "battle"


def _classify_x_import_reason(exc: Exception) -> str:
    raw = str(exc or "").strip()
    normalized = raw.lower()
    if normalized in {"missing_url", "invalid_x_url"}:
        return "invalid_x_url"
    if normalized == "invalid_payload":
        return "invalid_payload"
    if normalized == "xai_api_key_missing":
        return "missing_xai_key"
    if normalized == "empty_xai_seed":
        return "empty_extraction"
    if normalized.startswith("invalid_xai_seed:"):
        return "parse_failed"
    if normalized.startswith("network_error:"):
        return "x_fetch_failed"
    if normalized == "timeout" or "timed out" in normalized:
        return "timeout"
    if normalized.startswith("http_error:401:"):
        return "provider_401"
    if normalized.startswith("http_error:403:"):
        return "provider_403"
    if normalized.startswith("http_error:429:"):
        return "provider_429"
    if normalized.startswith("http_error:"):
        try:
            status = int(normalized.split(":", 2)[1])
        except Exception:
            status = 0
        if 500 <= status <= 599:
            return "provider_5xx"
        if status:
            return f"provider_{status}"
    return "battle_source_unavailable"


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


def _admin_page_path(path: str) -> Path | None:
    mapping = {
        "/admin/login": REPO / "mmar" / "apps" / "debate" / "admin_login.html",
        "/admin/history": REPO / "mmar" / "apps" / "debate" / "admin_history.html",
        "/admin/data": REPO / "mmar" / "apps" / "debate" / "admin_data.html",
        "/admin/admin.css": REPO / "mmar" / "apps" / "debate" / "admin.css",
        "/admin/admin_login.js": REPO / "mmar" / "apps" / "debate" / "admin_login.js",
        "/admin/admin_history.js": REPO / "mmar" / "apps" / "debate" / "admin_history.js",
        "/admin/admin_data.js": REPO / "mmar" / "apps" / "debate" / "admin_data.js",
    }
    candidate = mapping.get(path)
    if not candidate:
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


def _parse_cookies(handler: BaseHTTPRequestHandler) -> cookies.SimpleCookie:
    jar = cookies.SimpleCookie()
    raw = handler.headers.get("Cookie", "")
    if raw:
        jar.load(raw)
    return jar


def _admin_session(handler: BaseHTTPRequestHandler) -> dict[str, str] | None:
    jar = _parse_cookies(handler)
    morsel = jar.get(ADMIN_COOKIE_NAME)
    if not morsel:
        return None
    return ADMIN_SESSIONS.get(morsel.value)


def _service_sync_authorized(handler: BaseHTTPRequestHandler) -> bool:
    token = str(handler.headers.get("X-MMAR-Admin-Sync-Token") or "").strip()
    return bool(ADMIN_SYNC_TOKEN and token == ADMIN_SYNC_TOKEN)


def _log_admin_auth_probe(handler: BaseHTTPRequestHandler, path: str) -> None:
    admin_session = _admin_session(handler)
    sync_header = str(handler.headers.get("X-MMAR-Admin-Sync-Token") or "").strip()
    print(
        "[dev_api] admin_auth_probe "
        + json.dumps(
            {
                "path": path,
                "env_tag": history_env_tag(),
                "admin_session": bool(admin_session),
                "service_sync_authorized": False,
                "sync_header_present": bool(sync_header),
                "sync_header_length": len(sync_header),
                "env_token_present": bool(ADMIN_SYNC_TOKEN),
                "forwarded_hint": bool(handler.headers.get("X-MMAR-Admin-Sync-Token")),
                "origin": str(handler.headers.get("Origin") or ""),
                "referer": str(handler.headers.get("Referer") or ""),
                "user_agent": str(handler.headers.get("User-Agent") or ""),
            },
            ensure_ascii=False,
        )
    )


def _admin_actor(handler: BaseHTTPRequestHandler) -> str:
    session = _admin_session(handler)
    return str((session or {}).get("user") or "admin").strip()


def _extract_turns(debate_result: dict | None) -> tuple[list, list, list]:
    debate = debate_result if isinstance(debate_result, dict) else {}
    raw_turns = debate.get("raw_turns") if isinstance(debate.get("raw_turns"), list) else []
    display_turns = debate.get("display_turns") if isinstance(debate.get("display_turns"), list) else []
    transcript = debate.get("transcript_json") if isinstance(debate.get("transcript_json"), list) else []
    return raw_turns, display_turns, transcript


def _record_excerpt(debate_result: dict | None) -> str:
    raw_turns, display_turns, transcript = _extract_turns(debate_result)
    turns = display_turns or raw_turns or transcript
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        for key in ("a", "b", "text", "content", "summary"):
            text = str(turn.get(key) or "").strip()
            if text:
                compact = " ".join(text.split())
                return compact[:180]
    return ""


def _record_turn_count(record: dict, debate_result: dict | None) -> int:
    debate = debate_result if isinstance(debate_result, dict) else {}
    explicit = debate.get("turn_count")
    if isinstance(explicit, int) and explicit > 0:
        return explicit
    for turns in _extract_turns(debate):
        if turns:
            return len(turns)
    return int(record.get("turn_count") or 0)


def _flatten_saved_record(record: dict, *, curated: bool | None = None) -> dict:
    if not isinstance(record, dict):
        return {}
    try:
        record = _normalize_localized_view_cache(record, lang="en")
    except Exception:
        record = dict(record)
    nested_run = record.get("run_json") if isinstance(record.get("run_json"), dict) else {}
    debate_result = record.get("debate_result") if isinstance(record.get("debate_result"), dict) else {}
    judge_result = record.get("judge_result") if isinstance(record.get("judge_result"), dict) else {}
    nested_debate_result = nested_run.get("debate_result") if isinstance(nested_run.get("debate_result"), dict) else {}
    nested_judge_json = nested_run.get("judge_json") if isinstance(nested_run.get("judge_json"), dict) else {}
    raw_turns, display_turns, transcript = _extract_turns(debate_result)
    if not (raw_turns or display_turns or transcript):
        raw_turns, display_turns, transcript = _extract_turns(nested_debate_result)
    judge_json = judge_result or nested_judge_json
    if judge_json:
        try:
            judge_json = _normalize_summary(judge_json, transcript or display_turns or raw_turns or [])
        except Exception:
            judge_json = judge_result or nested_judge_json
    turn_count = _record_turn_count(record, debate_result)
    if not turn_count:
        turn_count = _record_turn_count(nested_run, nested_debate_result)
    context_cards = []
    for candidate in (
        record.get("context_cards"),
        debate_result.get("context_cards"),
        nested_run.get("context_cards"),
        nested_debate_result.get("context_cards"),
    ):
        if isinstance(candidate, list):
            context_cards = candidate
            break
    is_published = bool(curated) if curated is not None else bool(record.get("curated"))
    lifecycle_state = run_lifecycle_state(record, published=is_published)
    flattened = {
        **record,
        "id": str(record.get("id") or record.get("session_id") or ""),
        "run_id": str(record.get("run_id") or record.get("session_id") or ""),
        "topic": str(record.get("topic") or debate_result.get("topic") or nested_run.get("topic") or nested_debate_result.get("topic") or ""),
        "stance_a": str(record.get("stance_a") or debate_result.get("stance_a") or nested_run.get("stance_a") or nested_debate_result.get("stance_a") or ""),
        "stance_b": str(record.get("stance_b") or debate_result.get("stance_b") or nested_run.get("stance_b") or nested_debate_result.get("stance_b") or ""),
        "experience_mode": str(record.get("experience_mode") or debate_result.get("experience_mode") or nested_run.get("experience_mode") or nested_debate_result.get("experience_mode") or "debate"),
        "battle_lang": str(record.get("battle_lang") or debate_result.get("battle_lang") or nested_run.get("battle_lang") or nested_debate_result.get("battle_lang") or "ja"),
        "source_type": str(record.get("source_type") or debate_result.get("source_type") or nested_run.get("source_type") or nested_debate_result.get("source_type") or ""),
        "source_url": str(record.get("source_url") or debate_result.get("source_url") or nested_run.get("source_url") or nested_debate_result.get("source_url") or ""),
        "source_image": str(record.get("source_image") or debate_result.get("source_image") or nested_run.get("source_image") or nested_debate_result.get("source_image") or ""),
        "source_summary": str(record.get("source_summary") or debate_result.get("source_summary") or nested_run.get("source_summary") or nested_debate_result.get("source_summary") or ""),
        "context_card_mode": str(record.get("context_card_mode") or debate_result.get("context_card_mode") or nested_run.get("context_card_mode") or nested_debate_result.get("context_card_mode") or ""),
        "context_cards": context_cards,
        "canonical_lang": str(record.get("canonical_lang") or debate_result.get("canonical_lang") or nested_run.get("canonical_lang") or nested_debate_result.get("canonical_lang") or "ja"),
        "localized_views": record.get("localized_views") if isinstance(record.get("localized_views"), dict) else (nested_run.get("localized_views") if isinstance(nested_run.get("localized_views"), dict) else {}),
        "x_embed_status": str(record.get("x_embed_status") or nested_run.get("x_embed_status") or ""),
        "x_embed_html": str(record.get("x_embed_html") or nested_run.get("x_embed_html") or ""),
        "x_embed_media_url": str(record.get("x_embed_media_url") or nested_run.get("x_embed_media_url") or ""),
        "x_embed_source_url": str(record.get("x_embed_source_url") or nested_run.get("x_embed_source_url") or ""),
        "x_embed_checked_at": str(record.get("x_embed_checked_at") or nested_run.get("x_embed_checked_at") or ""),
        "x_embed_error": str(record.get("x_embed_error") or nested_run.get("x_embed_error") or ""),
        "views": int(record.get("views", nested_run.get("views", 0)) or 0),
        "opens": int(record.get("opens", nested_run.get("opens", 0)) or 0),
        "shares": int(record.get("shares", nested_run.get("shares", 0)) or 0),
        "saves": int(record.get("saves", nested_run.get("saves", 0)) or 0),
        "turn_count": turn_count,
        "raw_turns": raw_turns,
        "display_turns": display_turns or raw_turns or transcript,
        "transcript_json": transcript or display_turns or raw_turns,
        "provider_statuses": debate_result.get("provider_statuses") or nested_debate_result.get("provider_statuses") or {},
        "output_meta": debate_result.get("output_meta") or nested_debate_result.get("output_meta") or "",
        "elapsed_seconds": debate_result.get("elapsed_seconds") or nested_debate_result.get("elapsed_seconds"),
        "source_mode": debate_result.get("source_mode") or nested_debate_result.get("source_mode") or "",
        "judge_json": judge_json,
        "excerpt": _record_excerpt(debate_result or nested_debate_result),
        "tease": _record_excerpt(debate_result or nested_debate_result),
        "curated": is_published,
        "deleted_at": str(record.get("deleted_at") or ""),
        "deleted_by": str(record.get("deleted_by") or ""),
        "archived_at": str(record.get("archived_at") or ""),
        "archived_by": str(record.get("archived_by") or ""),
        "record_state": lifecycle_state,
    }
    return flattened


def _range_days_from_key(range_key: str) -> int | None:
    key = str(range_key or "7d").strip().lower()
    if key == "7d":
        return 7
    if key == "14d":
        return 14
    return None


def _normalize_admin_sort_key(sort_key: str) -> str:
    key = str(sort_key or "views").strip().lower()
    return key if key in ADMIN_DATA_SORT_KEYS else "views"


def _normalize_admin_audience(audience_key: str) -> str:
    key = str(audience_key or "external").strip().lower()
    return key if key in {"external", "internal", "all"} else "external"


def _title_for_admin_item(item: dict) -> str:
    topic = str(item.get("topic") or "").strip()
    if topic:
        return topic
    issue = str(item.get("issue") or "").strip()
    if issue:
        return issue
    return "(no title)"


def _metric_snapshot_for_item(item: dict, counts: dict[str, int] | None = None) -> dict[str, int]:
    source = counts or {}
    return {
        "views": int(source.get("views", item.get("views", 0)) or 0),
        "opens": int(source.get("opens", item.get("opens", 0)) or 0),
        "shares": int(source.get("shares", item.get("shares", 0)) or 0),
        "saves": int(source.get("saves", item.get("saves", 0)) or 0),
    }


def _admin_data_summary(*, range_key: str, state_filter: str, sort_key: str, audience_key: str) -> dict[str, object]:
    normalized_state = str(state_filter or "all").strip().lower()
    normalized_range = str(range_key or "7d").strip().lower()
    normalized_sort = _normalize_admin_sort_key(sort_key)
    normalized_audience = _normalize_admin_audience(audience_key)
    items = _flatten_run_records_for_admin(list_run_records(limit=500))
    if normalized_state in {"all", "candidate", "published", "failed", "archived", "deleted", "trash"}:
        items = [item for item in items if _state_filter_matches(item, normalized_state)]
    range_days = _range_days_from_key(normalized_range)
    event_counts = metric_event_counts(range_days=range_days, audience=normalized_audience)
    table_rows: list[dict[str, object]] = []
    for item in items:
        record_id = str(item.get("id") or item.get("run_id") or item.get("session_id") or "").strip()
        counts = _metric_snapshot_for_item(
            item,
            (event_counts.get(record_id) or {"views": 0, "opens": 0, "shares": 0, "saves": 0}),
        )
        table_rows.append(
            {
                "id": record_id,
                "run_id": str(item.get("run_id") or record_id),
                "session_id": str(item.get("session_id") or record_id),
                "title": _title_for_admin_item(item),
                "status": str(item.get("record_state") or "candidate"),
                "created_at": str(item.get("created_at") or ""),
                **counts,
            }
        )
    table_rows.sort(
        key=lambda row: (
            -int(row.get(normalized_sort, 0) or 0),
            -int(row.get("views", 0) or 0),
            str(row.get("created_at") or ""),
        )
    )
    totals = {
        metric: sum(int(row.get(metric, 0) or 0) for row in table_rows)
        for metric in ("views", "opens", "shares", "saves")
    }
    return {
        "range": normalized_range,
        "status": normalized_state,
        "sort": normalized_sort,
        "audience": normalized_audience,
        "top_cards": table_rows[:50],
        "totals": totals,
    }


def _normalize_metric_days(value: str) -> int:
    try:
        days = int(str(value or "30").strip())
    except ValueError:
        days = 30
    return max(1, min(days, 90))


def _admin_daily_metric_rows(*, days: int) -> list[dict[str, object]]:
    today = datetime.now(timezone.utc).date()
    rows = [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "views": 0,
            "opens": 0,
            "shares": 0,
            "saves": 0,
            "published_count": 0,
        }
        for offset in range(days - 1, -1, -1)
    ]
    published = list_published_cards(sort="recent")
    totals = {
        "views": sum(int(record.get("views", 0) or 0) for record in published),
        "opens": sum(int(record.get("opens", 0) or 0) for record in published),
        "shares": sum(int(record.get("shares", 0) or 0) for record in published),
        "saves": sum(int(record.get("saves", 0) or 0) for record in published),
        "published_count": len(published),
    }
    if rows:
        rows[-1].update(totals)
    return rows


def _metric_audience_for_request(handler: BaseHTTPRequestHandler) -> str:
    if history_env_tag() != "public":
        return "internal"
    referer = str(handler.headers.get("Referer") or "").strip().lower()
    origin = str(handler.headers.get("Origin") or "").strip().lower()
    if "/admin/" in referer or "/admin/" in origin:
        return "internal"
    return "external"


def _increment_battle_metric(record_id: str, metric: str, *, audience: str) -> tuple[dict | None, bool]:
    published_record = increment_published_metric(record_id, metric)
    run_record = increment_run_metric(record_id, metric)
    try:
        log_metric_event(record_id, metric, audience=audience)
    except Exception:
        pass
    return published_record or run_record, bool(published_record)


def _flatten_run_records_for_admin(records: list[dict]) -> list[dict]:
    published_ids = list_published_run_ids()
    return [
        _flatten_saved_record(item, curated=(str(item.get("session_id") or "") in published_ids))
        for item in records
    ]


def _state_filter_matches(item: dict, state_filter: str) -> bool:
    state = str(item.get("record_state") or "candidate").strip().lower()
    if state_filter == "all":
        return state in {"candidate", "published", "failed"}
    if state_filter == "trash":
        return state in {"deleted", "archived"}
    return state == state_filter


def _is_admin_hidden_record(record: dict | None) -> bool:
    if not isinstance(record, dict):
        return False
    return bool(str(record.get("deleted_at") or "").strip() or str(record.get("archived_at") or "").strip())


def _self_origin() -> str:
    host = "127.0.0.1" if HOST in {"0.0.0.0", "::"} else HOST
    return f"http://{host}:{PORT}"


def _maybe_sync_candidate_to_admin(record: dict) -> None:
    if not ADMIN_SYNC_ORIGIN or not ADMIN_SYNC_TOKEN or not isinstance(record, dict):
        return
    if ADMIN_SYNC_ORIGIN == _self_origin():
        return
    body = json.dumps({"record": record}, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(
        f"{ADMIN_SYNC_ORIGIN}/api/admin/runs/import",
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-MMAR-Admin-Sync-Token": ADMIN_SYNC_TOKEN,
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=5) as response:
            if response.status >= 400:
                raise RuntimeError(f"admin_sync_http_{response.status}")
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, RuntimeError):
        return


def _persist_battle_record(record: dict, *, published: bool = False) -> dict:
    saved = save_run_record(record)
    persisted_record = saved.get("record") or record
    if published:
        try:
            publish_record(persisted_record)
        except Exception:
            pass
    return saved


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict, extra_headers: dict[str, str] | None = None) -> None:
        started_at = datetime.now(timezone.utc).isoformat()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("X-Build-SHA", GIT_SHA)
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
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
            published_meta = published_store_meta()
            self._send_json(
                200,
                {
                    "ok": True,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "boot_at": BOOT_AT,
                    "build_sha": GIT_SHA,
                    "api_base": _external_origin(self),
                    "env_tag": history_env_tag(),
                    "history_store_id": history_store_id(),
                    "history_count": len(list_history_records()),
                    "gallery_store_id": published_store_id(),
                    "gallery_count": count_published_cards(),
                    **published_meta,
                    "env": {
                        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
                        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
                        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
                        "XAI_API_KEY": bool(os.getenv("XAI_API_KEY")),
                    },
                },
            )
            return
        if path == "/api/admin/session":
            session = _admin_session(self)
            self._send_json(200, {"ok": True, "authenticated": bool(session), "user": session.get("user") if session else ""})
            return
        if path == "/api/history/list":
            query = parse_qs(parsed_url.query or "")
            sort = str(query.get("sort", ["recent"])[0] or "recent")
            items = [_flatten_saved_record(item, curated=True) for item in list_history_records(sort=sort)]
            self._send_json(
                200,
                {
                    "ok": True,
                    "items": items,
                    "env_tag": history_env_tag(),
                    "history_store_id": history_store_id(),
                    "build_sha": GIT_SHA,
                    "boot_at": BOOT_AT,
                },
            )
            return
        if path == "/api/gallery/list":
            query = parse_qs(parsed_url.query or "")
            sort = str(query.get("sort", ["recent"])[0] or "recent")
            items = [_flatten_saved_record(item, curated=True) for item in list_published_cards(sort=sort)]
            self._send_json(
                200,
                {
                    "ok": True,
                    "items": items,
                    "env_tag": history_env_tag(),
                    "gallery_store_id": published_store_id(),
                    "gallery_count": len(items),
                    "build_sha": GIT_SHA,
                    "boot_at": BOOT_AT,
                },
            )
            return
        if path == "/api/gallery/count":
            self._send_json(
                200,
                {
                    "ok": True,
                    "count": count_published_cards(),
                    "gallery_store_id": published_store_id(),
                    "build_sha": GIT_SHA,
                    "boot_at": BOOT_AT,
                },
            )
            return
        if path.startswith("/api/battle/"):
            if path.endswith("/localize"):
                record_id = path.removeprefix("/api/battle/").removesuffix("/localize").strip()
                run_record = get_run_record(record_id)
                published_record = get_published_card(record_id)
                is_published = bool(published_record)
                record = published_record or (run_record if not _is_admin_hidden_record(run_record) else None)
                if not record:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                query = parse_qs(parsed_url.query or "")
                requested_lang = str(query.get("lang", ["en"])[0] or "en").strip().lower()
                try:
                    localized = localize_battle_record(record, lang=requested_lang)
                except Exception as exc:
                    reason = exc.reason if isinstance(exc, LocalizeError) else "localize_unavailable"
                    try:
                        failed_record = _normalize_localized_view_cache(record, lang=requested_lang)
                        if requested_lang == "en":
                            failed_views = failed_record.get("localized_views") if isinstance(failed_record.get("localized_views"), dict) else {}
                            failed_view = dict(failed_views.get("en") or {}) if isinstance(failed_views.get("en"), dict) else {}
                            failed_view["status"] = "failed"
                            failed_view["error_reason"] = reason
                            failed_views["en"] = failed_view
                            failed_record["localized_views"] = failed_views
                            failed_record["localized_en_payload"] = failed_view
                            failed_record["localized_en_status"] = "failed"
                            failed_record["localized_en_source_hash"] = str(failed_view.get("source_hash") or failed_record.get("localized_en_source_hash") or "")
                            failed_record["localized_en_generator_version"] = str(failed_view.get("generator_version") or failed_record.get("localized_en_generator_version") or "")
                        _persist_battle_record(failed_record, published=is_published)
                    except Exception:
                        pass
                    self._send_json(502, {"ok": False, "error": "localize_unavailable", "reason": reason})
                    return
                try:
                    saved = _persist_battle_record(localized.get("record") or record, published=is_published)
                except Exception:
                    self._send_json(502, {"ok": False, "error": "localize_unavailable", "reason": "save_failed"})
                    return
                refreshed_published = get_published_card(record_id) if is_published else None
                refreshed = refreshed_published or get_run_record(record_id) or saved.get("record") or record
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "record": _flatten_saved_record(refreshed, curated=is_published),
                        "localized_view": localized.get("localized_view") or {},
                        "cache_hit": bool(localized.get("cache_hit")),
                    },
                )
                return
            record_id = path.removeprefix("/api/battle/").strip()
            run_record = get_run_record(record_id)
            published_record = get_published_card(record_id)
            record = published_record or (run_record if not _is_admin_hidden_record(run_record) else None)
            if not record:
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            self._send_json(200, {"ok": True, "record": _flatten_saved_record(record, curated=bool(published_record))})
            return
        if path == "/api/x/oembed":
            query = parse_qs(parsed_url.query or "")
            post_url = str(query.get("url", [""])[0] or "").strip()
            if not post_url:
                self._send_json(400, {"ok": False, "error": "missing_url"})
                return
            try:
                payload = _fetch_x_oembed(post_url)
            except ValueError:
                self._send_json(400, {"ok": False, "error": "invalid_x_post_url"})
                return
            except Exception as exc:
                reason = str(exc or "").strip()
                if reason == "x_oembed_http_403":
                    self._send_json(403, {"ok": False, "error": "x_forbidden"})
                    return
                if reason == "x_oembed_missing_html":
                    self._send_json(502, {"ok": False, "error": "missing_html"})
                    return
                if reason in {"x_oembed_timeout", "x_oembed_network"}:
                    self._send_json(502, {"ok": False, "error": "oembed_unavailable"})
                    return
                self._send_json(502, {"ok": False, "error": "oembed_unavailable"})
                return
            self._send_json(200, payload)
            return
        if path.startswith("/api/history/"):
            record_id = path.removeprefix("/api/history/").strip()
            record = get_history_record(record_id)
            if not record:
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            self._send_json(200, {"ok": True, "item": _flatten_saved_record(record, curated=True)})
            return
        if path == "/api/admin/runs":
            if not _admin_session(self):
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            query = parse_qs(parsed_url.query or "")
            limit = int(str(query.get("limit", ["200"])[0] or "200"))
            state_filter = str(query.get("state", ["all"])[0] or "all").strip().lower()
            items = _flatten_run_records_for_admin(list_run_records(limit=limit))
            if state_filter in {"all", "candidate", "published", "failed", "archived", "deleted", "trash"}:
                items = [item for item in items if _state_filter_matches(item, state_filter)]
            self._send_json(200, {"ok": True, "items": items})
            return
        if path.startswith("/api/admin/runs/"):
            if not _admin_session(self):
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            session_id = path.removeprefix("/api/admin/runs/").strip()
            item = get_run_record(session_id)
            if not item:
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            self._send_json(
                200,
                {
                    "ok": True,
                    "item": _flatten_saved_record(item, curated=(session_id in list_published_run_ids())),
                },
            )
            return
        if path == "/api/admin/data/summary":
            if not _admin_session(self):
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            query = parse_qs(parsed_url.query or "")
            range_key = str(query.get("range", ["7d"])[0] or "7d")
            state_filter = str(query.get("status", ["all"])[0] or "all")
            sort_key = str(query.get("sort", ["views"])[0] or "views")
            audience_key = str(query.get("audience", ["external"])[0] or "external")
            summary = _admin_data_summary(
                range_key=range_key,
                state_filter=state_filter,
                sort_key=sort_key,
                audience_key=audience_key,
            )
            self._send_json(200, {"ok": True, **summary})
            return
        if path == "/api/admin/metrics/daily":
            if not _admin_session(self):
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            query = parse_qs(parsed_url.query or "")
            days = _normalize_metric_days(str(query.get("days", ["30"])[0] or "30"))
            self._send_json(200, {"ok": True, "days": days, "rows": _admin_daily_metric_rows(days=days)})
            return
        admin_page = _admin_page_path(path)
        if admin_page:
            body = admin_page.read_bytes()
            content_type, _ = mimetypes.guess_type(str(admin_page))
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Build-SHA", GIT_SHA)
            _cors_headers(self)
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/battle/"):
            battle_page = REPO / "mmar" / "apps" / "debate" / "debate.html"
            body = battle_page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Build-SHA", GIT_SHA)
            _cors_headers(self)
            self.end_headers()
            self.wfile.write(body)
            return
        if path in {"/gallery", "/debate/gallery.html"}:
            gallery_page = REPO / "mmar" / "apps" / "debate" / "gallery.html"
            body = gallery_page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Build-SHA", GIT_SHA)
            _cors_headers(self)
            self.end_headers()
            self.wfile.write(body)
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
        if path not in {
            "/api/debate",
            "/api/debate_pure",
            "/api/debate_v2",
            "/api/debate_v3",
            "/api/debate_v4",
            "/api/ask_match",
            "/api/battle_from_x_url",
            "/api/history/save",
            "/api/provider_preflight",
            "/api/judge",
            "/api/runs/save",
            "/api/admin/login",
            "/api/admin/logout",
            "/api/admin/history/add",
            "/api/admin/history/remove",
            "/api/admin/history/import_snapshot",
            "/api/admin/gallery/publish",
            "/api/admin/gallery/remove",
            "/api/admin/runs/import",
            "/api/admin/runs/x_embed",
            "/api/admin/runs/delete",
            "/api/admin/runs/archive",
            "/api/admin/runs/restore",
        } and not path.startswith("/api/history/view/") and not path.startswith("/api/history/like/") and not path.startswith("/api/battle/"):
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
            if path == "/api/admin/login":
                admin_password = _configured_admin_password()
                if not admin_password:
                    self._send_json(503, {"ok": False, "error": "admin_password_unset"})
                    return
                password = str(payload.get("password") or "").strip()
                if not password or password != admin_password:
                    self._send_json(401, {"ok": False, "error": "invalid_password"})
                    return
                session_id = secrets.token_urlsafe(24)
                ADMIN_SESSIONS[session_id] = {
                    "user": "Shin",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._send_json(
                    200,
                    {"ok": True, "authenticated": True, "user": "Shin"},
                    extra_headers={
                        "Set-Cookie": f"{ADMIN_COOKIE_NAME}={session_id}; Path=/; HttpOnly; SameSite=Lax"
                    },
                )
                return
            if path == "/api/admin/logout":
                jar = _parse_cookies(self)
                morsel = jar.get(ADMIN_COOKIE_NAME)
                if morsel:
                    ADMIN_SESSIONS.pop(morsel.value, None)
                self._send_json(
                    200,
                    {"ok": True},
                    extra_headers={
                        "Set-Cookie": f"{ADMIN_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
                    },
                )
                return
            if path == "/api/admin/runs/import":
                token = str(self.headers.get("X-MMAR-Admin-Sync-Token") or "").strip()
                if not ADMIN_SYNC_TOKEN or token != ADMIN_SYNC_TOKEN:
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                record = payload.get("record") if isinstance(payload.get("record"), dict) else payload
                saved = save_run_record(record)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "record": _flatten_saved_record(saved.get("record") or {}, curated=False),
                        "saved_id": saved.get("saved_id") or "",
                    },
                )
                return
            if path == "/api/runs/save":
                saved = save_run_record(payload)
                _maybe_sync_candidate_to_admin(saved.get("record") or {})
                saved_record = _flatten_saved_record(saved.get("record") or {}, curated=False)
                self._send_json(200, {"ok": True, **saved, "history_item": None, "record": saved_record})
                return
            if path == "/api/admin/runs/x_embed":
                if not _admin_session(self):
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                session_id = str(payload.get("session_id") or "").strip()
                if not session_id:
                    self._send_json(400, {"ok": False, "error": "missing_session_id"})
                    return
                item = get_run_record(session_id)
                if not item:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                merged = dict(item)
                merged.update(_sanitize_admin_x_embed_payload(payload))
                saved = save_run_record(merged)
                published_record = get_published_card(session_id)
                if published_record:
                    try:
                        publish_record(saved.get("record") or merged)
                    except Exception:
                        pass
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "item": _flatten_saved_record(saved.get("record") or merged, curated=bool(published_record)),
                    },
                )
                return
            if path in {"/api/admin/history/add", "/api/admin/gallery/publish"}:
                if not (_admin_session(self) or _service_sync_authorized(self)):
                    _log_admin_auth_probe(self, path)
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                session_id = str(payload.get("session_id") or "").strip()
                if not session_id:
                    self._send_json(400, {"ok": False, "error": "missing_session_id"})
                    return
                item = get_run_record(session_id)
                if not item:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                lifecycle_state = run_lifecycle_state(item, published=bool(get_published_card(session_id)))
                if lifecycle_state in {"deleted", "archived"}:
                    self._send_json(409, {"ok": False, "error": "restore_required", "record_state": lifecycle_state})
                    return
                promote_run_to_history(session_id)
                published = publish_record(item)
                self._send_json(200, {"ok": True, "item": _flatten_saved_record(published, curated=True)})
                return
            if path in {"/api/admin/history/remove", "/api/admin/gallery/remove"}:
                if not (_admin_session(self) or _service_sync_authorized(self)):
                    _log_admin_auth_probe(self, path)
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                session_id = str(payload.get("session_id") or "").strip()
                if not session_id:
                    self._send_json(400, {"ok": False, "error": "missing_session_id"})
                    return
                remove_run_from_history(session_id)
                removed = unpublish_record(session_id)
                if not removed:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, {"ok": True, **removed})
                return
            if path in {"/api/admin/runs/delete", "/api/admin/runs/archive", "/api/admin/runs/restore"}:
                if not _admin_session(self):
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                session_id = str(payload.get("session_id") or "").strip()
                if not session_id:
                    self._send_json(400, {"ok": False, "error": "missing_session_id"})
                    return
                item = get_run_record(session_id)
                if not item:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                actor = _admin_actor(self)
                is_published = bool(get_published_card(session_id))
                lifecycle_state = run_lifecycle_state(item, published=is_published)
                if path == "/api/admin/runs/delete":
                    if is_published:
                        self._send_json(409, {"ok": False, "error": "published_delete_forbidden"})
                        return
                    if lifecycle_state not in {"candidate", "failed"}:
                        self._send_json(409, {"ok": False, "error": "delete_not_allowed", "record_state": lifecycle_state})
                        return
                    updated = soft_delete_run(session_id, deleted_by=actor)
                    self._send_json(200, {"ok": True, "item": _flatten_saved_record(updated or {}, curated=False)})
                    return
                if path == "/api/admin/runs/archive":
                    if not is_published:
                        self._send_json(409, {"ok": False, "error": "archive_requires_published"})
                        return
                    remove_run_from_history(session_id)
                    removed = unpublish_record(session_id)
                    if not removed:
                        self._send_json(404, {"ok": False, "error": "not found"})
                        return
                    updated = archive_run(session_id, archived_by=actor)
                    self._send_json(200, {"ok": True, "item": _flatten_saved_record(updated or {}, curated=False)})
                    return
                if lifecycle_state not in {"deleted", "archived"}:
                    self._send_json(409, {"ok": False, "error": "restore_not_needed", "record_state": lifecycle_state})
                    return
                updated = restore_run(session_id)
                self._send_json(200, {"ok": True, "item": _flatten_saved_record(updated or {}, curated=False)})
                return
            if path == "/api/admin/history/import_snapshot":
                if not _admin_session(self):
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
                snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
                if not isinstance(snapshot, dict):
                    self._send_json(400, {"ok": False, "error": "invalid_snapshot"})
                    return
                env_tag = history_env_tag()
                confirm_env_tag = str(payload.get("confirm_env_tag") or snapshot.get("confirm_env_tag") or "").strip().lower()
                if confirm_env_tag and confirm_env_tag != env_tag:
                    self._send_json(
                        409,
                        {
                            "ok": False,
                            "error": "env_tag_mismatch",
                            "expected_env_tag": env_tag,
                            "received_env_tag": confirm_env_tag,
                        },
                    )
                    return
                clear_existing = bool(payload.get("clear_existing"))
                if clear_existing and env_tag == "public":
                    self._send_json(403, {"ok": False, "error": "public_clear_forbidden"})
                    return
                result = import_history_snapshot(snapshot, clear_existing=clear_existing)
                self._send_json(200, {"ok": True, **result})
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
            if path == "/api/battle_from_x_url":
                if history_env_tag() == "public":
                    self._send_json(403, {"ok": False, "error": "battle_run_preview_only"})
                    return
                try:
                    result = build_battle_from_x_url(payload)
                except Exception as exc:
                    status, error_code = _public_battle_from_x_error(exc)
                    self._send_json(status, {"ok": False, "error": error_code, "reason": error_code})
                    return
                self._send_json(200, result)
                return
            if path in {"/api/debate", "/api/debate_pure", "/api/debate_v2", "/api/debate_v3", "/api/debate_v4"}:
                if path != "/api/debate_v4" and os.getenv("READ_ONLY_DEMO", "").lower() == "true":
                    self._send_json(403, {"ok": False, "error": "read-only demo"})
                    return
                if _public_battle_run_forbidden(payload):
                    self._send_json(403, {"ok": False, "error": "battle_run_preview_only"})
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
            if path.startswith("/api/battle/") and path.endswith("/view"):
                record_id = path.removeprefix("/api/battle/").removesuffix("/view").strip()
                record, curated = _increment_battle_metric(record_id, "views", audience=_metric_audience_for_request(self))
                if not record:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, {"ok": True, "item": _flatten_saved_record(record, curated=curated)})
                return
            if path.startswith("/api/battle/") and path.endswith("/open"):
                record_id = path.removeprefix("/api/battle/").removesuffix("/open").strip()
                record, curated = _increment_battle_metric(record_id, "opens", audience=_metric_audience_for_request(self))
                if not record:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, {"ok": True, "item": _flatten_saved_record(record, curated=curated)})
                return
            if path.startswith("/api/battle/") and path.endswith("/share"):
                record_id = path.removeprefix("/api/battle/").removesuffix("/share").strip()
                record, curated = _increment_battle_metric(record_id, "shares", audience=_metric_audience_for_request(self))
                if not record:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, {"ok": True, "item": _flatten_saved_record(record, curated=curated)})
                return
            if path.startswith("/api/battle/") and path.endswith("/save"):
                record_id = path.removeprefix("/api/battle/").removesuffix("/save").strip()
                record, curated = _increment_battle_metric(record_id, "saves", audience=_metric_audience_for_request(self))
                if not record:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, {"ok": True, "item": _flatten_saved_record(record, curated=curated)})
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
    print(f"[dev_api] GET  /api/admin/session")
    print(f"[dev_api] GET  /api/admin/runs")
    print(f"[dev_api] GET  /api/admin/data/summary")
    print(f"[dev_api] GET  /admin/login")
    print(f"[dev_api] GET  /admin/history")
    print(f"[dev_api] GET  /admin/data")
    print(f"[dev_api] POST /api/debate")
    print(f"[dev_api] POST /api/battle_from_x_url")
    print(f"[dev_api] POST /api/ask_match")
    print(f"[dev_api] POST /api/history/save")
    print(f"[dev_api] POST /api/runs/save")
    print(f"[dev_api] POST /api/admin/login")
    print(f"[dev_api] POST /api/admin/logout")
    print(f"[dev_api] POST /api/admin/history/add")
    print(f"[dev_api] POST /api/history/view/{{id}}")
    print(f"[dev_api] POST /api/battle/{{id}}/open")
    print(f"[dev_api] POST /api/battle/{{id}}/share")
    print(f"[dev_api] POST /api/battle/{{id}}/save")
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
