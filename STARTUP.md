# Evaluator Startup Guide

## Supported evaluation

Personalization Control Plane 0.1 is a local, fully seeded product demonstration
for governed recommendation optimization. Use fictional data only. It is not a
production recommendation, experimentation, identity, or compliance service.

## Prerequisites

- macOS or Linux
- Python 3.11 or newer
- `uv`
- local port `8102`

No cloud account, API key, database server, or model provider is required.

## Start

```bash
./scripts/demo.sh
```

Open:

- product site: `http://127.0.0.1:8102`
- operator dashboard: `http://127.0.0.1:8102/dashboard`
- architecture explorer: `http://127.0.0.1:8102/architecture`
- OpenAPI: `http://127.0.0.1:8102/api/docs`

The service creates `data/personalization-control-plane.db` and loads the
canonical fictional portfolio.

## Five-minute acceptance path

1. Confirm the landing page states the local and ethical boundaries.
2. Open the dashboard and verify the fictional commerce, media, and community
   portfolio.
3. Run the transparent-ranking scenario.
4. Show the small-cohort metric value suppressed as `null`.
5. Advance the risky launch to its named human approval.
6. Trigger a guardrail breach and confirm automatic rollback.
7. Enable the global kill switch and confirm baseline serving.
8. Verify the audit chain, then reset the demo.

## Validation

```bash
./scripts/validate.sh
./scripts/smoke.sh
```

Expected baseline:

- 17 tests pass;
- branch coverage remains at or above 80%;
- lint and package validation pass;
- the static site matches the packaged browser files;
- the smoke test exercises all three pages and a governed rank request.

## Static backup

```bash
python3 -m http.server 8102 --directory site
```

The static dashboard uses read-only fictional fallback data. State-changing
controls require the FastAPI service.

## Reset and stop

Reset from the dashboard or call `POST /api/v1/demo/reset`. Stop the foreground
server with `Ctrl-C`. The SQLite database is local and can be removed only when
the evaluator no longer needs its demo state.

## Before sharing

- do not expose the local service directly to an untrusted network;
- do not enter personal data, credentials, or confidential feature values;
- describe the fairness ratio as a diagnostic, not proof of fair impact;
- describe deterministic scoring as transparent, not causally validated;
- end with the limitations in `docs/ETHICS.md` and
  `docs/PRODUCTION_READINESS.md`.
