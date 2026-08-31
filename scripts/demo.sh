#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from the official Astral distribution, then retry." >&2
  exit 1
fi

export PCP_HOST="${PCP_HOST:-127.0.0.1}"
export PCP_PORT="${PCP_PORT:-8102}"
export PCP_DB_PATH="${PCP_DB_PATH:-data/personalization-control-plane.db}"
export PYTHONDONTWRITEBYTECODE=1

exec uv run --locked --extra dev pcp-demo \
  --host "${PCP_HOST}" \
  --port "${PCP_PORT}" \
  --db "${PCP_DB_PATH}"
