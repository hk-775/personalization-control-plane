"""Product-wide safety and governance constants."""

from __future__ import annotations

DEFAULT_MIN_COHORT_SIZE = 50
DEFAULT_FAIRNESS_RATIO_FLOOR = 0.80
AUTO_LAUNCH_TRAFFIC_CAP = 5.0
HARD_EXPERIMENT_TRAFFIC_CAP = 25.0
GLOBAL_EXPERIMENT_TRAFFIC_CAP = 30.0
MAX_EXPLORATION_RATE = 0.10
RISKY_EXPLORATION_RATE = 0.03
MAX_CANDIDATES_PER_REQUEST = 100

ALLOWED_OBJECTIVES = frozenset(
    {
        "accessibility",
        "diversity",
        "freshness",
        "quality",
        "relevance",
        "safety",
        "satisfaction",
        "trust",
        "user_value",
    }
)

PROHIBITED_OPTIMIZATION_TERMS = frozenset(
    {
        "addiction",
        "compulsion",
        "conversion_at_any_cost",
        "dark_pattern",
        "deception",
        "dwell_time",
        "fear",
        "infinite_scroll",
        "outrage",
        "rage",
        "scarcity_pressure",
        "time_spent",
        "urgency",
    }
)

SENSITIVE_ATTRIBUTE_KEYS = frozenset(
    {
        "age",
        "biometric",
        "biometric_data",
        "citizenship",
        "disability",
        "ethnic_origin",
        "ethnicity",
        "gender",
        "gender_identity",
        "genetic_data",
        "health",
        "health_condition",
        "immigration_status",
        "medical",
        "national_origin",
        "political_affiliation",
        "political_opinion",
        "pregnancy",
        "race",
        "religion",
        "religious_belief",
        "sex",
        "sexual_orientation",
        "union_membership",
        "veteran_status",
    }
)

DIRECT_IDENTIFIER_KEYS = frozenset(
    {
        "address",
        "email",
        "email_address",
        "full_name",
        "government_id",
        "ip_address",
        "name",
        "phone",
        "phone_number",
        "postal_address",
    }
)

ALLOWED_OUTCOME_TYPES = frozenset(
    {
        "completion",
        "conversion",
        "dismiss",
        "hide",
        "report",
        "return",
        "save",
        "satisfaction",
    }
)

EXPERIMENT_STATES = frozenset(
    {
        "approved",
        "completed",
        "draft",
        "killed",
        "paused",
        "pending_approval",
        "review",
        "rolled_back",
        "running",
    }
)

TERMINAL_EXPERIMENT_STATES = frozenset({"completed", "killed", "rolled_back"})

DEFAULT_GUARDRAILS = {
    "min_quality_score": 0.72,
    "max_harm_rate": 0.02,
    "max_complaint_rate": 0.03,
    "min_fairness_ratio": DEFAULT_FAIRNESS_RATIO_FLOOR,
}
