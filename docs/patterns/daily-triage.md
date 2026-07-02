# Daily Triage Pattern

A loop that runs daily to review and prioritize tasks.

## When

- Daily at 9 AM
- Or when triggered manually

## Read

- Open issues from GitHub
- Open PRs from GitHub
- Slack messages with 🔥 emoji
- Calendar for today

## Judge

Success means:
- All issues labeled with priority
- PRs assigned to reviewers
- Calendar conflicts flagged
- Blockers identified

## Output

- Labeled issues
- Assigned PRs
- Slack summary message
- Updated project board

## Stop

- Do not close issues without human approval
- Do not merge PRs
- Do not exceed 10,000 tokens
- Stop after 5 iterations

## Configuration

```yaml
name: daily-triage
pattern: daily-triage
tool: claude

runtime:
  max_iterations: 5
  checkpoint_preset: manual

budget:
  max_tokens: 10000
  max_cost: 1.00
  max_steps: 10

discovery:
  skills_dir: .loop/skills
  load_latest_on_start: true

verification:
  enable_pre_gates: true
  enable_post_gates: true
  mandatory_gates:
    - syntax
    - security
```

## Cost Estimate

| Model | Per-Run Cost | Monthly Cost* |
|-------|-------------|---------------|
| Claude Sonnet | $0.15 | $4.50 |
| Claude Opus | $0.75 | $22.50 |
| GPT-4 | $0.90 | $27.00 |

*30 runs/month

## Example Run

```bash
$ loop-engine cost --pattern daily-triage

💰 Cost Estimate: daily-triage
Model: claude-sonnet
Cadence: daily

Per Run:
  Input tokens:  2,000
  Output tokens: 1,500
  Total tokens:  3,500
  Cost:          $0.0150

Monthly Estimate:
  Runs:          30
  Total tokens:  105,000
  Cost:          $0.45
```

## Safety Guidelines

1. **Budget**: Set max_tokens to 10,000 for safety
2. **Checkpoints**: Use manual preset to review changes
3. **Gates**: Enable syntax and security gates
4. **Scope**: Only label/assign, don't close or merge

## Integration

### GitHub Actions

```yaml
name: Daily Triage
on:
  schedule:
    - cron: '0 9 * * *'  # 9 AM daily

jobs:
  triage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: loop-engineering/action@v1
        with:
          pattern: daily-triage
          api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

### Slack Notification

Add to your SKILL.md:

```markdown
## Output

- Post summary to #daily-updates
- Tag @channel for blockers
- Include priority counts
```

## See Also

- [Issue Triage](issue-triage.md) - More focused on issues
- [PR Babysitter](pr-babysitter.md) - Focus on pull requests
