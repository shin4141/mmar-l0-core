#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8787}"
HOST="${HOST:-127.0.0.1}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="${LOG_FILE:-/tmp/dev_api.log}"

echo "[restart] repo=${REPO_DIR}"
echo "[restart] stopping old process on ${HOST}:${PORT} ..."
PIDS="$(lsof -ti tcp:${PORT} || true)"
if [[ -n "${PIDS}" ]]; then
  echo "${PIDS}" | xargs kill -9 || true
  sleep 1
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
echo "[restart] log tail:"
tail -n 5 "${LOG_FILE}" || true
