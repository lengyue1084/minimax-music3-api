#!/usr/bin/env bash
set -euo pipefail
MODEL_DIR="${MUSIC3_MODEL_PATH:-/home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3}"
MODELSCOPE_ENDPOINT="${MODELSCOPE_ENDPOINT:-https://www.modelscope.cn}"
mkdir -p "$MODEL_DIR"
df -h "$MODEL_DIR"
echo "即将下载约 54GB 全量模型到：$MODEL_DIR"
read -r -p "输入 DOWNLOAD 继续：" confirmation
[[ "$confirmation" == "DOWNLOAD" ]]
# 使用临时下载环境，避免项目的 Git Diffusers 依赖阻塞模型下载。
uv run --no-project --with modelscope==1.39.1 modelscope download \
  --endpoint "$MODELSCOPE_ENDPOINT" MiniMax/MiniMax-Music3 \
  --revision master --local-dir "$MODEL_DIR"
du -sh "$MODEL_DIR"
find "$MODEL_DIR" -type f | wc -l
