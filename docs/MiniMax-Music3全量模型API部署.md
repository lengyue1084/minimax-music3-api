# MiniMax-Music3 全量模型 HTTP API 部署

## 结论

本项目下载 ModelScope 的 `MiniMax/MiniMax-Music3` 全量权重，并通过独立 FastAPI 提供 HTTP API。模型最长约 5 分钟；全量 Diffusers 管线原生输出 44.1kHz 立体声 WAV，官方 SGLang 参考服务会再重采样为 32kHz、16-bit、立体声 WAV。

本机 RTX 4060 Ti 16GB 无法把全量模型一次放入显存，因此服务使用官方 Diffusers 的自动 CPU offload 和语言模型逐层 streaming offload。单 GPU 只启动一个 worker，多个请求排队而不是并行推理。

本机配置：RTX 4060 Ti 16GB、32GB RAM、CUDA 13 驱动、NVMe 约 465GB。当前实际下载的全量仓库约 54GB，建议预留 100GB 以上。没有 swap 时不建议加载全量模型，建议配置 32～64GB swap。swap 会明显变慢并增加 SSD 写入，但正常使用不会损坏硬盘。

### 启用已有 swap

本机已创建 `/swapfile-minimax-h3`（32GB）。每次重启后如果 `swapon --show` 没有列出它，执行：

```bash
sudo swapon /swapfile-minimax-h3
free -h
swapon --show
```

若希望开机自动启用，可将下面一行加入 `/etc/fstab`（需要 sudo）：

```text
/swapfile-minimax-h3 none swap sw 0 0
```

未启用 swap 时加载全量模型很可能被 Linux OOM killer 直接终止；服务重启后会把遗留的 `running` 任务自动标记为 `failed`，并在任务 JSON 中记录进程中断原因。

## 目录

代码：`/home/alone/workspace/minimax-music3-api`

默认模型：`/home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3`

默认输出、任务、日志：`/home/alone/workspace/minimax-music3-data/{outputs,jobs,logs}`，端口 `8190`。

## 安装

先停止旧 H3/ComfyUI，释放显存并检查资源：

```bash
nvidia-smi
free -h
swapon --show
df -h /home/alone/workspace
```

首次安装和下载默认使用 ModelScope 国内站点 `https://www.modelscope.cn`，下载完成后的纯本地推理不需要联网。只有国内站点访问不稳定时，才考虑临时使用 VPN 或国际端点。

```bash
cd /home/alone/workspace/minimax-music3-api
chmod +x scripts/*.sh
./scripts/01_prepare_env.sh
```

项目已在 `vendor/diffusers` 固定保存包含 Music3 集成的官方 Diffusers 提交，启动时从本地源码加载，不需要重复从 GitHub 克隆。由于本机已有兼容的 CUDA 运行库，安装脚本通过 `.pth` 只读复用旧 H3 环境的 Python 包，避免再次下载数 GB 的 PyTorch CUDA wheel；代码和模型目录仍保持独立。

## 下载全量权重

确认至少有 70GB 磁盘空间后执行。脚本会要求输入 `DOWNLOAD`，中断后可重复执行并复用已完成文件：

```bash
cd /home/alone/workspace/minimax-music3-api
df -h /home/alone/workspace
mkdir -p /home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3
./scripts/02_download_full_model.sh
du -sh /home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3
```

脚本内部执行的核心下载命令等价于：

```bash
uv run --no-project --with modelscope==1.39.1 modelscope download MiniMax/MiniMax-Music3 \
  --revision master \
  --local-dir /home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3
```

如果中国 CDN 超时，可指定国际端点：

```bash
MODELSCOPE_ENDPOINT=https://www.modelscope.ai ./scripts/02_download_full_model.sh
```

下载时可以在另一个终端观察磁盘和文件增长：

```bash
watch -n 5 'du -sh /home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3 2>/dev/null || true'
```

如果网络中断，重新执行 `./scripts/02_download_full_model.sh` 即可。ModelScope 会跳过已完整下载的文件，继续补齐缺失文件；不要删除目标目录。下载完成后执行完整性检查：

```bash
MODEL_DIR=/home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3
test -f "$MODEL_DIR/configuration.json"
test -f "$MODEL_DIR/flowmatching_vae.pth"
test -f "$MODEL_DIR/dav.pth"
test -f "$MODEL_DIR/transformer/diffusion_pytorch_model.safetensors.index.json"
test -f "$MODEL_DIR/language_model/model.safetensors.index.json"
du -sh "$MODEL_DIR"
find "$MODEL_DIR" -type f | wc -l
```

只有上述检查全部通过，才进入 API 安装和启动步骤。若总大小明显小于 30GB 或关键文件缺失，说明下载尚未完成。

## 启动 API

```bash
cd /home/alone/workspace/minimax-music3-api
./scripts/03_start_api.sh
```

服务监听 `0.0.0.0:8190`。模型懒加载，第一次生成会加载全部组件，耗时较长是正常现象。不要把 Uvicorn workers 改成大于 1，否则可能产生多个模型副本。

## 健康检查

```bash
curl -sS http://127.0.0.1:8190/health | jq
curl -sS http://127.0.0.1:8190/v1/system/status | jq
```

## 异步接口

提交请求，字段为 `input`（歌词）、`instructions`（音乐描述）、`duration_seconds`（时长）、`seed`。也可用官方字段 `max_new_tokens`，模型每秒生成 25 帧，因此 250 帧约为 10 秒、750 帧约为 30 秒。接口返回 `id` 后查询 `/v1/jobs/{id}`，成功后从 `/v1/jobs/{id}/result` 下载 WAV。

```bash
curl -fsS -X POST http://127.0.0.1:8190/v1/audio/generations -H 'Content-Type: application/json' -d '{"model":"MiniMax/MiniMax-Music3","input":"[Verse]\\nMorning light over the quiet city\\n[Chorus]\\nWe begin again together","instructions":"Warm cinematic acoustic pop, intimate female vocal, fingerpicked guitar, soft piano, gentle drums.","response_format":"wav","duration_seconds":10,"seed":7,"stream":false}' | jq
```

查询和下载：

```bash
curl -sS http://127.0.0.1:8190/v1/jobs/JOB_ID | jq
curl -fL -o music3-JOB_ID.wav http://127.0.0.1:8190/v1/jobs/JOB_ID/result
ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,sample_rate,channels,bits_per_sample -of json music3-JOB_ID.wav
```

服务也兼容官方同步路径 `/v1/audio/speech`，但长音频建议使用异步接口。

## 日志、并发和验收

请求、响应、耗时、输出路径和异常记录在 `/home/alone/workspace/minimax-music3-data/logs/api.jsonl`。默认最多 8 个排队任务，同时只运行 1 个 GPU 推理任务，超过队列上限返回 HTTP 429。

建议按 10 秒、30 秒、60 秒、180 秒逐级测试，再尝试 300 秒。全量模型在本机单卡上会受 CPU-GPU 搬运限制，不适合低延迟生产服务。

`CUDA out of memory` 时停止其他 GPU 程序、确认 offload、降低时长并增加 swap；进程直接显示 `Killed` 通常表示系统内存耗尽；`Model path does not exist` 则检查 `config.toml` 或 `MUSIC3_MODEL_PATH`。
