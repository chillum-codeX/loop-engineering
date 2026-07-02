#!/usr/bin/env python3
"""
Loop Engineering CLI

Main entry point for the loop-engine command.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from datetime import datetime

from .. import __version__
from ..runtime_contracts import RuntimeConfig, TaskPriority
from ..skills import SkillParser


# ASCII Art Logo
LOGO = r"""
╔═══════════════════════════════════════════════════════════╗
║  _                    _____                       _       ║
║ | |                  |  ___|                     | |      ║
║ | |     ___   __ _   | |__  _   _ _ __ __ _  __ _| | ___  ║
║ | |    / _ \ / _` |  |  __|| | | | '__/ _` |/ _` | |/ _ \\ ║
║ | |___| (_) | (_| |  | |___| |_| | | | (_| | (_| | |  __/ ║
║ |______\\___/ \\__, |  \\____/\\__,_|_|  \\__,_|\\__, |_|\\___| ║
║               __/ |                            __/ |      ║
║              |___/           Engineering      |___/       ║
║                                                           ║
║     Design systems that prompt your agents.              ║
╚═══════════════════════════════════════════════════════════╝
"""


@click.group()
@click.version_option(version=__version__, prog_name="loop-engine")
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose):
    """
    Loop Engineering - Design systems that prompt your agents.

    Loop engineering is replacing yourself as the person who prompts the agent.
    You design the system that prompts your agents instead.

    Examples:
        loop-engine init --pattern daily-triage
        loop-engine audit --suggest
        loop-engine run --config loop.yaml
        loop-engine cost --pattern pr-babysitter
    """
    # Avoid UnicodeEncodeError on legacy Windows terminals and redirected logs.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose

    if verbose:
        click.echo(LOGO)


@cli.command()
@click.option('--pattern', '-p',
              type=click.Choice(['daily-triage', 'pr-babysitter', 'ci-sweeper',
                                'dependency-sweeper', 'changelog-drafter',
                                'post-merge-cleanup', 'issue-triage', 'custom']),
              default='daily-triage',
              help='Pattern to scaffold')
@click.option('--tool', '-t',
              type=click.Choice(['claude', 'codex', 'grok', 'generic']),
              default='claude',
              help='AI tool to configure for')
@click.option('--name', '-n', prompt='Project name', help='Project name')
@click.option('--output', '-o', default='.', help='Output directory')
@click.option('--force', '-f', is_flag=True, help='Overwrite existing files')
@click.pass_context
def init(ctx, pattern, tool, name, output, force):
    """
    Scaffold a new loop project.

    Creates a new project with the selected pattern, configuration files,
    and starter templates ready to customize.

    Examples:
        loop-engine init --pattern daily-triage --name my-project
        loop-engine init -p pr-babysitter -t claude -o ./my-loop
    """
    verbose = ctx.obj.get('verbose', False)

    output_dir = Path(output) / name if output == '.' else Path(output)

    if output_dir.exists() and not force:
        click.echo(f"❌ Directory {output_dir} already exists. Use --force to overwrite.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        click.echo(f"Creating {pattern} pattern in {output_dir}...")

    # Create directory structure
    (output_dir / ".loop").mkdir(exist_ok=True)
    (output_dir / ".loop" / "skills").mkdir(exist_ok=True)
    (output_dir / ".loop" / "state").mkdir(exist_ok=True)
    (output_dir / ".loop" / "worktrees").mkdir(exist_ok=True)

    # Create loop.yaml configuration
    config_content = generate_config(pattern, tool, name)
    (output_dir / "loop.yaml").write_text(config_content)

    # Create SKILL.md
    skill_content = generate_skill(pattern, tool)
    (output_dir / ".loop" / "skills" / f"{pattern}.md").write_text(skill_content)

    # Create README
    readme_content = generate_readme(pattern, name, tool)
    (output_dir / "README.md").write_text(readme_content)

    # Create .gitignore
    gitignore_content = """# Loop Engineering
.loop/state/
.loop/worktrees/
.loop/logs/
*.loop.json
.loop_schedule.json
"""
    (output_dir / ".gitignore").write_text(gitignore_content)

    click.echo(f"✅ Created {pattern} loop project: {name}")
    click.echo(f"📁 Location: {output_dir.absolute()}")
    click.echo(f"\nNext steps:")
    click.echo(f"  cd {output_dir}")
    click.echo(f"  # Edit loop.yaml to customize")
    click.echo(f"  loop-engine audit        # Check readiness")
    click.echo(f"  loop-engine run          # Execute the loop")


@cli.command()
@click.argument('path', default='.')
@click.option('--suggest', '-s', is_flag=True, help='Suggest improvements')
@click.option('--format', '-f', 'output_format',
              type=click.Choice(['table', 'json', 'yaml']),
              default='table',
              help='Output format')
@click.option('--threshold', '-t', default=70, help='Minimum passing score (0-100)')
@click.pass_context
def audit(ctx, path, suggest, output_format, threshold):
    """
    Audit loop readiness (0-100 score).

    Analyzes your loop configuration and provides a readiness score
    based on completeness, safety, and best practices.

    Examples:
        loop-engine audit                    # Audit current directory
        loop-engine audit ./my-loop --suggest # With improvement suggestions
        loop-engine audit --format json      # JSON output for CI/CD
    """
    verbose = ctx.obj.get('verbose', False)

    target_path = Path(path)

    if not target_path.exists():
        click.echo(f"❌ Path {target_path} does not exist.")
        sys.exit(1)

    if verbose:
        click.echo(f"Auditing {target_path}...")

    # Perform audit
    results = perform_audit(target_path, suggest)

    # Check threshold
    if results['score'] < threshold:
        results['passed'] = False

    # Output results
    if output_format == 'json':
        click.echo(json.dumps(results, indent=2))
    elif output_format == 'yaml':
        import yaml
        click.echo(yaml.dump(results, default_flow_style=False))
    else:
        print_audit_results(results, suggest)

    # Exit with error if below threshold
    if not results['passed']:
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='loop.yaml', help='Configuration file')
@click.option('--dry-run', '-n', is_flag=True, help='Simulate without executing')
@click.option('--trace-id', '-t', help='Trace ID for this run')
@click.option('--max-iterations', '-i', type=int, help='Maximum iterations')
@click.pass_context
def run(ctx, config, dry_run, trace_id, max_iterations):
    """
    Execute a loop from configuration.

    Runs the loop defined in the configuration file, executing
    all phases: Discovery, Handoff, Verification, Persistence, Scheduling.

    Examples:
        loop-engine run                    # Run with default config
        loop-engine run -c my-loop.yaml    # Use custom config
        loop-engine run --dry-run          # Simulate execution
    """
    verbose = ctx.obj.get('verbose', False)

    config_path = Path(config)

    if not config_path.exists():
        click.echo(f"❌ Configuration file {config_path} not found.")
        sys.exit(1)

    if verbose:
        click.echo(f"Loading configuration from {config_path}...")

    # Load configuration
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        click.echo(f"❌ Failed to load configuration: {e}")
        sys.exit(1)

    if dry_run:
        click.echo("🔍 DRY RUN MODE - No changes will be made")
        click.echo(f"\nConfiguration:")
        click.echo(f"  Name: {config_data.get('name', 'unnamed')}")
        click.echo(f"  Pattern: {config_data.get('pattern', 'unknown')}")
        click.echo(f"  Tool: {config_data.get('tool', 'generic')}")
        click.echo(f"\nWould execute phases:")
        click.echo("  1. Discovery   - Load state, discover tasks")
        click.echo("  2. Handoff     - Reserve budget, create worktree")
        click.echo("  3. Verification - Run gates, generate, evaluate")
        click.echo("  4. Persistence - Save state, update ledger")
        click.echo("  5. Scheduling  - Determine next run")
        return

    # Execute loop
    click.echo("🚀 Starting loop execution...")

    try:
        from ..runtime_v1 import create_runtime

        config_root = config_path.resolve().parent
        runtime_settings = config_data.get('runtime', {})
        discovery_settings = config_data.get('discovery', {})
        handoff_settings = config_data.get('handoff', {})
        verification_settings = config_data.get('verification', {})
        persistence_settings = config_data.get('persistence', {})
        scheduling_settings = config_data.get('scheduling', {})
        budget_settings = config_data.get('budget', {})
        integration_settings = config_data.get('integrations', {})

        runtime_config = RuntimeConfig()
        runtime_config.trace_id = trace_id
        runtime_config.discovery.skills_dir = config_root / discovery_settings.get(
            'skills_dir', '.loop/skills'
        )
        runtime_config.discovery.state_dir = config_root / discovery_settings.get(
            'state_dir', '.loop/state'
        )
        runtime_config.discovery.load_latest_on_start = discovery_settings.get(
            'load_latest_on_start', True
        )
        runtime_config.handoff.default_token_budget = budget_settings.get(
            'max_tokens', runtime_config.handoff.default_token_budget
        )
        runtime_config.handoff.default_cost_budget = budget_settings.get(
            'max_cost', runtime_config.handoff.default_cost_budget
        )
        runtime_config.handoff.default_step_budget = budget_settings.get(
            'max_steps', runtime_config.handoff.default_step_budget
        )
        runtime_config.handoff.worktrees_dir = config_root / handoff_settings.get(
            'worktrees_dir', '.loop/worktrees'
        )
        runtime_config.handoff.auto_cleanup_worktrees = handoff_settings.get(
            'auto_cleanup', True
        )
        runtime_config.verification.enable_pre_gates = verification_settings.get(
            'enable_pre_gates', True
        )
        runtime_config.verification.enable_post_gates = verification_settings.get(
            'enable_post_gates', True
        )
        runtime_config.verification.mandatory_gates = verification_settings.get(
            'mandatory_gates', ['syntax', 'security']
        )
        runtime_config.verification.checkpoint_preset = runtime_settings.get(
            'checkpoint_preset',
            verification_settings.get('checkpoint_preset', 'production'),
        )
        runtime_config.persistence.state_dir = config_root / persistence_settings.get(
            'state_dir', '.loop/state'
        )
        runtime_config.persistence.format = persistence_settings.get('format', 'json')
        runtime_config.persistence.auto_save = persistence_settings.get('auto_save', True)
        runtime_config.persistence.max_history = persistence_settings.get(
            'max_history', runtime_config.persistence.max_history
        )
        runtime_config.scheduling.exit_on_no_tasks = scheduling_settings.get(
            'exit_on_no_tasks', True
        )
        runtime_config.scheduling.exit_on_budget_exhausted = scheduling_settings.get(
            'exit_on_budget_exhausted', True
        )

        effective_max_iterations = (
            max_iterations
            if max_iterations is not None
            else runtime_settings.get('max_iterations', 100)
        )
        task_handlers = {}
        github_settings = integration_settings.get('github', {})
        if github_settings.get('enabled', False):
            from ..patterns import (
                DailyTriageConfig,
                DailyTriageHandler,
                PRBabysitterConfig,
                PRBabysitterHandler,
            )
            from ..tools import GitHubAdapter, PermissionPolicy

            repository = github_settings.get(
                'repository',
                config_data.get('pattern_config', {}).get('github_repo'),
            )
            if not repository:
                raise ValueError(
                    "integrations.github.repository is required when GitHub is enabled"
                )
            github = GitHubAdapter(
                repository=repository,
                policy=PermissionPolicy.read_only_github(),
            )
            if config_data.get('pattern') == 'daily-triage':
                report_path = config_root / github_settings.get(
                    'report_path', '.loop/state/daily-triage-report.json'
                )
                task_handlers['daily-triage'] = DailyTriageHandler(
                    github,
                    DailyTriageConfig(output_path=report_path),
                )
            elif config_data.get('pattern') == 'pr-babysitter':
                report_path = config_root / github_settings.get(
                    'report_path', '.loop/state/pr-babysitter-report.json'
                )
                task_handlers['pr-babysitter'] = PRBabysitterHandler(
                    github,
                    PRBabysitterConfig(
                        output_path=report_path,
                        stale_after_hours=github_settings.get(
                            'stale_after_hours', 48
                        ),
                    ),
                )

        runtime = create_runtime(
            runtime_config=runtime_config,
            max_iterations=effective_max_iterations,
            task_handlers=task_handlers,
        )

        import asyncio

        result = asyncio.run(runtime.run())

        click.echo(f"\n✅ Loop completed: {result.status.name}")
        click.echo(f"   Tasks discovered: {result.tasks_discovered}")
        click.echo(f"   Tasks completed: {result.tasks_completed}")
        click.echo(f"   Tasks failed: {result.tasks_failed}")
        click.echo(f"   Iterations: {result.iterations}")

        if result.get_duration_seconds():
            click.echo(f"   Duration: {result.get_duration_seconds():.2f}s")

        if result.status.name != "COMPLETED":
            sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Loop execution failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option('--pattern', '-p',
              type=click.Choice(['daily-triage', 'pr-babysitter', 'ci-sweeper',
                                'dependency-sweeper', 'changelog-drafter',
                                'post-merge-cleanup', 'issue-triage']),
              help='Pattern to estimate')
@click.option('--cadence', '-c',
              type=click.Choice(['hourly', 'daily', 'weekly', 'monthly']),
              default='daily',
              help='Execution cadence')
@click.option('--model', '-m',
              type=click.Choice(['claude-sonnet', 'claude-opus', 'gpt-4', 'gpt-4o']),
              default='claude-sonnet',
              help='Model to use')
@click.option('--iterations', '-i', default=10, help='Expected iterations per run')
@click.option('--format', '-f', 'output_format',
              type=click.Choice(['table', 'json']),
              default='table',
              help='Output format')
@click.pass_context
def cost(ctx, pattern, cadence, model, iterations, output_format):
    """
    Estimate token/cost for loop patterns.

    Calculates estimated token usage and cost based on pattern complexity,
    execution cadence, and model selection.

    Examples:
        loop-engine cost --pattern daily-triage
        loop-engine cost -p pr-babysitter -c hourly -m claude-opus
        loop-engine cost --format json  # For CI/CD integration
    """
    verbose = ctx.obj.get('verbose', False)

    if verbose:
        click.echo(f"Calculating cost for {pattern} pattern...")

    # Cost calculation
    estimates = calculate_cost(pattern, cadence, model, iterations)

    if output_format == 'json':
        click.echo(json.dumps(estimates, indent=2))
    else:
        print_cost_estimate(estimates)


@cli.command()
@click.argument('path', default='.')
@click.option('--strict', '-s', is_flag=True, help='Strict validation (fail on warnings)')
@click.pass_context
def validate(ctx, path, strict):
    """
    Validate loop configurations.

    Validates SKILL.md files, loop.yaml configurations, and
    checks for common anti-patterns.

    Examples:
        loop-engine validate           # Validate current directory
        loop-engine validate ./my-loop --strict
    """
    verbose = ctx.obj.get('verbose', False)

    target_path = Path(path)

    if not target_path.exists():
        click.echo(f"❌ Path {target_path} does not exist.")
        sys.exit(1)

    if verbose:
        click.echo(f"Validating {target_path}...")

    # Perform validation
    results = perform_validation(target_path, strict)

    click.echo(f"\n{'✅' if results['valid'] else '❌'} Validation {'passed' if results['valid'] else 'failed'}")
    click.echo(f"   Files checked: {results['files_checked']}")
    click.echo(f"   Errors: {results['errors']}")
    click.echo(f"   Warnings: {results['warnings']}")

    if results['issues']:
        click.echo(f"\nIssues:")
        for issue in results['issues']:
            emoji = "❌" if issue['severity'] == 'error' else "⚠️"
            click.echo(f"   {emoji} {issue['file']}: {issue['message']}")

    if not results['valid']:
        sys.exit(1)


# Helper functions

def generate_config(pattern: str, tool: str, name: str) -> str:
    """Generate loop.yaml configuration."""
    return f"""# Loop Engineering Configuration
# Pattern: {pattern}
# Generated: {datetime.now().isoformat()}

name: {name}
pattern: {pattern}
tool: {tool}
version: "0.4.0"

# Runtime configuration
runtime:
  max_iterations: 100
  checkpoint_preset: production  # manual, conservative, production

# Budget limits
budget:
  max_tokens: 100000
  max_cost: 10.00
  max_steps: 50

# Discovery phase
discovery:
  skills_dir: .loop/skills
  load_latest_on_start: true

# Handoff phase
handoff:
  worktrees_dir: .loop/worktrees
  auto_cleanup: true

# Verification phase
verification:
  enable_pre_gates: true
  enable_post_gates: true
  mandatory_gates:
    - syntax
    - security

# Persistence phase
persistence:
  state_dir: .loop/state
  format: json
  auto_save: true

# Scheduling phase
scheduling:
  exit_on_no_tasks: true
  exit_on_budget_exhausted: true

# Pattern-specific configuration
pattern_config:
  # Add your custom configuration here
"""


def generate_skill(pattern: str, tool: str) -> str:
    """Generate SKILL.md content."""
    return f"""# {pattern}

## When
Trigger conditions for this loop pattern.

## Read
- Configuration files
- State from previous runs
- Context relevant to this pattern

## Judge
Success criteria for this pattern.

## Output
Expected outputs and deliverables.

## Stop
- Do not exceed budget limits
- Do not modify protected files
- Do not execute without human approval for destructive operations

## Tool Configuration
Optimized for: {tool}
"""


def generate_readme(pattern: str, name: str, tool: str) -> str:
    """Generate project README."""
    return f"""# {name}

A Loop Engineering project using the **{pattern}** pattern.

## Overview

This project implements an autonomous loop that runs on a schedule,
following the Loop Engineering principles from Anthropic's research.

## Pattern: {pattern}

Description of what this pattern does.

## Configuration

- **Tool**: {tool}
- **Pattern**: {pattern}
- **Version**: 0.4.0

## Usage

```bash
# Audit readiness
loop-engine audit

