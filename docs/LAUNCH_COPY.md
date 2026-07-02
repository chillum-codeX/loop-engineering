# Launch Copy Pack

Use this file as the copy bank for public launch posts.

## Canonical links

- Repo: https://github.com/chillum-codeX/loop-engineering
- Release: https://github.com/chillum-codeX/loop-engineering/releases/tag/v0.4.1
- Discussions: https://github.com/chillum-codeX/loop-engineering/discussions

## Short one-line description

Loop Engineering is a Python runtime for agent loops with budgets, deterministic gates, recovery, checkpoints, and persistence.

## GitHub Discussion / repo announcement

Loop Engineering v0.4.1 is live.

What is in the repo now:

- Working Python runtime for loop engineering
- CLI for `init`, `audit`, `run`, `cost`, and `validate`
- Deterministic gates before model calls
- Budget enforcement and recovery handlers
- Human checkpoints and JSON/SQLite persistence
- Docker, GitHub Actions, starter patterns, and community files

Validation:

- 97 tests passing locally
- Build passing
- Release artifacts validated
- GitHub Actions green on `main`

If you want to try it, start with the README and `docs/QUICKSTART.md`.

## X / Twitter

Shipping today: Loop Engineering v0.4.1

A Python runtime for building agent loops with:
- budgets
- deterministic gates
- checkpoints
- recovery
- persistence

Repo: https://github.com/chillum-codeX/loop-engineering

## Hacker News

Title:

Show HN: Loop Engineering — a Python runtime for budgeted, verifiable agent loops

Body:

I built Loop Engineering to make autonomous agent loops more controlled and inspectable.

The current release includes a Python runtime, CLI, deterministic gates before LLM calls, budget enforcement, human checkpoints, recovery handlers, and JSON/SQLite persistence.

Current validation status:

- 97 tests passing
- packaging and release artifacts validated
- GitHub Actions green on main

Repo: https://github.com/chillum-codeX/loop-engineering

I would especially love feedback on the runtime model, the CLI, and which production loop patterns are most useful.

## Reddit

Title:

I open-sourced a Python runtime for safer agent loops

Body:

I just published Loop Engineering, a Python runtime for agent loops with deterministic gates, budget limits, recovery handlers, checkpoints, and persistence.

It is meant for people experimenting with autonomous agent workflows who want more structure than prompt-only patterns.

Repo: https://github.com/chillum-codeX/loop-engineering

If you try it, I’d love feedback on missing patterns, rough edges in the CLI, and the benchmark design.
