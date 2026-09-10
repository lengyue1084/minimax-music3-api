#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ ! -x .venv/bin/python ]]; then
  uv venv .venv --python 3.12
fi
# 旧 H3 环境已经包含兼容的 CUDA/Python 运行库；通过 .pth 只读复用，避免重复下载数 GB wheel。
SITE_PACKAGES=".venv/lib/python3.12/site-packages"
mkdir -p "$SITE_PACKAGES"
printf '%s\n' '/home/alone/workspace/minimax-h3/.venv/lib/python3.12/site-packages' \
  > "$SITE_PACKAGES/h3-compat-site-packages.pth"
echo "环境已创建：$PROJECT_ROOT/.venv"
echo "已复用旧环境的只读依赖；Diffusers 源码由 scripts/03_start_api.sh 从 vendor/diffusers 加载。"
