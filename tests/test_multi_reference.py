from __future__ import annotations

import numpy as np
import pytest

from face_watch.multi_reference import (
    PersonGallery,
    PersonPolicy,
    ReferenceEmbedding,
    decide_face,
    score_person,
)


def policy(**overrides: object) -> PersonPolicy:
    values: dict[str, object] = {
        "candidate_threshold": 0.55,
        "confirm_threshold": 0.70,
        "margin_threshold": 0.08,
        "confirmation_strategy": "topk_mean",
    }
    values.update(overrides)
    return PersonPolicy(**values)  # type: ignore[arg-type]


def test_duplicate_reference_cluster_only_contributes_once_to_topk() -> None:
    gallery = PersonGallery(
        "person.a",
        (
            ReferenceEmbedding(np.array([1.0, 0.0, 0.0]), cluster_id="burst"),
            ReferenceEmbedding(np.array([0.99, 0.01, 0.0]), cluster_id="burst"),
            ReferenceEmbedding(np.array([0.0, 1.0, 0.0]), cluster_id="profile"),
        ),
    )
    scores = score_person(np.array([1.0, 0.0, 0.0]), gallery, policy())
    assert scores.max_score == pytest.approx(1.0)
    assert scores.topk_mean_score == pytest.approx(0.5, abs=0.01)


def test_any_good_reference_can_recall_but_not_auto_confirm() -> None:
    gallery = PersonGallery(
        "person.a",
        (
            ReferenceEmbedding(np.array([1.0, 0.0, 0.0]), cluster_id="front"),
            ReferenceEmbedding(np.array([0.0, 1.0, 0.0]), cluster_id="profile"),
        ),
    )
    decision = decide_face(
        np.array([1.0, 0.0, 0.0]),
        (gallery,),
        {"person.a": policy(candidate_threshold=0.8, confirm_threshold=0.9)},
    )
    assert decision.decision == "candidate"
    assert decision.primary is not None
    assert decision.primary.max_score == pytest.approx(1.0)
    assert decision.primary.topk_mean_score == pytest.approx(0.5)


def test_small_identity_margin_becomes_ambiguous() -> None:
    first = PersonGallery("person.a", (ReferenceEmbedding(np.array([1.0, 0.0])),))
    second = PersonGallery("person.b", (ReferenceEmbedding(np.array([0.99, 0.01])),))
    decision = decide_face(
        np.array([1.0, 0.0]),
        (first, second),
        {"person.a": policy(confirmation_strategy="max"), "person.b": policy(confirmation_strategy="max")},
    )
    assert decision.decision == "ambiguous"
    assert decision.primary is not None
    assert decision.primary.person_id == "person.a"


def test_unknown_face_is_not_forced_into_a_person_gallery() -> None:
    gallery = PersonGallery("person.a", (ReferenceEmbedding(np.array([1.0, 0.0])),))
    decision = decide_face(
        np.array([0.0, 1.0]),
        (gallery,),
        {"person.a": policy(confirmation_strategy="max")},
    )
    assert decision.decision == "not_observed"
    assert decision.primary is None


def test_duplicate_cluster_does_not_shift_centroid():
    a = ReferenceEmbedding(np.array([1., 0.]), cluster_id='a')
    b = ReferenceEmbedding(np.array([0., 1.]), cluster_id='b')
    first = score_person(np.array([1., 0.]), PersonGallery('p', (a,b)), policy())
    repeated = score_person(np.array([1., 0.]), PersonGallery('p', (a,a,a,b)), policy())
    assert first.centroid_score == pytest.approx(repeated.centroid_score)


def test_invalid_embedding_rejected():
    with pytest.raises(ValueError):
        ReferenceEmbedding(np.array([np.nan, 1.]))
