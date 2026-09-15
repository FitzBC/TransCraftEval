from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable
from uuid import uuid4

import cv2
import numpy as np


@dataclass(frozen=True)
class AnalyzerConfig:
    detector_model: Path
    recognizer_model: Path
    output_dir: Path
    detection_score_threshold: float = 0.70
    review_threshold: float = 0.35
    confirm_threshold: float = 0.50
    strong_single_threshold: float = 0.65
    event_gap_seconds: float = 1.25
    min_support_frames: int = 2
    max_detection_side: int = 960
    frame_stride: int = 1
    artifact_url_prefix: str = "/artifacts"


@dataclass
class Observation:
    timestamp: float
    score: float
    frame_jpeg: bytes
    face: np.ndarray


class OpenCvAnalyzer:
    def __init__(self, config: AnalyzerConfig) -> None:
        self.config = config
        if not config.detector_model.is_file():
            raise FileNotFoundError(f"Detector model not found: {config.detector_model}")
        if not config.recognizer_model.is_file():
            raise FileNotFoundError(f"Recognizer model not found: {config.recognizer_model}")
        self.detector = cv2.FaceDetectorYN.create(
            str(config.detector_model),
            "",
            (320, 320),
            config.detection_score_threshold,
            0.3,
            5000,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(
            str(config.recognizer_model),
            "",
        )
        # OpenCV's detector input size is mutable. Serialize prototype jobs so
        # simultaneous API requests cannot corrupt each other's inference state.
        self._analysis_lock = Lock()

    def analyze(
        self,
        video_path: Path,
        reference_image_path: Path,
        person_name: str,
        on_progress: Callable[[float], None],
    ) -> list[dict[str, object]]:
        with self._analysis_lock:
            return self._analyze(video_path, reference_image_path, person_name, on_progress)

    def _analyze(
        self,
        video_path: Path,
        reference_image_path: Path,
        person_name: str,
        on_progress: Callable[[float], None],
    ) -> list[dict[str, object]]:
        reference_image = self._read_image(reference_image_path)
        reference_faces = self._detect_faces(reference_image)
        if len(reference_faces) != 1:
            raise ValueError(
                "Reference image must contain exactly one detectable face; "
                f"found {len(reference_faces)}"
            )
        reference_feature = self._feature(reference_image, reference_faces[0])

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError(f"Unable to open video: {video_path}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not np.isfinite(fps) or fps <= 0:
            fps = 25.0
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        observations: list[Observation] = []
        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % self.config.frame_stride == 0:
                    timestamp = frame_index / fps
                    for face in self._detect_faces(frame):
                        feature = self._feature(frame, face)
                        score = float(np.dot(reference_feature, feature))
                        if score >= self.config.review_threshold:
                            encoded_ok, frame_jpeg = cv2.imencode(
                                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
                            )
                            if not encoded_ok:
                                raise ValueError("Unable to encode candidate evidence frame")
                            observations.append(
                                Observation(
                                    timestamp,
                                    score,
                                    frame_jpeg.tobytes(),
                                    face.copy(),
                                )
                            )
                frame_index += 1
                if frame_index % 25 == 0 and total_frames > 0:
                    on_progress(min(0.99, frame_index / total_frames))
        finally:
            capture.release()

        events = self._events_from_observations(observations, person_name)
        on_progress(1.0)
        return events

    def _read_image(self, path: Path) -> np.ndarray:
        data = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Unable to read image: {path}")
        return image

    def _detect_faces(self, image: np.ndarray) -> list[np.ndarray]:
        height, width = image.shape[:2]
        scale = min(1.0, self.config.max_detection_side / max(height, width))
        if scale < 1.0:
            detection_image = cv2.resize(
                image,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            detection_image = image
        detection_height, detection_width = detection_image.shape[:2]
        self.detector.setInputSize((detection_width, detection_height))
        _, faces = self.detector.detect(detection_image)
        if faces is None:
            return []
        result: list[np.ndarray] = []
        for detected_face in faces:
            face = detected_face.astype(np.float32, copy=True)
            if scale < 1.0:
                face[:14] /= scale
            result.append(face)
        return result

    def _feature(self, image: np.ndarray, face: np.ndarray) -> np.ndarray:
        aligned = self.recognizer.alignCrop(image, face)
        feature = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feature))
        if norm == 0:
            raise ValueError("Face recognizer returned a zero-length feature")
        return feature / norm

    def _events_from_observations(
        self,
        observations: list[Observation],
        person_name: str,
    ) -> list[dict[str, object]]:
        if not observations:
            return []
        groups: list[list[Observation]] = [[observations[0]]]
        for observation in observations[1:]:
            if observation.timestamp - groups[-1][-1].timestamp <= self.config.event_gap_seconds:
                groups[-1].append(observation)
            else:
                groups.append([observation])

        run_dir = self.config.output_dir / uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=True)
        events: list[dict[str, object]] = []
        for index, group in enumerate(groups, start=1):
            best = max(group, key=lambda item: item.score)
            decision = "review"
            if best.score >= self.config.strong_single_threshold or (
                best.score >= self.config.confirm_threshold
                and len(group) >= self.config.min_support_frames
            ):
                decision = "confirmed"
            evidence_path = run_dir / f"event_{index:03d}.jpg"
            self._write_evidence(evidence_path, best)
            events.append(
                {
                    "person_name": person_name,
                    "start_seconds": round(group[0].timestamp, 3),
                    "end_seconds": round(group[-1].timestamp, 3),
                    "best_score": round(best.score, 4),
                    "decision": decision,
                    "evidence_image": (
                        f"{self.config.artifact_url_prefix.rstrip('/')}/"
                        f"{run_dir.name}/{evidence_path.name}"
                    ),
                    "support_frames": len(group),
                }
            )
        return events

    def _write_evidence(self, path: Path, observation: Observation) -> None:
        frame = cv2.imdecode(
            np.frombuffer(observation.frame_jpeg, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if frame is None:
            raise ValueError(f"Unable to decode evidence image: {path}")
        x, y, width, height = (int(value) for value in observation.face[:4])
        cv2.rectangle(frame, (x, y), (x + width, y + height), (52, 211, 153), 3)
        cv2.putText(
            frame,
            f"score {observation.score:.3f}",
            (max(0, x), max(30, y - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (52, 211, 153),
            2,
            cv2.LINE_AA,
        )
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise ValueError(f"Unable to encode evidence image: {path}")
        encoded.tofile(path)
