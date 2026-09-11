from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class SpeechRequest(BaseModel):
    model: str = "MiniMax/MiniMax-Music3"
    input: str = Field(min_length=1, max_length=40000)
    instructions: str = Field(min_length=1, max_length=40000)
    response_format: Literal["wav"] = "wav"
    seed: int = Field(default=7, ge=0, le=2**32 - 1)
    duration_seconds: float | None = Field(default=None, gt=0, le=300.0)
    max_new_tokens: int | None = Field(default=None, ge=1, le=7500)
    stream: Literal[False] = False

    def requested_duration(self) -> float:
        """Prefer seconds; otherwise convert official API frames at 25 fps."""
        if self.duration_seconds is not None:
            return self.duration_seconds
        if self.max_new_tokens is not None:
            return self.max_new_tokens / 25.0
        return 10.0


class JobCreated(BaseModel):
    id: str
    status: Literal["queued"]
    status_url: str
    result_url: str


class JobStatus(BaseModel):
    id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float | None = None
    stage: Literal["queued", "loading", "semantic", "denoise", "decode", "saving", "completed", "failed"] = "queued"
    progress_current: int = Field(default=0, ge=0)
    progress_total: int = Field(default=0, ge=0)
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    output: str | None = None
    error: str | None = None
