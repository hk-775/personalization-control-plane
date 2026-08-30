# Meeting Demo Guide

## Start

```bash
./scripts/demo.sh
```

Open `http://127.0.0.1:8102`.

The recommended walkthrough takes seven to ten minutes. Every name and metric
is fictional.

## 1. Product framing — 60 seconds

On the landing page:

> Recommendation optimization is not only a model problem. It is a control
> problem: who defines value, how much traffic can move, what data is allowed,
> when a human must approve, and how the system stops.

Point out:

- no credentials or external calls;
- three domains using one neutral control plane;
- safety behaviors enforced before scoring and launch;
- explicit limitations.

## 2. Portfolio — 60 seconds

Open `http://127.0.0.1:8102/dashboard`.

Use **Overview**:

- two running experiments with only 7% total portfolio traffic;
- one risky media launch pending human approval;
- one intentionally undersized cohort;
- active immutable policy versions;
- verified audit chain.

## 3. Transparent ranking — 90 seconds

Open **Guided demo** and run **Transparent deterministic ranking**.

Talk track:

1. Consent and exact purpose are checked before policy selection.
2. The subject receives a stable experiment bucket.
3. The policy scores relevance, quality, user value, diversity, freshness,
   satisfaction, and safety.
4. One fictional supplement candidate is below the candidate safety floor and
   is excluded.
5. Each recommendation exposes exact factor contributions and deterministic
   exploration adjustment.
6. The decision is persisted with a subject hash, not the submitted subject id.

## 4. Privacy and approval — 90 seconds

Run **Minimum cohort privacy floor**:

- the cohort has 34 people;
- the configured floor is 50;
- the metric value is `null`;
- the experiment cannot advance.

Then run **Human approval for risky launches**:

- proposed traffic is 12%, above the 5% autonomous cap;
- exploration is 5.5%, above the 3% low-risk threshold;
- the lifecycle state is `pending_approval`;
- in **Approvals & audit**, approve or deny it;
- approval moves it only to `approved`; a separate launch action is still
  required and re-checks kill switch and traffic capacity.

## 5. Guardrail rollback — 90 seconds

Run **Automatic guardrail rollback**.

The scenario submits an eligible aggregate in which:

- quality is below floor;
- harm and complaint rates exceed ceilings;
- fairness ratio is below threshold.

The service immediately changes the experiment from `running` to
`rolled_back`, records the reason, and removes it from future allocation.

Open **Approvals & audit** to show both the evaluation and rollback records.

## 6. Global kill switch — 60 seconds

Reset the demo if the prior experiment state is useful to restore, then run
**Global kill switch**.

Point out:

- every running experiment is paused;
- ranking still returns an approved baseline;
- disabling the switch never auto-resumes experiments;
- a human must inspect and resume each one.

## 7. Architecture — 60 seconds

Open `http://127.0.0.1:8102/architecture`.

Select:

- **Rank request**
- **Risky experiment launch**
- **Guardrail breach**
- **Outcome feedback**

The animation traces the same components exercised by the dashboard.

## Reset

Use **Reset demo** in the dashboard, or:

```bash
curl -sS http://127.0.0.1:8102/api/v1/demo/reset \
  -H 'Content-Type: application/json' \
  -d '{
    "actor": "demo-presenter",
    "reason": "Restore canonical meeting seed."
  }'
```

## Offline backup

`site/` contains the same landing, dashboard, and architecture pages. A static
dashboard fallback displays the complete fictional portfolio and read-only
scenario previews when the API is unavailable.

```bash
python3 -m http.server 8102 --directory site
```
