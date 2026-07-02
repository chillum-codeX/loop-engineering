"""Deterministic, read-only pull-request health analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..runtime_contracts import TaskRecord
from ..tools import GitHubAdapter


@dataclass
class PRBabysitterConfig:
    output_path: Optional[Path] = None
    stale_after_hours: int = 48


class PRBabysitterHandler:
    """Inspect open PRs and report actionable blockers without mutating them."""

    def __init__(
        self,
        github: GitHubAdapter,
        config: Optional[PRBabysitterConfig] = None,
        *,
        now: Optional[datetime] = None,
    ):
        self.github = github
        self.config = config or PRBabysitterConfig()
        self.now = now

    def _age_hours(self, timestamp: Optional[str]) -> Optional[float]:
        if not timestamp:
            return None
        updated = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        current = self.now or datetime.now(timezone.utc)
        return (current - updated).total_seconds() / 3600

    def __call__(self, task: TaskRecord) -> Dict[str, Any]:
        pulls = self.github.list_pull_requests().data or []
        analyses = []
        for summary in pulls:
            number = summary["number"]
            detail = self.github.get_pull_request(number).data or summary
            reviews = self.github.list_pull_request_reviews(number).data or []
            head_sha = detail.get("head", {}).get("sha")
            checks = (
                (self.github.list_check_runs(head_sha).data or {}).get("check_runs", [])
                if head_sha
                else []
            )

            review_states = {
                review.get("state", "").upper()
                for review in reviews
            }
            failed_checks = [
                check.get("name", "unnamed")
                for check in checks
                if check.get("conclusion") in {
                    "failure", "timed_out", "cancelled", "action_required"
                }
            ]
            pending_checks = [
                check.get("name", "unnamed")
                for check in checks
                if check.get("status") != "completed"
            ]
            blockers = []
            if detail.get("draft"):
                blockers.append("draft")
            if detail.get("mergeable") is False:
                blockers.append("merge_conflict")
            if "CHANGES_REQUESTED" in review_states:
                blockers.append("changes_requested")
            if "APPROVED" not in review_states:
                blockers.append("approval_missing")
            if failed_checks:
                blockers.append("checks_failed")
            if pending_checks:
                blockers.append("checks_pending")

            age_hours = self._age_hours(detail.get("updated_at"))
            stale = (
                age_hours is not None
                and age_hours >= self.config.stale_after_hours
            )
            if stale:
                blockers.append("stale")
            analyses.append(
                {
                    "pull_number": number,
                    "title": detail.get("title", ""),
                    "blockers": blockers,
                    "failed_checks": failed_checks,
                    "pending_checks": pending_checks,
                    "age_hours": round(age_hours, 1) if age_hours is not None else None,
                    "recommendation": "ready_for_human_merge"
                    if not blockers
                    else "human_attention_required",
                }
            )

        report = {
            "repository": self.github.repository,
            "mode": "read_only_analysis",
            "pull_requests_reviewed": len(analyses),
            "ready_count": sum(
                item["recommendation"] == "ready_for_human_merge"
                for item in analyses
            ),
            "attention_count": sum(
                item["recommendation"] == "human_attention_required"
                for item in analyses
            ),
            "pull_requests": analyses,
            "mutations_performed": 0,
        }
        if self.config.output_path:
            self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.output_path.write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
        return report
