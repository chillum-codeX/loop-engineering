"""Permission and transport contract tests for the GitHub adapter."""

import pytest

from loop_engine.tools import (
    GitHubAdapter,
    PermissionDenied,
    PermissionPolicy,
    ToolScope,
)


class FakeResponse:
    content = b"[]"

    def raise_for_status(self):
        return None

    def json(self):
        return []


class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse()


def test_read_only_policy_allows_reads_and_does_not_leak_token():
    session = FakeSession()
    adapter = GitHubAdapter(
        "owner/repo",
        token="secret-token",
        session=session,
        policy=PermissionPolicy.read_only_github(),
    )

    result = adapter.list_issues()

    assert result.executed is True
    assert session.calls[0][0] == "GET"
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in repr(result)


def test_write_is_denied_without_scope():
    adapter = GitHubAdapter(
        "owner/repo",
        policy=PermissionPolicy.read_only_github(),
    )

    with pytest.raises(PermissionDenied, match="Scope is not allowed"):
        adapter.add_issue_labels(1, ["P1"], dry_run=True)


def test_dry_run_previews_write_without_token_or_network():
    session = FakeSession()
    policy = PermissionPolicy(
        allowed_scopes={ToolScope.GITHUB_ISSUES_WRITE}
    )
    adapter = GitHubAdapter("owner/repo", policy=policy, session=session)

    result = adapter.add_issue_labels(7, ["P0"], dry_run=True)

    assert result.executed is False
    assert result.preview["payload"] == {"labels": ["P0"]}
    assert session.calls == []


def test_live_write_requires_and_consumes_one_time_approval():
    session = FakeSession()
    policy = PermissionPolicy(
        allowed_scopes={ToolScope.GITHUB_ISSUES_WRITE},
        approval_ids={"approve-123"},
    )
    adapter = GitHubAdapter(
        "owner/repo",
        token="token",
        policy=policy,
        session=session,
    )

    result = adapter.add_issue_labels(
        3,
        ["P2"],
        approval_id="approve-123",
    )

    assert result.executed is True
    assert "approve-123" not in policy.approval_ids
    with pytest.raises(PermissionDenied, match="requires"):
        adapter.add_issue_labels(3, ["P1"], approval_id="approve-123")


def test_repository_format_is_validated():
    with pytest.raises(ValueError, match="owner/name"):
        GitHubAdapter("not a repository")
