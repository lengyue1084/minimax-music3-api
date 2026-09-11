# MiniMax-Music3 API 字段与测试说明

服务地址：`http://127.0.0.1:8190`

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 服务、模型和队列检查 |
| GET | `/v1/system/status` | GPU 和队列状态 |
| POST | `/v1/audio/generations` | 异步提交 |
| GET | `/v1/jobs/{job_id}` | 查询任务 |
| GET | `/v1/jobs/{job_id}/result` | 下载 WAV |
| POST | `/v1/audio/speech` | 同步生成 WAV |

## 生成请求字段

请求头：`Content-Type: application/json`。异步和同步接口使用相同 JSON 字段。

| 字段 | 类型 | 必填 | 默认值 | 约束/枚举 | 说明 |
|---|---|---:|---|---|---|
| `model` | string | 否 | `MiniMax/MiniMax-Music3` | 当前部署固定该模型 | 模型标识 |
| `input` | string | 是 | 无 | 长度 1～40000 | 歌词或文本 |
| `instructions` | string | 是 | 无 | 长度 1～40000 | 风格、速度、乐器、人声、情绪 |
| `response_format` | string | 否 | `wav` | 枚举：`wav` | 当前只支持 WAV |
| `seed` | integer | 否 | 7 | 0～4294967295 | 随机种子 |
| `duration_seconds` | number | 二选一 | 无 | 大于 0 且不超过 300 | 目标时长，优先于 `max_new_tokens` |
| `max_new_tokens` | integer | 二选一 | 无 | 1～7500 | 按约 25 帧/秒换算时长 |
| `stream` | boolean | 否 | false | 仅支持 `false` | 不支持流式返回 |

时长规则：`duration_seconds` 优先；否则使用 `max_new_tokens / 25`；两者都未传时默认 10 秒。完整歌词不会自动决定音频长度。

## 歌词标签

标签单独占一行，例如：

```text
[intro]
[verse]
第一句歌词
[pre-chorus]
情绪增强
[chorus]
副歌歌词
[bridge]
桥段歌词
[outro]
```

常用标签：`[intro]`、`[verse]`、`[pre-chorus]`、`[chorus]`、`[hook]`、`[bridge]`、`[solo]`、`[instrumental]`、`[outro]`。

## 异步提交

```bash
curl -fsS -X POST http://127.0.0.1:8190/v1/audio/generations \
  -H 'Content-Type: application/json' \
  -d '{"model":"MiniMax/MiniMax-Music3","input":"[verse]\\n你说时间会把一切带走\\n[chorus]\\n我爱你却不得不放手","instructions":"华语流行抒情女声，清澈细腻、略带沙哑，约72 BPM，钢琴和弦乐，情绪克制而心碎。","response_format":"wav","duration_seconds":15,"seed":20260909,"stream":false}' | tee /tmp/music3-job.json | jq
JOB_ID=$(jq -r .id /tmp/music3-job.json)
```

响应 HTTP `202`，字段：`id`（任务 ID）、`status`（固定为 `queued`）、`status_url`、`result_url`。

## 查询与下载

```bash
curl -sS "http://127.0.0.1:8190/v1/jobs/$JOB_ID" | jq
curl -fL -o music3-$JOB_ID.wav \
  "http://127.0.0.1:8190/v1/jobs/$JOB_ID/result"
```

任务 `status` 枚举：`queued`、`running`、`succeeded`、`failed`。进度字段为 `stage`、`progress_current`、`progress_total` 和 `progress_percent`；`stage` 枚举为 `queued`、`loading`、`semantic`、`denoise`、`decode`、`saving`、`completed`、`failed`。其中 `semantic` 按真实生成帧计数，`denoise` 按真实扩散步数计数。其他字段：`created_at`、`started_at`、`completed_at`、`elapsed_seconds`、`output`、`error`。

```bash
curl -sS "http://127.0.0.1:8190/v1/jobs/$JOB_ID" \
  | jq '{status,stage,progress_current,progress_total,progress_percent,elapsed_seconds,error,output}'
```

验收：

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,codec_type,sample_rate,channels,bits_per_sample -of json music3-$JOB_ID.wav
```

正常结果为 `pcm_s16le`、44100Hz、双声道、16-bit WAV。

## 健康检查

```bash
curl -sS http://127.0.0.1:8190/health | jq
curl -sS http://127.0.0.1:8190/v1/system/status | jq
```

`/health` 返回 `status`（`ok`）、`model_loaded`、`model_path_exists`、`queued_jobs`；系统状态返回 `gpu` 和 `queue_size`。

## 错误码与日志

`404`：任务/结果不存在；`409`：任务尚未完成；`422`：字段或时长不合法；`429`：队列已满；`500`：推理或写文件失败。

日志：`/home/alone/workspace/minimax-music3-data/logs/api.jsonl`，每行一个 JSON，记录请求、响应、耗时、输出和异常。

## 同步接口

```bash
curl -fS -X POST http://127.0.0.1:8190/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"[verse]\\n短暂的旋律","instructions":"温暖钢琴独奏，纯音乐，不要人声。","duration_seconds":5,"seed":7,"response_format":"wav","stream":false}' \
  -o music3-sync.wav
```
