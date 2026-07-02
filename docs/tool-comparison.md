# Tool Selection Guide

Loop Engineering is a runtime layer, not a foundation model or coding-agent
replacement. It is designed to wrap repeatable workflows with explicit
lifecycle controls.

## Choose by workflow

| Need | Good starting point |
|------|---------------------|
| Interactive code exploration and implementation | A coding agent such as Claude Code or Codex |
| Current web information and general assistance | A web-connected assistant such as Grok |
| Repeatable workflow with explicit state and budgets | Loop Engineering around a model/tool adapter |
| One-off task | Use the underlying assistant directly |
| Recurring task that must resume after interruption | Use a persistent workflow runtime |

Capabilities and commercial products change quickly. Verify current provider
documentation before choosing a tool; this guide intentionally avoids
checkmark comparisons that would become stale or imply unsupported
superiority.

## What Loop Engineering adds

- Validated runtime states and transitions
- Token, cost, step, and retry budgets
- Deterministic checks before model calls
- Separate generator and evaluator configuration
- Configurable human checkpoints
- Recovery handlers
- JSON and SQLite persistence
- A CLI for scaffolding, validation, auditing, execution, and estimates

These controls reduce operational ambiguity; they are not a security or
correctness guarantee. External side effects require an explicit adapter and
the default runtime does not silently simulate them.

## Hybrid workflow

1. Develop and inspect the task with your preferred coding agent.
2. Capture the stable workflow as a `SKILL.md` contract.
3. Configure conservative budgets, gates, and checkpoints.
4. Connect only the external adapters the workflow needs.
5. Run in dry-run mode, inspect state, then enable writes deliberately.

## Cost notes

`loop-engine cost` produces planning estimates from configured assumptions.
Actual cost varies by provider, model, prompt, output, caching, and retries.
For supported live calls, the provider adapter records provider-reported token
usage and cost when the API supplies it.

## See also

- [Quickstart](QUICKSTART.md)
- [State machine specification](STATE_MACHINE_SPECIFICATION.md)
- [Recovery execution](RECOVERY_EXECUTION_SPECIFICATION.md)
- [Starter patterns](patterns/daily-triage.md)
