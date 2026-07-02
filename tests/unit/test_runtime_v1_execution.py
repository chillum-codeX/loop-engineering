"""End-to-end tests for the executable five-phase runtime."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from loop_engine.cli.main import cli
from loop_engine.runtime_persistence import (
    RuntimePersistenceConfig,
    RuntimeStatePersistence,
)
from loop_engine.runtime_v1 import create_runtime
from loop_engine.runtime_contracts import RuntimeState
from loop_engine.skills import SkillLoader


VALID_SKILL = """# daily-triage

## When
Run daily.

## Read
- Open issues

## Judge
Keep actionable findings.

## Output
Write a triage report.

## Stop
- Do not merge pull requests.
"""


@pytest.mark.asyncio
async def test_runtime_executes_all_five_phases(tmp_path: Path):
    skills_dir = tmp_path / ".loop" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "daily-triage.md").write_text(VALID_SKILL, encoding="utf-8")

    runtime = create_runtime(
        skills_dir=str(skills_dir),
        state_dir=str(tmp_path / ".loop" / "state"),
        max_iterations=5,
    )
    result = await runtime.run()

    assert result.status.name == "COMPLETED"
    assert result.tasks_discovered == 1
    assert result.tasks_completed == 1
    assert result.tasks_failed == 0
    assert result.iterations == 1
    assert {event.phase.value for event in result.events if event.phase} == {
        "discovery",
        "handoff",
        "verification",
        "persistence",
        "scheduling",
    }
    assert list((tmp_path / ".loop" / "state").glob("runtime_state_*.json"))


@pytest.mark.asyncio
async def test_runtime_rejects_skill_without_stop_boundaries(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "unsafe.md").write_text(
        VALID_SKILL.replace("## Stop\n- Do not merge pull requests.\n", ""),
        encoding="utf-8",
    )

    runtime = create_runtime(
        skills_dir=str(skills_dir),
        state_dir=str(tmp_path / "state"),
    )
    result = await runtime.run()

    assert result.status.name == "FAILED"
    assert result.tasks_failed == 1


def test_skill_loader_supports_flat_and_directory_layouts(tmp_path: Path):
    (tmp_path / "flat.md").write_text(VALID_SKILL, encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "SKILL.md").write_text(
        VALID_SKILL.replace("# daily-triage", "# nested-skill"),
        encoding="utf-8",
    )

    skills = SkillLoader(tmp_path).load_all()

    assert set(skills) == {"daily-triage", "nested-skill"}


def test_sqlite_backend_round_trip(tmp_path: Path):
    persistence = RuntimeStatePersistence(
        RuntimePersistenceConfig(
            state_dir=tmp_path,
            backend="sqlite",
            verify_on_save=True,
        )
    )
    state = RuntimeState(runtime_id="sqlite-runtime", trace_id="sqlite-trace")
    state.current_iteration = 7

    path = persistence.save(state)
    loaded = persistence.load("sqlite-trace")

    assert path == tmp_path / "runtime_state.db"
    assert loaded is not None
    assert loaded.runtime_id == "sqlite-runtime"
    assert loaded.current_iteration == 7
    assert persistence.list_saved_states()[0]["format"] == "sqlite"


def test_unknown_persistence_backend_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="Unsupported persistence backend"):
        RuntimeStatePersistence(
            RuntimePersistenceConfig(state_dir=tmp_path, backend="mystery")
        )


def test_cli_executes_starter_configuration(tmp_path: Path):
    skills_dir = tmp_path / ".loop" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "daily-triage.md").write_text(VALID_SKILL, encoding="utf-8")
    config = tmp_path / "loop.yaml"
    config.write_text(
        """
name: test-loop
pattern: daily-triage
runtime:
  max_iterations: 3
budget:
  max_tokens: 1000
  max_cost: 1.0
  max_steps: 3
discovery:
  skills_dir: .loop/skills
verification:
  mandatory_gates: [syntax, security]
persistence:
  state_dir: .loop/state
  format: sqlite
  auto_save: true
""".strip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["run", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert "Tasks completed: 1" in result.output
    assert (tmp_path / ".loop" / "state" / "runtime_state.db").exists()
