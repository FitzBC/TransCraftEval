#!/usr/bin/env python3
"""Run a reproducible, local-only multi-reference face retrieval validation.

The script deliberately reports candidate evidence, not face-identification
accuracy.  Accuracy requires the blind labels exported in the result folder.
It decodes each local file sequentially, so transport streams with unreliable
random seeking are not treated as negative evidence.
"""

from __future__ import annotations

import argparse
import heapq
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from face_watch.opencv_analyzer import AnalyzerConfig, OpenCvAnalyzer
from face_watch.multi_reference import PersonGallery, PersonPolicy, ReferenceEmbedding, score_person


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "frontend_dist/assets/references/historical-validation"
DEFAULT_OUTPUT_DIR = ROOT / "output/multi_reference_validation"


@dataclass(frozen=True)
class ActorSpec:
    key: str
    name: str
    reference_files: tuple[str, ...]
    expected_media: tuple[str, ...]


ACTORS = (
    ActorSpec("tao_jin", "陶金", ("tao-jin.jpg", "tao-jin-film-still.jpg"), ("一江春水向东流",)),
    ActorSpec("shangguan_yunzhu", "上官云珠", ("shangguan-yunzhu.jpg", "shangguan-yunzhu-2.jpg"), ("一江春水向东流",)),
    ActorSpec("shu_xiuwen", "舒绣文", ("shu-xiuwen.jpg",), ("一江春水向东流",)),
    ActorSpec("liu_yuru", "刘玉茹", ("liu-yuru.jpg",), ("上甘岭",)),
    ActorSpec("yang_likun", "杨丽坤", ("yang-likun.jpg",), ("五朵金花",)),
    ActorSpec("wang_suya", "王苏娅", ("wang-suya.jpg",), ("五朵金花",)),
    ActorSpec("guo_lanying", "郭兰英", ("guo-lanying.jpg", "guo-lanying-young-performance.jpg"), ("东方红",)),
    ActorSpec("deng_yuhua", "邓玉华", ("deng-yuhua.jpg",), ("东方红",)),
    ActorSpec("zhang_weixin", "张伟欣", ("zhang-weixin.jpg",), ("乡音",)),
    ActorSpec("zhao_yue", "赵越", ("zhao-yue.jpg", "zhao-yue-2.jpg"), ("乡音",)),
)

EvidenceEntry = tuple[float, int, bytes, np.ndarray, dict[str, object]]


NEUTRAL_POLICY = PersonPolicy(
    candidate_threshold=-1.0,
    confirm_threshold=-1.0,
    margin_threshold=0.0,
)


def fusion_scores(feature: np.ndarray, gallery: PersonGallery) -> dict[str, float]:
    """Return the production scorer's component scores for offline re-scoring."""
    scored = score_person(feature, gallery, NEUTRAL_POLICY)
    return {
        "max": scored.max_score,
        "topk_mean": scored.topk_mean_score,
        "centroid": scored.centroid_score,
    }


def media_key(path: Path) -> str:
    for key in ("一江春水向东流", "上甘岭", "五朵金花", "东方红", "乡音"):
        if key in str(path):
            return key
    return path.stem


def find_media() -> list[Path]:
    media_root = ROOT / "媒资"
    return sorted(
        path
        for pattern in ("*.mp4", "*.ts", "*.mkv", "*.mov")
        for path in media_root.rglob(pattern)
    )


def read_reference_features(analyzer: OpenCvAnalyzer, actors: Iterable[ActorSpec]) -> dict[str, PersonGallery]:
    galleries: dict[str, PersonGallery] = {}
    for actor in actors:
        features: list[np.ndarray] = []
        for file_name in actor.reference_files:
            image_path = REFERENCE_DIR / file_name
            image = analyzer._read_image(image_path)
            faces = analyzer._detect_faces(image)
            if len(faces) != 1:
                raise ValueError(f"{actor.name} reference {image_path} has {len(faces)} detectable faces")
            features.append(analyzer._feature(image, faces[0]))
        galleries[actor.key] = PersonGallery(
            actor.key,
            tuple(
                ReferenceEmbedding(feature, cluster_id=file_name)
                for feature, file_name in zip(features, actor.reference_files, strict=True)
            ),
        )
    return galleries


