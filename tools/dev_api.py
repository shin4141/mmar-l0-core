#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = 8787
MAX_THINK_SECONDS = 900

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

def _extract_before_section(compare_txt: str) -> str:
    txt = compare_txt or ""
    marker = "=== BEFORE (Single / seed) ==="
    idx = txt.find(marker)
    if idx < 0:
        return ""
    rest = txt[idx + len(marker):]
    end_m = "\n=== AFTER (MMAR / EXPAND) ==="
    end = rest.find(end_m)
    if end < 0:
        return rest.strip()
    return rest[:end].strip()

def _restore_before_section(compare_txt: str, before_snapshot: str) -> str:
    txt = compare_txt or ""
    marker_b = "=== BEFORE (Single / seed) ==="
    marker_a = "\n=== AFTER (MMAR / EXPAND) ==="
    i = txt.find(marker_b)
    if i < 0:
        return txt
    j = txt.find(marker_a, i + len(marker_b))
    if j < 0:
        return txt
    head = txt[: i + len(marker_b)]
    tail = txt[j:]
    return f"{head}\n{before_snapshot.strip()}\n{tail.lstrip()}"

def _derive_llm_mode(payload: dict) -> str:
    expand_txt = (payload.get("expand") or "").strip()
    if "\n(full)\n" in f"\n{expand_txt}\n" or expand_txt.endswith("\n(full)") or expand_txt.endswith("(full)"):
        return "full"
    return "lite"


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
    started_at = time.time()
    before_snapshot = _extract_before_section(_read_text(OUT_FILES["compare"]))
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "mode": "think", "started_at": started_at}

    def _worker():
        stop_monitor = threading.Event()

        def _monitor_expand():
            while not stop_monitor.is_set():
                expand_txt = _read_text(OUT_FILES["expand"]).strip()
                if expand_txt:
                    with JOBS_LOCK:
                        cur = JOBS.get(job_id, {})
                        if cur.get("status") in ("running", "slow"):
                            nxt = dict(cur)
                            nxt["expand"] = expand_txt
                            nxt["stage"] = "draft"
                            JOBS[job_id] = nxt
                    return
                stop_monitor.wait(0.4)

        monitor_thread = threading.Thread(target=_monitor_expand, daemon=True)
        monitor_thread.start()
        try:
            proc = _run_ask_triad(user_input, timeout_s=None, env_extra=None)
            if proc.returncode != 0:
                err = (proc.stderr or "")
                if len(err) > 1200:
                    err = err[:1200] + "..."
                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "status": "error",
                        "mode": "think",
                        "started_at": started_at,
                        "error": "subprocess_failed",
                        "returncode": proc.returncode,
                        "stderr_trunc": err,
                    }
                return
            payload, missing = _collect_outputs()
            if missing:
                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "status": "error",
                        "mode": "think",
                        "started_at": started_at,
                        "error": "missing_outputs",
                        "missing": missing,
                    }
                return
            if before_snapshot and isinstance(payload.get("compare"), str):
                payload["compare"] = _restore_before_section(payload["compare"], before_snapshot)
                OUT_FILES["compare"].write_text(payload["compare"], encoding="utf-8")
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "done",
                    "stage": "final",
                    "mode": "think",
                    "llm_mode": _derive_llm_mode(payload),
                    "started_at": started_at,
                    **payload,
                }
        except Exception as e:
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "error", "mode": "think", "started_at": started_at, "error": str(e)}
        finally:
            stop_monitor.set()

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
            started_at = job.get("started_at")
            elapsed_sec = 0.0
            if isinstance(started_at, (int, float)):
                elapsed_sec = max(0.0, time.time() - float(started_at))

            # Thinkは強制timeoutしない
            # elapsed_secは表示のみ

            out = dict(job)
            if out.get("status") in ("running", "slow") and elapsed_sec > MAX_THINK_SECONDS:
                out["status"] = "error"
                out["error"] = "timeout"
                out["hint"] = "max think time exceeded"
                with JOBS_LOCK:
                    JOBS[job_id] = dict(out)
            if out.get("status") == "running" and elapsed_sec > 20:
                out["status"] = "slow"
                out["hint"] = "still running"
            out["elapsed_sec"] = round(elapsed_sec, 1)
            self._send_json(200, out)
            return
        else:
            self._send_json(404, {"error": "not found"})
            return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/cancel/"):
            job_id = path.split("/api/cancel/", 1)[1].strip()
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    self._send_json(404, {"ok": False, "error": "job_not_found"})
                    return
                if job.get("status") in ("running", "slow"):
                    nxt = dict(job)
                    nxt["status"] = "cancelled"
                    nxt["hint"] = "user cancelled"
                    JOBS[job_id] = nxt
            self._send_json(200, {"ok": True, "status": "cancelled"})
            return
        if path != "/api/triad":
            self._send_json(404, {"error": "not found"})
            return

        try:
            qs = parse_qs(parsed.query)
            mode = (qs.get("mode", ["core"])[0] or "core").lower()
            if mode == "quick":
                mode = "core"
            if mode == "think":
                mode = "deep"
            if mode not in ("seed", "core", "deep"):
                mode = "core"
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

            if mode == "deep":
                job_id = _start_full_job(user_input)
                self._send_json(202, {"ok": True, "job_id": job_id, "mode": "deep"})
                return

            if mode == "seed":
                proc = _run_ask_triad(
                    user_input,
                    timeout_s=8,
                    env_extra={"MMAR_SEED_ONLY": "1", "MMAR_NO_LLM": "1", "MMAR_LLM_TIMEOUT": "4"},
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
                self._send_json(200, {"ok": True, "mode": "seed", **payload})
                return

            proc = _run_ask_triad(
                user_input,
                timeout_s=12,
                env_extra={"MMAR_CORE_ONLY": "1", "MMAR_LLM_TIMEOUT": "6"},
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
            self._send_json(504, {"ok": False, "error": "timeout", "mode": "core"})
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
