#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8787}"
HOST="${HOST:-127.0.0.1}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="${LOG_FILE:-/tmp/dev_api.log}"

echo "[restart] repo=${REPO_DIR}"
EXPECTED_SHA="$(cd "${REPO_DIR}" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
OLD_PIDS="$(lsof -t -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
echo "[restart] stopping old process on ${HOST}:${PORT} ..."
if [[ -n "${OLD_PIDS}" ]]; then
  echo "${OLD_PIDS}" | xargs kill -9 || true
fi

for i in {1..25}; do
  CUR="$(lsof -t -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "${CUR}" ]]; then
    break
  fi
  sleep 0.2
done
if [[ -n "$(lsof -t -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)" ]]; then
  echo "[restart] failed: port ${PORT} still occupied"
  lsof -nP -iTCP:${PORT} -sTCP:LISTEN || true
  exit 1
fi

echo "[restart] starting dev_api ..."
cd "${REPO_DIR}"
nohup .venv/bin/python tools/dev_api.py >>"${LOG_FILE}" 2>&1 &
NEW_PID=$!
echo "[restart] started pid=${NEW_PID}"

echo "[restart] waiting for /api/health ..."
for i in {1..25}; do
  if curl -fsS "http://${HOST}:${PORT}/api/health" >/tmp/mmar_health.json 2>/dev/null; then
    break
  fi
  sleep 0.4
done

if [[ ! -s /tmp/mmar_health.json ]]; then
  echo "[restart] health check failed"
  exit 1
fi

echo "[restart] health:"
cat /tmp/mmar_health.json
echo
HEALTH_SHA="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path('/tmp/mmar_health.json')
try:
    d=json.loads(p.read_text())
except Exception:
    d={}
print(d.get('build_sha','-'))
PY
)"
HEALTH_PID="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path('/tmp/mmar_health.json')
try:
    d=json.loads(p.read_text())
except Exception:
    d={}
print(d.get('pid','-'))
PY
)"
echo "[restart] expected_sha=${EXPECTED_SHA} health_sha=${HEALTH_SHA} health_pid=${HEALTH_PID} old_pids=${OLD_PIDS:-none}"
echo
echo "[restart] log tail:"
tail -n 5 "${LOG_FILE}" || true
