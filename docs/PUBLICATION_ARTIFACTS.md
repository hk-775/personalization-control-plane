# Publication Artifacts

## Purpose

This inventory defines the customer-facing artifact set for Personalization
Control Plane and keeps the repository, packaged web experience, static site,
architecture material, evaluator guidance, and release checks aligned.

## Customer-facing set

| Artifact | Purpose | Canonical source |
|---|---|---|
| Repository overview | Product boundary, demo, controls, limitations, document index | `README.md` |
| Quick evaluation | Installation and first walkthrough | `QUICKSTART.md` |
| Evaluator startup | Acceptance checks, static backup, sharing cautions | `STARTUP.md` |
| Product site | Public framing and enforced boundaries | `site/index.html` |
| Operator dashboard | Seeded portfolio, controls, guided scenarios, audit | `site/dashboard.html` |
| Architecture explorer | Interactive implemented flows and downloadable diagrams | `site/architecture.html` |
| Current architecture | Implemented local process and trust boundary | `site/assets/system-architecture.drawio`, `.png` |
| AWS reference architecture | Proposed production deployment, clearly labeled | `site/assets/aws-reference-architecture.drawio`, `.png` |
| Long-form architecture | Components, lifecycle, events, audit, static mirror | `docs/ARCHITECTURE.md` |
| API reference | Endpoints and state contracts | `docs/API.md` |
| Demo guide | Seven-to-ten-minute presenter path | `docs/DEMO.md` |
| Ethics and responsible use | Enforced controls, residual risk, excluded uses | `docs/ETHICS.md` |
| Threat model | Assets, actors, threats, controls, residual risks | `docs/THREAT_MODEL.md` |
| Production readiness | Evidence, blockers, maturation sequence | `docs/PRODUCTION_READINESS.md` |
| Deployment guide | Local/Docker profiles and adaptation checklist | `docs/DEPLOYMENT.md` |
| Launch materials | Supportable claims, claims to avoid, asset locations | `launch-materials.md` |

## Visual source of truth

- `system-architecture.drawio` is the editable current-system diagram.
- `system-architecture.png` is the README and presentation render.
- `aws-reference-architecture.drawio` is the editable proposed deployment.
- `aws-reference-architecture.png` is its presentation render.

The four files exist under both the packaged web assets and `site/assets/`.
`scripts/validate_package.py` requires exact byte equality.

## Static publication

The Pages workflow publishes only `site/`. It contains no credentials,
telemetry, remote fonts, third-party scripts, or network API dependency. The
dashboard falls back to fictional read-only data when the FastAPI service is
absent.

## Validation

Before publication:

```bash
./scripts/validate.sh
./scripts/smoke.sh
```

Then serve `site/` locally and inspect `/`, `/dashboard.html`, and
`/architecture.html` with scripts enabled and disabled.

## Intentional omissions

Version 0.1 does not publish cloud templates, production dashboards, fairness
certifications, benchmark claims, real customer data, trained models, feature
pipelines, or signed runtime artifacts. Publishing those would imply an
operational surface or assurance level that does not exist.
