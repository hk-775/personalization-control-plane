#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

export PYTHONDONTWRITEBYTECODE=1

uv run --locked --extra dev pytest tests -q --tb=short \
  --cov=personalization_control_plane \
  --cov-branch \
  --cov-report=term-missing
