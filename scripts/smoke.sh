#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pcp-smoke.XXXXXX")"
SMOKE_LOG="${SMOKE_DIR}/server.log"
SMOKE_DB="${SMOKE_DIR}/smoke.db"
SMOKE_PORT="${PCP_PORT:-8102}"
SERVER_PID=""

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [[ "${status}" -ne 0 ]] && [[ -s "${SMOKE_LOG}" ]]; then
    echo "Smoke server log:" >&2
    tail -n 80 "${SMOKE_LOG}" >&2
  fi
  rm -rf "${SMOKE_DIR}"
  exit "${status}"
}
trap cleanup EXIT

export PYTHONDONTWRITEBYTECODE=1

uv run --frozen --extra dev pcp-demo \
  --host 127.0.0.1 \
  --port "${SMOKE_PORT}" \
  --db "${SMOKE_DB}" >"${SMOKE_LOG}" 2>&1 &
SERVER_PID=$!

PCP_PORT="${SMOKE_PORT}" uv run --frozen --extra dev python scripts/smoke.py
echo "Smoke test passed on http://127.0.0.1:${SMOKE_PORT}."
