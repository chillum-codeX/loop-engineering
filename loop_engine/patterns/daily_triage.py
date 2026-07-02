"""Deterministic, read-only GitHub Daily Triage pattern."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..runtime_contracts import TaskRecord
from ..tools import GitHubAdapter


@dataclass
class DailyTriageConfig:
    output_path: Optional[Path] = None
    priority_labels: tuple[str, str, str] = ("P0", "P1", "P2")


class DailyTriageHandler:
    """Read GitHub state and produce explainable, non-mutating recommendations."""

    P0_TERMS = {
        "security",
        "vulnerability",
        "outage",
        "data loss",
        "production down",
    }
    P1_TERMS = {
        "blocker",
        "regression",
        "crash",
        "failing",
        "failure",
        "bug",
    }

    def __init__(
        self,
        github: GitHubAdapter,
        config: Optional[DailyTriageConfig] = None,
    ):
        self.github = github
        self.config = config or DailyTriageConfig()

    def _priority(self, issue: Dict[str, Any]) -> tuple[str, str]:
        text = f"{issue.get('title', '')}\n{issue.get('body') or ''}".lower()
        if any(term in text for term in self.P0_TERMS):
            return self.config.priority_labels[0], "matched critical-impact term"
        if any(term in text for term in self.P1_TERMS):
            return self.config.priority_labels[1], "matched defect/blocker term"
        return self.config.priority_labels[2], "default actionable priority"

    def __call__(self, task: TaskRecord) -> Dict[str, Any]:
        issue_data = self.github.list_issues().data or []
        pull_data = self.github.list_pull_requests().data or []
        issues = [item for item in issue_data if "pull_request" not in item]

        recommendations: List[Dict[str, Any]] = []
        for issue in issues:
            current_labels = {
                label["name"] if isinstance(label, dict) else str(label)
                for label in issue.get("labels", [])
            }
            priority, reason = self._priority(issue)
            recommendations.append(
                {
                    "issue_number": issue.get("number"),
                    "title": issue.get("title", ""),
                    "recommended_priority": priority,
                    "reason": reason,
                    "already_labeled": priority in current_labels,
                }
            )

        unassigned_pulls = [
            {
                "pull_number": pull.get("number"),
                "title": pull.get("title", ""),
            }
            for pull in pull_data
            if not pull.get("requested_reviewers") and not pull.get("assignees")
        ]
        report = {
            "repository": self.github.repository,
            "mode": "read_only_recommendations",
            "issues_reviewed": len(issues),
            "pull_requests_reviewed": len(pull_data),
            "priority_recommendations": recommendations,
            "pull_requests_needing_reviewers": unassigned_pulls,
            "mutations_performed": 0,
        }
        if self.config.output_path:
            self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.output_path.write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
        return report
