# Daily Triage - Example Loop

This is a starter template for the **Daily Triage** pattern from Loop Engineering.

## Overview

This loop runs daily to:
- Review and label open issues
- Assign reviewers to PRs
- Check for calendar conflicts
- Flag blockers

## Quick Start

```bash
# Install Loop Engineering
pip install loop-engineering

# Audit the configuration
loop-engine audit

# Run (dry run first)
loop-engine run --dry-run

# Run for real
loop-engine run
```

## Configuration

Edit `loop.yaml` to customize:

```yaml
pattern_config:
  github_repo: your-org/your-repo
  slack_channel: "#your-channel"
```

## Cost

Estimated cost: $0.15 per run ($4.50/month at daily cadence)

## Safety

- Budget cap: 10,000 tokens
- Manual checkpoint preset
- Syntax and security gates enabled
