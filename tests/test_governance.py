from __future__ import annotations

from copy import deepcopy


def test_consent_is_required(client, commerce_rank_payload: dict) -> None:
    payload = {**commerce_rank_payload, "consent": False}

    response = client.post("/api/v1/recommendations/rank", json=payload)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "consent_required"


def test_sensitive_attributes_and_identifiers_are_rejected(
    client,
    commerce_rank_payload: dict,
) -> None:
    sensitive = deepcopy(commerce_rank_payload)
    sensitive["context"] = {"user_age_years": 41}
    direct_identifier = deepcopy(commerce_rank_payload)
    direct_identifier["request_id"] = "req-test-commerce-002"
    direct_identifier["candidates"][0]["metadata"]["email_address"] = "person@example.test"

    sensitive_response = client.post("/api/v1/recommendations/rank", json=sensitive)
    identifier_response = client.post(
        "/api/v1/recommendations/rank",
        json=direct_identifier,
    )

    assert sensitive_response.status_code == 422
    assert sensitive_response.json()["error"]["code"] == "sensitive_attribute_prohibited"
    assert identifier_response.status_code == 422
    assert identifier_response.json()["error"]["code"] == "sensitive_attribute_prohibited"


def test_dark_pattern_policy_objectives_are_prohibited(client) -> None:
    response = client.post(
        "/api/v1/policies",
        json={
            "id": "pol-dark-pattern-test",
            "name": "Prohibited compulsion test",
            "domain": "media",
            "purpose": "surface relevant and trustworthy stories without maximizing compulsion",
            "objective_weights": {
                "relevance": 0.6,
                "time_spent": 0.4,
            },
            "exploration_rate": 0.01,
            "allowed_candidate_features": ["relevance", "time_spent"],
            "constraints": {"candidate_safety_floor": 0.8},
            "actor": "test-operator",
        },
    )

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "policy_governance_violation"
    assert any("dark-pattern" in violation for violation in body["details"]["violations"])


def test_small_cohort_forces_baseline_and_suppresses_metrics(
    client,
    commerce_rank_payload: dict,
) -> None:
    payload = {
        **commerce_rank_payload,
        "request_id": "req-small-cohort-001",
        "cohort_id": "cohort-commerce-small-pilot",
        "policy_id": "pol-commerce-value-v4",
    }

    rank_response = client.post("/api/v1/recommendations/rank", json=payload)
    metric_response = client.get(
        "/api/v1/metrics",
        params={"experiment_id": "exp-commerce-small-pilot"},
    )
    launch_response = client.post(
        "/api/v1/experiments/exp-commerce-small-pilot/transition",
        json={
            "target_state": "review",
            "actor": "test-operator",
            "reason": "Attempt launch readiness check.",
        },
    )

    assert rank_response.status_code == 200
    rank = rank_response.json()
    assert rank["policy"]["id"] == "pol-commerce-balanced-v3"
    assert rank["governance"]["cohort_privacy"] == "fallback"
    assert rank["assignment"]["experiment_id"] is None

    metric = metric_response.json()["metrics"][0]
    assert metric["privacy_status"] == "suppressed"
    assert metric["value"] is None

    assert launch_response.status_code == 409
    assert launch_response.json()["error"]["code"] == "cohort_privacy_floor"
