from pathlib import Path
from time import monotonic, sleep

from fastapi.testclient import TestClient

from face_watch.api import create_app


class ExampleAnalyzer:
    def analyze(self, video_path, reference_image_path, person_name, on_progress):
        on_progress(0.5)
        return [
            {
                "person_name": person_name,
                "start_seconds": 12.4,
                "end_seconds": 18.8,
                "best_score": 0.72,
                "decision": "confirmed",
                "evidence_image": "/evidence/job/frame.jpg",
            }
        ]


def test_user_can_create_a_video_face_search_job(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")

    client = TestClient(create_app())
    response = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "测试人物",
            "run_async": False,
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "job_id": response.json()["job_id"],
        "status": "queued",
        "person_name": "测试人物",
    }


def test_user_can_read_job_status_and_empty_results(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")
    client = TestClient(create_app())

    created = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "测试人物",
            "run_async": False,
        },
    ).json()

    response = client.get(f"/api/jobs/{created['job_id']}")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": created["job_id"],
        "status": "queued",
        "person_name": "测试人物",
        "progress": 0.0,
        "events": [],
        "error": None,
    }


def test_user_can_run_job_and_read_match_events(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")
    client = TestClient(create_app(analyzer=ExampleAnalyzer()))
    created = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "许灵均",
            "run_async": False,
        },
    ).json()

    run_response = client.post(f"/api/jobs/{created['job_id']}/run")
    result = client.get(f"/api/jobs/{created['job_id']}").json()

    assert run_response.status_code == 202
    assert result["status"] == "completed"
    assert result["progress"] == 1.0
    assert result["events"] == [
        {
            "person_name": "许灵均",
            "start_seconds": 12.4,
            "end_seconds": 18.8,
            "best_score": 0.72,
            "decision": "confirmed",
            "evidence_image": "/evidence/job/frame.jpg",
        }
    ]


def test_async_job_completes_without_blocking_creation(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video")
    reference.write_bytes(b"image")
    client = TestClient(create_app(analyzer=ExampleAnalyzer()))

    created = client.post(
        "/api/jobs",
        json={
            "video_path": str(video),
            "reference_image_path": str(reference),
            "person_name": "许灵均",
            "run_async": True,
        },
    )

    assert created.status_code == 202
    deadline = monotonic() + 1.0
    while monotonic() < deadline:
        result = client.get(f"/api/jobs/{created.json()['job_id']}").json()
        if result["status"] == "completed":
            break
        sleep(0.01)
    assert result["status"] == "completed"


def test_web_ui_and_evidence_are_served(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    artifacts = tmp_path / "artifacts"
    frontend.mkdir()
    artifacts.mkdir()
    (frontend / "index.html").write_text("<main>Face Watch</main>", encoding="utf-8")
    (artifacts / "evidence.jpg").write_bytes(b"evidence")
    client = TestClient(
        create_app(frontend_dir=frontend, artifact_dir=artifacts)
    )

    page = client.get("/")
    evidence = client.get("/artifacts/evidence.jpg")

    assert page.status_code == 200
    assert "Face Watch" in page.text
    assert evidence.status_code == 200
    assert evidence.content == b"evidence"


def test_web_ui_can_load_demo_defaults() -> None:
    client = TestClient(
        create_app(
            defaults={
                "video_path": "/demo/movie.mp4",
                "reference_image_path": "/demo/person.png",
                "person_name": "许灵均",
            }
        )
    )

    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "video_path": "/demo/movie.mp4",
        "reference_image_path": "/demo/person.png",
        "person_name": "许灵均",
    }


def test_web_ui_can_preview_configured_demo_media(tmp_path: Path) -> None:
    video = tmp_path / "movie.mp4"
    reference = tmp_path / "person.png"
    video.write_bytes(b"video-bytes")
    reference.write_bytes(b"image-bytes")
    client = TestClient(
        create_app(
            demo_media={"video": video, "reference": reference}
        )
    )

    video_response = client.get("/demo/video")
    reference_response = client.get("/demo/reference")

    assert video_response.status_code == 200
    assert video_response.content == b"video-bytes"
    assert reference_response.status_code == 200
    assert reference_response.content == b"image-bytes"
