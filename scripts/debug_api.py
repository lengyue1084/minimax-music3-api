"""PyCharm entry point for debugging the MiniMax-Music3 API."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Make the project packages importable when PyCharm launches this file directly.
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "vendor" / "diffusers" / "src"))

os.environ.setdefault("MUSIC3_CONFIG", str(project_root / "config.toml"))

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "minimax_music3_api.main:app",
        host=os.getenv("MUSIC3_HOST", "0.0.0.0"),
        port=int(os.getenv("MUSIC3_PORT", "8190")),
        workers=1,
    )
