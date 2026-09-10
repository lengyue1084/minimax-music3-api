# MiniMax-Music3 本地全量模型部署与 API 生成实战

本文记录在 Ubuntu 本机上从硬件检查、模型下载、环境准备到 HTTP API 生成歌曲的完整流程。所有硬件数据和生成结果均来自本机实际运行。

## 一、项目与机器配置

项目目录：/home/alone/workspace/minimax-music3-api
数据目录：/home/alone/workspace/minimax-music3-data
模型目录：/home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3

| 项目 | 实测配置 |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 Ti |
| 显存 | 16380 MiB，约 16GB |
| 驱动 | 580.173.02 |
| CUDA | NVIDIA-SMI 显示 13.0 |
| Compute Capability | 8.9 |
| 内存 | 31GiB，约 32GB |
| 磁盘 | KINGSTON SNV2S500G NVMe，约 465.8GB |
| Python | CPython 3.12.14，uv 管理 |
| 系统 | Ubuntu 22.04 系列 |
| API 端口 | 8190 |

硬件检查命令：

```bash
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
nvidia-smi --query-gpu=compute_cap --format=csv
free -h
swapon --show
df -hT /
lsblk -d -o NAME,MODEL,SIZE,ROTA,TRAN
ffmpeg -version | head -n 1
cmake --version | head -n 1
git lfs version
```

## 二、启用 swap

全量模型实际约 54GB，运行时还需要权重映射、临时张量和 offload 的额外内存。本机 32GB RAM 在未启用 swap 时曾被 Linux OOM killer 杀死。机器已有 32GB swap 文件 /swapfile-minimax-h3。

```bash
sudo swapon /swapfile-minimax-h3
swapon --show
free -h
```

swap 不会增加显存或提升画质，只提供内存余量；代价是速度变慢和增加 SSD 读写。长期启用可在 /etc/fstab 加入：

```text
/swapfile-minimax-h3 none swap sw 0 0
```

## 三、下载全量模型

首次下载使用 ModelScope 国内站点，不需要 Hugging Face：

```bash
cd /home/alone/workspace/minimax-music3-api
./scripts/02_download_full_model.sh
```

核心命令：

```bash
uv run --no-project --with modelscope==1.39.1 modelscope download MiniMax/MiniMax-Music3 \
  --revision master \
  --local-dir /home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3
```

断点续传时重复执行脚本即可。检查下载完整性：

```bash
MODEL_DIR=/home/alone/workspace/minimax-music3-data/models/MiniMax/MiniMax-Music3
test -f "$MODEL_DIR/configuration.json"
test -f "$MODEL_DIR/flowmatching_vae.pth"
test -f "$MODEL_DIR/language_model/model.safetensors.index.json"
test -f "$MODEL_DIR/transformer/diffusion_pytorch_model.safetensors.index.json"
find "$MODEL_DIR" -name "*.incomplete" -print
du -sh "$MODEL_DIR"
```

实测结果：约 54GB、89 个文件、没有 incomplete 文件。主要目录包括 language_model 约 16GB、Qwen 7B 约 18GB、Flow VAE 约 9.2GB、transformer 约 9.1GB。

## 四、创建环境并启动服务

```bash
cd /home/alone/workspace/minimax-music3-api
uv venv .venv --python 3.12
./scripts/01_prepare_env.sh
./scripts/03_start_api.sh
```

服务监听 0.0.0.0:8190。不要把 Uvicorn workers 设置为大于 1，否则可能加载多份模型。健康检查：

```bash
curl -sS http://127.0.0.1:8190/health | jq
curl -sS http://127.0.0.1:8190/v1/system/status | jq
```

配置文件 config.toml 开启了 cuda、bfloat16、自动 CPU offload 和语言模型 streaming offload；最长时长 300 秒，最多 8 个任务排队，实际只运行一个 GPU 任务。

## 五、请求字段

| 字段 | 类型 | 必填 | 默认或范围 | 说明 |
|---|---|---:|---|---|
| model | string | 否 | MiniMax/MiniMax-Music3 | 当前部署固定模型 |
| input | string | 是 | 1～40000 字符 | 歌词或文本 |
| instructions | string | 是 | 1～40000 字符 | 风格、速度、乐器、人声、情绪 |
| response_format | string | 否 | 仅 wav | 输出格式 |
| seed | integer | 否 | 默认 7，范围 0～4294967295 | 随机种子 |
| duration_seconds | number | 二选一 | 0～300 秒 | 目标时长，优先使用 |
| max_new_tokens | integer | 二选一 | 1～7500 | 按约 25 帧/秒换算 |
| stream | boolean | 否 | 仅支持 false | 当前不支持流式 |

结构标签应单独占一行，例如 [intro]、[verse]、[pre-chorus]、[chorus]、[bridge]、[outro]。请求时长是上限，模型可能提前结束。

