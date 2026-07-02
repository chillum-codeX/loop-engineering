# Quickstart Guide

Get up and running with Loop Engineering in 5 minutes.

## Installation

```bash
git clone https://github.com/chillum-codeX/loop-engineering.git
cd loop-engineering
pip install -e .
```

Or install the v0.4.1 release wheel directly:

```bash
pip install https://github.com/chillum-codeX/loop-engineering/releases/download/v0.4.1/loop_engineering-0.4.1-py3-none-any.whl
```

The package is not yet published to PyPI.

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
import asyncio

from loop_engine import RuntimeConfig, create_runtime

config = RuntimeConfig()
config.discovery.skills_dir = ".loop/skills"
config.persistence.state_dir = ".loop/state"
config.persistence.format = "sqlite"
config.handoff.default_token_budget = 100_000
config.handoff.default_cost_budget = 10.0
config.handoff.default_step_budget = 50

runtime = create_runtime(runtime_config=config, max_iterations=50)
result = asyncio.run(runtime.run())

print(f"Completed: {result.status.name}")
print(f"Tasks completed: {result.tasks_completed}")
```

## Next Steps

- Try the [starter patterns](patterns/daily-triage.md)
- Read the [state machine specification](STATE_MACHINE_SPECIFICATION.md)
- Review the [step lifecycle specification](STEP_LIFECYCLE_SPECIFICATION.md)
- Understand the [recovery model](RECOVERY_EXECUTION_SPECIFICATION.md)

## Getting Help

- [GitHub Discussions](https://github.com/chillum-codeX/loop-engineering/discussions)
- [Documentation home](index.md)
- [Issues](https://github.com/chillum-codeX/loop-engineering/issues)
