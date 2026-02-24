#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
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
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
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

    def do_POST(self) -> None:
        if self.path != "/api/triad":
            self._send_json(404, {"error": "not found"})
            return

        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n)
            data = json.loads(raw.decode("utf-8"))
            user_input = data.get("input", "") if isinstance(data, dict) else ""
            if not isinstance(user_input, str):
                self._send_json(400, {"error": "input must be string"})
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
                timeout=180,
            )
            if proc.returncode != 0:
                self._send_json(
                    500,
                    {
                        "error": "triad pipeline failed",
                        "returncode": proc.returncode,
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                    },
                )
                return

            payload = {k: _read_text(p) for k, p in OUT_FILES.items()}
            self._send_json(200, payload)

        except subprocess.TimeoutExpired:
            self._send_json(504, {"error": "triad pipeline timed out"})
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})


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
