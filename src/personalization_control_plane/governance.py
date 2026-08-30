"""Ethical and operational governance checks enforced by product behavior."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .constants import (
    ALLOWED_OBJECTIVES,
    AUTO_LAUNCH_TRAFFIC_CAP,
    DEFAULT_FAIRNESS_RATIO_FLOOR,
    DEFAULT_MIN_COHORT_SIZE,
    DIRECT_IDENTIFIER_KEYS,
    MAX_EXPLORATION_RATE,
    PROHIBITED_OPTIMIZATION_TERMS,
    RISKY_EXPLORATION_RATE,
    SENSITIVE_ATTRIBUTE_KEYS,
)


def normalize_key(value: str) -> str:
    """Normalize an input key for policy comparisons."""

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def prohibited_attribute_paths(value: Any, prefix: str = "") -> list[str]:
    """Return paths whose keys refer to sensitive or protected attributes."""

    matches: list[str] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = normalize_key(str(raw_key))
            path = f"{prefix}.{raw_key}" if prefix else str(raw_key)
            padded_key = f"_{key}_"
            if any(
                f"_{prohibited}_" in padded_key
                for prohibited in SENSITIVE_ATTRIBUTE_KEYS | DIRECT_IDENTIFIER_KEYS
            ):
                matches.append(path)
            matches.extend(prohibited_attribute_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]"
            matches.extend(prohibited_attribute_paths(child, path))
    return matches


def prohibited_optimization_terms(values: Iterable[str]) -> list[str]:
    """Return dark-pattern or manipulation objectives found in input names."""

    matches: set[str] = set()
    for raw_value in values:
        value = normalize_key(raw_value)
        for term in PROHIBITED_OPTIMIZATION_TERMS:
            if term in value:
                matches.add(raw_value)
    return sorted(matches)


def validate_policy_definition(
    *,
    objective_weights: dict[str, float],
    exploration_rate: float,
    allowed_candidate_features: list[str],
    constraints: dict[str, float],
) -> list[str]:
    """Return human-readable policy violations; an empty list means valid."""

    violations: list[str] = []
    normalized_objectives = {normalize_key(key): weight for key, weight in objective_weights.items()}
    prohibited = prohibited_optimization_terms(
        [*objective_weights, *allowed_candidate_features, *constraints]
    )
    if prohibited:
        violations.append(
            "dark-pattern optimization terms are prohibited: " + ", ".join(prohibited)
        )

    unknown = sorted(set(normalized_objectives) - ALLOWED_OBJECTIVES)
    if unknown:
        violations.append("unsupported objectives: " + ", ".join(unknown))

    total = sum(objective_weights.values())
    if abs(total - 1.0) > 1e-6:
        violations.append(f"objective weights must sum to 1.0; received {total:.6f}")

    if exploration_rate < 0.0 or exploration_rate > MAX_EXPLORATION_RATE:
        violations.append(
            f"exploration_rate must be between 0 and {MAX_EXPLORATION_RATE:.2f}"
        )

    sensitive = sorted(
        {
            feature
            for feature in [*objective_weights, *allowed_candidate_features, *constraints]
            if any(
                f"_{prohibited}_" in f"_{normalize_key(feature)}_"
                for prohibited in SENSITIVE_ATTRIBUTE_KEYS | DIRECT_IDENTIFIER_KEYS
            )
        }
    )
    if sensitive:
        violations.append(
            "sensitive attributes cannot be policy inputs: " + ", ".join(sensitive)
        )

    safety_floor = constraints.get("candidate_safety_floor", 0.0)
    if safety_floor < 0.0 or safety_floor > 1.0:
        violations.append("candidate_safety_floor must be between 0 and 1")

    return violations


@dataclass(frozen=True)
class RiskAssessment:
    level: str
    reasons: tuple[str, ...]
    requires_human_approval: bool


def assess_experiment_risk(
    *,
    traffic_percent: float,
    control_policy: dict[str, Any],
    treatment_policy: dict[str, Any],
) -> RiskAssessment:
    """Classify launch risk from traffic, exploration, and objective movement."""

    reasons: list[str] = []
    if traffic_percent > AUTO_LAUNCH_TRAFFIC_CAP:
        reasons.append(
            f"traffic {traffic_percent:.1f}% exceeds the "
            f"{AUTO_LAUNCH_TRAFFIC_CAP:.1f}% autonomous launch cap"
        )

    treatment_exploration = float(treatment_policy["exploration_rate"])
    if treatment_exploration > RISKY_EXPLORATION_RATE:
        reasons.append(
            f"exploration {treatment_exploration:.1%} exceeds the "
            f"{RISKY_EXPLORATION_RATE:.1%} low-risk threshold"
        )

    control_weights = control_policy["objective_weights"]
    treatment_weights = treatment_policy["objective_weights"]
    objective_names = set(control_weights) | set(treatment_weights)
    largest_delta = max(
        (
            abs(
                float(treatment_weights.get(name, 0.0))
                - float(control_weights.get(name, 0.0))
            )
            for name in objective_names
        ),
        default=0.0,
    )
    if largest_delta > 0.15:
        reasons.append(
            f"largest objective-weight change {largest_delta:.2f} exceeds 0.15"
        )

    if reasons:
        return RiskAssessment(
            level="high",
            reasons=tuple(reasons),
            requires_human_approval=True,
        )
    return RiskAssessment(level="low", reasons=(), requires_human_approval=False)


def evaluate_guardrails(
    metrics: dict[str, float],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Evaluate quality, harm, complaint, and fairness guardrails."""

    checks: list[dict[str, Any]] = []
    definitions = (
        ("quality_score", "min_quality_score", "minimum"),
        ("harm_rate", "max_harm_rate", "maximum"),
        ("complaint_rate", "max_complaint_rate", "maximum"),
        ("fairness_ratio", "min_fairness_ratio", "minimum"),
    )
    for metric_name, threshold_name, direction in definitions:
        if metric_name not in metrics:
            checks.append(
                {
                    "metric": metric_name,
                    "status": "missing",
                    "threshold": thresholds.get(threshold_name),
                }
            )
            continue
        value = float(metrics[metric_name])
        threshold = float(thresholds[threshold_name])
        passed = value >= threshold if direction == "minimum" else value <= threshold
        checks.append(
            {
                "metric": metric_name,
                "value": round(value, 6),
                "threshold": threshold,
                "direction": direction,
                "status": "pass" if passed else "fail",
            }
        )

    failures = [check for check in checks if check["status"] == "fail"]
    missing = [check for check in checks if check["status"] == "missing"]
    if failures:
        status = "failed"
    elif missing:
        status = "insufficient_data"
    else:
        status = "passed"
    return {"status": status, "checks": checks, "failure_count": len(failures)}


