# Quickstart Guide

Get up and running with Loop Engineering in 5 minutes.

## Installation

```bash
pip install loop-engineering
```

Or install with development dependencies:

```bash
pip install "loop-engineering[dev]"
```

## Your First Loop

### 1. Create a Project

```bash
loop-engine init --pattern daily-triage --name my-first-loop
cd my-first-loop
```

This creates:

```text
my-first-loop/
|-- loop.yaml          # Main configuration
|-- README.md          # Project docs
|-- .gitignore         # Git ignore rules
`-- .loop/
    |-- skills/        # SKILL.md files
    |-- state/         # Persistent state
    `-- worktrees/     # Git worktrees
```

### 2. Review Configuration

Edit `loop.yaml`:

```yaml
name: my-first-loop
pattern: daily-triage
tool: claude

runtime:
  max_iterations: 10
  checkpoint_preset: manual

budget:
  max_tokens: 10000
  max_cost: 1.00
  max_steps: 10
```

### 3. Audit Your Setup

```bash
loop-engine audit
```

You should see:

```text
Audit Results
Score: 100/100
[####################] 100%
```

### 4. Dry Run

Test without making changes:

```bash
loop-engine run --dry-run
```

### 5. Run Your Loop

```bash
loop-engine run
```

## Python API

For programmatic use:

```python
from loop_engine import LoopEngine, Budget

budget = Budget(
    max_tokens=100_000,
    max_cost=10.0,
    max_steps=50,
)

loop = LoopEngine(budget=budget)
result = loop.run("Optimize database queries")

print(f"Status: {result.status}")
print(f"Tokens: {result.tokens_used}")
print(f"Cost: ${result.cost:.2f}")
```

## Next Steps

- Try different [patterns](../patterns/)
- Read about [failure modes](failure-modes.md)
- Learn [anti-patterns](anti-patterns.md) to avoid
- Explore the [API reference](api-reference.md)

## Getting Help

- [GitHub Discussions](https://github.com/chillum-codeX/loop-engineering/discussions)
- [Documentation](../README.md)
- [Issues](https://github.com/chillum-codeX/loop-engineering/issues)
