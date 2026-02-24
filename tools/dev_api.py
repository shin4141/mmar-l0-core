#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = 8787

REPO = Path(__file__).resolve().parents[1]
ASK_TRIAD = REPO / "tools" / "ask_triad.py"
INCOMING = REPO / "incoming"

OUT_FILES = {
    "compare": INCOMING / "out_compare.txt",
    "expand": INCOMING / "out_expand.txt",
    "diff": INCOMING / "out_diff.txt",
    "merge": INCOMING / "out_merge.txt",
}

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def _collect_outputs() -> tuple[dict, list[str]]:
    missing = [k for k, p in OUT_FILES.items() if not p.exists()]
    if missing:
        return {}, missing
    return {k: _read_text(p) for k, p in OUT_FILES.items()}, []


def _run_ask_triad(user_input: str, timeout_s: int | None, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(ASK_TRIAD),
        "--tab",
        "expand",
        user_input,
    ]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=env,
    )


def _start_full_job(user_input: str) -> str:
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running"}

    def _worker():
        try:
            proc = _run_ask_triad(user_input, timeout_s=None, env_extra=None)
            if proc.returncode != 0:
                err = (proc.stderr or "")
                if len(err) > 1200:
                    err = err[:1200] + "..."
                with JOBS_LOCK:
                    JOBS[job_id] = {"status": "error", "error": "subprocess_failed", "returncode": proc.returncode, "stderr_trunc": err}
                return
            payload, missing = _collect_outputs()
            if missing:
                with JOBS_LOCK:
                    JOBS[job_id] = {"status": "error", "error": "missing_outputs", "missing": missing}
                return
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "done", **payload}
        except Exception as e:
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "error", "error": str(e)}

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        _cors_headers(self)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "cwd": str(REPO),
                },
            )
            return
        if path.startswith("/api/job/"):
            job_id = path.split("/api/job/", 1)[1].strip()
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                self._send_json(404, {"ok": False, "error": "job_not_found"})
                return
            self._send_json(200, job)
            return
        else:
            self._send_json(404, {"error": "not found"})
            return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path != "/api/triad":
            self._send_json(404, {"error": "not found"})
            return

        try:
            qs = parse_qs(parsed.query)
            mode = (qs.get("mode", ["quick"])[0] or "quick").lower()
            if mode not in ("quick", "think"):
                mode = "quick"
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict) or "input" not in data:
                self._send_json(400, {"ok": False, "error": "missing_input"})
                return
            user_input = data.get("input")
            if not isinstance(user_input, str):
                self._send_json(400, {"ok": False, "error": "input must be string"})
                return

            if mode == "think":
                job_id = _start_full_job(user_input)
                self._send_json(202, {"ok": True, "job_id": job_id, "mode": "think"})
                return

            proc = _run_ask_triad(
                user_input,
                timeout_s=12,
                env_extra={"MMAR_LLM_TIMEOUT": "6", "MMAR_NO_LLM": "1"},
            )
            if proc.returncode != 0:
                err = proc.stderr or ""
                if len(err) > 1200:
                    err = err[:1200] + "..."
                self._send_json(
                    500,
                    {
                        "ok": False,
                        "error": "subprocess_failed",
                        "returncode": proc.returncode,
                        "stderr_trunc": err,
                    },
                )
                return

            payload, missing = _collect_outputs()
            if missing:
                self._send_json(500, {"ok": False, "error": "missing_outputs", "missing": missing})
                return

            self._send_json(200, {"ok": True, **payload})

        except subprocess.TimeoutExpired:
            self._send_json(504, {"ok": False, "error": "timeout", "mode": "quick"})
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[dev_api] listening on http://{HOST}:{PORT}")
    print("[dev_api] POST /api/triad  body: {\"input\": \"...\"}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