def evaluate_fairness(
    groups: list[dict[str, Any]],
    *,
    minimum_cohort_size: int = DEFAULT_MIN_COHORT_SIZE,
    ratio_floor: float = DEFAULT_FAIRNESS_RATIO_FLOOR,
) -> dict[str, Any]:
    """Evaluate aggregate group parity without exposing small-cohort metrics."""

    undersized = [
        {
            "group_key": group["group_key"],
            "sample_size": int(group["sample_size"]),
        }
        for group in groups
        if int(group["sample_size"]) < minimum_cohort_size
    ]
    if undersized:
        return {
            "status": "suppressed",
            "reason": "minimum_cohort_size",
            "minimum_cohort_size": minimum_cohort_size,
            "undersized_groups": undersized,
            "group_metrics": [],
        }

    rates = [float(group["positive_rate"]) for group in groups]
    qualities = [float(group["quality_score"]) for group in groups]
    maximum_rate = max(rates)
    minimum_rate = min(rates)
    ratio = 1.0 if maximum_rate == 0.0 else minimum_rate / maximum_rate
    minimum_quality = min(qualities)
    status = "passed" if ratio >= ratio_floor else "failed"
    return {
        "status": status,
        "fairness_ratio": round(ratio, 6),
        "ratio_floor": ratio_floor,
        "minimum_quality_score": round(minimum_quality, 6),
        "group_metrics": [
            {
                "group_key": group["group_key"],
                "sample_size": int(group["sample_size"]),
                "positive_rate": float(group["positive_rate"]),
                "quality_score": float(group["quality_score"]),
            }
            for group in groups
        ],
    }
