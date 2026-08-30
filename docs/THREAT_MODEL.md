# Threat Model

## Scope

This model covers the local v0.1 FastAPI service, deterministic ranker,
experiment lifecycle, guardrails, SQLite state, static pages, and seeded demo.

## Assets

- Approved recommendation-policy versions and exact purposes.
- Experiment state, traffic limits, and human approvals.
- Pseudonymous decision, exposure, and outcome linkage.
- Privacy-suppressed metric values.
- Guardrail thresholds, rollback state, and kill-switch state.
- Audit sequence and record hashes.
- Availability of baseline serving and operator controls.

## Actors

- Product client submitting rank and event requests.
- Human operator managing policies and experiments.
- Local evaluator controlling the host.
- Malicious client attempting malformed or abusive input.
- Local process or administrator with filesystem access.
- Contributor proposing source changes.

## Trust assumptions

- The local evaluator protects the host account and database file.
- Caller-supplied actor names and consent assertions are truthful.
- Candidate features are normalized, accurate, and purpose appropriate.
- Cooperative writers use the application service.
- Python, SQLite, FastAPI, and the operating system behave as documented.

The identity, consent, and feature-provenance assumptions are major evaluation
limitations.

## Threats and controls

### Personalization without consent or outside purpose

Controls: mandatory affirmative consent, exact purpose equality across policy,
cohort, decision, exposure, and outcome, and refusal before scoring.

Residual risk: consent is asserted by the caller; there is no authoritative
consent ledger, withdrawal feed, or versioned purpose registry.

### Sensitive or identifying data enters scoring

Controls: recursive rejection of sensitive and direct-identifier keys,
allowlisted normalized feature contracts, and persisted subject hashes.

Residual risk: benign-looking features can proxy protected traits, and free
text can still contain sensitive content.

### Manipulative objective or unbounded optimization

Controls: prohibited objective terms, bounded weights, exploration cap,
candidate safety floor, traffic caps, and human approval thresholds.

Residual risk: harmless labels can conceal harmful metric definitions or user
experience incentives.

### Unauthorized experiment launch or approval

Controls: explicit lifecycle states, risk re-evaluation at transition and
launch, pending approval, separate launch action, and global traffic cap.

Residual risk: actor names are unauthenticated and there is no tenant RBAC,
conflict-of-interest handling, or revocation.

### Allocation manipulation or inconsistent decisions

Controls: deterministic SHA-256 allocation, stable tie-breaking, strict models,
and persisted decision evidence.

Residual risk: changing salts or policy contracts without a migration strategy
can reassign traffic; multi-process concurrency is not certified.

### Event forgery, replay, or cross-subject linkage

Controls: idempotency keys, decision-bound candidate checks, subject-hash
matching, purpose matching, and allowlisted outcome types.

Residual risk: the caller can fabricate events, and the local service has no
signed producer identity or durable event broker.

### Small-cell disclosure

Controls: cohort-size launch floor, aggregate-group floor, and metric values
returned as `null` below the minimum.

Residual risk: repeated or differenced queries, auxiliary information, and
operator access patterns are not modeled as a formal privacy system.

### Harmful treatment continues

Controls: quality, harm, complaint, and fairness thresholds; automatic rollback;
global kill switch; approved baseline fallback; no automatic resume.

Residual risk: delayed harms, missing events, poisoned metrics, and weak
statistical power can prevent or delay detection.

### Audit tampering

Controls: canonical record serialization, previous-hash linkage, sequence
verification, and visible failure reporting.

Residual risk: a privileged local attacker can replace the database and the
entire chain consistently. There is no signature or external anchor.

### Denial of service

Controls: strict request models, bounded candidate collections, normalized
numeric values, traffic caps, and local-only default binding.

Residual risk: no production rate limiting, queue isolation, load testing, or
aggregate storage quota exists.

### Browser or static-asset compromise

Controls: repository-owned assets, no third-party runtime scripts, escaped text
rendering, and fictional static fallback data.

Residual risk: the application does not yet set a complete production browser
security-header policy or authenticate state-changing dashboard actions.

## Out of scope

- Compromised host administrator, Python runtime, browser, or kernel.
- Training-data or model-supply-chain attacks.
- Independent verification of feature truth or causal impact.
- Legal or regulatory sufficiency.
- High-impact eligibility, employment, housing, credit, health, education, or
  public-benefit decisions.

## Required production work

See `docs/PRODUCTION_READINESS.md`, `docs/DEPLOYMENT.md`, and `docs/ETHICS.md`.
