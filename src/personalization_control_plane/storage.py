"""Small SQLite repository with deterministic seed and hash-chained audit records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from . import seed


def utc_now() -> str:
    """Return a compact UTC timestamp."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    """Serialize JSON in a stable form suitable for hashes and comparisons."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


RESET_QUERIES = (
    "DELETE FROM outcomes",
    "DELETE FROM exposures",
    "DELETE FROM decisions",
    "DELETE FROM metrics",
    "DELETE FROM approvals",
    "DELETE FROM experiments",
    "DELETE FROM cohorts",
    "DELETE FROM policies",
    "DELETE FROM settings",
    "DELETE FROM audit_log",
)
COUNT_QUERIES = {
    "policies": "SELECT COUNT(*) FROM policies",
    "cohorts": "SELECT COUNT(*) FROM cohorts",
    "experiments": "SELECT COUNT(*) FROM experiments",
    "approvals": "SELECT COUNT(*) FROM approvals",
    "decisions": "SELECT COUNT(*) FROM decisions",
    "exposures": "SELECT COUNT(*) FROM exposures",
    "outcomes": "SELECT COUNT(*) FROM outcomes",
    "audit_log": "SELECT COUNT(*) FROM audit_log",
}
POLICY_UPDATE_QUERIES = {
    "name": "UPDATE policies SET name = ? WHERE id = ?",
    "objective_weights": "UPDATE policies SET objective_weights_json = ? WHERE id = ?",
    "exploration_rate": "UPDATE policies SET exploration_rate = ? WHERE id = ?",
    "allowed_candidate_features": (
        "UPDATE policies SET allowed_candidate_features_json = ? WHERE id = ?"
    ),
    "constraints": "UPDATE policies SET constraints_json = ? WHERE id = ?",
    "status": "UPDATE policies SET status = ? WHERE id = ?",
    "updated_at": "UPDATE policies SET updated_at = ? WHERE id = ?",
}
EXPERIMENT_UPDATE_QUERIES = {
    "status": "UPDATE experiments SET status = ? WHERE id = ?",
    "risk_level": "UPDATE experiments SET risk_level = ? WHERE id = ?",
    "risk_reasons": "UPDATE experiments SET risk_reasons_json = ? WHERE id = ?",
    "guardrails": "UPDATE experiments SET guardrails_json = ? WHERE id = ?",
    "updated_at": "UPDATE experiments SET updated_at = ? WHERE id = ?",
    "started_at": "UPDATE experiments SET started_at = ? WHERE id = ?",
    "ended_at": "UPDATE experiments SET ended_at = ? WHERE id = ?",
    "rollback_reason": "UPDATE experiments SET rollback_reason = ? WHERE id = ?",
}
APPROVAL_UPDATE_QUERIES = {
    "status": "UPDATE approvals SET status = ? WHERE id = ?",
    "decided_by": "UPDATE approvals SET decided_by = ? WHERE id = ?",
    "decided_at": "UPDATE approvals SET decided_at = ? WHERE id = ?",
    "decision_reason": "UPDATE approvals SET decision_reason = ? WHERE id = ?",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    objective_weights_json TEXT NOT NULL,
    exploration_rate REAL NOT NULL,
    allowed_candidate_features_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cohorts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    purpose TEXT NOT NULL,
    description TEXT NOT NULL,
    estimated_size INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    purpose TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    status TEXT NOT NULL,
    control_policy_id TEXT NOT NULL,
    treatment_policy_id TEXT NOT NULL,
    cohort_id TEXT NOT NULL,
    traffic_percent REAL NOT NULL,
    treatment_share REAL NOT NULL,
    risk_level TEXT NOT NULL,
    risk_reasons_json TEXT NOT NULL,
    guardrails_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    rollback_reason TEXT,
    FOREIGN KEY(control_policy_id) REFERENCES policies(id),
    FOREIGN KEY(treatment_policy_id) REFERENCES policies(id),
    FOREIGN KEY(cohort_id) REFERENCES cohorts(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_reason TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    domain TEXT NOT NULL,
    purpose TEXT NOT NULL,
    cohort_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    experiment_id TEXT,
    variant TEXT NOT NULL,
    candidate_ids_json TEXT NOT NULL,
    explanation_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exposures (
    event_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    subject_hash TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    experiment_id TEXT,
    variant TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(decision_id) REFERENCES decisions(id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    event_id TEXT PRIMARY KEY,
    exposure_event_id TEXT NOT NULL,
    outcome_type TEXT NOT NULL,
    value REAL NOT NULL,
    purpose TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(exposure_event_id) REFERENCES exposures(event_id)
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    cohort_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    variant TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    value REAL NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    details_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_experiments_status
    ON experiments(status, domain, cohort_id);
CREATE INDEX IF NOT EXISTS idx_metrics_experiment
    ON metrics(experiment_id, metric_name, observed_at);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp
    ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_approvals_status
    ON approvals(status, requested_at DESC);
"""


class Database:
    """SQLite-backed source of truth for one local control-plane process."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            seeded = connection.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
        if not seeded:
            self.reset(actor="system-bootstrap", reason="initial deterministic demo seed")

    def reset(self, *, actor: str, reason: str) -> int:
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT value_json FROM settings WHERE key = 'reset_generation'"
            ).fetchone()
            generation = 1
            if existing is not None:
                generation = int(json.loads(existing["value_json"])) + 1

            for query in RESET_QUERIES:
                connection.execute(query)
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('metrics', 'audit_log')"
            )

            self._set_setting(
                connection,
                "kill_switch",
                {"enabled": False, "reason": None, "actor": "system-seed"},
                seed.SEED_TIMESTAMP,
            )
            self._set_setting(
                connection,
                "governance",
                {
                    "minimum_cohort_size": 50,
                    "fairness_ratio_floor": 0.80,
                    "autonomous_traffic_cap_percent": 5.0,
                    "hard_experiment_traffic_cap_percent": 25.0,
                    "global_concurrent_traffic_cap_percent": 30.0,
                    "maximum_exploration_rate": 0.10,
                    "sensitive_attributes": "prohibited",
                    "dark_pattern_optimization": "prohibited",
                },
                seed.SEED_TIMESTAMP,
            )
            self._set_setting(
                connection,
                "reset_generation",
                generation,
                seed.SEED_TIMESTAMP,
            )

            for policy in seed.POLICIES:
                connection.execute(
                    """
                    INSERT INTO policies (
                        id, name, domain, purpose, status, objective_weights_json,
                        exploration_rate, allowed_candidate_features_json,
                        constraints_json, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        policy["id"],
                        policy["name"],
                        policy["domain"],
                        policy["purpose"],
                        policy["status"],
                        canonical_json(policy["objective_weights"]),
                        policy["exploration_rate"],
                        canonical_json(policy["allowed_candidate_features"]),
                        canonical_json(policy["constraints"]),
                        policy["version"],
                        seed.SEED_TIMESTAMP,
                        seed.SEED_TIMESTAMP,
                    ),
                )

            for cohort in seed.COHORTS:
                connection.execute(
                    """
                    INSERT INTO cohorts (
                        id, name, domain, purpose, description, estimated_size,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cohort["id"],
                        cohort["name"],
                        cohort["domain"],
                        cohort["purpose"],
                        cohort["description"],
                        cohort["estimated_size"],
                        cohort["status"],
                        seed.SEED_TIMESTAMP,
                        seed.SEED_TIMESTAMP,
                    ),
                )

            for experiment in seed.EXPERIMENTS:
                connection.execute(
                    """
                    INSERT INTO experiments (
                        id, name, domain, purpose, hypothesis, status,
                        control_policy_id, treatment_policy_id, cohort_id,
                        traffic_percent, treatment_share, risk_level,
                        risk_reasons_json, guardrails_json, created_at, updated_at,
                        started_at, ended_at, rollback_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        experiment["id"],
                        experiment["name"],
                        experiment["domain"],
                        experiment["purpose"],
                        experiment["hypothesis"],
                        experiment["status"],
                        experiment["control_policy_id"],
                        experiment["treatment_policy_id"],
                        experiment["cohort_id"],
                        experiment["traffic_percent"],
                        experiment["treatment_share"],
                        experiment["risk_level"],
                        canonical_json(experiment["risk_reasons"]),
                        canonical_json(experiment["guardrails"]),
                        seed.SEED_TIMESTAMP,
                        seed.SEED_TIMESTAMP,
                        experiment["started_at"],
                        None,
                        None,
                    ),
                )

            for approval in seed.APPROVALS:
                connection.execute(
                    """
                    INSERT INTO approvals (
                        id, resource_type, resource_id, action, status, risk_level,
                        reasons_json, requested_by, requested_at, decided_by,
                        decided_at, decision_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        approval["id"],
                        approval["resource_type"],
                        approval["resource_id"],
                        approval["action"],
                        approval["status"],
                        approval["risk_level"],
                        canonical_json(approval["reasons"]),
                        approval["requested_by"],
                        approval["requested_at"],
                        approval.get("decided_by"),
                        approval.get("decided_at"),
                        approval.get("decision_reason"),
                    ),
                )

            for metric in seed.METRICS:
                connection.execute(
                    """
                    INSERT INTO metrics (
                        experiment_id, cohort_id, metric_name, variant,
                        sample_size, value, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metric["experiment_id"],
                        metric["cohort_id"],
                        metric["metric_name"],
                        metric["variant"],
                        metric["sample_size"],
                        metric["value"],
                        seed.SEED_TIMESTAMP,
                    ),
                )

            self._append_audit(
                connection,
                timestamp=seed.SEED_TIMESTAMP,
                actor=actor,
                action="demo.reset",
                resource_type="system",
                resource_id="local-demo",
                details={"generation": generation, "reason": reason},
            )
            for experiment in seed.EXPERIMENTS:
                self._append_audit(
                    connection,
                    timestamp=seed.SEED_TIMESTAMP,
                    actor="system-seed",
                    action="experiment.seeded",
                    resource_type="experiment",
                    resource_id=experiment["id"],
                    details={
                        "status": experiment["status"],
                        "domain": experiment["domain"],
                        "fictional_data": True,
                    },
                )
            self._append_audit(
                connection,
                timestamp=seed.SEED_TIMESTAMP,
                actor="system-seed",
                action="governance.enabled",
                resource_type="system",
                resource_id="ethical-controls",
                details={
                    "consent_required": True,
                    "purpose_limitation": True,
                    "sensitive_attributes_prohibited": True,
                    "minimum_cohort_size": 50,
                    "human_approval_for_high_risk": True,
                },
            )
        return generation

    def _set_setting(
        self,
        connection: sqlite3.Connection,
        key: str,
        value: Any,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, canonical_json(value), timestamp),
        )

    def set_setting(self, key: str, value: Any, *, timestamp: str | None = None) -> None:
        with self.transaction() as connection:
            self._set_setting(connection, key, value, timestamp or utc_now())

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return default if row is None else json.loads(row["value_json"])

    @staticmethod
    def _policy(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["objective_weights"] = json.loads(value.pop("objective_weights_json"))
        value["allowed_candidate_features"] = json.loads(
            value.pop("allowed_candidate_features_json")
        )
        value["constraints"] = json.loads(value.pop("constraints_json"))
        return value

    @staticmethod
    def _experiment(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["risk_reasons"] = json.loads(value.pop("risk_reasons_json"))
        value["guardrails"] = json.loads(value.pop("guardrails_json"))
        return value

    @staticmethod
    def _approval(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["reasons"] = json.loads(value.pop("reasons_json"))
        return value

    @staticmethod
    def _decision(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["candidate_ids"] = json.loads(value.pop("candidate_ids_json"))
        value["explanation"] = json.loads(value.pop("explanation_json"))
        return value

    def list_policies(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM policies ORDER BY domain, name, version"
            ).fetchall()
        return [self._policy(row) for row in rows if row is not None]

    def get_policy(self, policy_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM policies WHERE id = ?",
                (policy_id,),
            ).fetchone()
        return self._policy(row)

    def default_policy(self, domain: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM policies
                WHERE domain = ? AND status = 'active'
                ORDER BY version ASC, id ASC
                LIMIT 1
                """,
                (domain,),
            ).fetchone()
        return self._policy(row)

    def insert_policy(self, policy: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO policies (
                    id, name, domain, purpose, status, objective_weights_json,
                    exploration_rate, allowed_candidate_features_json,
                    constraints_json, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy["id"],
                    policy["name"],
                    policy["domain"],
                    policy["purpose"],
                    policy["status"],
                    canonical_json(policy["objective_weights"]),
                    policy["exploration_rate"],
                    canonical_json(policy["allowed_candidate_features"]),
                    canonical_json(policy["constraints"]),
                    policy["version"],
                    policy["created_at"],
                    policy["updated_at"],
                ),
            )

    def update_policy(self, policy_id: str, fields: dict[str, Any]) -> None:
        json_fields = {"objective_weights", "allowed_candidate_features", "constraints"}
        updates: list[tuple[str, Any]] = []
        for key, value in fields.items():
            query = POLICY_UPDATE_QUERIES.get(key)
            if query is None:
                raise ValueError(f"unsupported policy update field: {key}")
            updates.append(
                (query, canonical_json(value) if key in json_fields else value)
            )
        with self.transaction() as connection:
            for query, value in updates:
                connection.execute(query, (value, policy_id))

    def list_cohorts(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM cohorts ORDER BY domain, name"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_cohort(self, cohort_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM cohorts WHERE id = ?",
                (cohort_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def list_experiments(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM experiments
                ORDER BY
                    CASE status
                        WHEN 'running' THEN 0
                        WHEN 'pending_approval' THEN 1
                        WHEN 'approved' THEN 2
                        WHEN 'review' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC,
                    id
                """
            ).fetchall()
        return [self._experiment(row) for row in rows if row is not None]

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()
        return self._experiment(row)

    def running_experiments(self, domain: str, cohort_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM experiments
                WHERE status = 'running' AND domain = ? AND cohort_id = ?
                ORDER BY started_at, id
                """,
                (domain, cohort_id),
            ).fetchall()
        return [self._experiment(row) for row in rows if row is not None]

    def insert_experiment(self, experiment: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO experiments (
                    id, name, domain, purpose, hypothesis, status,
                    control_policy_id, treatment_policy_id, cohort_id,
                    traffic_percent, treatment_share, risk_level,
                    risk_reasons_json, guardrails_json, created_at, updated_at,
                    started_at, ended_at, rollback_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment["id"],
                    experiment["name"],
                    experiment["domain"],
                    experiment["purpose"],
                    experiment["hypothesis"],
                    experiment["status"],
                    experiment["control_policy_id"],
                    experiment["treatment_policy_id"],
                    experiment["cohort_id"],
                    experiment["traffic_percent"],
                    experiment["treatment_share"],
                    experiment["risk_level"],
                    canonical_json(experiment["risk_reasons"]),
                    canonical_json(experiment["guardrails"]),
                    experiment["created_at"],
                    experiment["updated_at"],
                    experiment.get("started_at"),
                    experiment.get("ended_at"),
                    experiment.get("rollback_reason"),
                ),
            )

    def update_experiment(self, experiment_id: str, fields: dict[str, Any]) -> None:
        json_fields = {"risk_reasons", "guardrails"}
        updates: list[tuple[str, Any]] = []
        for key, value in fields.items():
            query = EXPERIMENT_UPDATE_QUERIES.get(key)
            if query is None:
                raise ValueError(f"unsupported experiment update field: {key}")
            updates.append(
                (query, canonical_json(value) if key in json_fields else value)
            )
        with self.transaction() as connection:
            for query, value in updates:
                connection.execute(query, (value, experiment_id))

    def running_traffic_total(self, *, exclude_id: str | None = None) -> float:
        query = "SELECT COALESCE(SUM(traffic_percent), 0) FROM experiments WHERE status = 'running'"
        parameters: tuple[Any, ...] = ()
        if exclude_id is not None:
            query += " AND id != ?"
            parameters = (exclude_id,)
        with self.connect() as connection:
            return float(connection.execute(query, parameters).fetchone()[0])

    def pause_running_experiments(self, *, timestamp: str, reason: str) -> list[str]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT id FROM experiments WHERE status = 'running' ORDER BY id"
            ).fetchall()
            identifiers = [row["id"] for row in rows]
            connection.execute(
                """
                UPDATE experiments
                SET status = 'paused', updated_at = ?, rollback_reason = ?
                WHERE status = 'running'
                """,
                (timestamp, reason),
            )
        return identifiers

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM approvals"
        parameters: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY requested_at DESC, id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._approval(row) for row in rows if row is not None]

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE id = ?",
                (approval_id,),
            ).fetchone()
        return self._approval(row)

    def pending_approval(
        self,
        *,
        resource_type: str,
        resource_id: str,
        action: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM approvals
                WHERE resource_type = ? AND resource_id = ?
                    AND action = ? AND status = 'pending'
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                (resource_type, resource_id, action),
            ).fetchone()
        return self._approval(row)

    def insert_approval(self, approval: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO approvals (
                    id, resource_type, resource_id, action, status, risk_level,
                    reasons_json, requested_by, requested_at, decided_by,
                    decided_at, decision_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval["id"],
                    approval["resource_type"],
                    approval["resource_id"],
                    approval["action"],
                    approval["status"],
                    approval["risk_level"],
                    canonical_json(approval["reasons"]),
                    approval["requested_by"],
                    approval["requested_at"],
                    approval.get("decided_by"),
                    approval.get("decided_at"),
                    approval.get("decision_reason"),
                ),
            )

    def update_approval(self, approval_id: str, fields: dict[str, Any]) -> None:
        updates: list[tuple[str, Any]] = []
        for key, value in fields.items():
            query = APPROVAL_UPDATE_QUERIES.get(key)
            if query is None:
                raise ValueError(f"unsupported approval update field: {key}")
            updates.append((query, value))
        with self.transaction() as connection:
            for query, value in updates:
                connection.execute(query, (value, approval_id))

    def insert_decision(self, decision: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO decisions (
                    id, request_id, subject_hash, domain, purpose, cohort_id,
                    policy_id, experiment_id, variant, candidate_ids_json,
                    explanation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision["id"],
                    decision["request_id"],
                    decision["subject_hash"],
                    decision["domain"],
                    decision["purpose"],
                    decision["cohort_id"],
                    decision["policy_id"],
                    decision.get("experiment_id"),
                    decision["variant"],
                    canonical_json(decision["candidate_ids"]),
                    canonical_json(decision["explanation"]),
                    decision["created_at"],
                ),
            )

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        return self._decision(row)

    def get_exposure(self, event_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM exposures WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def insert_exposure(self, event: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO exposures (
                    event_id, decision_id, subject_hash, candidate_id, purpose,
                    experiment_id, variant, policy_id, occurred_at, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["decision_id"],
                    event["subject_hash"],
                    event["candidate_id"],
                    event["purpose"],
                    event.get("experiment_id"),
                    event["variant"],
                    event["policy_id"],
                    event["occurred_at"],
                    event["recorded_at"],
                ),
            )

    def get_outcome(self, event_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM outcomes WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def insert_outcome(self, event: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO outcomes (
                    event_id, exposure_event_id, outcome_type, value, purpose,
                    occurred_at, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["exposure_event_id"],
                    event["outcome_type"],
                    event["value"],
                    event["purpose"],
                    event["occurred_at"],
                    event["recorded_at"],
                ),
            )

    def insert_metric(
        self,
        *,
        experiment_id: str,
        cohort_id: str,
        metric_name: str,
        variant: str,
        sample_size: int,
        value: float,
        observed_at: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO metrics (
                    experiment_id, cohort_id, metric_name, variant,
                    sample_size, value, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    cohort_id,
                    metric_name,
                    variant,
                    sample_size,
                    value,
                    observed_at,
                ),
            )

    def list_metrics(self, experiment_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM metrics"
        parameters: tuple[Any, ...] = ()
        if experiment_id:
            query += " WHERE experiment_id = ?"
            parameters = (experiment_id,)
        query += " ORDER BY observed_at DESC, id DESC"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self.connect() as connection:
            return {
                table: int(connection.execute(query).fetchone()[0])
                for table, query in COUNT_QUERIES.items()
            }

    def append_audit(
        self,
        *,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any],
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            return self._append_audit(
                connection,
                timestamp=timestamp or utc_now(),
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        timestamp: str,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        previous = connection.execute(
            "SELECT record_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["record_hash"] if previous else "GENESIS"
        next_sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM audit_log"
            ).fetchone()[0]
        )
        audit_id = f"aud-{next_sequence:08d}"
        payload = {
            "id": audit_id,
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details,
        }
        record_hash = sha256(
            f"{previous_hash}:{canonical_json(payload)}".encode()
        ).hexdigest()
        connection.execute(
            """
            INSERT INTO audit_log (
                id, timestamp, actor, action, resource_type, resource_id,
                details_json, previous_hash, record_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                timestamp,
                actor,
                action,
                resource_type,
                resource_id,
                canonical_json(details),
                previous_hash,
                record_hash,
            ),
        )
        return {**payload, "previous_hash": previous_hash, "record_hash": record_hash}

    def list_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["details"] = json.loads(record.pop("details_json"))
            records.append(record)
        return records

    def verify_audit_chain(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
        expected_previous = "GENESIS"
        for row in rows:
            details = json.loads(row["details_json"])
            payload = {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "actor": row["actor"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "details": details,
            }
            expected_hash = sha256(
                f"{expected_previous}:{canonical_json(payload)}".encode()
            ).hexdigest()
            if row["previous_hash"] != expected_previous or row["record_hash"] != expected_hash:
                return {
                    "valid": False,
                    "records_checked": int(row["seq"]) - 1,
                    "failed_record": row["id"],
                }
            expected_previous = row["record_hash"]
        return {
            "valid": True,
            "records_checked": len(rows),
            "head_hash": expected_previous,
        }
