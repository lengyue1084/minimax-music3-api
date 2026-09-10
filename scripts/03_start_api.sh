#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export MUSIC3_CONFIG="${MUSIC3_CONFIG:-$PROJECT_ROOT/config.toml}"
export PYTHONPATH="$PROJECT_ROOT/src:$PROJECT_ROOT/vendor/diffusers/src${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m uvicorn minimax_music3_api.main:app --host "${MUSIC3_HOST:-0.0.0.0}" --port "${MUSIC3_PORT:-8190}" --workers 1
