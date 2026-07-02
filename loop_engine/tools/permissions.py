"""Deny-by-default permissions for external tool adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set


class RiskLevel(Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ToolScope(Enum):
    GITHUB_ISSUES_READ = "github:issues:read"
    GITHUB_ISSUES_WRITE = "github:issues:write"
    GITHUB_PULLS_READ = "github:pulls:read"
    GITHUB_PULLS_WRITE = "github:pulls:write"
    GITHUB_CHECKS_READ = "github:checks:read"


class PermissionDenied(RuntimeError):
    """Raised before an adapter performs an unauthorized action."""


@dataclass(frozen=True)
class ToolRequest:
    adapter: str
    action: str
    scope: ToolScope
    risk: RiskLevel
    parameters: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    approval_id: Optional[str] = None


@dataclass
class ToolResult:
    success: bool
    executed: bool
    action: str
    data: Any = None
    preview: Optional[Dict[str, Any]] = None


@dataclass
class PermissionPolicy:
    """Explicit scopes plus one-time approval IDs for mutating operations."""

    allowed_scopes: Set[ToolScope] = field(default_factory=set)
    approval_ids: Set[str] = field(default_factory=set)
    require_write_approval: bool = True

    @classmethod
    def read_only_github(cls) -> "PermissionPolicy":
        return cls(
            allowed_scopes={
                ToolScope.GITHUB_ISSUES_READ,
                ToolScope.GITHUB_PULLS_READ,
                ToolScope.GITHUB_CHECKS_READ,
            }
        )

    def authorize(self, request: ToolRequest) -> None:
        if request.scope not in self.allowed_scopes:
            raise PermissionDenied(f"Scope is not allowed: {request.scope.value}")
        if request.dry_run:
            return
        if (
            request.risk in {RiskLevel.WRITE, RiskLevel.DESTRUCTIVE}
            and self.require_write_approval
            and request.approval_id not in self.approval_ids
        ):
            raise PermissionDenied(
                f"Action {request.action!r} requires an approved approval_id"
            )

    def consume_approval(self, approval_id: Optional[str]) -> None:
        if approval_id:
            self.approval_ids.discard(approval_id)
