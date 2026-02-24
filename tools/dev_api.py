#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


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
        if self.path != "/api/health":
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(
            200,
            {
                "ok": True,
                "cwd": str(REPO),
                "python": sys.executable,
                "time": datetime.now(timezone.utc).isoformat(),
            },
        )

    def do_POST(self) -> None:
        if self.path != "/api/triad":
            self._send_json(404, {"error": "not found"})
            return

        try:
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

            cmd = [
                sys.executable,
                str(ASK_TRIAD),
                "--tab",
                "expand",
                user_input,
            ]
            proc = subprocess.run(
                cmd,
                cwd=str(REPO),
                capture_output=True,
                text=True,
                timeout=30,
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
                        "stderr": err,
                    },
                )
                return

            missing = [k for k, p in OUT_FILES.items() if not p.exists()]
            if missing:
                self._send_json(500, {"ok": False, "error": "missing_outputs", "missing": missing})
                return

            payload = {k: _read_text(p) for k, p in OUT_FILES.items()}
            self._send_json(200, {"ok": True, **payload})

        except subprocess.TimeoutExpired:
            self._send_json(504, {"ok": False, "error": "subprocess_timeout"})
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
