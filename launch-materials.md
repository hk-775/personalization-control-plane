# Personalization Control Plane Launch Materials

Status: customer-review draft for the open-source v0.1 repository.

## One-line description

An open-source control plane for governed recommendation optimization and
experimentation.

## Short description

Personalization Control Plane versions recommendation policy, bounds
experiments, allocates traffic deterministically, exposes scoring factors,
links outcomes, requires human approval for elevated risk, suppresses small
cohorts, rolls back guardrail breaches, and records a verifiable local audit
chain.

## Suggested announcement

We are sharing Personalization Control Plane as a fully seeded open-source
evaluation package for teams exploring accountable recommendation optimization.
It includes a product site, operator dashboard, interactive architecture,
fictional multi-domain portfolio, guided scenarios, API, tests, Docker profile,
editable diagrams, and explicit ethics and production-readiness boundaries.

The package makes no production fairness, legal-compliance, causal-impact, or
business-lift claim. It is designed to make controls inspectable.

## Demo talking points

1. Frame personalization as a control problem, not only a model problem.
2. Show one policy model across commerce, media, and community examples.
3. Run deterministic ranking and inspect every factor contribution.
4. Show an unsafe candidate excluded before ranking.
5. Show small-cohort metric suppression.
6. Show a risky experiment paused for named human approval.
7. Trigger automatic rollback on a guardrail breach.
8. Trigger the global kill switch and baseline fallback.
9. Verify the audit chain and end with production blockers.

## Supportable claims

- Fully seeded local demo with no credentials or external runtime calls.
- Deterministic allocation and explainable weighted scoring.
- Consent, purpose, sensitive-input, privacy-floor, traffic, and exploration
  controls enforced in code.
- Human approval for configured elevated-risk launches.
- Automatic rollback and global kill-switch behavior.
- Hash-linked local audit records with verification.
- Static offline customer experience with fictional fallback data.

## Claims to avoid

- Production ready, enterprise ready, highly available, or scalable.
- Fair, unbiased, compliant, certified, privacy preserving, or zero trust.
- Causal uplift, improved well-being, or business-impact claims.
- Tamper-proof audit, authenticated approvals, or non-repudiation.
- Safe use for high-impact eligibility or allocation decisions.

## Assets

- Repository: `https://github.com/hk-775/personalization-control-plane`
- Project site: `https://hk-775.github.io/personalization-control-plane/`
- Landing page: `site/index.html`
- Operator dashboard: `site/dashboard.html`
- Architecture explorer: `site/architecture.html`
- Current architecture PNG: `site/assets/system-architecture.png`
- Current architecture source: `site/assets/system-architecture.drawio`
- AWS reference PNG: `site/assets/aws-reference-architecture.png`
- AWS reference source: `site/assets/aws-reference-architecture.drawio`
- Presenter guide: `docs/DEMO.md`
- Publication inventory: `docs/PUBLICATION_ARTIFACTS.md`

## Pre-publication checklist

- Run validation and smoke tests from a clean checkout.
- Run `node scripts/test_public_site.mjs` with Node.js 22 and Chrome/Chromium.
- Review diagram labels against the implemented code and readiness ledger.
- Confirm repository visibility, Pages settings, branch protection, topics,
  license, and private vulnerability reporting.
- Keep the Pages job gated while the repository is private; after publication
  approval, make the repository public and enable GitHub Actions as the Pages
  source before the first deployment.
- Test the static site at its subpath and with the API unavailable.
- Confirm the published dashboard makes no API or WebSocket requests.
- Review accessibility, ethics, security, and announcement copy.
