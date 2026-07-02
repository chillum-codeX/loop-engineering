"""Offline PR Babysitter pattern tests."""

from datetime import datetime, timezone

from loop_engine.patterns import PRBabysitterConfig, PRBabysitterHandler
from loop_engine.tools.permissions import ToolResult


class FakeGitHub:
    repository = "owner/repo"

    def list_pull_requests(self):
        return ToolResult(True, True, "list", data=[
            {"number": 10},
            {"number": 11},
        ])

    def get_pull_request(self, number):
        if number == 10:
            data = {
                "number": 10,
                "title": "Ready change",
                "draft": False,
                "mergeable": True,
                "updated_at": "2026-07-01T11:00:00Z",
                "head": {"sha": "ready"},
            }
        else:
            data = {
                "number": 11,
                "title": "Broken stale change",
                "draft": False,
                "mergeable": False,
                "updated_at": "2026-06-28T00:00:00Z",
                "head": {"sha": "broken"},
            }
        return ToolResult(True, True, "detail", data=data)

    def list_pull_request_reviews(self, number):
        states = [{"state": "APPROVED"}] if number == 10 else [
            {"state": "CHANGES_REQUESTED"}
        ]
        return ToolResult(True, True, "reviews", data=states)

    def list_check_runs(self, git_ref):
        checks = (
            [{"name": "tests", "status": "completed", "conclusion": "success"}]
            if git_ref == "ready"
            else [{"name": "tests", "status": "completed", "conclusion": "failure"}]
        )
        return ToolResult(True, True, "checks", data={"check_runs": checks})


def test_pr_babysitter_reports_ready_and_blocked_prs(tmp_path):
    handler = PRBabysitterHandler(
        FakeGitHub(),
        PRBabysitterConfig(
            output_path=tmp_path / "report.json",
            stale_after_hours=48,
        ),
        now=datetime(2026, 7, 2, 12, tzinfo=timezone.utc),
    )

    report = handler(None)

    assert report["ready_count"] == 1
    assert report["attention_count"] == 1
    assert report["mutations_performed"] == 0
    assert report["pull_requests"][0]["blockers"] == []
    assert set(report["pull_requests"][1]["blockers"]) == {
        "merge_conflict",
        "changes_requested",
        "approval_missing",
        "checks_failed",
        "stale",
    }
    assert (tmp_path / "report.json").exists()
