"""Application service implementing governed recommendation and experiment behavior."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from .constants import (
    ALLOWED_OUTCOME_TYPES,
    DEFAULT_FAIRNESS_RATIO_FLOOR,
    DEFAULT_MIN_COHORT_SIZE,
    GLOBAL_EXPERIMENT_TRAFFIC_CAP,
    TERMINAL_EXPERIMENT_STATES,
)
from .engine import deterministic_allocation, score_candidates
from .governance import (
    assess_experiment_risk,
    evaluate_fairness,
    evaluate_guardrails,
    normalize_key,
    prohibited_attribute_paths,
    validate_policy_definition,
)
from .models import (
    ApprovalDecision,
    DemoScenarioRequest,
    ExperimentCreate,
    ExperimentTransition,
    ExposureEvent,
    FairnessEvaluationRequest,
    GuardrailEvaluationRequest,
    KillSwitchRequest,
    OutcomeEvent,
    PolicyCreate,
    PolicyUpdate,
    RankRequest,
)
from .seed import DEMO_CANDIDATES
from .storage import Database, canonical_json, utc_now


class ControlPlaneError(Exception):
    """Typed service error converted into the public API error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _subject_hash(subject_id: str) -> str:
    return sha256(f"pcp-subject-v1:{subject_id}".encode()).hexdigest()


def _identifier(prefix: str, *parts: str, length: int = 18) -> str:
    digest = sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


