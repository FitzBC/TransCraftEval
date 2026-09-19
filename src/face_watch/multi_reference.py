"""Deterministic, multi-reference scoring for local face-review candidates.

This module deliberately stops before detection, tracking, or policy decisions
about media content.  It turns one already-normalized face embedding into
auditable identity candidates, leaving final human review outside the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


FusionStrategy = Literal["max", "topk_mean", "centroid"]
Decision = Literal["not_observed", "candidate", "confirmed", "ambiguous"]


def _normalize(vector: np.ndarray) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float32).reshape(-1)
    length = float(np.linalg.norm(value))
    if not np.isfinite(value).all() or not np.isfinite(length) or length == 0:
        raise ValueError("face embedding must be finite and nonzero")
    return value / length


@dataclass(frozen=True)
class ReferenceEmbedding:
    """One identity-verified reference embedding.

    ``cluster_id`` groups near-duplicate source images.  Only the best match
    from a cluster contributes to the Top-K confirmation score, preventing a
    burst of nearly identical photos from overwhelming one diverse reference.
    """

    embedding: np.ndarray
    quality_weight: float = 1.0
    cluster_id: str = "default"

    def __post_init__(self) -> None:
        if not 0 < self.quality_weight <= 1:
            raise ValueError("quality_weight must be in (0, 1]")
        object.__setattr__(self, "embedding", _normalize(self.embedding))


@dataclass(frozen=True)
class PersonGallery:
    person_id: str
    references: tuple[ReferenceEmbedding, ...]

    def __post_init__(self) -> None:
        if not self.references:
            raise ValueError("a person gallery needs at least one reference")


@dataclass(frozen=True)
class PersonPolicy:
    """Versioned, object-level thresholds selected from held-out labels."""

    candidate_threshold: float
    confirm_threshold: float
    margin_threshold: float
    confirmation_strategy: FusionStrategy = "topk_mean"

    def __post_init__(self) -> None:
        for field_name in ("candidate_threshold", "confirm_threshold", "margin_threshold"):
            value = getattr(self, field_name)
            if not -1 <= value <= 1:
                raise ValueError(f"{field_name} must be in [-1, 1]")
        if self.confirm_threshold < self.candidate_threshold:
            raise ValueError("confirm_threshold must not be below candidate_threshold")


@dataclass(frozen=True)
class PersonScore:
    person_id: str
    max_score: float
    topk_mean_score: float
    centroid_score: float
    recall_score: float
    confirmation_score: float


@dataclass(frozen=True)
class FaceDecision:
    decision: Decision
    primary: PersonScore | None
    runner_up: PersonScore | None
    margin: float | None


def score_person(feature: np.ndarray, gallery: PersonGallery, policy: PersonPolicy) -> PersonScore:
    """Score a face against one person using diversity-aware reference fusion."""
    feature = _normalize(feature)
    cluster_best: dict[str, tuple[float, float]] = {}
    cluster_refs: dict[str, list[ReferenceEmbedding]] = {}
    raw_scores: list[float] = []
    for reference in gallery.references:
        cluster_refs.setdefault(reference.cluster_id, []).append(reference)
        similarity = float(feature @ reference.embedding)
        raw_scores.append(similarity)
        current = cluster_best.get(reference.cluster_id)
        if current is None or similarity > current[0]:
            cluster_best[reference.cluster_id] = (similarity, reference.quality_weight)

    ranked_clusters = sorted(cluster_best.values(), reverse=True)
    selected = ranked_clusters[: min(2, len(ranked_clusters))]
    weighted_topk = sum(score * weight for score, weight in selected) / sum(
        weight for _, weight in selected
    )
    # Each duplicate cluster has a bounded contribution, including to the centroid.
    prototypes = [max(refs, key=lambda r: r.quality_weight) for refs in cluster_refs.values()]
    aggregate = sum(r.embedding*r.quality_weight for r in prototypes)
    centroid = _normalize(aggregate) if np.linalg.norm(aggregate) > 1e-7 else prototypes[0].embedding
    max_score = max(raw_scores)
    centroid_score = float(feature @ centroid)
    strategy_scores = {
        "max": max_score,
        "topk_mean": float(weighted_topk),
        "centroid": centroid_score,
    }
    return PersonScore(
        person_id=gallery.person_id,
        max_score=max_score,
        topk_mean_score=float(weighted_topk),
        centroid_score=centroid_score,
        recall_score=max(max_score, centroid_score),
        confirmation_score=strategy_scores[policy.confirmation_strategy],
    )


def decide_face(
    feature: np.ndarray,
    galleries: tuple[PersonGallery, ...],
    policies: dict[str, PersonPolicy],
) -> FaceDecision:
    """Assign an auditable candidate state without treating similarity as fact."""
    if not galleries:
        raise ValueError("at least one gallery is required")
    scored = [score_person(feature, gallery, policies[gallery.person_id]) for gallery in galleries]
    ranked = sorted(scored, key=lambda item: item.recall_score, reverse=True)
    primary = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    primary_policy = policies[primary.person_id]
    margin = primary.recall_score - runner_up.recall_score if runner_up else None
    if primary.recall_score < primary_policy.candidate_threshold:
        return FaceDecision("not_observed", None, runner_up, margin)
    if margin is not None and margin < primary_policy.margin_threshold:
        return FaceDecision("ambiguous", primary, runner_up, margin)
    if primary.confirmation_score >= primary_policy.confirm_threshold:
        return FaceDecision("confirmed", primary, runner_up, margin)
    return FaceDecision("candidate", primary, runner_up, margin)
