# Contributing

Thank you for helping improve Personalization Control Plane.

## Development setup

```bash
uv sync --extra dev
./scripts/test.sh
./scripts/validate.sh
```

Run the seeded service on the standard local port:

```bash
./scripts/demo.sh
# http://127.0.0.1:8102
```

## Change expectations

- Add or update tests for every behavior change.
- Preserve deterministic allocation and ranking.
- Treat consent, purpose, sensitive-input rejection, cohort floors, human
  approval, exploration caps, fairness, rollback, and audit as hard product
  contracts.
- Do not add objectives that optimize manipulation, compulsion, outrage,
  deceptive urgency, or time spent for its own sake.
- Use fictional data in examples and tests.
- Keep `site/` byte-for-byte synchronized with the served `web/` files.
- Do not commit credentials, local databases, caches, dependency directories,
  generated binaries, or production data.

## Pull requests

Describe the user-visible outcome, governance implications, tests run, and
remaining limitations. Security and ethical-risk changes should explain both
the intended behavior and how failure is tested.
