"""FastAPI application with a persistent JSON job record and one GPU worker."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse

from .config import Settings, load_settings
from .generator import MusicGenerator
from .schemas import JobCreated, JobStatus, SpeechRequest


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JsonFormatter(logging.Formatter):
    """Write one machine-readable JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": utc_now().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        if hasattr(record, "data"):
            payload["data"] = record.data
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> logging.Logger:
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("minimax_music3_api")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = JsonFormatter()
        file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.propagate = False
    return logger


class JobManager:
    """Accept several queued jobs while executing only one GPU task at a time."""

    def __init__(self, settings: Settings, generator: MusicGenerator, logger: logging.Logger) -> None:
        self.settings = settings
        self.generator = generator
        self.logger = logger
        self.jobs: dict[str, JobStatus] = {}
        self.requests: dict[str, SpeechRequest] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=settings.max_queue_size)
        self.worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings.job_dir.mkdir(parents=True, exist_ok=True)
        self._recover_interrupted_jobs()
        self.worker_task = asyncio.create_task(self._worker(), name="music3-gpu-worker")

    def _recover_interrupted_jobs(self) -> None:
        """Mark jobs left running by a crashed/OOM-killed API process as failed."""
        for job_path in self.settings.job_dir.glob("*.json"):
            if job_path.name.endswith(".request.json"):
                continue
            try:
                job = JobStatus.model_validate_json(job_path.read_text(encoding="utf-8"))
            except Exception:
                self.logger.warning(
                    "unable to read persisted job during recovery",
                    extra={"event": "recovery_warning", "data": {"path": str(job_path)}},
                )
                continue
            if job.status != "running":
                continue
            job.status = "failed"
            job.error = "API process exited before the job completed (possible OOM kill or restart)."
            job.completed_at = utc_now()
            if job.started_at:
                job.elapsed_seconds = round((job.completed_at - job.started_at).total_seconds(), 3)
            self._persist(job)
            self.logger.warning(
                "recovered interrupted job",
                extra={"event": "job_recovered", "data": job.model_dump(mode="json")},
            )

    async def stop(self) -> None:
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def submit(self, request: SpeechRequest) -> JobStatus:
        if self.queue.full():
            raise HTTPException(status_code=429, detail="Generation queue is full")

        job_id = uuid.uuid4().hex
        job = JobStatus(id=job_id, status="queued", created_at=utc_now())
        self.jobs[job_id] = job
        self.requests[job_id] = request
        self._persist(job, request)
        await self.queue.put(job_id)
        self.logger.info(
            "generation request accepted",
            extra={"event": "request", "data": {"job": job_id, **request.model_dump()}},
        )
        return job

    def get(self, job_id: str) -> JobStatus:
        job = self.jobs.get(job_id)
        if job is None:
            record = self.settings.job_dir / f"{job_id}.json"
            if record.exists():
                job = JobStatus.model_validate_json(record.read_text(encoding="utf-8"))
                self.jobs[job_id] = job
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status == "running" and job.started_at:
            job.elapsed_seconds = round((utc_now() - job.started_at).total_seconds(), 3)
        return job

    @staticmethod
    def _overall_percent(stage: str, current: int, total: int) -> float:
        """Map real per-stage counters onto a monotonic overall percentage."""
        ratio = min(max(current / total, 0.0), 1.0) if total else 0.0
        ranges = {
            "loading": (0.0, 2.0),
            "semantic": (2.0, 80.0),
            "denoise": (80.0, 98.0),
            "decode": (98.0, 99.0),
            "saving": (99.0, 100.0),
        }
        start, end = ranges.get(stage, (0.0, 0.0))
        return round(start + (end - start) * ratio, 2)

    def _persist(self, job: JobStatus, request: SpeechRequest | None = None) -> None:
        job_path = self.settings.job_dir / f"{job.id}.json"
        job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        if request is not None:
            request_path = self.settings.job_dir / f"{job.id}.request.json"
            request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")

    async def _worker(self) -> None:
        while True:
            job_id = await self.queue.get()
            job = self.jobs[job_id]
            request = self.requests[job_id]
            started = time.monotonic()
            job.status = "running"
            job.started_at = utc_now()
            job.stage = "loading"
            self._persist(job)

            try:
                output_path = self.settings.output_dir / f"{job_id}.wav"
                progress_state = {"last_persisted": 0.0, "last_logged_bucket": -1}

                def update_progress(stage: str, current: int, total: int) -> None:
                    job.stage = stage
                    job.progress_current = current
                    job.progress_total = total
                    job.progress_percent = self._overall_percent(stage, current, total)
                    job.elapsed_seconds = round(time.monotonic() - started, 3)

                    now = time.monotonic()
                    bucket = int(job.progress_percent // 5)
                    should_persist = now - progress_state["last_persisted"] >= 2 or current == total
                    if should_persist:
                        self._persist(job)
                        progress_state["last_persisted"] = now
                    if bucket > progress_state["last_logged_bucket"] or current == total:
                        self.logger.info(
                            "generation progress",
                            extra={"event": "progress", "data": job.model_dump(mode="json")},
                        )
                        progress_state["last_logged_bucket"] = bucket

                await asyncio.to_thread(
                    self.generator.generate,
                    lyrics=request.input,
                    instructions=request.instructions,
                    duration_seconds=request.requested_duration(),
                    seed=request.seed,
                    output_path=output_path,
                    progress_callback=update_progress,
                )
                job.status = "succeeded"
                job.stage = "completed"
                job.progress_current = 1
                job.progress_total = 1
                job.progress_percent = 100.0
                job.output = str(output_path)
            except Exception as exc:
                job.status = "failed"
                job.stage = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                self.logger.exception(
                    "generation failed", extra={"event": "failure", "data": {"job": job_id}}
                )
            finally:
                job.completed_at = utc_now()
                job.elapsed_seconds = round(time.monotonic() - started, 3)
                self._persist(job)
                self.logger.info(
                    "generation completed",
                    extra={"event": "response", "data": job.model_dump(mode="json")},
                )
                self.requests.pop(job_id, None)
                self.queue.task_done()


settings = load_settings()
logger = configure_logging(settings)
generator = MusicGenerator(settings)
manager = JobManager(settings, generator, logger)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await manager.start()
    yield
    await manager.stop()


app = FastAPI(title="MiniMax-Music3 Full Model API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": generator.loaded,
        "model_path_exists": settings.model_path.exists(),
        "queued_jobs": manager.queue.qsize(),
    }


@app.get("/v1/system/status")
async def system_status() -> dict:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=5)
    return {"gpu": result.stdout.strip(), "queue_size": manager.queue.qsize()}


