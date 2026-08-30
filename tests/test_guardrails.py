from __future__ import annotations


def test_guardrail_breach_automatically_rolls_back_running_experiment(client) -> None:
    response = client.post(
        "/api/v1/guardrails/evaluate",
        json={
            "experiment_id": "exp-community-trust",
            "sample_size": 240,
            "metrics": {
                "quality_score": 0.61,
                "harm_rate": 0.018,
                "complaint_rate": 0.031,
                "fairness_ratio": 0.79,
            },
            "actor": "guardrail-monitor",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed"
    assert result["action"] == "rolled_back"
    assert result["failure_count"] == 4

    experiment = client.get("/api/v1/experiments/exp-community-trust").json()
    assert experiment["status"] == "rolled_back"
    assert "Guardrail breach" in experiment["rollback_reason"]


def test_guardrail_metrics_below_privacy_floor_are_suppressed(client) -> None:
    response = client.post(
        "/api/v1/guardrails/evaluate",
        json={
            "experiment_id": "exp-community-trust",
            "sample_size": 22,
            "metrics": {
                "quality_score": 0.2,
                "harm_rate": 0.9,
            },
            "actor": "guardrail-monitor",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "suppressed",
        "reason": "minimum_cohort_size",
        "sample_size": 22,
        "minimum_cohort_size": 50,
        "metrics": {},
        "action": "none",
    }


def test_fairness_pass_failure_suppression_and_opaque_keys(client) -> None:
    passed = client.post(
        "/api/v1/guardrails/fairness",
        json={
            "experiment_id": "exp-community-trust",
            "groups": [
                {
                    "group_key": "group-a",
                    "sample_size": 120,
                    "positive_rate": 0.80,
                    "quality_score": 0.78,
                },
                {
                    "group_key": "group-b",
                    "sample_size": 130,
                    "positive_rate": 0.70,
                    "quality_score": 0.76,
                },
            ],
            "actor": "fairness-monitor",
        },
    )
    assert passed.status_code == 200
    assert passed.json()["status"] == "passed"
    assert passed.json()["action"] == "none"

    suppressed = client.post(
        "/api/v1/guardrails/fairness",
        json={
            "experiment_id": "exp-community-trust",
            "groups": [
                {
                    "group_key": "group-a",
                    "sample_size": 49,
                    "positive_rate": 0.80,
                    "quality_score": 0.78,
                },
                {
                    "group_key": "group-b",
                    "sample_size": 130,
                    "positive_rate": 0.70,
                    "quality_score": 0.76,
                },
            ],
            "actor": "fairness-monitor",
        },
    )
    assert suppressed.status_code == 200
    assert suppressed.json()["status"] == "suppressed"
    assert suppressed.json()["group_metrics"] == []

    semantic_key = client.post(
        "/api/v1/guardrails/fairness",
        json={
            "experiment_id": "exp-community-trust",
            "groups": [
                {
                    "group_key": "race-a",
                    "sample_size": 120,
                    "positive_rate": 0.80,
                    "quality_score": 0.78,
                },
                {
                    "group_key": "group-b",
                    "sample_size": 130,
                    "positive_rate": 0.70,
                    "quality_score": 0.76,
                },
            ],
            "actor": "fairness-monitor",
        },
    )
    assert semantic_key.status_code == 422
    assert semantic_key.json()["error"]["code"] == "opaque_group_keys_required"

    failed = client.post(
        "/api/v1/guardrails/fairness",
        json={
            "experiment_id": "exp-community-trust",
            "groups": [
                {
                    "group_key": "group-a",
                    "sample_size": 120,
                    "positive_rate": 0.90,
                    "quality_score": 0.78,
                },
                {
                    "group_key": "group-b",
                    "sample_size": 130,
                    "positive_rate": 0.60,
                    "quality_score": 0.76,
                },
            ],
            "actor": "fairness-monitor",
        },
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["action"] == "rolled_back"
    assert (
        client.get("/api/v1/experiments/exp-community-trust").json()["status"]
        == "rolled_back"
    )
