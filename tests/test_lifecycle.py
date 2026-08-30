from __future__ import annotations


def _transition(client, experiment_id: str, target_state: str):
    return client.post(
        f"/api/v1/experiments/{experiment_id}/transition",
        json={
            "target_state": target_state,
            "actor": "lifecycle-reviewer",
            "reason": f"Test transition to {target_state}.",
        },
    )


def test_high_risk_lifecycle_requires_approval_and_supports_rollback(client) -> None:
    experiment_id = "exp-test-high-risk"
    create = client.post(
        "/api/v1/experiments",
        json={
            "id": experiment_id,
            "name": "Test broader discovery launch",
            "domain": "media",
            "purpose": "surface relevant and trustworthy stories without maximizing compulsion",
            "hypothesis": (
                "Increasing bounded discovery breadth improves satisfaction while "
                "preserving quality and trust."
            ),
            "control_policy_id": "pol-media-depth-v2",
            "treatment_policy_id": "pol-media-breadth-v3",
            "cohort_id": "cohort-media-weekend",
            "traffic_percent": 10.0,
            "treatment_share": 0.5,
            "guardrails": {
                "min_quality_score": 0.75,
                "max_harm_rate": 0.015,
                "max_complaint_rate": 0.025,
                "min_fairness_ratio": 0.82,
            },
            "actor": "lifecycle-reviewer",
        },
    )
    assert create.status_code == 201
    assert create.json()["status"] == "draft"

    review = _transition(client, experiment_id, "review")
    assert review.status_code == 200
    assert review.json()["status"] == "review"

    approval_gate = _transition(client, experiment_id, "approved")
    assert approval_gate.status_code == 200
    assert approval_gate.json()["status"] == "pending_approval"
    approval_id = approval_gate.json()["pending_approval_id"]
    assert approval_id

    launch_before_approval = _transition(client, experiment_id, "running")
    assert launch_before_approval.status_code == 409
    assert (
        launch_before_approval.json()["error"]["code"]
        == "invalid_experiment_transition"
    )

    decision = client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={
            "decision": "approved",
            "actor": "human-reviewer",
            "reason": "Reviewed purpose, cohort, risk, and rollback controls.",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    launch = _transition(client, experiment_id, "running")
    assert launch.status_code == 200
    assert launch.json()["status"] == "running"

    rollback = _transition(client, experiment_id, "rolled_back")
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "rolled_back"
    assert "rolled_back" in rollback.json()["status"]
    assert rollback.json()["rollback_reason"]

    actions = {
        record["action"]
        for record in client.get("/api/v1/audit").json()["records"]
    }
    assert "experiment.approval_requested" in actions
    assert "approval.approved" in actions
    assert "experiment.launched" in actions
    assert "experiment.rolled_back" in actions


def test_kill_switch_pauses_running_experiments_and_blocks_launch(client) -> None:
    enabled = client.post(
        "/api/v1/control/kill-switch",
        json={
            "enabled": True,
            "actor": "incident-commander",
            "reason": "Test emergency stop behavior.",
        },
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert set(enabled.json()["paused_experiments"]) == {
        "exp-commerce-durable-value",
        "exp-community-trust",
    }

    experiments = client.get("/api/v1/experiments").json()["experiments"]
    assert all(experiment["status"] != "running" for experiment in experiments)

    disabled = client.post(
        "/api/v1/control/kill-switch",
        json={
            "enabled": False,
            "actor": "incident-commander",
            "reason": "Test complete; leave experiments paused for manual review.",
        },
    )
    assert disabled.status_code == 200
    experiments = client.get("/api/v1/experiments").json()["experiments"]
    assert all(experiment["status"] != "running" for experiment in experiments)
