from __future__ import annotations

from copy import deepcopy

from personalization_control_plane.engine import (
    deterministic_allocation,
    score_candidates,
)
from personalization_control_plane.seed import DEMO_CANDIDATES


def test_allocation_is_deterministic_and_bounded() -> None:
    first = deterministic_allocation(
        subject_id="subject-001",
        experiment_id="experiment-001",
        traffic_percent=5.0,
        treatment_share=0.5,
    )
    second = deterministic_allocation(
        subject_id="subject-001",
        experiment_id="experiment-001",
        traffic_percent=5.0,
        treatment_share=0.5,
    )

    assert first == second
    assert first["variant"] in {"treatment", "control", "holdout"}
    assert 0 <= first["bucket"] < 10_000


def test_candidate_scoring_is_deterministic_and_explainable() -> None:
    arguments = {
        "subject_id": "subject-001",
        "request_id": "request-001",
        "candidates": deepcopy(DEMO_CANDIDATES["commerce"]),
        "objective_weights": {
            "relevance": 0.4,
            "quality": 0.3,
            "user_value": 0.2,
            "safety": 0.1,
        },
        "exploration_rate": 0.02,
        "safety_floor": 0.7,
        "limit": 10,
    }

    first_ranked, first_excluded = score_candidates(**arguments)
    second_ranked, second_excluded = score_candidates(**arguments)

    assert first_ranked == second_ranked
    assert first_excluded == second_excluded
    assert len(first_ranked) == 3
    assert first_excluded == [
        {
            "candidate_id": "item-nova-supplement",
            "reason": "candidate_safety_floor",
            "value": 0.41,
            "threshold": 0.7,
        }
    ]
    assert first_ranked[0]["position"] == 1
    assert first_ranked[0]["factors"]
    assert {
        "objective",
        "value",
        "weight",
        "contribution",
    } <= set(first_ranked[0]["factors"][0])
