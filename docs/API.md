# API Guide

Base URL for the local demo:

```text
http://127.0.0.1:8102
```

Interactive OpenAPI documentation:

```text
http://127.0.0.1:8102/api/docs
```

All JSON request models reject unknown fields. Errors use:

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "Human-readable message.",
    "details": {},
    "request_id": "req-http-..."
  }
}
```

## System and portfolio

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Lightweight health alias |
| GET | `/api/v1/health` | Storage, audit-chain, kill-switch, and dependency health |
| GET | `/api/v1/portfolio` | Dashboard summary and governance configuration |

## Recommendation policies

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/policies` | List versions |
| POST | `/api/v1/policies` | Create a validated draft version |
| GET | `/api/v1/policies/{id}` | Inspect one version |
| PUT | `/api/v1/policies/{id}` | Update a draft version |
| POST | `/api/v1/policies/{id}/activate` | Activate a valid draft |

Active policy versions are immutable. Create a new id/version to change serving
behavior.

## Cohorts

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/cohorts` | List fictional operational cohorts and privacy eligibility |

The demo intentionally does not expose per-person cohort membership.

## Experiments

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/experiments` | List and enrich experiments |
| POST | `/api/v1/experiments` | Create a draft |
| GET | `/api/v1/experiments/{id}` | Inspect lifecycle, risk, guardrails, and approval |
| POST | `/api/v1/experiments/{id}/transition` | Request a valid state transition |

Transition request:

```json
{
  "target_state": "approved",
  "actor": "operator-01",
  "reason": "Purpose, cohort, treatment, and guardrails reviewed."
}
```

Valid targets depend on current state. A high-risk transition from `review`
toward approval produces `pending_approval` instead of `approved`.

## Approvals

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/approvals` | List; optional `status` query |
| POST | `/api/v1/approvals/{id}/decision` | Approve or deny a pending request |

Decision:

```json
{
  "decision": "approved",
  "actor": "reviewer-01",
  "reason": "Risk controls and rollback plan are acceptable."
}
```

## Ranking

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/recommendations/rank` | Govern, allocate, score, explain, and persist a decision |
| GET | `/api/v1/decisions/{id}` | Inspect the persisted decision |

Required rank concepts:

- pseudonymous `subject_id`;
- exact `domain` and `purpose`;
- affirmative `consent`;
- a known operational `cohort_id`;
- one to 100 candidates;
- normalized feature values from zero to one.

Unknown candidate features, direct identifiers, and sensitive keys fail.

## Events

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/events/exposures` | Record one displayed candidate from a decision |
| POST | `/api/v1/events/outcomes` | Record an allowlisted outcome linked to exposure |

Allowed outcome types:

- `completion`
- `conversion`
- `dismiss`
- `hide`
- `report`
- `return`
- `save`
- `satisfaction`

Raw events older than 90 days are rejected. The demo does not yet run a
background retention deletion worker.

## Metrics and guardrails

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/metrics` | List metrics; optional `experiment_id` |
| POST | `/api/v1/guardrails/evaluate` | Evaluate normalized aggregate metrics |
| POST | `/api/v1/guardrails/fairness` | Evaluate opaque aggregate groups |

Guardrail request:

```json
{
  "experiment_id": "exp-community-trust",
  "sample_size": 240,
  "metrics": {
    "quality_score": 0.61,
    "harm_rate": 0.018,
    "complaint_rate": 0.031,
    "fairness_ratio": 0.79
  },
  "actor": "guardrail-monitor"
}
```

If the experiment is running and one or more hard checks fail, the response
contains `"action": "rolled_back"`.

Fairness groups must use opaque identifiers such as `group-a`, never semantic
protected-attribute labels. Each group must have at least 50 samples.

## Emergency control

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/control/kill-switch` | Read current state |
| POST | `/api/v1/control/kill-switch` | Enable or disable |

Enabling pauses every running experiment. Disabling never resumes one.

## Audit

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/audit` | List newest records and verify the complete chain |

`limit` is bounded from 1 to 500.

## Demo

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/demo` | Scenario manifest and fictional sample candidates |
| POST | `/api/v1/demo/scenarios/{id}` | Execute a guided scenario |
| POST | `/api/v1/demo/reset` | Clear mutable state and restore the canonical seed |

Reset is intentionally destructive to local demo data and should not be exposed
in a production deployment.
