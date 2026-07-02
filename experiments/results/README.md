# Results provenance

This directory contains artifacts with different evidence levels.

## Validated artifacts

- `deterministic_validation.json` validates benchmark evaluators only. Oracle
  answers pass and empty negative controls fail. It makes no model-performance
  claim and uses no network calls.
- `live_provider_smoke_paid.json` is sanitized evidence from one paid
  OpenRouter smoke request. It verifies protocol compatibility and
  provider-reported usage/cost capture, not model quality. The prompt,
  response, and credential are not stored.

## Historical mock artifacts

`main_results.json`, `ablation_results.json`, `redteam_results.json`, and
`statistical_analysis.json` were produced with mock components. They are
retained for benchmark-development history and must not be cited as evidence
of model performance, security effectiveness, or production readiness.

Generated figures based on those historical files carry the same limitation.
