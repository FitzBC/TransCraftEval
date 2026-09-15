from pathlib import Path
from threading import Thread
from typing import Callable, Protocol
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles


class CreateJobRequest(BaseModel):
    video_path: Path
    reference_image_path: Path
    person_name: str
    run_async: bool = True


class Analyzer(Protocol):
    def analyze(
        self,
        video_path: Path,
        reference_image_path: Path,
        person_name: str,
        on_progress: Callable[[float], None],
    ) -> list[dict[str, object]]: ...


def create_app(
    analyzer: Analyzer | None = None,
    frontend_dir: Path | None = None,
    artifact_dir: Path | None = None,
    defaults: dict[str, str] | None = None,
    demo_media: dict[str, Path] | None = None,
) -> FastAPI:
    app = FastAPI(title="Face Watch Prototype")
    jobs: dict[str, dict[str, object]] = {}
    job_inputs: dict[str, CreateJobRequest] = {}

    @app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_job(request: CreateJobRequest) -> dict[str, str]:
        if not request.video_path.is_file():
            raise HTTPException(status_code=422, detail="video_path does not exist")
        if not request.reference_image_path.is_file():
            raise HTTPException(status_code=422, detail="reference_image_path does not exist")
        job_id = uuid4().hex
        job = {
            "job_id": job_id,
            "status": "queued",
            "person_name": request.person_name,
            "progress": 0.0,
            "events": [],
            "error": None,
        }
        jobs[job_id] = job
        job_inputs[job_id] = request
        if request.run_async and analyzer is not None:
            def execute_async() -> None:
                job["status"] = "running"

                def on_progress(value: float) -> None:
                    job["progress"] = max(0.0, min(1.0, value))

                try:
                    job["events"] = analyzer.analyze(
                        request.video_path,
                        request.reference_image_path,
                        request.person_name,
                        on_progress,
                    )
                    job["progress"] = 1.0
                    job["status"] = "completed"
                except Exception as exc:
                    job["status"] = "failed"
                    job["error"] = str(exc)

            Thread(target=execute_async, daemon=True).start()
        return {
            "job_id": job_id,
            "status": "queued",
            "person_name": request.person_name,
        }

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/api/settings")
    def get_settings() -> dict[str, str]:
        return defaults or {}

    @app.get("/demo/{media_kind}")
    def get_demo_media(media_kind: str) -> FileResponse:
        media_path = (demo_media or {}).get(media_kind)
        if media_path is None or not media_path.is_file():
            raise HTTPException(status_code=404, detail="demo media not found")
        return FileResponse(media_path)

    @app.post("/api/jobs/{job_id}/run", status_code=status.HTTP_202_ACCEPTED)
    def run_job(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        request = job_inputs.get(job_id)
        if job is None or request is None:
            raise HTTPException(status_code=404, detail="job not found")
        if analyzer is None:
            raise HTTPException(status_code=503, detail="analyzer is not configured")

        job["status"] = "running"

        def on_progress(value: float) -> None:
            job["progress"] = max(0.0, min(1.0, value))

        try:
            job["events"] = analyzer.analyze(
                request.video_path,
                request.reference_image_path,
                request.person_name,
                on_progress,
            )
            job["progress"] = 1.0
            job["status"] = "completed"
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
        return job

    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/artifacts", StaticFiles(directory=artifact_dir), name="artifacts")
    if frontend_dir is not None and frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app
