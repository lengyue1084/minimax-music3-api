# MiniMax-Music3 全量模型 API

独立的 MiniMax-Music3 本地 HTTP API 项目，面向 Ubuntu + NVIDIA GPU 的本地化部署测试，不修改旧 MiniMax-H3 或 ComfyUI 项目。

当前验证硬件：NVIDIA GeForce RTX 4060 Ti 16GB、32GB RAM、Ubuntu 22.04、Python 3.12、uv。全量模型约 54GB，不随 Git 仓库提交；按文档从 ModelScope 下载到本地后，服务通过官方 Diffusers Music3 管线生成 WAV。

## 快速开始

```bash
cd /home/alone/workspace/minimax-music3-api
uv venv .venv --python 3.12
./scripts/01_prepare_env.sh
./scripts/02_download_full_model.sh
sudo swapon /swapfile-minimax-h3
./scripts/03_start_api.sh
```

API 默认监听 `0.0.0.0:8190`，异步生成接口为 `POST /v1/audio/generations`。

详细部署过程见 [全量模型 API 部署文档](docs/MiniMax-Music3全量模型API部署.md)，字段和测试命令见 [API 字段与测试说明](docs/MiniMax-Music3_API字段与测试说明.md)，完整硬件到生成记录见 [实战博客](docs/MiniMax-Music3_从硬件检查到API生成实战博客.md)。

## 目录说明

- `src/minimax_music3_api/`：FastAPI 服务、任务队列、模型加载和配置读取。
- `scripts/`：环境准备、模型下载、命令行启动和 PyCharm 调试入口。
- `vendor/diffusers/`：固定的本地 Diffusers 源码，包含当前 Music3 集成。
- `docs/`：部署、API、PyCharm 和实测记录。

仓库不包含模型权重、虚拟环境、生成音频、运行日志和任务数据；这些文件由 `.gitignore` 排除。
