# PyCharm 调试启动说明

项目已添加共享运行配置：`MiniMax Music3 API (Debug)`。

## 使用步骤

1. 在 PyCharm 打开项目目录：`/home/alone/workspace/minimax-music3-api`。
2. 确认项目解释器为：`$PROJECT_DIR$/.venv/bin/python`。
3. 在右上角运行配置下拉框选择 `MiniMax Music3 API (Debug)`。
4. 点击虫子图标 `Debug` 启动。
5. 首次生成会触发全量模型加载，耗时较长属于正常现象。

如果右上角仍显示旧配置，删除旧的 `MiniMax Music3 API (Debug)` 后重新加载项目，选择项目中 `.idea/runConfigurations/MiniMax_Music3_API_Debug.xml` 提供的同名配置。不要选择以 `debugpy` 为脚本名的配置；debugpy 是 PyCharm 的调试器，不是本项目的启动目标。

配置直接运行 `scripts/debug_api.py`，因此 PyCharm 的 debugpy 会得到明确的 Python 文件目标，不会出现 `Error: missing target`。配置等价于：

```bash
cd /home/alone/workspace/minimax-music3-api
PYTHONPATH="$PWD/src:$PWD/vendor/diffusers/src" \
  .venv/bin/python scripts/debug_api.py
```

## 调试断点

可在以下位置设置断点：

- `src/minimax_music3_api/main.py`：请求接收、任务排队、状态更新。
- `src/minimax_music3_api/generator.py`：模型加载和实际生成。
- `src/minimax_music3_api/config.py`：配置读取。

不要把 `--workers` 改成大于 `1`，否则可能加载多份全量模型并耗尽内存或显存。

## 启动后检查

```bash
curl -sS http://127.0.0.1:8190/health | jq
curl -sS http://127.0.0.1:8190/v1/system/status | jq
```

如果提示 8190 端口已被占用，先停止已经运行的 API 进程，或在运行配置和 `config.toml` 中同步修改端口。
