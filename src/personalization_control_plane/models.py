"""Pydantic request contracts for the control-plane API."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .constants import (
    DEFAULT_GUARDRAILS,
    HARD_EXPERIMENT_TRAFFIC_CAP,
    MAX_CANDIDATES_PER_REQUEST,
    MAX_EXPLORATION_RATE,
)

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=80,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$",
    ),
]
PseudonymousIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=64,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$",
    ),
]


class StrictModel(BaseModel):
    """Reject unknown fields so policy inputs cannot silently drift."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PolicyCreate(StrictModel):
    id: Identifier
    name: str = Field(min_length=3, max_length=120)
    domain: Identifier
    purpose: str = Field(min_length=3, max_length=120)
    objective_weights: dict[str, float] = Field(min_length=1, max_length=12)
    exploration_rate: float = Field(default=0.0, ge=0.0, le=MAX_EXPLORATION_RATE)
    allowed_candidate_features: list[Identifier] = Field(min_length=1, max_length=30)
    constraints: dict[str, float] = Field(default_factory=dict)
    actor: str = Field(default="api-operator", min_length=3, max_length=80)

    @field_validator("objective_weights")
    @classmethod
    def validate_weight_values(cls, value: dict[str, float]) -> dict[str, float]:
        if any(weight < 0.0 or weight > 1.0 for weight in value.values()):
            raise ValueError("objective weights must each be between 0 and 1")
        return value


class PolicyUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    objective_weights: dict[str, float] | None = Field(
        default=None,
        min_length=1,
        max_length=12,
    )
    exploration_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=MAX_EXPLORATION_RATE,
    )
    allowed_candidate_features: list[Identifier] | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )
    constraints: dict[str, float] | None = None
    actor: str = Field(default="api-operator", min_length=3, max_length=80)
    reason: str = Field(min_length=3, max_length=240)


class Candidate(StrictModel):
    id: Identifier
    features: dict[str, float] = Field(min_length=1, max_length=30)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("features")
    @classmethod
    def validate_features(cls, value: dict[str, float]) -> dict[str, float]:
        if any(score < 0.0 or score > 1.0 for score in value.values()):
            raise ValueError("candidate features must be normalized between 0 and 1")
        return value


class RankRequest(StrictModel):
    request_id: Identifier | None = None
    subject_id: PseudonymousIdentifier
    domain: Identifier
    purpose: str = Field(min_length=3, max_length=120)
    consent: bool
    cohort_id: Identifier
    policy_id: Identifier | None = None
    candidates: list[Candidate] = Field(
        min_length=1,
        max_length=MAX_CANDIDATES_PER_REQUEST,
    )
    context: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=50)


class ExperimentCreate(StrictModel):
    id: Identifier
    name: str = Field(min_length=3, max_length=120)
    domain: Identifier
    purpose: str = Field(min_length=3, max_length=120)
    hypothesis: str = Field(min_length=12, max_length=500)
    control_policy_id: Identifier
    treatment_policy_id: Identifier
    cohort_id: Identifier
    traffic_percent: float = Field(ge=0.1, le=HARD_EXPERIMENT_TRAFFIC_CAP)
    treatment_share: float = Field(default=0.5, gt=0.0, lt=1.0)
    guardrails: dict[str, float] = Field(
        default_factory=lambda: dict(DEFAULT_GUARDRAILS)
    )
    actor: str = Field(default="api-operator", min_length=3, max_length=80)


class ExperimentTransition(StrictModel):
    target_state: Literal[
        "review",
        "approved",
        "running",
        "paused",
        "completed",
        "rolled_back",
        "killed",
    ]
    actor: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=3, max_length=300)


class ApprovalDecision(StrictModel):
    decision: Literal["approved", "denied"]
    actor: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=3, max_length=300)


class ExposureEvent(StrictModel):
    event_id: Identifier
    decision_id: Identifier
    subject_id: PseudonymousIdentifier
    candidate_id: Identifier
    purpose: str = Field(min_length=3, max_length=120)
    occurred_at: str | None = None


class OutcomeEvent(StrictModel):
    event_id: Identifier
    exposure_event_id: Identifier
    outcome_type: Identifier
    value: float = Field(default=1.0, ge=0.0, le=1.0)
    purpose: str = Field(min_length=3, max_length=120)
    occurred_at: str | None = None


class GuardrailEvaluationRequest(StrictModel):
    experiment_id: Identifier
    sample_size: int = Field(ge=1)
    metrics: dict[str, float] = Field(min_length=1, max_length=12)
    actor: str = Field(default="metrics-monitor", min_length=3, max_length=80)


class FairnessGroup(StrictModel):
    group_key: Identifier
    sample_size: int = Field(ge=1)
    positive_rate: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=1.0)


class FairnessEvaluationRequest(StrictModel):
    experiment_id: Identifier
    groups: list[FairnessGroup] = Field(min_length=2, max_length=20)
    actor: str = Field(default="fairness-monitor", min_length=3, max_length=80)


class KillSwitchRequest(StrictModel):
    enabled: bool
    actor: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=5, max_length=300)


class DemoScenarioRequest(StrictModel):
    actor: str = Field(default="guided-demo", min_length=3, max_length=80)


class OperatorAction(StrictModel):
    actor: str = Field(min_length=3, max_length=80)
    reason: str = Field(min_length=3, max_length=300)