## 六、提交完整歌词生成任务

```bash
curl -fsS -X POST http://127.0.0.1:8190/v1/audio/generations \
  -H "Content-Type: application/json" \
  -d @request.json | tee /tmp/music3-job.json | jq
JOB_ID=$(jq -r .id /tmp/music3-job.json)
```

request.json 的 input 填完整歌词，instructions 填完整风格描述；duration_seconds 例如设置为 120。返回 HTTP 202，包含 id、status、status_url 和 result_url。

## 七、查询、下载与验收

```bash
curl -sS http://127.0.0.1:8190/v1/jobs/$JOB_ID | jq
curl -fL -o result.wav http://127.0.0.1:8190/v1/jobs/$JOB_ID/result
ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,sample_rate,channels,bits_per_sample -of json result.wav
```

任务状态枚举：queued、running、succeeded、failed。日志位于 /home/alone/workspace/minimax-music3-data/logs/api.jsonl；请求原文和任务状态位于 jobs 目录。歌词不会嵌入 WAV。

## 八、真实生成结果

本次完整歌曲任务 ID：ecc21b69a6b0408ebac86bbcfd0d7546。

| 项目 | 实测结果 |
|---|---|
| 请求目标时长 | 120 秒 |
| 实际音频时长 | 112.303311 秒 |
| 推理耗时 | 4528.15 秒，约 75 分钟 |
| 文件大小 | 约 19MB |
| 编码 | pcm_s16le |
| 采样率 | 44100Hz |
| 声道 | 双声道 |
| 位深 | 16-bit |
| 文件 | /home/alone/workspace/minimax-music3-data/outputs/ecc21b69a6b0408ebac86bbcfd0d7546.wav |

下载：

```bash
curl -fL -o 爱而不得放手-完整歌曲.wav http://127.0.0.1:8190/v1/jobs/ecc21b69a6b0408ebac86bbcfd0d7546/result
```

## 九、排障记录

1. 首次加载曾尝试访问 Hugging Face；已将模型清单改为本地路径，并启用 local_files_only。
2. 未启用 swap 时进程被 OOM killer 终止；启用 32GB swap 后成功。
3. 推理完成后曾因 NumPy 数组调用 .float() 写 WAV 失败；代码现已兼容 Tensor 和 NumPy。
4. API 重启时会把遗留 running 任务标记为 failed，避免状态永久卡住。

## 十、部署结论（先行摘要）

本机 RTX 4060 Ti 16GB、32GB RAM 可以运行全量 MiniMax-Music3，但必须使用 CPU/offload 和 swap。单个 120 秒任务约 75 分钟，适合离线生成，不适合低延迟或高并发生产。


## 十一、详细请求示例

建议先把完整请求保存为 JSON 文件，避免在 shell 中处理大量中文和换行：

```bash
cat > /tmp/music3-request.json <<'JSON'
{
  "model": "MiniMax/MiniMax-Music3",
  "input": "[verse]\n测试歌词",
  "instructions": "华语流行抒情女声，清澈细腻，钢琴与弦乐，情绪克制。",
  "response_format": "wav",
  "duration_seconds": 10,
  "seed": 7,
  "stream": false
}
JSON
```

字段校验规则如下：`input` 和 `instructions` 必须提供且长度为 1～40000；`response_format` 只能是 `wav`；`seed` 范围是 0～4294967295；`duration_seconds` 大于 0 且不超过 300；`max_new_tokens` 范围是 1～7500；`stream` 当前只能为 `false`。

提交：

```bash
curl -fsS -X POST http://127.0.0.1:8190/v1/audio/generations \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/music3-request.json \
  | tee /tmp/music3-job.json | jq
JOB_ID=$(jq -r .id /tmp/music3-job.json)
```

## 十二、任务状态和响应结构

任务状态只有四种：`queued`、`running`、`succeeded`、`failed`。

```bash
curl -sS "http://127.0.0.1:8190/v1/jobs/$JOB_ID" | jq
```

返回字段：

| 字段 | 含义 |
|---|---|
| `id` | 任务 ID |
| `status` | 当前状态枚举 |
| `created_at` | 创建时间，UTC ISO-8601 |
| `started_at` | 开始处理时间 |
| `completed_at` | 完成或失败时间 |
| `elapsed_seconds` | 实际处理秒数 |
| `output` | 成功时的 WAV 绝对路径 |
| `error` | 失败时的错误文本 |

轮询时不要反复提交相同请求：

```bash
while :; do
  BODY=$(curl -fsS "http://127.0.0.1:8190/v1/jobs/$JOB_ID")
  echo "$BODY" | jq '{status,elapsed_seconds,error,output}'
  STATUS=$(echo "$BODY" | jq -r '.status')
  case "$STATUS" in
    succeeded|failed) break ;;
    *) sleep 10 ;;
  esac
done
```

