from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    model_path: Path
    device: str
    dtype: str
    cpu_offload: bool
    language_model_streaming: bool
    max_duration_seconds: float
    max_queue_size: int
    output_dir: Path
    job_dir: Path
    log_file: Path


def load_settings() -> Settings:
    default = Path(__file__).resolve().parents[2] / "config.toml"
    with Path(os.getenv("MUSIC3_CONFIG", default)).expanduser().open("rb") as stream:
        raw = tomllib.load(stream)
    return Settings(
        host=os.getenv("MUSIC3_HOST", raw["server"]["host"]),
        port=int(os.getenv("MUSIC3_PORT", raw["server"]["port"])),
        model_path=Path(os.getenv("MUSIC3_MODEL_PATH", raw["model"]["path"])).expanduser(),
        device=raw["model"]["device"], dtype=raw["model"]["dtype"],
        cpu_offload=bool(raw["model"]["cpu_offload"]),
        language_model_streaming=bool(raw["model"]["language_model_streaming"]),
        max_duration_seconds=float(raw["generation"]["max_duration_seconds"]),
        max_queue_size=int(raw["generation"]["max_queue_size"]),
        output_dir=Path(raw["storage"]["output_dir"]).expanduser(),
        job_dir=Path(raw["storage"]["job_dir"]).expanduser(),
        log_file=Path(raw["storage"]["log_file"]).expanduser(),
    )

