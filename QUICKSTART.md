# Quickstart

## 1. Prerequisites

- Python 3.11 or newer
- `uv`
- A free local port `8102`

No database server, cloud account, API key, Node.js installation, or external
runtime service is required.

## 2. Start the seeded product

From the repository root:

```bash
./scripts/demo.sh
```

Open `http://127.0.0.1:8102`.

The command creates a local environment, installs the package, starts FastAPI,
creates the SQLite database if needed, and loads the canonical fictional seed.

To use an alternate database while retaining the standard port:

```bash
PCP_DB_PATH=/tmp/pcp-demo.db ./scripts/demo.sh
```

## 3. Suggested five-minute walkthrough

1. Open the landing page and review the enforced boundaries.
2. Open **Operator dashboard** and scan the portfolio overview.
3. In **Experiments**, note:
   - one 4% commerce experiment running;
   - one 12% media experiment waiting for human approval;
   - one intentionally undersized experiment blocked by the privacy floor.
4. Open **Guided demo**:
   - run **Transparent deterministic ranking**;
   - run **Minimum cohort privacy floor**;
   - inspect **Human approval for risky launches**;
   - run **Automatic guardrail rollback**;
   - finish with **Global kill switch**.
5. Open **Approvals & audit** to verify the resulting evidence.
6. Click **Reset demo** to restore the canonical seed.

The full presenter notes are in [docs/DEMO.md](docs/DEMO.md).

## 4. Try the API

Health:

```bash
curl -sS http://127.0.0.1:8102/api/v1/health
```

Portfolio:

```bash
curl -sS http://127.0.0.1:8102/api/v1/portfolio
```

Experiments:

```bash
curl -sS http://127.0.0.1:8102/api/v1/experiments
```

Audit verification:

```bash
curl -sS 'http://127.0.0.1:8102/api/v1/audit?limit=20'
```

Interactive API documentation:

```text
http://127.0.0.1:8102/api/docs
```

## 5. Run with Docker

```bash
docker compose up --build
```

The service is available at `http://127.0.0.1:8102` and stores the SQLite file
in the named `pcp-data` volume.

Stop it:

```bash
docker compose down
```

Reset the Docker volume as well:

```bash
docker compose down --volumes
```

## 6. Test and validate

```bash
./scripts/test.sh
./scripts/smoke.sh
./scripts/validate.sh
```

The smoke test starts an isolated server on port `8102`, checks all three pages,
calls health, and submits a governed rank request.

## 7. Static site

`site/` is a byte-for-byte mirror of the served landing, dashboard, and
architecture pages plus their assets. The dashboard automatically switches to
a populated read-only fictional preview when the API is unavailable.

Serve it with any static file server:

```bash
python3 -m http.server 8102 --directory site
```

Open `http://127.0.0.1:8102`.