## 十三、同步接口与异步接口的选择

短音频可以直接使用同步接口：

```bash
curl -fS -X POST http://127.0.0.1:8190/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"[verse]\n短暂旋律","instructions":"温暖钢琴独奏，纯音乐，不要人声。","duration_seconds":5,"seed":7,"response_format":"wav","stream":false}' \
  -o music3-sync.wav
```

同步接口会一直保持 HTTP 连接，直到模型完成；长音频不建议使用。异步接口返回任务 ID，适合 30 秒以上的生成，也方便客户端断线后继续查询。

## 十四、局域网调用

服务绑定 `0.0.0.0:8190` 时，部署机本地和局域网都能访问。部署机查看地址：

```bash
ip -4 route get 1.1.1.1
ss -ltnp | grep ':8190'
```

局域网客户端把 `127.0.0.1` 换成部署机 IP：

```bash
curl -sS http://部署机局域网IP:8190/health | jq
curl -sS http://部署机局域网IP:8190/v1/system/status | jq
```

如果连接失败，检查 Ubuntu 防火墙、路由和端口放行；当前接口没有鉴权，不应直接暴露到公网。

## 十五、PyCharm 调试

项目提供 `.idea/runConfigurations/MiniMax_Music3_API_Debug.xml`。PyCharm 中打开项目后，选择 `MiniMax Music3 API (Debug)`，确认解释器是 `.venv/bin/python`，然后点击 Debug。

等价命令：

```bash
PYTHONPATH="$PWD/src:$PWD/vendor/diffusers/src" \
  .venv/bin/python -m uvicorn minimax_music3_api.main:app \
  --host 0.0.0.0 --port 8190 --workers 1
```

可在 `main.py` 的任务提交/状态更新处，以及 `generator.py` 的模型加载/生成处设置断点。不要增加 worker 数量。

## 十六、日志、监控和清理

查看 JSON 日志：

```bash
tail -f /home/alone/workspace/minimax-music3-data/logs/api.jsonl
```

查看任务请求和状态：

```bash
cat /home/alone/workspace/minimax-music3-data/jobs/$JOB_ID.request.json | jq
cat /home/alone/workspace/minimax-music3-data/jobs/$JOB_ID.json | jq
```

查看输出占用：

```bash
du -sh /home/alone/workspace/minimax-music3-data/outputs
```

不要在任务运行期间删除对应 job JSON 或输出文件。确认任务已完成后，再按任务 ID 清理旧 WAV 和日志，避免磁盘逐渐耗尽。

## 十七、排障决策表

| 现象 | 判断 | 处理 |
|---|---|---|
| 服务端口拒绝连接 | API 未启动或端口不一致 | 检查 `ss -ltnp`，启动脚本和 `config.toml` |
| `model_path_exists=false` | 模型路径错误 | 检查 `config.toml` 和模型目录 |
| `Killed` | 系统 OOM killer | 启用 swap，停止其他模型，保持单 worker |
| `CUDA out of memory` | 显存不足 | 检查 `nvidia-smi`，保持 CPU offload |
| 访问 Hugging Face | 组件清单仍是远程路径 | 使用项目本地 manifest 和 `local_files_only` |
| 任务一直 running | 进程曾被杀或重启 | 当前启动恢复逻辑会标记为 failed |
| `numpy.ndarray has no attribute float` | 输出数组类型不兼容 | 当前 generator 已同时支持 Tensor/NumPy |
| HTTP 409 | 任务还未成功 | 继续轮询 |
| HTTP 422 | 字段、范围或时长不合法 | 按字段表修正 |
| HTTP 429 | 8 个等待槽已满 | 等待已有任务完成 |

## 十八、性能和并发边界

当前服务允许多个请求进入队列，但只运行一个 GPU 推理任务。增加并发不会加快单任务，增加 Uvicorn worker 还会复制模型并放大内存压力。本机实测 15 秒约 11 分钟、120 秒约 75 分钟，主要瓶颈是 16GB 显存、CPU/GPU 搬运和 swap。

因此建议：先用 5～10 秒请求验证；确认歌词、风格和模型结果后再提交长任务；长任务使用异步接口；运行期间持续观察 RAM、swap 和 GPU 利用率。

## 十九、完整复现清单

```bash
sudo swapon /swapfile-minimax-h3
cd /home/alone/workspace/minimax-music3-api
uv venv .venv --python 3.12
./scripts/01_prepare_env.sh
./scripts/02_download_full_model.sh  # 已下载完成时跳过
./scripts/03_start_api.sh

curl -sS http://127.0.0.1:8190/health | jq
curl -fsS -X POST http://127.0.0.1:8190/v1/audio/generations \
  -H 'Content-Type: application/json' \
  -d '{"input":"[verse]\n测试歌词","instructions":"温暖钢琴流行，女声，短试听。","duration_seconds":10,"seed":7,"response_format":"wav","stream":false}' \
  | tee /tmp/music3-job.json | jq
JOB_ID=$(jq -r .id /tmp/music3-job.json)
curl -sS http://127.0.0.1:8190/v1/jobs/$JOB_ID | jq
curl -fL -o result.wav http://127.0.0.1:8190/v1/jobs/$JOB_ID/result
ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,sample_rate,channels,bits_per_sample -of json result.wav
```

