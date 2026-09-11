#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ ! -x .venv/bin/python ]]; then
  uv venv .venv --python 3.12
fi
echo "环境已创建：$PROJECT_ROOT/.venv"
echo "使用 Music3 项目自己的依赖；Diffusers 源码由 scripts/03_start_api.sh 从 vendor/diffusers 加载。"