class ControlPlane:
    """Canonical local control-plane service."""

    def __init__(self, database: Database) -> None:
        self.db = database
        self.db.initialize()

    @property
    def governance(self) -> dict[str, Any]:
        return self.db.get_setting("governance", {})

    @property
    def minimum_cohort_size(self) -> int:
        return int(
            self.governance.get("minimum_cohort_size", DEFAULT_MIN_COHORT_SIZE)
        )

    def health(self) -> dict[str, Any]:
        chain = self.db.verify_audit_chain()
        kill_switch = self.db.get_setting("kill_switch", {"enabled": False})
        return {
            "status": "healthy" if chain["valid"] else "degraded",
            "service": "personalization-control-plane",
            "version": "0.1.0",
            "time": utc_now(),
            "storage": {"driver": "sqlite", "status": "ready"},
            "audit_chain": chain,
            "kill_switch": kill_switch,
            "external_dependencies": [],
        }

    def portfolio(self) -> dict[str, Any]:
        experiments = self.db.list_experiments()
        approvals = self.db.list_approvals()
        counts = self.db.counts()
        state_counts = Counter(experiment["status"] for experiment in experiments)
        domains = sorted({experiment["domain"] for experiment in experiments})
        metrics = self.list_metrics()
        visible_metrics = [metric for metric in metrics if metric["privacy_status"] == "visible"]
        return {
            "summary": {
                "domains": len(domains),
                "active_experiments": state_counts["running"],
                "pending_approvals": sum(
                    approval["status"] == "pending" for approval in approvals
                ),
                "active_policies": sum(
                    policy["status"] == "active" for policy in self.db.list_policies()
                ),
                "recorded_decisions": counts["decisions"],
                "audit_records": counts["audit_log"],
            },
            "domains": domains,
            "experiment_states": dict(sorted(state_counts.items())),
            "kill_switch": self.db.get_setting("kill_switch", {"enabled": False}),
            "governance": self.governance,
            "metric_health": {
                "visible": len(visible_metrics),
                "suppressed": len(metrics) - len(visible_metrics),
            },
            "fictional_demo_data": True,
        }

    def list_policies(self) -> list[dict[str, Any]]:
        return self.db.list_policies()

    def get_policy(self, policy_id: str) -> dict[str, Any]:
        policy = self.db.get_policy(policy_id)
        if policy is None:
            raise ControlPlaneError(404, "policy_not_found", "Recommendation policy not found.")
        return policy

    def create_policy(self, request: PolicyCreate) -> dict[str, Any]:
        if self.db.get_policy(request.id):
            raise ControlPlaneError(409, "policy_exists", "A policy with this id already exists.")
        values = request.model_dump()
        violations = validate_policy_definition(
            objective_weights=values["objective_weights"],
            exploration_rate=values["exploration_rate"],
            allowed_candidate_features=values["allowed_candidate_features"],
            constraints=values["constraints"],
        )
        if violations:
            raise ControlPlaneError(
                422,
                "policy_governance_violation",
                "Policy definition violates enforced governance controls.",
                details={"violations": violations},
            )
        now = utc_now()
        versions = [
            int(policy["version"])
            for policy in self.db.list_policies()
            if policy["domain"] == request.domain
        ]
        policy = {
            **values,
            "status": "draft",
            "version": max(versions, default=0) + 1,
            "created_at": now,
            "updated_at": now,
        }
        actor = policy.pop("actor")
        self.db.insert_policy(policy)
        self.db.append_audit(
            actor=actor,
            action="policy.created",
            resource_type="policy",
            resource_id=policy["id"],
            details={
                "domain": policy["domain"],
                "purpose": policy["purpose"],
                "status": "draft",
            },
        )
        return self.get_policy(policy["id"])

    def update_policy(self, policy_id: str, request: PolicyUpdate) -> dict[str, Any]:
        policy = self.get_policy(policy_id)
        if policy["status"] != "draft":
            raise ControlPlaneError(
                409,
                "immutable_policy_version",
                "Active policy versions are immutable; create a new draft version instead.",
            )
        updates = request.model_dump(exclude_none=True)
        actor = updates.pop("actor")
        reason = updates.pop("reason")
        candidate = {**policy, **updates}
        violations = validate_policy_definition(
            objective_weights=candidate["objective_weights"],
            exploration_rate=candidate["exploration_rate"],
            allowed_candidate_features=candidate["allowed_candidate_features"],
            constraints=candidate["constraints"],
        )
        if violations:
            raise ControlPlaneError(
                422,
                "policy_governance_violation",
                "Policy update violates enforced governance controls.",
                details={"violations": violations},
            )
        updates["updated_at"] = utc_now()
        self.db.update_policy(policy_id, updates)
        self.db.append_audit(
            actor=actor,
            action="policy.updated",
            resource_type="policy",
            resource_id=policy_id,
            details={"fields": sorted(updates), "reason": reason},
        )
        return self.get_policy(policy_id)

    def activate_policy(self, policy_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        policy = self.get_policy(policy_id)
        if policy["status"] == "active":
            return policy
        if policy["status"] != "draft":
            raise ControlPlaneError(
                409,
                "invalid_policy_state",
                f"Policy in state {policy['status']} cannot be activated.",
            )
        violations = validate_policy_definition(
            objective_weights=policy["objective_weights"],
            exploration_rate=policy["exploration_rate"],
            allowed_candidate_features=policy["allowed_candidate_features"],
            constraints=policy["constraints"],
        )
        if violations:
            raise ControlPlaneError(
                422,
                "policy_governance_violation",
                "Policy cannot be activated.",
                details={"violations": violations},
            )
        self.db.update_policy(policy_id, {"status": "active", "updated_at": utc_now()})
        self.db.append_audit(
            actor=actor,
            action="policy.activated",
            resource_type="policy",
            resource_id=policy_id,
            details={"reason": reason, "version": policy["version"]},
        )
        return self.get_policy(policy_id)

    def list_cohorts(self) -> list[dict[str, Any]]:
        minimum = self.minimum_cohort_size
        return [
            {
                **cohort,
                "privacy": {
                    "minimum_size": minimum,
                    "launch_eligible": int(cohort["estimated_size"]) >= minimum,
                    "metric_visibility": (
                        "visible"
                        if int(cohort["estimated_size"]) >= minimum
                        else "suppressed"
                    ),
                },
            }
            for cohort in self.db.list_cohorts()
        ]

    def list_experiments(self) -> list[dict[str, Any]]:
        return [self._enrich_experiment(experiment) for experiment in self.db.list_experiments()]

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        experiment = self.db.get_experiment(experiment_id)
        if experiment is None:
            raise ControlPlaneError(404, "experiment_not_found", "Experiment not found.")
        return self._enrich_experiment(experiment)

    def _enrich_experiment(self, experiment: dict[str, Any]) -> dict[str, Any]:
        cohort = self.db.get_cohort(experiment["cohort_id"])
        approval = self.db.pending_approval(
            resource_type="experiment",
            resource_id=experiment["id"],
            action="launch",
        )
        minimum = self.minimum_cohort_size
        return {
            **experiment,
            "cohort_size": None if cohort is None else cohort["estimated_size"],
            "launch_eligible": bool(
                cohort
                and int(cohort["estimated_size"]) >= minimum
                and experiment["status"] not in TERMINAL_EXPERIMENT_STATES
            ),
            "minimum_cohort_size": minimum,
            "pending_approval_id": None if approval is None else approval["id"],
        }

    def create_experiment(self, request: ExperimentCreate) -> dict[str, Any]:
        if self.db.get_experiment(request.id):
            raise ControlPlaneError(
                409,
                "experiment_exists",
                "An experiment with this id already exists.",
            )
        control = self.get_policy(request.control_policy_id)
        treatment = self.get_policy(request.treatment_policy_id)
        cohort = self.db.get_cohort(request.cohort_id)
        if cohort is None:
            raise ControlPlaneError(404, "cohort_not_found", "Target cohort not found.")
        if request.control_policy_id == request.treatment_policy_id:
            raise ControlPlaneError(
                422,
                "identical_variants",
                "Control and treatment policies must be different versions.",
            )
        self._validate_experiment_alignment(
            domain=request.domain,
            purpose=request.purpose,
            control=control,
            treatment=treatment,
            cohort=cohort,
        )
        guardrails = self._validate_guardrails(request.guardrails)
        risk = assess_experiment_risk(
            traffic_percent=request.traffic_percent,
            control_policy=control,
            treatment_policy=treatment,
        )
        risk_reasons = list(risk.reasons)
        if int(cohort["estimated_size"]) < self.minimum_cohort_size:
            risk_reasons.append("cohort is below the minimum privacy floor")
        now = utc_now()
        experiment = {
            **request.model_dump(),
            "status": "draft",
            "risk_level": risk.level,
            "risk_reasons": risk_reasons,
            "guardrails": guardrails,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "ended_at": None,
            "rollback_reason": None,
        }
        actor = experiment.pop("actor")
        self.db.insert_experiment(experiment)
        self.db.append_audit(
            actor=actor,
            action="experiment.created",
            resource_type="experiment",
            resource_id=experiment["id"],
            details={
                "domain": experiment["domain"],
                "traffic_percent": experiment["traffic_percent"],
                "risk_level": experiment["risk_level"],
                "risk_reasons": risk_reasons,
            },
        )
        return self.get_experiment(experiment["id"])

    def _validate_experiment_alignment(
        self,
        *,
        domain: str,
        purpose: str,
        control: dict[str, Any],
        treatment: dict[str, Any],
        cohort: dict[str, Any],
    ) -> None:
        mismatches: list[str] = []
        for label, resource in (
            ("control policy", control),
            ("treatment policy", treatment),
            ("cohort", cohort),
        ):
            if resource["domain"] != domain:
                mismatches.append(f"{label} domain is {resource['domain']!r}")
            if resource["purpose"] != purpose:
                mismatches.append(f"{label} purpose does not exactly match")
        if control["status"] != "active" or treatment["status"] != "active":
            mismatches.append("both policy versions must be active")
        if mismatches:
            raise ControlPlaneError(
                422,
                "experiment_scope_mismatch",
                "Experiment resources must share one domain and exact purpose.",
                details={"mismatches": mismatches},
            )

    def _validate_guardrails(self, guardrails: dict[str, float]) -> dict[str, float]:
        required = {
            "min_quality_score",
            "max_harm_rate",
            "max_complaint_rate",
            "min_fairness_ratio",
        }
        missing = sorted(required - set(guardrails))
        unknown = sorted(set(guardrails) - required)
        violations: list[str] = []
        if missing:
            violations.append("missing guardrails: " + ", ".join(missing))
        if unknown:
            violations.append("unknown guardrails: " + ", ".join(unknown))
        for name, value in guardrails.items():
            if value < 0.0 or value > 1.0:
                violations.append(f"{name} must be between 0 and 1")
        if guardrails.get("min_fairness_ratio", 1.0) < DEFAULT_FAIRNESS_RATIO_FLOOR:
            violations.append(
                f"min_fairness_ratio cannot be below {DEFAULT_FAIRNESS_RATIO_FLOOR:.2f}"
            )
        if guardrails.get("max_harm_rate", 0.0) > 0.10:
            violations.append("max_harm_rate cannot exceed 0.10")
        if guardrails.get("max_complaint_rate", 0.0) > 0.10:
            violations.append("max_complaint_rate cannot exceed 0.10")
        if violations:
            raise ControlPlaneError(
                422,
                "invalid_guardrails",
                "Experiment guardrails are incomplete or too permissive.",
                details={"violations": violations},
            )
        return {name: float(guardrails[name]) for name in sorted(required)}

    def transition_experiment(
        self,
        experiment_id: str,
        request: ExperimentTransition,
    ) -> dict[str, Any]:
        experiment = self.get_experiment(experiment_id)
        current = experiment["status"]
        target = request.target_state
        allowed = {
            "draft": {"review"},
            "review": {"approved", "killed"},
            "approved": {"running", "killed"},
            "running": {"paused", "completed", "rolled_back", "killed"},
            "paused": {"running", "rolled_back", "killed"},
        }
        if target not in allowed.get(current, set()):
            raise ControlPlaneError(
                409,
                "invalid_experiment_transition",
                f"Cannot transition experiment from {current} to {target}.",
                details={"allowed_targets": sorted(allowed.get(current, set()))},
            )

        now = utc_now()
        if current == "draft" and target == "review":
            self._assert_launch_readiness(experiment, require_capacity=False)
            fields = {"status": "review", "updated_at": now}
            action = "experiment.reviewed"
        elif current == "review" and target == "approved":
            self._assert_launch_readiness(experiment, require_capacity=False)
            control = self.get_policy(experiment["control_policy_id"])
            treatment = self.get_policy(experiment["treatment_policy_id"])
            risk = assess_experiment_risk(
                traffic_percent=float(experiment["traffic_percent"]),
                control_policy=control,
                treatment_policy=treatment,
            )
            if risk.requires_human_approval:
                approval = self._request_launch_approval(
                    experiment=experiment,
                    actor=request.actor,
                    reasons=list(risk.reasons),
                )
                self.db.update_experiment(
                    experiment_id,
                    {
                        "status": "pending_approval",
                        "risk_level": risk.level,
                        "risk_reasons": list(risk.reasons),
                        "updated_at": now,
                    },
                )
                self.db.append_audit(
                    actor=request.actor,
                    action="experiment.approval_requested",
                    resource_type="experiment",
                    resource_id=experiment_id,
                    details={
                        "approval_id": approval["id"],
                        "reason": request.reason,
                        "risk_reasons": list(risk.reasons),
                    },
                )
                return self.get_experiment(experiment_id)
            fields = {"status": "approved", "updated_at": now}
            action = "experiment.approved_automatically"
        elif target == "running":
            self._assert_launch_readiness(experiment, require_capacity=True)
            fields = {
                "status": "running",
                "updated_at": now,
                "started_at": now,
                "ended_at": None,
                "rollback_reason": None,
            }
            action = "experiment.launched"
        else:
            fields = {"status": target, "updated_at": now}
            if target in {"completed", "rolled_back", "killed"}:
                fields["ended_at"] = now
            if target in {"rolled_back", "killed"}:
                fields["rollback_reason"] = request.reason
            action = f"experiment.{target}"

        self.db.update_experiment(experiment_id, fields)
        self.db.append_audit(
            actor=request.actor,
            action=action,
            resource_type="experiment",
            resource_id=experiment_id,
            details={"from": current, "to": target, "reason": request.reason},
        )
        return self.get_experiment(experiment_id)

    def _assert_launch_readiness(
        self,
        experiment: dict[str, Any],
        *,
        require_capacity: bool,
    ) -> None:
        cohort = self.db.get_cohort(experiment["cohort_id"])
        if cohort is None:
            raise ControlPlaneError(409, "cohort_missing", "Experiment cohort no longer exists.")
        if int(cohort["estimated_size"]) < self.minimum_cohort_size:
            raise ControlPlaneError(
                409,
                "cohort_privacy_floor",
                "Experiment cannot launch because its cohort is below the privacy floor.",
                details={
                    "cohort_size": cohort["estimated_size"],
                    "minimum_cohort_size": self.minimum_cohort_size,
                },
            )
        control = self.get_policy(experiment["control_policy_id"])
        treatment = self.get_policy(experiment["treatment_policy_id"])
        self._validate_experiment_alignment(
            domain=experiment["domain"],
            purpose=experiment["purpose"],
            control=control,
            treatment=treatment,
            cohort=cohort,
        )
        self._validate_guardrails(experiment["guardrails"])
        if require_capacity:
            kill_switch = self.db.get_setting("kill_switch", {"enabled": False})
            if kill_switch.get("enabled"):
                raise ControlPlaneError(
                    409,
                    "kill_switch_active",
                    "No experiment may launch while the global kill switch is active.",
                )
            total = self.db.running_traffic_total(exclude_id=experiment["id"])
            proposed = total + float(experiment["traffic_percent"])
            if proposed > GLOBAL_EXPERIMENT_TRAFFIC_CAP:
                raise ControlPlaneError(
                    409,
                    "global_traffic_cap",
                    "Launching this experiment would exceed the global experiment traffic cap.",
                    details={
                        "running_traffic_percent": total,
                        "proposed_traffic_percent": proposed,
                        "cap_percent": GLOBAL_EXPERIMENT_TRAFFIC_CAP,
                    },
                )

    def _request_launch_approval(
        self,
        *,
        experiment: dict[str, Any],
        actor: str,
        reasons: list[str],
    ) -> dict[str, Any]:
        existing = self.db.pending_approval(
            resource_type="experiment",
            resource_id=experiment["id"],
            action="launch",
        )
        if existing:
            return existing
        now = utc_now()
        approval = {
            "id": _identifier(
                "apr",
                experiment["id"],
                now,
                str(len(self.db.list_approvals())),
            ),
            "resource_type": "experiment",
            "resource_id": experiment["id"],
            "action": "launch",
            "status": "pending",
            "risk_level": "high",
            "reasons": reasons,
            "requested_by": actor,
            "requested_at": now,
            "decided_by": None,
            "decided_at": None,
            "decision_reason": None,
        }
        self.db.insert_approval(approval)
        return approval

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        return self.db.list_approvals(status=status)

    def decide_approval(
        self,
        approval_id: str,
        request: ApprovalDecision,
    ) -> dict[str, Any]:
        approval = self.db.get_approval(approval_id)
        if approval is None:
            raise ControlPlaneError(404, "approval_not_found", "Approval request not found.")
        if approval["status"] != "pending":
            raise ControlPlaneError(
                409,
                "approval_already_decided",
                "Approval request has already been decided.",
            )
        experiment: dict[str, Any] | None = None
        if approval["resource_type"] == "experiment" and approval["action"] == "launch":
            experiment = self.get_experiment(approval["resource_id"])
            if experiment["status"] != "pending_approval":
                raise ControlPlaneError(
                    409,
                    "approval_resource_state_changed",
                    "The experiment is no longer waiting for this approval.",
                )
        now = utc_now()
        self.db.update_approval(
            approval_id,
            {
                "status": request.decision,
                "decided_by": request.actor,
                "decided_at": now,
                "decision_reason": request.reason,
            },
        )
        if experiment is not None:
            target = "approved" if request.decision == "approved" else "review"
            self.db.update_experiment(
                experiment["id"],
                {"status": target, "updated_at": now},
            )
        self.db.append_audit(
            actor=request.actor,
            action=f"approval.{request.decision}",
            resource_type=approval["resource_type"],
            resource_id=approval["resource_id"],
            details={
                "approval_id": approval_id,
                "action": approval["action"],
                "reason": request.reason,
            },
        )
        return self.db.get_approval(approval_id) or {}

    def set_kill_switch(self, request: KillSwitchRequest) -> dict[str, Any]:
        current = self.db.get_setting("kill_switch", {"enabled": False})
        now = utc_now()
        paused: list[str] = []
        if request.enabled and not current.get("enabled"):
            paused = self.db.pause_running_experiments(
                timestamp=now,
                reason=f"Paused by global kill switch: {request.reason}",
            )
        value = {
            "enabled": request.enabled,
            "actor": request.actor,
            "reason": request.reason,
            "updated_at": now,
            "paused_experiments": paused,
            "manual_resume_required": True,
        }
        self.db.set_setting("kill_switch", value, timestamp=now)
        self.db.append_audit(
            actor=request.actor,
            action="kill_switch.enabled" if request.enabled else "kill_switch.disabled",
            resource_type="system",
            resource_id="global-kill-switch",
            details={
                "reason": request.reason,
                "paused_experiments": paused,
                "experiments_auto_resumed": False,
            },
        )
        return value

    def rank(self, request: RankRequest) -> dict[str, Any]:
        if not request.consent:
            raise ControlPlaneError(
                403,
                "consent_required",
                "Personalized ranking requires affirmative consent.",
            )
        payload = request.model_dump()
        prohibited = prohibited_attribute_paths(
            {
                "context": payload["context"],
                "candidates": [
                    {"features": item["features"], "metadata": item["metadata"]}
                    for item in payload["candidates"]
                ],
            }
        )
        if prohibited:
            raise ControlPlaneError(
                422,
                "sensitive_attribute_prohibited",
                "Sensitive attributes cannot be supplied to ranking or scoring.",
                details={"paths": prohibited},
            )

        cohort = self.db.get_cohort(request.cohort_id)
        if cohort is None:
            raise ControlPlaneError(404, "cohort_not_found", "Cohort not found.")
        if cohort["domain"] != request.domain:
            raise ControlPlaneError(
                422,
                "cohort_domain_mismatch",
                "Cohort is not defined for the requested domain.",
            )
        if cohort["purpose"] != request.purpose:
            raise ControlPlaneError(
                403,
                "purpose_limitation",
                "Requested purpose does not exactly match the cohort's approved purpose.",
                details={
                    "approved_purpose": cohort["purpose"],
                    "requested_purpose": request.purpose,
                },
            )

        request_fingerprint = sha256(
            canonical_json(
                {
                    **payload,
                    "request_id": None,
                }
            ).encode("utf-8")
        ).hexdigest()
        request_id = request.request_id or _identifier("req", request_fingerprint)
        kill_switch = self.db.get_setting("kill_switch", {"enabled": False})
        privacy_fallback = int(cohort["estimated_size"]) < self.minimum_cohort_size
        experiment: dict[str, Any] | None = None
        allocation = {
            "variant": "baseline",
            "bucket": None,
            "traffic_percent": 0.0,
            "treatment_share": 0.0,
        }

        if request.policy_id:
            policy = self.get_policy(request.policy_id)
            if policy["status"] != "active":
                raise ControlPlaneError(
                    409,
                    "policy_not_active",
                    "Only active policy versions can serve recommendations.",
                )
        else:
            policy = self.db.default_policy(request.domain)
            if policy is None:
                raise ControlPlaneError(
                    503,
                    "no_active_policy",
                    "No active baseline policy is available for this domain.",
                )

        if policy["domain"] != request.domain or policy["purpose"] != request.purpose:
            raise ControlPlaneError(
                403,
                "purpose_limitation",
                "Policy scope does not match the request domain and purpose.",
            )

        if kill_switch.get("enabled") or privacy_fallback:
            baseline = self.db.default_policy(request.domain)
            if baseline is None:
                raise ControlPlaneError(
                    503,
                    "no_active_policy",
                    "No approved baseline policy is available for safe fallback.",
                )
            policy = baseline

        if not request.policy_id and not kill_switch.get("enabled") and not privacy_fallback:
            running = self.db.running_experiments(request.domain, request.cohort_id)
            if running:
                experiment = running[0]
                allocation = deterministic_allocation(
                    subject_id=request.subject_id,
                    experiment_id=experiment["id"],
                    traffic_percent=float(experiment["traffic_percent"]),
                    treatment_share=float(experiment["treatment_share"]),
                )
                if allocation["variant"] == "treatment":
                    policy = self.get_policy(experiment["treatment_policy_id"])
                elif allocation["variant"] == "control":
                    policy = self.get_policy(experiment["control_policy_id"])
                else:
                    experiment = None

        allowed_features = set(policy["allowed_candidate_features"])
        unknown_features = sorted(
            {
                feature
                for candidate in payload["candidates"]
                for feature in candidate["features"]
                if feature not in allowed_features
            }
        )
        if unknown_features:
            raise ControlPlaneError(
                422,
                "candidate_feature_not_allowed",
                "Candidate input contains features outside the active policy contract.",
                details={"features": unknown_features},
            )

        decision_id = _identifier(
            "dec",
            request_id,
            policy["id"],
            experiment["id"] if experiment else "no-experiment",
            allocation["variant"],
        )
        existing = self.db.get_decision(decision_id)
        if existing is not None:
            if existing["explanation"].get("request_fingerprint") != request_fingerprint:
                raise ControlPlaneError(
                    409,
                    "request_id_conflict",
                    "Request id was already used with different ranking input.",
                )
            return existing["explanation"]["response"]

        rankings, excluded = score_candidates(
            subject_id=request.subject_id,
            request_id=request_id,
            candidates=payload["candidates"],
            objective_weights=policy["objective_weights"],
            exploration_rate=float(policy["exploration_rate"]),
            safety_floor=float(policy["constraints"].get("candidate_safety_floor", 0.0)),
            limit=request.limit,
        )
        governance = {
            "consent": "verified",
            "purpose_limitation": "verified",
            "sensitive_attributes": "not_present",
            "minimum_cohort_size": self.minimum_cohort_size,
            "cohort_size": cohort["estimated_size"],
            "cohort_privacy": "fallback" if privacy_fallback else "eligible",
            "kill_switch": "fallback" if kill_switch.get("enabled") else "inactive",
            "exploration_rate": policy["exploration_rate"],
            "dark_pattern_objectives": "prohibited",
        }
        response = {
            "decision_id": decision_id,
            "request_id": request_id,
            "created_at": utc_now(),
            "policy": {
                "id": policy["id"],
                "name": policy["name"],
                "version": policy["version"],
                "objective_weights": policy["objective_weights"],
            },
            "assignment": {
                **allocation,
                "experiment_id": None if experiment is None else experiment["id"],
            },
            "recommendations": rankings,
            "excluded_candidates": excluded,
            "governance": governance,
            "explanation": {
                "method": "bounded deterministic weighted-sum optimization",
                "tie_break": "stable SHA-256 fraction",
                "candidate_safety_floor": policy["constraints"].get(
                    "candidate_safety_floor",
                    0.0,
                ),
                "limitations": [
                    "Scores reflect only supplied normalized features.",
                    "The demo does not infer causality or protected-group membership.",
                    "Offline evaluation and human review remain required before production use.",
                ],
            },
        }
        self.db.insert_decision(
            {
                "id": decision_id,
                "request_id": request_id,
                "subject_hash": _subject_hash(request.subject_id),
                "domain": request.domain,
                "purpose": request.purpose,
                "cohort_id": request.cohort_id,
                "policy_id": policy["id"],
                "experiment_id": None if experiment is None else experiment["id"],
                "variant": allocation["variant"],
                "candidate_ids": [item["candidate_id"] for item in rankings],
                "explanation": {
                    "request_fingerprint": request_fingerprint,
                    "response": response,
                },
                "created_at": response["created_at"],
            }
        )
        self.db.append_audit(
            actor="ranking-service",
            action="recommendation.ranked",
            resource_type="decision",
            resource_id=decision_id,
            details={
                "subject_hash_prefix": _subject_hash(request.subject_id)[:12],
                "domain": request.domain,
                "purpose": request.purpose,
                "policy_id": policy["id"],
                "experiment_id": None if experiment is None else experiment["id"],
                "variant": allocation["variant"],
                "returned_candidates": len(rankings),
                "excluded_candidates": len(excluded),
                "governance": governance,
            },
        )
        return response

    def get_decision(self, decision_id: str) -> dict[str, Any]:
        decision = self.db.get_decision(decision_id)
        if decision is None:
            raise ControlPlaneError(404, "decision_not_found", "Decision not found.")
        return decision

    def ingest_exposure(self, request: ExposureEvent) -> dict[str, Any]:
        existing = self.db.get_exposure(request.event_id)
        occurred_at = (
            existing["occurred_at"]
            if existing is not None and request.occurred_at is None
            else self._event_timestamp(request.occurred_at)
        )
        decision = self.db.get_decision(request.decision_id)
        if decision is None:
            raise ControlPlaneError(
                404,
                "decision_not_found",
                "Exposure must reference an inspectable ranking decision.",
            )
        subject_hash = _subject_hash(request.subject_id)
        if decision["subject_hash"] != subject_hash:
            raise ControlPlaneError(
                403,
                "exposure_subject_mismatch",
                "Exposure subject does not match the ranking decision.",
            )
        if request.candidate_id not in decision["candidate_ids"]:
            raise ControlPlaneError(
                422,
                "candidate_not_in_decision",
                "Exposure candidate was not returned by the referenced decision.",
            )
        if request.purpose != decision["purpose"]:
            raise ControlPlaneError(
                403,
                "purpose_limitation",
                "Exposure purpose must match the original decision purpose.",
            )
        event = {
            "event_id": request.event_id,
            "decision_id": request.decision_id,
            "subject_hash": subject_hash,
            "candidate_id": request.candidate_id,
            "purpose": request.purpose,
            "experiment_id": decision["experiment_id"],
            "variant": decision["variant"],
            "policy_id": decision["policy_id"],
            "occurred_at": occurred_at,
            "recorded_at": utc_now(),
        }
        if existing is not None:
            comparable = {key: existing[key] for key in event if key != "recorded_at"}
            incoming = {key: event[key] for key in event if key != "recorded_at"}
            if comparable != incoming:
                raise ControlPlaneError(
                    409,
                    "idempotency_conflict",
                    "Exposure event id was already used with different data.",
                )
            return {**existing, "idempotent_replay": True}
        self.db.insert_exposure(event)
        self.db.append_audit(
            actor="event-ingest",
            action="exposure.recorded",
            resource_type="exposure",
            resource_id=request.event_id,
            details={
                "decision_id": request.decision_id,
                "candidate_id": request.candidate_id,
                "experiment_id": decision["experiment_id"],
                "variant": decision["variant"],
                "purpose": request.purpose,
            },
        )
        return {**event, "idempotent_replay": False}

    def ingest_outcome(self, request: OutcomeEvent) -> dict[str, Any]:
        outcome_type = request.outcome_type.lower()
        if outcome_type not in ALLOWED_OUTCOME_TYPES:
            raise ControlPlaneError(
                422,
                "outcome_type_not_allowed",
                "Outcome type is not part of the purpose-limited metric contract.",
                details={"allowed": sorted(ALLOWED_OUTCOME_TYPES)},
            )
        exposure = self.db.get_exposure(request.exposure_event_id)
        if exposure is None:
            raise ControlPlaneError(
                404,
                "exposure_not_found",
                "Outcome must reference a recorded exposure.",
            )
        if request.purpose != exposure["purpose"]:
            raise ControlPlaneError(
                403,
                "purpose_limitation",
                "Outcome purpose must match the exposure purpose.",
            )
        existing = self.db.get_outcome(request.event_id)
        occurred_at = (
            existing["occurred_at"]
            if existing is not None and request.occurred_at is None
            else self._event_timestamp(request.occurred_at)
        )
        event = {
            "event_id": request.event_id,
            "exposure_event_id": request.exposure_event_id,
            "outcome_type": outcome_type,
            "value": request.value,
            "purpose": request.purpose,
            "occurred_at": occurred_at,
            "recorded_at": utc_now(),
        }
        if existing is not None:
            comparable = {key: existing[key] for key in event if key != "recorded_at"}
            incoming = {key: event[key] for key in event if key != "recorded_at"}
            if comparable != incoming:
                raise ControlPlaneError(
                    409,
                    "idempotency_conflict",
                    "Outcome event id was already used with different data.",
                )
            return {**existing, "idempotent_replay": True}
        self.db.insert_outcome(event)
        self.db.append_audit(
            actor="event-ingest",
            action="outcome.recorded",
            resource_type="outcome",
            resource_id=request.event_id,
            details={
                "exposure_event_id": request.exposure_event_id,
                "outcome_type": outcome_type,
                "value": request.value,
                "purpose": request.purpose,
            },
        )
        return {**event, "idempotent_replay": False}

    def _event_timestamp(self, raw: str | None) -> str:
        if raw is None:
            return utc_now()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            parsed = parsed.astimezone(UTC)
        except ValueError as exc:
            raise ControlPlaneError(
                422,
                "invalid_event_timestamp",
                "Event timestamp must be ISO-8601.",
            ) from exc
        now = datetime.now(UTC)
        if parsed > now + timedelta(minutes=5):
            raise ControlPlaneError(
                422,
                "future_event_timestamp",
                "Event timestamp cannot be more than five minutes in the future.",
            )
        if parsed < now - timedelta(days=90):
            raise ControlPlaneError(
                422,
                "event_retention_window",
                "Raw events older than the 90-day retention window are rejected.",
            )
        return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def list_metrics(self, experiment_id: str | None = None) -> list[dict[str, Any]]:
        minimum = self.minimum_cohort_size
        output: list[dict[str, Any]] = []
        for metric in self.db.list_metrics(experiment_id):
            if int(metric["sample_size"]) < minimum:
                output.append(
                    {
                        **metric,
                        "value": None,
                        "privacy_status": "suppressed",
                        "suppression_reason": "minimum_cohort_size",
                        "minimum_cohort_size": minimum,
                    }
                )
            else:
                output.append(
                    {
                        **metric,
                        "privacy_status": "visible",
                        "suppression_reason": None,
                        "minimum_cohort_size": minimum,
                    }
                )
        return output

    def evaluate_experiment_guardrails(
        self,
        request: GuardrailEvaluationRequest,
    ) -> dict[str, Any]:
        experiment = self.get_experiment(request.experiment_id)
        if request.sample_size < self.minimum_cohort_size:
            result = {
                "status": "suppressed",
                "reason": "minimum_cohort_size",
                "sample_size": request.sample_size,
                "minimum_cohort_size": self.minimum_cohort_size,
                "metrics": {},
                "action": "none",
            }
            self.db.append_audit(
                actor=request.actor,
                action="guardrail.evaluation_suppressed",
                resource_type="experiment",
                resource_id=request.experiment_id,
                details=result,
            )
            return result
        supported = {
            "quality_score",
            "harm_rate",
            "complaint_rate",
            "fairness_ratio",
        }
        unknown = sorted(set(request.metrics) - supported)
        invalid = sorted(
            name for name, value in request.metrics.items() if value < 0.0 or value > 1.0
        )
        if unknown or invalid:
            raise ControlPlaneError(
                422,
                "invalid_guardrail_metrics",
                "Guardrail metrics must use supported names and normalized values.",
                details={"unknown": unknown, "out_of_range": invalid},
            )
        result = evaluate_guardrails(request.metrics, experiment["guardrails"])
        now = utc_now()
        for metric_name, value in request.metrics.items():
            self.db.insert_metric(
                experiment_id=request.experiment_id,
                cohort_id=experiment["cohort_id"],
                metric_name=metric_name,
                variant="aggregate",
                sample_size=request.sample_size,
                value=value,
                observed_at=now,
            )
        action = "none"
        if result["status"] == "failed" and experiment["status"] == "running":
            failed = [
                check["metric"]
                for check in result["checks"]
                if check["status"] == "fail"
            ]
            self._automatic_rollback(
                experiment_id=request.experiment_id,
                actor=request.actor,
                reason="Guardrail breach: " + ", ".join(failed),
                details={"evaluation": result, "sample_size": request.sample_size},
            )
            action = "rolled_back"
        self.db.append_audit(
            actor=request.actor,
            action="guardrail.evaluated",
            resource_type="experiment",
            resource_id=request.experiment_id,
            details={
                "status": result["status"],
                "sample_size": request.sample_size,
                "checks": result["checks"],
                "action": action,
            },
        )
        return {**result, "sample_size": request.sample_size, "action": action}

    def evaluate_experiment_fairness(
        self,
        request: FairnessEvaluationRequest,
    ) -> dict[str, Any]:
        experiment = self.get_experiment(request.experiment_id)
        groups = [group.model_dump() for group in request.groups]
        semantic_group_keys = [
            group["group_key"]
            for group in groups
            if any(
                f"_{term}_" in f"_{normalize_key(group['group_key'])}_"
                for term in (
                    "age",
                    "disability",
                    "ethnicity",
                    "gender",
                    "race",
                    "religion",
                    "sex",
                    "sexual_orientation",
                )
            )
        ]
        if semantic_group_keys:
            raise ControlPlaneError(
                422,
                "opaque_group_keys_required",
                "Fairness evaluation accepts opaque aggregate group keys only.",
                details={"invalid_group_keys": semantic_group_keys},
            )
        result = evaluate_fairness(
            groups,
            minimum_cohort_size=self.minimum_cohort_size,
            ratio_floor=float(experiment["guardrails"]["min_fairness_ratio"]),
        )
        action = "none"
        if result["status"] != "suppressed":
            self.db.insert_metric(
                experiment_id=request.experiment_id,
                cohort_id=experiment["cohort_id"],
                metric_name="fairness_ratio",
                variant="aggregate",
                sample_size=sum(group["sample_size"] for group in groups),
                value=float(result["fairness_ratio"]),
                observed_at=utc_now(),
            )
        if result["status"] == "failed" and experiment["status"] == "running":
            self._automatic_rollback(
                experiment_id=request.experiment_id,
                actor=request.actor,
                reason=(
                    f"Fairness ratio {result['fairness_ratio']:.3f} is below "
                    f"{result['ratio_floor']:.3f}"
                ),
                details={"evaluation": result},
            )
            action = "rolled_back"
        audit_result = {
            **result,
            "group_metrics": (
                result["group_metrics"] if result["status"] != "suppressed" else []
            ),
            "action": action,
        }
        self.db.append_audit(
            actor=request.actor,
            action="fairness.evaluated",
            resource_type="experiment",
            resource_id=request.experiment_id,
            details=audit_result,
        )
        return audit_result

    def _automatic_rollback(
        self,
        *,
        experiment_id: str,
        actor: str,
        reason: str,
        details: dict[str, Any],
    ) -> None:
        now = utc_now()
        self.db.update_experiment(
            experiment_id,
            {
                "status": "rolled_back",
                "updated_at": now,
                "ended_at": now,
                "rollback_reason": reason,
            },
        )
        self.db.append_audit(
            actor=actor,
            action="experiment.auto_rolled_back",
            resource_type="experiment",
            resource_id=experiment_id,
            details={"reason": reason, **details},
        )

    def list_audit(self, limit: int = 100) -> dict[str, Any]:
        return {
            "records": self.db.list_audit(limit=limit),
            "verification": self.db.verify_audit_chain(),
        }

    def reset_demo(self, *, actor: str, reason: str) -> dict[str, Any]:
        generation = self.db.reset(actor=actor, reason=reason)
        return {
            "status": "reset",
            "generation": generation,
            "counts": self.db.counts(),
            "kill_switch": self.db.get_setting("kill_switch"),
            "fictional_demo_data": True,
        }

    def run_demo_scenario(
        self,
        scenario_id: str,
        request: DemoScenarioRequest,
    ) -> dict[str, Any]:
        if scenario_id == "transparent-ranking":
            rank_request = RankRequest(
                subject_id="demo-visitor-017",
                domain="commerce",
                purpose="help people find useful products they are likely to value",
                consent=True,
                cohort_id="cohort-commerce-returning",
                candidates=DEMO_CANDIDATES["commerce"],
                limit=4,
            )
            decision = self.rank(rank_request)
            return {
                "scenario": scenario_id,
                "title": "Transparent deterministic ranking",
                "result": decision,
                "talk_track": [
                    "Consent and purpose are checked before scoring.",
                    "One low-safety candidate is excluded.",
                    "Every score shows weighted factor contributions.",
                ],
            }
        if scenario_id == "privacy-floor":
            metrics = self.list_metrics("exp-commerce-small-pilot")
            return {
                "scenario": scenario_id,
                "title": "Minimum cohort privacy floor",
                "result": metrics,
                "talk_track": [
                    "The stored sample is intentionally below 50.",
                    "The API returns no metric value.",
                    "The experiment cannot advance to launch approval.",
                ],
            }
        if scenario_id == "approval-gate":
            experiment = self.get_experiment("exp-media-broader-discovery")
            approval = self.db.get_approval("apr-media-broader-discovery")
            return {
                "scenario": scenario_id,
                "title": "Human approval for a risky launch",
                "result": {"experiment": experiment, "approval": approval},
                "talk_track": [
                    "Traffic and exploration exceed autonomous thresholds.",
                    "The treatment cannot launch until a named human approves.",
                    "The decision and reason are written to the audit chain.",
                ],
            }
        if scenario_id == "guardrail-rollback":
            experiment_id = "exp-community-trust"
            experiment = self.get_experiment(experiment_id)
            if experiment["status"] != "running":
                self.db.update_experiment(
                    experiment_id,
                    {
                        "status": "running",
                        "started_at": utc_now(),
                        "ended_at": None,
                        "rollback_reason": None,
                        "updated_at": utc_now(),
                    },
                )
                self.db.append_audit(
                    actor=request.actor,
                    action="demo.experiment_rearmed",
                    resource_type="experiment",
                    resource_id=experiment_id,
                    details={"scenario": scenario_id},
                )
            evaluation = self.evaluate_experiment_guardrails(
                GuardrailEvaluationRequest(
                    experiment_id=experiment_id,
                    sample_size=240,
                    metrics={
                        "quality_score": 0.61,
                        "harm_rate": 0.018,
                        "complaint_rate": 0.031,
                        "fairness_ratio": 0.79,
                    },
                    actor=request.actor,
                )
            )
            return {
                "scenario": scenario_id,
                "title": "Automatic guardrail rollback",
                "result": {
                    "evaluation": evaluation,
                    "experiment": self.get_experiment(experiment_id),
                },
                "talk_track": [
                    "Quality, complaints, and fairness cross bounded thresholds.",
                    "The running experiment is rolled back immediately.",
                    "The full evaluation remains inspectable in audit.",
                ],
            }
        if scenario_id == "kill-switch":
            state = self.set_kill_switch(
                KillSwitchRequest(
                    enabled=True,
                    actor=request.actor,
                    reason="Guided demo of the global safe fallback.",
                )
            )
            rank_request = RankRequest(
                subject_id="demo-reader-021",
                domain="media",
                purpose=(
                    "surface relevant and trustworthy stories without maximizing compulsion"
                ),
                consent=True,
                cohort_id="cohort-media-weekend",
                candidates=DEMO_CANDIDATES["media"],
                limit=3,
            )
            decision = self.rank(rank_request)
            return {
                "scenario": scenario_id,
                "title": "Global kill switch",
                "result": {"kill_switch": state, "decision": decision},
                "talk_track": [
                    "All running experiments are paused.",
                    "Ranking continues on an approved baseline policy.",
                    "Disabling the switch never auto-resumes experiments.",
                ],
            }
        raise ControlPlaneError(
            404,
            "demo_scenario_not_found",
            "Unknown guided demo scenario.",
            details={
                "available": [
                    "transparent-ranking",
                    "privacy-floor",
                    "approval-gate",
                    "guardrail-rollback",
                    "kill-switch",
                ]
            },
        )
