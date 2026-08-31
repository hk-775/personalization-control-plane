from __future__ import annotations

import pytest


def test_exposure_outcome_idempotency_and_purpose(
    client,
    commerce_rank_payload: dict,
    monkeypatch,
) -> None:
    rank = client.post(
        "/api/v1/recommendations/rank",
        json=commerce_rank_payload,
    )
    assert rank.status_code == 200
    decision = rank.json()
    candidate_id = decision["recommendations"][0]["candidate_id"]

    timestamps = iter(
        f"2026-08-31T00:00:{second:02d}Z"
        for second in range(20)
    )
    monkeypatch.setattr(
        "personalization_control_plane.service.utc_now",
        lambda: next(timestamps),
    )

    exposure_payload = {
        "event_id": "evt-exposure-001",
        "decision_id": decision["decision_id"],
        "subject_id": commerce_rank_payload["subject_id"],
        "candidate_id": candidate_id,
        "purpose": commerce_rank_payload["purpose"],
    }
    exposure = client.post("/api/v1/events/exposures", json=exposure_payload)
    replay = client.post("/api/v1/events/exposures", json=exposure_payload)

    assert exposure.status_code == 201
    assert exposure.json()["idempotent_replay"] is False
    assert replay.status_code == 201
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["occurred_at"] == exposure.json()["occurred_at"]

    conflict = client.post(
        "/api/v1/events/exposures",
        json={**exposure_payload, "candidate_id": "item-not-in-decision"},
    )
    assert conflict.status_code in {409, 422}

    outcome_payload = {
        "event_id": "evt-outcome-001",
        "exposure_event_id": exposure_payload["event_id"],
        "outcome_type": "satisfaction",
        "value": 0.9,
        "purpose": commerce_rank_payload["purpose"],
    }
    outcome = client.post("/api/v1/events/outcomes", json=outcome_payload)
    outcome_replay = client.post("/api/v1/events/outcomes", json=outcome_payload)
    prohibited = client.post(
        "/api/v1/events/outcomes",
        json={
            **outcome_payload,
            "event_id": "evt-outcome-002",
            "outcome_type": "time_spent",
        },
    )

    assert outcome.status_code == 201
    assert outcome_replay.json()["idempotent_replay"] is True
    assert outcome_replay.json()["occurred_at"] == outcome.json()["occurred_at"]
    assert prohibited.status_code == 422
    assert prohibited.json()["error"]["code"] == "outcome_type_not_allowed"


def test_audit_chain_detects_tampering(client, app) -> None:
    client.post(
        "/api/v1/control/kill-switch",
        json={
            "enabled": True,
            "actor": "audit-tester",
            "reason": "Create an auditable state change.",
        },
    )
    before = client.get("/api/v1/audit").json()["verification"]
    assert before["valid"] is True

    database = app.state.control_plane.db
    with database.connect() as connection:
        connection.execute(
            "UPDATE audit_log SET details_json = ? WHERE seq = 1",
            ('{"tampered":true}',),
        )
        connection.commit()

    after = client.get("/api/v1/audit").json()["verification"]
    assert after["valid"] is False
    assert after["failed_record"] == "aud-00000001"


def test_demo_reset_restores_seeded_state(
    client,
    commerce_rank_payload: dict,
) -> None:
    client.post("/api/v1/recommendations/rank", json=commerce_rank_payload)
    client.post(
        "/api/v1/control/kill-switch",
        json={
            "enabled": True,
            "actor": "reset-tester",
            "reason": "Change state before reset.",
        },
    )

    reset = client.post(
        "/api/v1/demo/reset",
        json={
            "actor": "reset-tester",
            "reason": "Restore the canonical seed.",
        },
    )

    assert reset.status_code == 200
    body = reset.json()
    assert body["status"] == "reset"
    assert body["counts"]["decisions"] == 0
    assert body["counts"]["exposures"] == 0
    assert body["kill_switch"]["enabled"] is False

    experiments = {
        experiment["id"]: experiment
        for experiment in client.get("/api/v1/experiments").json()["experiments"]
    }
    assert experiments["exp-commerce-durable-value"]["status"] == "running"
    assert experiments["exp-community-trust"]["status"] == "running"
    assert client.get("/api/v1/audit").json()["verification"]["valid"] is True


def test_api_pages_health_and_state_changes(client) -> None:
    assert client.get("/").status_code == 200
    assert "Optimize recommendations" in client.get("/").text
    for path, marker in (
        ("/", "Optimize recommendations"),
        ("/index.html", "Optimize recommendations"),
        ("/dashboard", "Operator Dashboard"),
        ("/dashboard.html", "Operator Dashboard"),
        ("/architecture", "One governed decision loop"),
        ("/architecture.html", "One governed decision loop"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert marker in response.text

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert health.json()["external_dependencies"] == []

    portfolio = client.get("/api/v1/portfolio")
    assert portfolio.status_code == 200
    assert set(portfolio.json()["domains"]) == {"commerce", "community", "media"}


def test_storage_rejects_unapproved_dynamic_update_columns(app) -> None:
    database = app.state.control_plane.db
    with pytest.raises(ValueError, match="unsupported policy update field"):
        database.update_policy("policy-id", {"status = 'active' --": "active"})
    with pytest.raises(ValueError, match="unsupported experiment update field"):
        database.update_experiment("experiment-id", {"status = 'running' --": "running"})
    with pytest.raises(ValueError, match="unsupported approval update field"):
        database.update_approval("approval-id", {"status = 'approved' --": "approved"})
