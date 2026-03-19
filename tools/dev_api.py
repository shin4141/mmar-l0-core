#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    from debate_api import ask_match_gemini, run_debate
    from history_store import get_history_record, increment_history_metric, list_history_records, save_history_record
except ModuleNotFoundError:
    from tools.debate_api import ask_match_gemini, run_debate
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
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Build-SHA", GIT_SHA)
        _cors_headers(self)
        self.end_headers()
        self.wfile.write(body)

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
        if path not in {"/api/debate", "/api/ask_match", "/api/history/save"} and not path.startswith("/api/history/view/") and not path.startswith("/api/history/like/"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(size)
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                self._send_json(400, {"ok": False, "error": "invalid_payload"})
                return
            if path == "/api/debate":
                result = run_debate(payload)
                print(
                    "[dev_api] result "
                    + json.dumps(
                        {
                            "mode": result.get("mode"),
                            "provider_statuses": result.get("provider_statuses"),
                            "warning": result.get("warning", ""),
                        },
                        ensure_ascii=False,
                    )
                )
                self._send_json(200, result)
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
