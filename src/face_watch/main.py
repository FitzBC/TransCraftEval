from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from .api import create_app
from .opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer


def build_app() -> FastAPI:
    project_root = Path(__file__).resolve().parents[2]
    artifact_dir = project_root / "artifacts"
    showcase = os.getenv('FACE_WATCH_PROFILE') == 'showcase'
    bundle = project_root/'showcase_bundle'
    seed, catalog = None, None
    if showcase:
        seed, catalog = {'library_items':[], 'review_tasks':[]}, []
        # Preserve the catalog for workspaces created before explicit import existed.
        if (project_root/'data/showcase/state.json').is_file() and (bundle/'seed.json').is_file():
            from .showcase import load_bundle
            try:
                _, catalog = load_bundle(bundle)
            except (OSError, ValueError, KeyError):
                pass
        artifact_dir = artifact_dir/'showcase'
    video_path = Path(
        os.getenv("FACE_WATCH_VIDEO") or project_root / "examples" / "sample.mp4"
    )
    reference_path = Path(
        os.getenv("FACE_WATCH_REFERENCE") or project_root / "examples" / "reference.jpeg"
    )
    person_name = os.getenv("FACE_WATCH_PERSON", "朱时茂（许灵均）")
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
        'profile': 'showcase' if showcase else 'local',
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
        state_file=project_root / 'data' / ('showcase/state.json' if showcase else 'media_review_state.json'),
        seed_state=seed,
        bundled_dir=bundle if showcase and bundle.is_dir() else None,
        media_catalog=catalog,
        setup_enabled=showcase,
    )


app = build_app()