## 二十、附录：本次完整歌曲请求文件

下面的请求文件对应本文记录的真实任务。保存前请确认 JSON 中的换行使用 `\n`，不要把未转义的多行字符串直接放在双引号内。

文件路径示例：`/tmp/music3-full-request.json`

```json
{
  "model": "MiniMax/MiniMax-Music3",
  "input": "[intro]\n\n[verse]\n你说时间会把一切带走\n我却还站在我们走过的街口\n明知道你已经不再回头\n却还骗自己你只是暂时沉默\n\n[pre-chorus]\n我把想你的话写了又删\n把眼泪藏在每一个夜晚\n如果爱只能走到这里\n我是不是该学会遗憾\n\n[chorus]\n我爱你却不得不放手\n看着你走却不能挽留\n我们之间隔着的不是距离\n是你已经不再爱我的理由\n我爱你却只能放你自由\n把最深的眷恋藏在身后\n愿你以后有人温柔守候\n而我带着心痛学会放手\n\n[bridge]\n原来最痛的不是失去\n是明明相爱却不能继续\n我会把你还给人海\n也把自己还给自己\n\n[outro]\n再见了 我曾经的所有\n我还爱你\n但我要放手",
  "instructions": "华语流行抒情女声，女歌手独唱，音色清澈细腻、略带沙哑和脆弱感，中高音区情绪充沛，咬字清晰。歌曲主题是爱而不得，在深爱之后不得不放手，表现克制、遗憾、心碎与自我成全。伤感电影感流行抒情，慢速，约72 BPM，4/4拍。前奏使用孤独的钢琴和轻微环境氛围，主歌保持留白，加入柔和弦乐和低沉的大提琴；预副歌逐渐增强情绪；副歌旋律大幅展开，女声带有哭腔但不要嘶吼；桥段加入短暂的安静和呼吸感；尾奏回到钢琴，留下空旷、释然却仍然心痛的余韵。编曲以钢琴、弦乐、木吉他、低频鼓组和氛围合成器为主，层次渐进，避免过度电子化。",
  "response_format": "wav",
  "duration_seconds": 120,
  "seed": 20260909,
  "stream": false
}
```

校验 JSON 格式：

```bash
jq empty /tmp/music3-full-request.json
```

提交并保存任务信息：

```bash
curl -fsS -X POST http://127.0.0.1:8190/v1/audio/generations \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/music3-full-request.json \
  | tee /tmp/music3-full-job.json | jq
JOB_ID=$(jq -r .id /tmp/music3-full-job.json)
```

任务成功后，服务器上的原始文件位于：

```text
/home/alone/workspace/minimax-music3-data/outputs/<JOB_ID>.wav
```

客户端下载并保留原始文件名：

```bash
curl -fL \
  -o "music3-${JOB_ID}.wav" \
  "http://127.0.0.1:8190/v1/jobs/${JOB_ID}/result"
```

## 二十一、附录：按分钟级任务运行的注意事项

120 秒任务在本机实际耗时约 75 分钟。提交长任务前建议：

1. 确认 `swapon --show` 已列出 32GB swap。
2. 确认 `nvidia-smi` 中没有其他推理进程。
3. 先用 5～10 秒请求验证歌词、风格和音色。
4. 长任务使用异步接口，不要让同步 HTTP 连接长时间占用客户端。
5. 提交后只轮询同一个 `JOB_ID`，不要重复提交造成队列堆积。
6. 保留 `jobs/<JOB_ID>.json` 和 `jobs/<JOB_ID>.request.json`，便于复现和排查。

如果客户端断线，任务不会因此停止；重新连接服务后继续查询原任务 ID 即可。只有状态为 `succeeded` 且 `output` 文件存在时，才执行下载和 ffprobe 验收。

## 二十二、最终总结

这套部署证明了在 RTX 4060 Ti 16GB、32GB RAM 的 Ubuntu 主机上，可以使用 ModelScope 下载的全量 MiniMax-Music3 权重完成中文歌词歌曲生成。关键条件是：模型文件完整、Diffusers 组件使用本地路径、启用 CPU/offload、配置足够 swap、单 worker 串行推理，并在生成结束后检查音频编码和实际时长。当前实现已经覆盖请求日志、任务持久化、异常恢复和 Tensor/NumPy 两种输出格式，适合作为本地化部署和效果评估基线。
