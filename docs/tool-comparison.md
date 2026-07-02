# Tool Comparison

Comparing Loop Engineering to other AI coding tools.

## Summary

| Feature | Claude Code | Codex | Grok | **Loop Engineering** |
|---------|-------------|-------|------|---------------------|
| **Paradigm** | Interactive | Interactive | Interactive | **Autonomous** |
| **Prompt Reuse** | ❌ | ❌ | ❌ | ✅ SKILL.md |
| **State Management** | ❌ | ❌ | ❌ | ✅ Full runtime |
| **Budget Enforcement** | ❌ | ❌ | ❌ | ✅ Hard limits |
| **Deterministic Gates** | ❌ | ❌ | ❌ | ✅ Pre-LLM checks |
| **Gen/Eval Separation** | ❌ | ❌ | ❌ | ✅ Different configs |
| **Human Checkpoints** | ❌ | ❌ | ❌ | ✅ Configurable |
| **Recovery** | ❌ | ❌ | ❌ | ✅ Automatic |
| **Persistence** | ❌ | ❌ | ❌ | ✅ JSON/SQLite |
| **CLI Tools** | ❌ | ✅ | ❌ | ✅ Full toolkit |
| **Cost Estimation** | ❌ | ❌ | ❌ | ✅ Built-in |

## Detailed Comparison

### Claude Code

**Best for**: Interactive exploration, one-off tasks

```bash
# You type prompts interactively
claude
> Review this PR
> Fix the bug in auth.py
```

**Limitations**:
- No prompt reuse
- No state between sessions
- No budget limits
- You must always be present

**When to use Claude Code**:
- Learning a new codebase
- One-time tasks
- When you want to guide every step

### Codex

**Best for**: Quick edits in existing code

```bash
# GitHub CLI integration
gh copilot suggest "Fix the bug"
```

**Limitations**:
- Limited context
- No persistent state
- Single-shot responses

**When to use Codex**:
- Quick fixes
- Within GitHub workflow
- Simple, contained tasks

### Grok

**Best for**: Real-time information

**Limitations**:
- No code-specific features
- No state management
- General purpose only

**When to use Grok**:
- Research
- Understanding concepts
- Real-time data queries

### Loop Engineering

**Best for**: Autonomous, repeatable tasks

```bash
# Scaffold once, run forever
loop-engine init --pattern daily-triage
loop-engine run  # Runs autonomously
```

**Advantages**:
- **Prompt reuse**: SKILL.md pays off intent debt
- **State management**: Survives crashes, resumes later
- **Budget enforcement**: Hard limits prevent surprises
- **Deterministic gates**: Catch issues before LLM calls
- **Human checkpoints**: Preserve control at critical points
- **Recovery**: Automatic retry with backoff
- **Persistence**: State saved to JSON/SQLite

**When to use Loop Engineering**:
- Recurring tasks (daily triage, CI monitoring)
- Long-running operations
- Safety-critical systems
- When you want to "fire and forget"

## Cost Comparison

### Daily Triage Pattern

| Tool | Setup Time | Per-Run Cost | Monthly Cost* |
|------|-----------|--------------|---------------|
| Claude Code | 0 min | $0.15 | $4.50 (manual) |
| Codex | 0 min | $0.15 | $4.50 (manual) |
| Loop Engineering | 5 min | $0.15 | $4.50 (automatic) |

*30 runs/month

### CI Sweeper Pattern (Hourly)

| Tool | Setup Time | Per-Run Cost | Monthly Cost* |
|------|-----------|--------------|---------------|
| Claude Code | N/A | N/A | Not possible |
| Codex | N/A | N/A | Not possible |
| Loop Engineering | 10 min | $0.35 | $255.50 |

*730 runs/month (hourly)

## Decision Matrix

| If you want... | Use |
|----------------|-----|
| Interactive exploration | Claude Code |
| Quick GitHub edits | Codex |
| Real-time research | Grok |
| Autonomous, repeatable tasks | **Loop Engineering** |
| Budget enforcement | **Loop Engineering** |
| Safety guarantees | **Loop Engineering** |
| State persistence | **Loop Engineering** |
| Human checkpoints | **Loop Engineering** |

## Migration Path

Starting with Claude Code and want to automate?

```bash
# 1. Capture your workflow
# Use Claude Code interactively to develop your process

# 2. Create SKILL.md
loop-engine init --pattern custom
# Document your WHEN, READ, JUDGE, OUTPUT, STOP

# 3. Add budget limits
# Edit loop.yaml with conservative limits

# 4. Run autonomously
loop-engine run
```

## Hybrid Approach

Use multiple tools together:

1. **Claude Code**: Develop and refine workflows
2. **Loop Engineering**: Automate refined workflows
3. **Codex**: Quick fixes within GitHub

## See Also

- [Failure Modes](failure-modes.md) - What can go wrong
- [Anti-Patterns](anti-patterns.md) - Common mistakes
- [Patterns](../patterns/) - Production-ready configurations
