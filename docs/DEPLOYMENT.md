# Deployment Guide

## Supported evaluation profiles

### Local Python

```bash
./scripts/demo.sh
```

Default bind:

```text
127.0.0.1:8102
```

Environment variables:

| Variable | Default |
|---|---|
| `PCP_HOST` | `127.0.0.1` |
| `PCP_BIND_ADDRESS` | `127.0.0.1` (Compose host binding) |
| `PCP_PORT` | `8102` |
| `PCP_DB_PATH` | `data/personalization-control-plane.db` |
| `PCP_LOG_LEVEL` | `info` |

### Docker Compose

```bash
docker compose up --build
```

Compose publishes host port `${PCP_PORT:-8102}` to container port `8102`,
persists `/app/data` in a named volume, drops Linux capabilities, enables
`no-new-privileges`, uses a read-only root filesystem, and health-checks the
local API. The image copies pinned `uv`, creates its runtime environment with
`uv sync --locked --no-dev --no-editable`, and starts the already-synchronized
environment with `uv run --locked --no-sync`. Compose binds to
`${PCP_BIND_ADDRESS:-127.0.0.1}` so the unauthenticated demo is not exposed to
the local network by default.

## Static site

Publish the contents of `site/` through any static host. It has no external
asset dependencies. On GitHub Pages, the landing page and dashboard enter an
explicit read-only synthetic mode before any request is made; they do not probe
the FastAPI service, open a WebSocket, or contact cloud resources. Other static
hosts fall back to the same fictional data when the API is absent.

The static site is not an operator control plane; state-changing actions require
the FastAPI service.

## Production adaptation checklist

The checked-in profiles are evaluation profiles. Before production:

### Identity and authorization

- authenticate workload and browser clients;
- authorize every policy, experiment, approval, kill-switch, audit, and reset
  action;
- enforce least privilege and separation of duties;
- remove or strongly restrict the demo reset endpoint;
- use server-derived actor identity, never request-body identity.

### Data protection

- replace free-form purpose text with versioned purpose identifiers;
- integrate an authoritative consent and withdrawal system;
- define deletion, retention, and subject-rights workflows;
- encrypt durable state and backups;
- keep raw subject identifiers out of the control plane;
- review candidate feature provenance and proxy risk;
- prevent logs and traces from collecting raw personal data.

### State and availability

- replace SQLite with a transactional, replicated database;
- make state mutation and audit append one atomic operation;
- use durable, idempotent event ingestion;
- run retention deletion and aggregate jobs;
- add concurrency control and revision checks;
- make kill-switch and rollback paths highly available and independently
  operable;
- test backup restore and regional recovery.

### Audit and evidence

- export audit records to append-only storage;
- sign or externally notarize audit heads;
- retain approval evidence outside the serving database;
- alert on verification failure;
- document clock, identity, and key-management assumptions.

### Experiment statistics

- define exposure units, interference assumptions, power, sequential testing,
  multiple-comparison controls, and stopping rules;
- separate safety guardrails from optimization metrics;
- account for novelty, seasonality, delayed outcomes, and data quality;
- require review before promoting a result beyond experiment traffic.

### Security and operations

- terminate TLS at a reviewed ingress;
- add request limits, rate limits, body-size limits, and timeouts;
- run dependency, container, secret, and static-analysis scans;
- capture metrics, logs, traces, and alerts without leaking personal data;
- rehearse approval, rollback, kill-switch, audit-failure, and database-failure
  incidents;
- conduct threat modeling and penetration testing.

### Ethical and legal review

- complete a domain-specific impact assessment;
- identify affected stakeholders and redress paths;
- validate accessibility;
- review fairness metrics with domain experts and affected communities;
- prohibit high-impact uses that need stronger safeguards;
- obtain applicable privacy, consumer-protection, sector, and employment review.

## Reverse proxy note

If an evaluation deployment must be shared, bind the service privately and put
an authenticated reverse proxy in front of port `8102`. The application does
not itself provide authentication and must not be directly exposed to an
untrusted network.

## Health and smoke

```bash
curl -sS http://127.0.0.1:8102/api/v1/health
./scripts/smoke.sh
```

The smoke script uses an isolated temporary database and removes it on exit.
