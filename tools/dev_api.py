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
MAX_THINK_SECONDS = 90
BOOT_AT = datetime.now(timezone.utc).isoformat()

REPO = Path(__file__).resolve().parents[1]
ASK_TRIAD = REPO / "tools" / "ask_triad.py"
INCOMING = REPO / "incoming"

OUT_FILES = {
    "compare": INCOMING / "out_compare.txt",
    "expand": INCOMING / "out_expand.txt",
    "diff": INCOMING / "out_diff.txt",
    "merge": INCOMING / "out_merge.txt",
}
DEEP_META = INCOMING / "deep_meta.json"
DECISION_CARD_LATEST = INCOMING / "decision_card_latest.json"

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


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
DEV_LOG = Path("/tmp/dev_api.log")


def _append_dev_log(msg: str) -> None:
    try:
        DEV_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DEV_LOG.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_latest_quality() -> tuple[dict, int]:
    try:
        if not DECISION_CARD_LATEST.exists():
            return {}, 0
        card = json.loads(DECISION_CARD_LATEST.read_text(encoding="utf-8", errors="replace"))
        q = card.get("quality") if isinstance(card, dict) and isinstance(card.get("quality"), dict) else {}
        total = int(q.get("total", 0) or 0)
        return q, total
    except Exception:
        return {}, 0


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Private-Network", "true")


def _collect_outputs(with_meta: bool = False) -> tuple[dict, list[str]]:
    missing = [k for k, p in OUT_FILES.items() if not p.exists()]
    if missing:
        return {}, missing
    payload = {k: _read_text(p) for k, p in OUT_FILES.items()}
    if with_meta and DEEP_META.exists():
        try:
            meta = json.loads(DEEP_META.read_text(encoding="utf-8", errors="replace"))
            if isinstance(meta, dict):
                if isinstance(meta.get("deep_status"), str):
                    payload["deep_status"] = meta["deep_status"]
                if isinstance(meta.get("fallback_reason"), str):
                    payload["fallback_reason"] = meta["fallback_reason"]
                if isinstance(meta.get("fallback_reason_secondary"), list):
                    payload["fallback_reason_secondary"] = meta["fallback_reason_secondary"]
                if isinstance(meta.get("missing_stages"), list):
                    payload["missing_stages"] = meta["missing_stages"]
                if isinstance(meta.get("missing_fields"), list):
                    payload["missing_fields"] = meta["missing_fields"]
                if isinstance(meta.get("domain"), str):
                    payload["domain"] = meta["domain"]
                if isinstance(meta.get("domain_guess"), dict):
                    payload["domain_guess"] = meta["domain_guess"]
                if isinstance(meta.get("domain_confidence"), (float, int)):
                    payload["domain_confidence"] = float(meta["domain_confidence"])
                if isinstance(meta.get("judgment_point_changes"), list):
                    payload["judgment_point_changes"] = meta["judgment_point_changes"]
                if isinstance(meta.get("quality"), dict):
                    payload["quality"] = meta["quality"]
                if isinstance(meta.get("quality_total"), (int, float)):
                    payload["quality_total"] = int(meta["quality_total"])
                if isinstance(meta.get("decision_card_path"), str):
                    payload["decision_card_path"] = meta["decision_card_path"]
                if isinstance(meta.get("timings"), dict):
                    payload["timings"] = meta["timings"]
        except Exception:
            pass
    if with_meta:
        if not isinstance(payload.get("deep_status"), str) or not payload.get("deep_status"):
            payload["deep_status"] = "schema_invalid"
            payload["fallback_reason"] = payload.get("fallback_reason") or "missing_deep_meta"
            payload["timings"] = payload.get("timings") if isinstance(payload.get("timings"), dict) else {}
            payload["warning"] = "build_or_version_mismatch"
    return payload, []

def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    txt = text or ""
    i = txt.find(start_marker)
    if i < 0:
        return ""
    rest = txt[i + len(start_marker):]
    j = rest.find(end_marker)
    if j < 0:
        return rest.strip()
    return rest[:j].strip()

def _replace_section(text: str, start_marker: str, end_marker: str, new_body: str) -> str:
    txt = text or ""
    i = txt.find(start_marker)
    if i < 0:
        return txt
    j = txt.find(end_marker, i + len(start_marker))
    if j < 0:
        return txt
    head = txt[: i + len(start_marker)]
    tail = txt[j:]
    return f"{head}\n{(new_body or '').strip()}\n{tail.lstrip()}"

def _extract_before_section(compare_txt: str) -> str:
    return _extract_section(
        compare_txt,
        "=== BEFORE (Single / seed) ===",
        "\n=== AFTER (MMAR / EXPAND) ===",
    )