@app.post("/v1/audio/generations", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_generation(payload: SpeechRequest, request: Request) -> JobCreated:
    if payload.requested_duration() > settings.max_duration_seconds:
        raise HTTPException(status_code=422, detail="Requested duration exceeds server limit")
    job = await manager.submit(payload)
    base = str(request.base_url).rstrip("/")
    return JobCreated(
        id=job.id,
        status="queued",
        status_url=f"{base}/v1/jobs/{job.id}",
        result_url=f"{base}/v1/jobs/{job.id}/result",
    )


@app.post("/v1/audio/speech")
async def speech(payload: SpeechRequest) -> FileResponse:
    """Synchronous compatibility endpoint; use generations for long requests."""
    job = await manager.submit(payload)
    while True:
        current = manager.get(job.id)
        if current.status == "succeeded":
            return FileResponse(current.output, media_type="audio/wav", filename=f"{job.id}.wav")
        if current.status == "failed":
            raise HTTPException(status_code=500, detail=current.error)
        await asyncio.sleep(1)


@app.get("/v1/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    return manager.get(job_id)


@app.get("/v1/jobs/{job_id}/result")
async def get_result(job_id: str) -> FileResponse:
    job = manager.get(job_id)
    if job.status != "succeeded" or not job.output:
        raise HTTPException(status_code=409, detail=f"Job status is {job.status}")
    output = Path(job.output)
    if not output.is_file():
        raise HTTPException(status_code=404, detail="Result file is missing")
    return FileResponse(output, media_type="audio/wav", filename=output.name)


def run() -> None:
    import uvicorn

    uvicorn.run("minimax_music3_api.main:app", host=settings.host, port=settings.port, workers=1)
