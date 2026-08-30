#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

export PYTHONDONTWRITEBYTECODE=1
export PYTEST_DEBUG_TEMPROOT="${PYTEST_DEBUG_TEMPROOT:-${TMPDIR:-/tmp}/personalization-control-plane-pytest}"
mkdir -p "${PYTEST_DEBUG_TEMPROOT}"

uv run --frozen --extra dev ruff check --no-cache src tests scripts
uv run --frozen --extra dev pytest tests -q --tb=short \
  --cov=personalization_control_plane \
  --cov-branch \
  --cov-report=term-missing
uv run --frozen --extra dev python scripts/validate_package.py

while IFS= read -r -d '' script; do
  bash -n "${script}"
done < <(find scripts -type f -name '*.sh' -print0)

echo "Package validation passed."