def _restore_before_section(compare_txt: str, before_snapshot: str) -> str:
    return _replace_section(
        compare_txt,
        "=== BEFORE (Single / seed) ===",
        "\n=== AFTER (MMAR / EXPAND) ===",
        before_snapshot,
    )

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
        stdin=subprocess.DEVNULL,
        timeout=timeout_s,
        env=env,
    )


def _start_full_job(user_input: str) -> str:
    job_id = str(uuid.uuid4())
    started_at = time.time()
    before_snapshot = _extract_before_section(_read_text(OUT_FILES["compare"]))
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "mode": "think",
            "started_at": started_at,
            "before_snapshot": before_snapshot,
        }

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
            proc = _run_ask_triad(
                user_input,
                timeout_s=MAX_THINK_SECONDS,
                env_extra={"MMAR_LLM_TIMEOUT": "30", "MMAR_OPENAI_RETRIES": "1", "MMAR_TIME_BUDGET_S": "85"},
            )
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
                        "deep_status": "timeout" if "timed out" in err.lower() else "llm_error",
                        "fallback_reason": "ask_triad_timeout_or_error",
                        "timings": {},
                    }
                return
            payload, missing = _collect_outputs(with_meta=True)
            if missing:
                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "status": "error",
                        "mode": "think",
                        "started_at": started_at,
                        "error": "missing_outputs",
                        "missing": missing,
                        "deep_status": "schema_invalid",
                        "fallback_reason": "missing_outputs",
                        "timings": {},
                    }
                return
            snapshot = before_snapshot
            with JOBS_LOCK:
                cur = JOBS.get(job_id, {})
                if isinstance(cur.get("before_snapshot"), str):
                    snapshot = cur.get("before_snapshot", "")
            if snapshot:
                compare_now = _read_text(OUT_FILES["compare"])
                compare_restored = _restore_before_section(compare_now, snapshot)
                OUT_FILES["compare"].write_text(compare_restored, encoding="utf-8")
                payload["compare"] = compare_restored
                print("[deep] restored BEFORE snapshot", flush=True)
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "done",
                    "stage": "final",
                    "mode": "think",
                    "llm_mode": _derive_llm_mode(payload),
                    "after_mode": _derive_llm_mode(payload),
                    "started_at": started_at,
                    "before_snapshot": snapshot,
                    **payload,
                }
            q = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
            _append_dev_log(
                f"{datetime.now(timezone.utc).isoformat()} mode=deep status={payload.get('deep_status','-')} "
                f"quality_total={int(q.get('total', payload.get('quality_total', 0) or 0))} "
                f"quality={json.dumps(q, ensure_ascii=False)}"
            )
        except subprocess.TimeoutExpired:
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "error",
                    "mode": "think",
                    "started_at": started_at,
                    "error": "timeout",
                    "hint": "ask_triad timeout",
                    "deep_status": "timeout",
                    "fallback_reason": "ask_triad_timeout",
                    "timings": {},
                }
        except Exception as e:
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "error",
                    "mode": "think",
                    "started_at": started_at,
                    "error": str(e),
                    "deep_status": "llm_error",
                    "fallback_reason": "exception",
                    "timings": {},
                }
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
                    "boot_at": BOOT_AT,
                    "sha": GIT_SHA,
                    "mmar_core_only": os.getenv("MMAR_CORE_ONLY", "").strip() == "1",
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
                out["deep_status"] = "timeout"
                out["fallback_reason"] = "max_think_exceeded"
                out["timings"] = out.get("timings") or {}
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
                q, total = _read_latest_quality()
                _append_dev_log(
                    f"{datetime.now(timezone.utc).isoformat()} mode=seed status=ok quality_total={total} quality={json.dumps(q, ensure_ascii=False)}"
                )
                self._send_json(200, {"ok": True, "mode": "seed", **payload})
                return

            proc = _run_ask_triad(
                user_input,
                timeout_s=12,
                env_extra={"MMAR_CORE_ONLY": "1", "MMAR_NO_LLM": "1", "MMAR_LLM_TIMEOUT": "6"},
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
            q, total = _read_latest_quality()
            _append_dev_log(
                f"{datetime.now(timezone.utc).isoformat()} mode=core status=ok quality_total={total} quality={json.dumps(q, ensure_ascii=False)}"
            )

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
    print(
        f"[dev_api] SERVER_BOOT sha={GIT_SHA} boot_at={BOOT_AT} "
        f"MMAR_CORE_ONLY={os.getenv('MMAR_CORE_ONLY', '').strip() or '0'}"
    )
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
