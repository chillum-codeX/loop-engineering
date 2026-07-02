# Loop Engineering

Loop Engineering is an alpha Python runtime for building repeatable agent
workflows with explicit state, budgets, deterministic checks, recovery,
checkpoints, and persistence.

## Start here

```bash
git clone https://github.com/chillum-codeX/loop-engineering.git
cd loop-engineering
pip install -e .
loop-engine --help
```

Continue with the [five-minute quickstart](QUICKSTART.md), then choose a
[starter pattern](patterns/daily-triage.md).

## Evidence level

- 97 automated tests pass locally and in GitHub Actions.
- Deterministic benchmark controls validate evaluator behavior, not model
  superiority.
- One paid OpenRouter smoke request verified provider-reported token and cost
  accounting without storing its prompt, response, or credential.
- Historical mock benchmark outputs are not model-performance or security
  evidence.

Loop Engineering makes no SOTA, production-readiness, or comparative
performance claim.

## Current release

[Loop Engineering v0.4.1](https://github.com/chillum-codeX/loop-engineering/releases/tag/v0.4.1)
is the current verified alpha release.
