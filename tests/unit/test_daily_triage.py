"""Offline Daily Triage pattern integration tests."""

import json

import pytest

from loop_engine.patterns import DailyTriageConfig, DailyTriageHandler
from loop_engine.runtime_v1 import create_runtime
from loop_engine.tools.permissions import ToolResult


class FakeGitHub:
    repository = "owner/repo"

    def list_issues(self):
        return ToolResult(
            success=True,
            executed=True,
            action="list_issues",
            data=[
                {
                    "number": 1,
                    "title": "Security vulnerability in auth",
                    "body": "Production exposure",
                    "labels": [],
                },
                {
                    "number": 2,
                    "title": "Small documentation typo",
                    "body": "",
                    "labels": [{"name": "P2"}],
                },
                {
                    "number": 9,
                    "title": "PR represented in issues API",
                    "pull_request": {"url": "example"},
                    "labels": [],
                },
            ],
        )

    def list_pull_requests(self):
        return ToolResult(
            success=True,
            executed=True,
            action="list_pull_requests",
            data=[
                {
                    "number": 3,
                    "title": "Fix tests",
                    "requested_reviewers": [],
                    "assignees": [],
                }
            ],
        )


def test_daily_triage_produces_explainable_read_only_report(tmp_path):
    report_path = tmp_path / "report.json"
    handler = DailyTriageHandler(
        FakeGitHub(),
        DailyTriageConfig(output_path=report_path),
    )

    report = handler(None)

    assert report["issues_reviewed"] == 2
    assert report["mutations_performed"] == 0
    assert report["priority_recommendations"][0]["recommended_priority"] == "P0"
    assert report["priority_recommendations"][1]["already_labeled"] is True
    assert report["pull_requests_needing_reviewers"][0]["pull_number"] == 3
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


@pytest.mark.asyncio
async def test_runtime_executes_daily_triage_handler(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "daily-triage.md").write_text(
        """# daily-triage
## When
Run daily.
## Read
- GitHub issues
## Judge
Recommend priority.
## Output
Write report.
## Stop
- Do not mutate GitHub.
""",
        encoding="utf-8",
    )
    handler = DailyTriageHandler(FakeGitHub())
    runtime = create_runtime(
        skills_dir=str(skills),
        state_dir=str(tmp_path / "state"),
        task_handlers={"daily-triage": handler},
    )

    result = await runtime.run()
    task = next(iter(runtime.state.task_ledger.tasks.values()))

    assert result.status.name == "COMPLETED"
    assert task.context["execution_output"]["issues_reviewed"] == 2
    assert task.context["execution_output"]["mutations_performed"] == 0
