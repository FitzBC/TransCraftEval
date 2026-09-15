from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from .api import create_app
from .opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer


def build_app() -> FastAPI:
    project_root = Path(__file__).resolve().parents[2]
    artifact_dir = project_root / "artifacts"
    video_path = Path(os.getenv("FACE_WATCH_VIDEO", ""))
    reference_path = Path(os.getenv("FACE_WATCH_REFERENCE", ""))
    person_name = os.getenv("FACE_WATCH_PERSON", "测试人物（老许）")
    analyzer = OpenCvAnalyzer(
        AnalyzerConfig(
            detector_model=project_root / "models/face_detection_yunet_2023mar.onnx",
            recognizer_model=project_root / "models/face_recognition_sface_2021dec.onnx",
            output_dir=artifact_dir,
            detection_score_threshold=0.65,
            review_threshold=0.255,
            confirm_threshold=0.34,
            strong_single_threshold=0.45,
            max_detection_side=960,
        )
    )
    defaults = {
        "video_path": str(video_path) if video_path.is_file() else "",
        "reference_image_path": str(reference_path) if reference_path.is_file() else "",
        "person_name": person_name,
    }
    demo_media = {}
    if video_path.is_file():
        demo_media["video"] = video_path
    if reference_path.is_file():
        demo_media["reference"] = reference_path
    return create_app(
        analyzer=analyzer,
        frontend_dir=project_root / "frontend_dist",
        artifact_dir=artifact_dir,
        defaults=defaults,
        demo_media=demo_media,
    )


app = build_app()
