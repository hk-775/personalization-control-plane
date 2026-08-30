"""Deterministic allocation and transparent multi-objective candidate scoring."""

from __future__ import annotations

from hashlib import sha256
from typing import Any


def stable_fraction(*parts: str) -> float:
    """Map stable string parts to a reproducible number in [0, 1)."""

    digest = sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def deterministic_allocation(
    *,
    subject_id: str,
    experiment_id: str,
    traffic_percent: float,
    treatment_share: float,
    salt: str = "pcp-allocation-v1",
) -> dict[str, Any]:
    """Assign a subject to treatment, control, or holdout deterministically."""

    fraction = stable_fraction(salt, experiment_id, subject_id)
    enrolled_fraction = max(0.0, min(1.0, traffic_percent / 100.0))
    treatment_boundary = enrolled_fraction * treatment_share
    if fraction < treatment_boundary:
        variant = "treatment"
    elif fraction < enrolled_fraction:
        variant = "control"
    else:
        variant = "holdout"
    return {
        "variant": variant,
        "bucket": int(fraction * 10_000),
        "traffic_percent": traffic_percent,
        "treatment_share": treatment_share,
    }


def score_candidates(
    *,
    subject_id: str,
    request_id: str,
    candidates: list[dict[str, Any]],
    objective_weights: dict[str, float],
    exploration_rate: float,
    safety_floor: float,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Score and rank candidates with inspectable factor contributions."""

    ranked: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for candidate in candidates:
        features = candidate["features"]
        safety = float(features.get("safety", 1.0))
        if safety < safety_floor:
            excluded.append(
                {
                    "candidate_id": candidate["id"],
                    "reason": "candidate_safety_floor",
                    "value": safety,
                    "threshold": safety_floor,
                }
            )
            continue

        contributions: list[dict[str, Any]] = []
        base_score = 0.0
        for objective, weight in objective_weights.items():
            value = float(features.get(objective, 0.0))
            contribution = value * float(weight)
            base_score += contribution
            contributions.append(
                {
                    "objective": objective,
                    "value": round(value, 6),
                    "weight": round(float(weight), 6),
                    "contribution": round(contribution, 6),
                }
            )

        exploration_unit = stable_fraction(
            "pcp-exploration-v1",
            subject_id,
            request_id,
            candidate["id"],
        )
        exploration_adjustment = (exploration_unit - 0.5) * exploration_rate
        final_score = max(0.0, min(1.0, base_score + exploration_adjustment))
        tie_break = stable_fraction("pcp-tie-v1", request_id, candidate["id"])
        ranked.append(
            {
                "candidate_id": candidate["id"],
                "score": round(final_score, 6),
                "base_score": round(base_score, 6),
                "exploration_adjustment": round(exploration_adjustment, 6),
                "factors": sorted(
                    contributions,
                    key=lambda item: (-item["contribution"], item["objective"]),
                ),
                "metadata": candidate.get("metadata", {}),
                "_tie_break": tie_break,
            }
        )

    ranked.sort(key=lambda item: (-item["score"], item["_tie_break"], item["candidate_id"]))
    for position, item in enumerate(ranked[:limit], start=1):
        item["position"] = position
        item.pop("_tie_break", None)
    return ranked[:limit], excluded
