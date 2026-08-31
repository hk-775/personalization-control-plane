# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Editable and rendered current-system and AWS reference architecture diagrams.
- Evaluator startup, threat model, production-readiness ledger, publication
  inventory, and launch materials.
- Downloadable architecture artifacts in the packaged and static sites.
- GitHub Pages publication workflow.

### Changed

- Container deployment now installs the locked environment with pinned `uv`
  on a security-updated Alpine base and starts the service through
  `uv run --no-sync`.
- CI uses immutable action revisions, runs the real Python 3.11/3.12 matrix,
  and audits source and locked runtime dependencies.
- Automated dependency-update pull requests are disabled; vulnerability alerts
  remain enabled and maintainers apply reviewed updates manually.
- Event replays without a supplied timestamp retain the original event time.
- Compose binds the unauthenticated demo to loopback by default.

## [0.1.0] - 2026-08-30

### Added

- Deterministic recommendation ranking with factor-level explanations.
- Versioned recommendation policies and bounded multi-objective optimization.
- Experiment CRUD, lifecycle transitions, traffic allocation, approval gates,
  rollback, and a global kill switch.
- Consent, purpose-limitation, sensitive-input, privacy-floor, exploration,
  dark-pattern, quality, harm, complaint, and fairness controls.
- Idempotent exposure and outcome ingestion with decision linkage.
- Privacy-bounded metrics and aggregate fairness evaluation.
- SHA-256 hash-chained audit records with verification.
- Fully seeded fictional commerce, media, and community demo portfolio.
- Responsive landing page, live operator dashboard, animated architecture
  explorer, and matching publishable static site.
- Docker, Compose, validation scripts, documentation, and CI.
