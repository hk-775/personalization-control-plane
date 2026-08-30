# Ethics, Safety, and Responsible Use

## Position

Recommendation systems can shape attention, opportunity, spending, speech, and
access. Personalization Control Plane therefore treats recommendation
optimization as a high technical and ethical risk, even in a local demo.

The package demonstrates mechanisms for making optimization more bounded and
inspectable. It does not prove that a recommendation system is fair, safe,
lawful, beneficial, or appropriate for a particular domain.

## Enforced controls

| Risk | Enforced behavior | Test coverage |
|---|---|---|
| Personalization without consent | Rank request returns `403 consent_required` | `test_consent_is_required` |
| Purpose drift | Policy, cohort, decision, exposure, and outcome purpose must match exactly | governance and event tests |
| Sensitive attributes in scoring | Sensitive and direct-identifier keys are recursively rejected | `test_sensitive_attributes_and_identifiers_are_rejected` |
| Manipulative optimization | Dark-pattern terms are prohibited in policy objectives, features, and constraints | `test_dark_pattern_policy_objectives_are_prohibited` |
| Small-cell privacy | Cohorts below 50 cannot advance and metric values are suppressed | `test_small_cohort_forces_baseline_and_suppresses_metrics` |
| Unbounded exploration | Absolute exploration cap is 10%; above 3% is high risk | policy validation and lifecycle tests |
| Large autonomous rollout | Above 5% traffic requires human approval; one experiment cannot exceed 25% | lifecycle tests |
| Portfolio blast radius | Running experiment traffic cannot exceed 30% in the demo | launch readiness |
| Hidden scoring | Candidate responses expose objective values, weights, contributions, and exclusions | engine tests |
| Quality or harm regression | Live guardrail failure triggers automatic rollback | `test_guardrail_breach_automatically_rolls_back_running_experiment` |
| Aggregate disparity | Fairness ratio floor is at least 0.80; each opaque group must meet the privacy floor | fairness tests |
| Unsafe continuation | Global kill switch pauses all running experiments and serves baseline policies | lifecycle tests |
| Unattributed changes | Consequential actions enter a verifiable SHA-256 hash chain | audit tests |

## Consent

The `consent` field is deliberately explicit and mandatory for rank requests.
The service does not infer consent from usage, terms acceptance, or prior
activity. A real integration must source consent from an authoritative,
revocable consent system and must respond promptly to withdrawal.

This demo does not implement a consent ledger or deletion workflow.

## Purpose limitation

Every policy and cohort has a human-readable purpose. Rank, exposure, and
outcome requests must use exactly that purpose. This avoids a common failure
mode in which data collected for one user benefit silently becomes an input to
a different commercial or behavioral objective.

Production systems should use stable purpose identifiers in addition to human
text, version them, and conduct review before expanding scope.

## Sensitive attributes and fairness

Sensitive attributes and direct identifiers are prohibited from online
scoring inputs. The runtime does not infer or proxy protected-group membership.

Fairness evaluation is separate and accepts only opaque aggregate group keys.
This illustrates an architectural separation:

- the serving path cannot use protected attributes to rank;
- a controlled offline or aggregate measurement path can assess whether
  outcomes differ across reviewed groups;
- the dashboard need not display semantic labels or small cells.

That separation does not eliminate proxy discrimination. Ordinary features can
correlate with protected traits, and an aggregate parity ratio can miss
allocation harms, quality differences, calibration issues, intersectional
effects, long-term feedback loops, or inaccessible experiences.

## No dark-pattern optimization

The policy validator rejects terms associated with:

- compulsion or addiction;
- outrage or fear;
- deceptive scarcity or urgency;
- infinite-scroll or time-spent maximization;
- conversion at any cost.

The allowlisted objectives emphasize relevance, quality, user value,
satisfaction, safety, trust, accessibility, freshness, and diversity.

Names alone are not a complete defense. A production review must inspect metric
definitions, data generation, user experience, and incentives to ensure a
benign label is not masking a harmful target.

## Human approval

Traffic above 5%, exploration above 3%, or an objective-weight movement above
0.15 makes a launch high risk. The lifecycle service creates a pending approval
and cannot launch until a named reviewer approves it.

The local demo records operator-supplied names but does not authenticate them.
Production requires strong identity, separation of duties, least privilege,
conflict-of-interest handling, and durable approval evidence.

## Guardrails and rollback

Guardrails are hard thresholds. A failed eligible aggregate rolls back a
running experiment immediately. The global kill switch pauses every running
experiment and never auto-resumes them when disabled.

Thresholds should not be treated as universal defaults. Each production domain
needs:

- reviewed metric semantics;
- appropriate windows and confidence requirements;
- baseline and seasonal adjustment;
- monitoring for delayed harms;
- incident ownership and rehearsal;
- conservative behavior when data is incomplete.

## Explainability

The demo returns exact arithmetic contributions because its scorer is a
weighted sum. This is faithful local explanation, not post-hoc approximation.

It still does not explain:

- whether the features are accurate;
- why a feature should be used;
- causal impact on a person or group;
- long-term feedback loops;
- whether the policy objective is normatively appropriate.

## Explicit limitations

Do not use this demo as:

- a production recommendation engine;
- evidence of legal or regulatory compliance;
- proof that a model or product is fair;
- an automated eligibility, employment, housing, credit, education, health, or
  public-benefit decision system;
- a substitute for privacy, accessibility, security, or human-rights review;
- a mechanism to infer sensitive traits.

Before production adaptation, conduct a documented impact assessment, identify
affected stakeholders, define appeal and redress paths, validate metric and
feature provenance, rehearse rollback, and obtain domain-specific legal and
ethical review.