def draw_candidate(frame: np.ndarray, face: np.ndarray) -> np.ndarray:
    canvas = frame.copy()
    x, y, width, height = (int(value) for value in face[:4])
    cv2.rectangle(canvas, (x, y), (x + width, y + height), (52, 211, 153), 3)
    return canvas


def scan_media(
    analyzer: OpenCvAnalyzer,
    media_path: Path,
    actors: tuple[ActorSpec, ...],
    galleries: dict[str, PersonGallery],
    sample_seconds: float,
    evidence_per_actor_media: int,
) -> tuple[list[dict[str, object]], dict[str, list[EvidenceEntry]]]:
    capture = cv2.VideoCapture(str(media_path))
    if not capture.isOpened():
        raise ValueError(f"unable to open media: {media_path}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 0:
        fps = 25.0
    frame_index = 0
    next_sample = 0.0
    selected_evidence: dict[str, list[EvidenceEntry]] = {}
    sequence = 0
    observations: list[dict[str, object]] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = frame_index / fps
            frame_index += 1
            if timestamp + 1e-6 < next_sample:
                continue
            next_sample += sample_seconds
            for face in analyzer._detect_faces(frame):
                feature = analyzer._feature(frame, face)
                per_actor = {
                    actor.key: fusion_scores(feature, galleries[actor.key])
                    for actor in actors
                }
                ranked = sorted(per_actor, key=lambda key: per_actor[key]["max"], reverse=True)
                first, second = ranked[:2]
                record: dict[str, object] = {
                    "media": media_key(media_path),
                    "timestamp_seconds": round(timestamp, 3),
                    "top1_actor": first,
                    "top1_name": next(actor.name for actor in actors if actor.key == first),
                    "top1_scores": {name: round(score, 5) for name, score in per_actor[first].items()},
                    "top2_actor": second,
                    "top2_name": next(actor.name for actor in actors if actor.key == second),
                    "top2_max": round(per_actor[second]["max"], 5),
                    "margin": round(per_actor[first]["max"] - per_actor[second]["max"], 5),
                    "all_scores": {
                        actor_key: {name: round(score, 5) for name, score in scores.items()}
                        for actor_key, scores in per_actor.items()
                    },
                }
                observations.append(record)
                # Keep a bounded top-N set for every actor, including actors that
                # are not the global Top-1 in the frame.  Blind-review images have
                # no actor label, score, or identifying filename.
                for actor in actors:
                    bucket = f"{media_key(media_path)}__{actor.key}"
                    score = per_actor[actor.key]["max"]
                    bucket_items = selected_evidence.setdefault(bucket, [])
                    if len(bucket_items) >= evidence_per_actor_media and score <= bucket_items[0][0]:
                        continue
                    encoded_ok, encoded = cv2.imencode(
                        ".jpg", draw_candidate(frame, face), [cv2.IMWRITE_JPEG_QUALITY, 88]
                    )
                    if not encoded_ok:
                        continue
                    sequence += 1
                    entry = (score, sequence, encoded.tobytes(), face.copy(), record)
                    if len(bucket_items) < evidence_per_actor_media:
                        heapq.heappush(bucket_items, entry)
                    else:
                        heapq.heapreplace(bucket_items, entry)
    finally:
        capture.release()
    return observations, selected_evidence


def summarize(
    observations: list[dict[str, object]], actors: tuple[ActorSpec, ...], thresholds: list[float]
) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    actor_by_key = {actor.key: actor for actor in actors}
    for actor in actors:
        for strategy in ("max", "topk_mean", "centroid"):
            for threshold in thresholds:
                expected = 0
                cross = 0
                ambiguous = 0
                for item in observations:
                    score = float(item["all_scores"][actor.key][strategy])
                    if score < threshold:
                        continue
                    ranked_score = item["top1_actor"] == actor.key
                    if ranked_score and float(item["margin"]) < 0.03:
                        ambiguous += 1
                    if item["media"] in actor_by_key[actor.key].expected_media:
                        expected += 1
                    else:
                        cross += 1
                summary.append(
                    {
                        "actor": actor.key,
                        "name": actor.name,
                        "references": len(actor.reference_files),
                        "strategy": strategy,
                        "threshold": threshold,
                        "expected_media_candidate_faces": expected,
                        "cross_media_candidate_faces": cross,
                        "ambiguous_top1_faces": ambiguous,
                    }
                )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-seconds", type=float, default=15.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--evidence-per-actor-media", type=int, default=3)
    parser.add_argument("--media", type=Path, action="append")
    args = parser.parse_args()
    if args.sample_seconds <= 0:
        raise SystemExit("--sample-seconds must be positive")

    output_dir = args.output_dir.resolve()
    evidence_dir = output_dir / "evidence"
    output_dir.mkdir(parents=True, exist_ok=True)
    analyzer = OpenCvAnalyzer(
        AnalyzerConfig(
            detector_model=ROOT / "models/face_detection_yunet_2023mar.onnx",
            recognizer_model=ROOT / "models/face_recognition_sface_2021dec.onnx",
            output_dir=output_dir / "unused_artifacts",
            max_detection_side=960,
        )
    )
    galleries = read_reference_features(analyzer, ACTORS)
    media_paths = args.media or find_media()
    if not media_paths:
        raise SystemExit("No local media files found; pass --media PATH.")

    all_observations: list[dict[str, object]] = []
    all_selected_evidence: dict[str, list[EvidenceEntry]] = {}
    for media_path in media_paths:
        print(f"Scanning sequentially: {media_path}", flush=True)
        observations, selected_evidence = scan_media(
            analyzer,
            media_path,
            ACTORS,
            galleries,
            args.sample_seconds,
            args.evidence_per_actor_media,
        )
        all_observations.extend(observations)
        all_selected_evidence.update(selected_evidence)

    # Retain full scores for offline re-scoring without another decode pass. The
    # score table is separated from the reviewer manifest so blind labels can be
    # created without exposing model recommendations.
    summary_rows = summarize(all_observations, ACTORS, [0.30, 0.35, 0.40, 0.45, 0.50])
    (output_dir / "machine_observations.json").write_text(
        json.dumps(all_observations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "proxy_summary.json").write_text(
        json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    blind_manifest: list[dict[str, object]] = []
    machine_evidence_manifest: list[dict[str, object]] = []
    evidence_index = 0
    for bucket, entries in sorted(all_selected_evidence.items()):
        for score, _, image_bytes, _, item in sorted(entries, reverse=True):
            evidence_index += 1
            relative_name = f"evidence/{evidence_index:04d}.jpg"
            output_path = output_dir / relative_name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            blind_manifest.append(
                {
                    "evidence_file": relative_name,
                    "label": "",  # target / other_known / unknown / no_face / unable_to_judge
                }
            )
            machine_evidence_manifest.append(
                {
                    "evidence_file": relative_name,
                    "candidate_bucket": bucket,
                    "candidate_score": round(score, 5),
                    "media": item["media"],
                    "timestamp_seconds": item["timestamp_seconds"],
                    "top1_actor": item["top1_actor"],
                }
            )
    (output_dir / "blind_review_manifest.json").write_text(
        json.dumps(blind_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "machine_evidence_manifest.json").write_text(
        json.dumps(machine_evidence_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"Wrote {len(all_observations)} detected-face observations, "
        f"{len(blind_manifest)} bounded evidence images to {output_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
