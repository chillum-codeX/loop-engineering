"""Permissioned GitHub REST adapter with dry-run previews."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, Optional

import requests

from .permissions import (
    PermissionPolicy,
    RiskLevel,
    ToolRequest,
    ToolResult,
    ToolScope,
)


class GitHubAdapter:
    """Small, injectable GitHub adapter for issue and pull-request workflows."""

    def __init__(
        self,
        repository: str,
        *,
        token: Optional[str] = None,
        policy: Optional[PermissionPolicy] = None,
        session: Optional[Any] = None,
        api_url: str = "https://api.github.com",
        timeout: float = 20.0,
    ):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("repository must use the 'owner/name' format")
        self.repository = repository
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.policy = policy or PermissionPolicy.read_only_github()
        self.session = session or requests.Session()
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _execute(
        self,
        method: str,
        path: str,
        *,
        action: str,
        scope: ToolScope,
        risk: RiskLevel,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        approval_id: Optional[str] = None,
    ) -> ToolResult:
        request = ToolRequest(
            adapter="github",
            action=action,
            scope=scope,
            risk=risk,
            parameters=payload or params or {},
            dry_run=dry_run,
            approval_id=approval_id,
        )
        self.policy.authorize(request)
        if dry_run:
            return ToolResult(
                success=True,
                executed=False,
                action=action,
                preview={
                    "method": method,
                    "url": f"{self.api_url}{path}",
                    "payload": payload,
                    "params": params,
                },
            )
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN is required for live GitHub requests")

        response = self.session.request(
            method,
            f"{self.api_url}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=payload,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        self.policy.consume_approval(approval_id)
        return ToolResult(
            success=True,
            executed=True,
            action=action,
            data=response.json() if response.content else None,
        )

    def list_issues(self, *, state: str = "open") -> ToolResult:
        return self._execute(
            "GET",
            f"/repos/{self.repository}/issues",
            action="list_issues",
            scope=ToolScope.GITHUB_ISSUES_READ,
            risk=RiskLevel.READ,
            params={"state": state},
        )

    def list_pull_requests(self, *, state: str = "open") -> ToolResult:
        return self._execute(
            "GET",
            f"/repos/{self.repository}/pulls",
            action="list_pull_requests",
            scope=ToolScope.GITHUB_PULLS_READ,
            risk=RiskLevel.READ,
            params={"state": state},
        )

    def get_pull_request(self, pull_number: int) -> ToolResult:
        return self._execute(
            "GET",
            f"/repos/{self.repository}/pulls/{pull_number}",
            action="get_pull_request",
            scope=ToolScope.GITHUB_PULLS_READ,
            risk=RiskLevel.READ,
        )

    def list_pull_request_reviews(self, pull_number: int) -> ToolResult:
        return self._execute(
            "GET",
            f"/repos/{self.repository}/pulls/{pull_number}/reviews",
            action="list_pull_request_reviews",
            scope=ToolScope.GITHUB_PULLS_READ,
            risk=RiskLevel.READ,
        )

    def list_check_runs(self, git_ref: str) -> ToolResult:
        return self._execute(
            "GET",
            f"/repos/{self.repository}/commits/{git_ref}/check-runs",
            action="list_check_runs",
            scope=ToolScope.GITHUB_CHECKS_READ,
            risk=RiskLevel.READ,
        )

    def add_issue_labels(
        self,
        issue_number: int,
        labels: Iterable[str],
        *,
        dry_run: bool = False,
        approval_id: Optional[str] = None,
    ) -> ToolResult:
        return self._execute(
            "POST",
            f"/repos/{self.repository}/issues/{issue_number}/labels",
            action="add_issue_labels",
            scope=ToolScope.GITHUB_ISSUES_WRITE,
            risk=RiskLevel.WRITE,
            payload={"labels": list(labels)},
            dry_run=dry_run,
            approval_id=approval_id,
        )

    def request_reviewers(
        self,
        pull_number: int,
        reviewers: Iterable[str],
        *,
        dry_run: bool = False,
        approval_id: Optional[str] = None,
    ) -> ToolResult:
        return self._execute(
            "POST",
            f"/repos/{self.repository}/pulls/{pull_number}/requested_reviewers",
            action="request_reviewers",
            scope=ToolScope.GITHUB_PULLS_WRITE,
            risk=RiskLevel.WRITE,
            payload={"reviewers": list(reviewers)},
            dry_run=dry_run,
            approval_id=approval_id,
        )
