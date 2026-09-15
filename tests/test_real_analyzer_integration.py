import os
from pathlib import Path

import cv2
import pytest
from fastapi.testclient import TestClient

from face_watch.api import create_app
from face_watch.opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer


@pytest.mark.integration
def test_matching_face_in_video_is_returned_as_an_event(tmp_path: Path) -> None:
    reference_value = os.getenv("TEST_REFERENCE_IMAGE")
    if not reference_value:
        pytest.skip("TEST_REFERENCE_IMAGE is not configured")
    reference = Path(reference_value)
    frame = cv2.imdecode(
        __import__("numpy").fromfile(reference, dtype="uint8"),
        cv2.IMREAD_COLOR,
    )
    assert frame is not None
    height, width = frame.shape[:2]
    video_path = tmp_path / "reference.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        5.0,
        (width, height),
    )
    for _ in range(10):
        writer.write(frame)
    writer.release()

    analyzer = OpenCvAnalyzer(
        AnalyzerConfig(
            detector_model=Path("models/face_detection_yunet_2023mar.onnx"),
            recognizer_model=Path("models/face_recognition_sface_2021dec.onnx"),
            output_dir=tmp_path / "artifacts",
            confirm_threshold=0.50,
            review_threshold=0.35,
        )
    )
    client = TestClient(create_app(analyzer=analyzer))
    created = client.post(
        "/api/jobs",
        json={
            "video_path": str(video_path),
            "reference_image_path": str(reference),
            "person_name": "测试人物",
            "run_async": False,
        },
    ).json()

    client.post(f"/api/jobs/{created['job_id']}/run")
    result = client.get(f"/api/jobs/{created['job_id']}").json()

    assert result["status"] == "completed", result["error"]
    assert len(result["events"]) == 1
    assert result["events"][0]["best_score"] > 0.95
    assert result["events"][0]["decision"] == "confirmed"