# Run the loop
loop-engine run

# Estimate costs
loop-engine cost --pattern {pattern}
```

## Structure

```
.
├── loop.yaml          # Main configuration
├── .loop/
│   ├── skills/        # SKILL.md files
│   ├── state/         # Persistent state
│   └── worktrees/     # Git worktrees
└── README.md          # This file
```

## License

MIT
"""


def perform_audit(path: Path, suggest: bool) -> dict:
    """Perform audit and return results."""
    results = {
        'passed': True,
        'score': 0,
        'max_score': 100,
        'categories': {},
        'suggestions': [],
    }

    score = 0

    # Check for loop.yaml
    loop_yaml = path / "loop.yaml"
    if loop_yaml.exists():
        score += 20
        results['categories']['configuration'] = {'score': 20, 'max': 20, 'status': 'pass'}
    else:
        results['categories']['configuration'] = {'score': 0, 'max': 20, 'status': 'fail'}
        results['suggestions'].append("Create loop.yaml configuration file")

    # Check for .loop directory
    loop_dir = path / ".loop"
    if loop_dir.exists():
        score += 15
        results['categories']['structure'] = {'score': 15, 'max': 15, 'status': 'pass'}

        # Check for skills
        skills_dir = loop_dir / "skills"
        if skills_dir.exists() and any(skills_dir.iterdir()):
            score += 15
            results['categories']['skills'] = {'score': 15, 'max': 15, 'status': 'pass'}
        else:
            results['categories']['skills'] = {'score': 0, 'max': 15, 'status': 'fail'}
            if suggest:
                results['suggestions'].append("Add SKILL.md files to .loop/skills/")
    else:
        results['categories']['structure'] = {'score': 0, 'max': 15, 'status': 'fail'}
        results['categories']['skills'] = {'score': 0, 'max': 15, 'status': 'fail'}

    # Check for README
    readme = path / "README.md"
    if readme.exists():
        score += 10
        results['categories']['documentation'] = {'score': 10, 'max': 10, 'status': 'pass'}
    else:
        results['categories']['documentation'] = {'score': 0, 'max': 10, 'status': 'fail'}
        if suggest:
            results['suggestions'].append("Add README.md with project documentation")

    # Check for .gitignore
    gitignore = path / ".gitignore"
    if gitignore.exists():
        score += 10
        results['categories']['git'] = {'score': 10, 'max': 10, 'status': 'pass'}
    else:
        results['categories']['git'] = {'score': 0, 'max': 10, 'status': 'fail'}
        if suggest:
            results['suggestions'].append("Add .gitignore file")

    # Check for budget configuration
    if loop_yaml.exists():
        try:
            import yaml
            with open(loop_yaml) as f:
                config = yaml.safe_load(f)
            if 'budget' in config:
                score += 15
                results['categories']['safety'] = {'score': 15, 'max': 15, 'status': 'pass'}
            else:
                results['categories']['safety'] = {'score': 0, 'max': 15, 'status': 'warn'}
                if suggest:
                    results['suggestions'].append("Add budget limits to loop.yaml for safety")
        except:
            pass
    else:
        results['categories']['safety'] = {'score': 0, 'max': 15, 'status': 'fail'}

    # Check for checkpoint configuration
    if loop_yaml.exists():
        try:
            import yaml
            with open(loop_yaml) as f:
                config = yaml.safe_load(f)
            runtime = config.get('runtime', {})
            if 'checkpoint_preset' in runtime:
                score += 15
                results['categories']['checkpoints'] = {'score': 15, 'max': 15, 'status': 'pass'}
            else:
                results['categories']['checkpoints'] = {'score': 0, 'max': 15, 'status': 'warn'}
                if suggest:
                    results['suggestions'].append("Configure checkpoint_preset for human oversight")
        except:
            pass
    else:
        results['categories']['checkpoints'] = {'score': 0, 'max': 15, 'status': 'fail'}

    results['score'] = score
    return results


def print_audit_results(results: dict, suggest: bool):
    """Print audit results in table format."""
    click.echo(f"\n{'✅' if results['passed'] else '❌'} Audit Results")
    click.echo(f"Score: {results['score']}/{results['max_score']}")

    # Progress bar
    percentage = int(results['score'] / results['max_score'] * 100)
    filled = int(percentage / 5)
    bar = '█' * filled + '░' * (20 - filled)
    click.echo(f"[{bar}] {percentage}%")

    click.echo(f"\nCategories:")
    for category, data in results['categories'].items():
        emoji = '✅' if data['status'] == 'pass' else '⚠️' if data['status'] == 'warn' else '❌'
        click.echo(f"  {emoji} {category.capitalize()}: {data['score']}/{data['max']}")

    if suggest and results['suggestions']:
        click.echo(f"\nSuggestions:")
        for suggestion in results['suggestions']:
            click.echo(f"  💡 {suggestion}")


def calculate_cost(pattern: str, cadence: str, model: str, iterations: int) -> dict:
    """Calculate cost estimates."""
    # Base costs per pattern (tokens per iteration)
    pattern_costs = {
        'daily-triage': {'input': 2000, 'output': 1500},
        'pr-babysitter': {'input': 3000, 'output': 2000},
        'ci-sweeper': {'input': 2500, 'output': 1500},
        'dependency-sweeper': {'input': 4000, 'output': 2500},
        'changelog-drafter': {'input': 3500, 'output': 2000},
        'post-merge-cleanup': {'input': 2000, 'output': 1000},
        'issue-triage': {'input': 3000, 'output': 2000},
    }

    # Model pricing (per 1M tokens)
    model_pricing = {
        'claude-sonnet': {'input': 3.00, 'output': 15.00},
        'claude-opus': {'input': 15.00, 'output': 75.00},
        'gpt-4': {'input': 30.00, 'output': 60.00},
        'gpt-4o': {'input': 5.00, 'output': 15.00},
    }

    # Cadence multiplier (runs per period)
    cadence_multiplier = {
        'hourly': 730,  # ~730 hours/month
        'daily': 30,    # ~30 days/month
        'weekly': 4,    # ~4 weeks/month
        'monthly': 1,
    }

    base = pattern_costs.get(pattern, {'input': 2000, 'output': 1500})
    pricing = model_pricing.get(model, {'input': 3.00, 'output': 15.00})
    multiplier = cadence_multiplier.get(cadence, 30)

    # Per-run costs
    input_tokens = base['input'] * iterations
    output_tokens = base['output'] * iterations

    input_cost = (input_tokens / 1_000_000) * pricing['input']
    output_cost = (output_tokens / 1_000_000) * pricing['output']
    per_run_cost = input_cost + output_cost

    # Monthly costs
    monthly_cost = per_run_cost * multiplier

    return {
        'pattern': pattern,
        'cadence': cadence,
        'model': model,
        'iterations': iterations,
        'per_run': {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'cost_usd': round(per_run_cost, 4),
        },
        'monthly': {
            'runs': multiplier,
            'total_tokens': (input_tokens + output_tokens) * multiplier,
            'estimated_cost_usd': round(monthly_cost, 2),
        },
    }


def print_cost_estimate(estimates: dict):
    """Print cost estimate in table format."""
    click.echo(f"\n💰 Cost Estimate: {estimates['pattern']}")
    click.echo(f"Model: {estimates['model']}")
    click.echo(f"Cadence: {estimates['cadence']}")
    click.echo(f"Iterations per run: {estimates['iterations']}")

    click.echo(f"\nPer Run:")
    click.echo(f"  Input tokens:  {estimates['per_run']['input_tokens']:,}")
    click.echo(f"  Output tokens: {estimates['per_run']['output_tokens']:,}")
    click.echo(f"  Total tokens:  {estimates['per_run']['total_tokens']:,}")
    click.echo(f"  Cost:          ${estimates['per_run']['cost_usd']:.4f}")

    click.echo(f"\nMonthly Estimate:")
    click.echo(f"  Runs:          {estimates['monthly']['runs']}")
    click.echo(f"  Total tokens:  {estimates['monthly']['total_tokens']:,}")
    click.echo(f"  Cost:          ${estimates['monthly']['estimated_cost_usd']:.2f}")


def perform_validation(path: Path, strict: bool) -> dict:
    """Perform validation on loop configuration."""
    results = {
        'valid': True,
        'files_checked': 0,
        'errors': 0,
        'warnings': 0,
        'issues': [],
    }

    # Validate loop.yaml
    loop_yaml = path / "loop.yaml"
    if loop_yaml.exists():
        results['files_checked'] += 1
        try:
            import yaml
            with open(loop_yaml) as f:
                config = yaml.safe_load(f)

            # Check required fields
            if 'name' not in config:
                results['issues'].append({
                    'file': 'loop.yaml',
                    'severity': 'error',
                    'message': 'Missing required field: name',
                })
                results['errors'] += 1

            if 'pattern' not in config:
                results['issues'].append({
                    'file': 'loop.yaml',
                    'severity': 'warning',
                    'message': 'Missing recommended field: pattern',
                })
                results['warnings'] += 1

        except Exception as e:
            results['issues'].append({
                'file': 'loop.yaml',
                'severity': 'error',
                'message': f'Invalid YAML: {e}',
            })
            results['errors'] += 1

    # Validate SKILL.md files
    skills_dir = path / ".loop" / "skills"
    if skills_dir.exists():
        for skill_file in skills_dir.glob("*.md"):
            results['files_checked'] += 1
            try:
                content = skill_file.read_text()
                # Check for required sections
                required_sections = ['## When', '## Read', '## Judge']
                for section in required_sections:
                    if section not in content:
                        results['issues'].append({
                            'file': str(skill_file.relative_to(path)),
                            'severity': 'warning' if not strict else 'error',
                            'message': f'Missing section: {section}',
                        })
                        if strict:
                            results['errors'] += 1
                        else:
                            results['warnings'] += 1
            except Exception as e:
                results['issues'].append({
                    'file': str(skill_file.relative_to(path)),
                    'severity': 'error',
                    'message': f'Error reading file: {e}',
                })
                results['errors'] += 1

    # Determine validity
    if results['errors'] > 0:
        results['valid'] = False
    if strict and results['warnings'] > 0:
        results['valid'] = False

    return results


if __name__ == '__main__':
    cli()
