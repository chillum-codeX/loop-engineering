"""
Budget Caps Module

Based on Anthropic's Loop Engineering paper (Section VIII):
- "Token blowout: The loop hatches helpers, retries, and runs round after round"
- "One bug can spin idle all night and produce an unfamiliar bill"
- "The guard is hard caps set before shipping"

Implements hard ceilings for resource consumption.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class CapType(Enum):
    """Types of resource caps."""
    TOKENS = auto()
    COST = auto()
    TIME = auto()
    RETRIES = auto()
    PARALLEL_AGENTS = auto()


@dataclass
class Usage:
    """Current resource usage."""
    tokens_used: int = 0
    cost_used: float = 0.0
    time_used: float = 0.0  # seconds
    retries_used: int = 0
    parallel_agents: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tokens_used": self.tokens_used,
            "cost_used": self.cost_used,
            "time_used": self.time_used,
            "retries_used": self.retries_used,
            "parallel_agents": self.parallel_agents,
        }


@dataclass
class BudgetCaps:
    """
    Hard ceilings for resource consumption.

    Following the paper's recommendation:
    "per-run budget, daily budget, max retries - so an idle bug
    cannot burn an entire night's quota"
    """
    # Per-run limits
    per_run_tokens: Optional[int] = 100_000
    per_run_cost: Optional[float] = 10.0
    per_run_time: Optional[float] = 300.0  # 5 minutes
    max_retries: int = 3
    max_parallel_agents: int = 5

    # Daily limits (for tracking)
    daily_tokens: Optional[int] = 1_000_000
    daily_cost: Optional[float] = 100.0

    # Emergency stop threshold
    emergency_stop_threshold: float = 0.95  # Stop at 95% of any cap

    def check(self, current: Usage) -> CapCheckResult:
        """
        Check if any cap is exceeded.

        Args:
            current: Current resource usage

        Returns:
            CapCheckResult with pass/fail status and details
        """
        exceeded = []
        warnings = []

        # Check tokens
        if self.per_run_tokens:
            usage_ratio = current.tokens_used / self.per_run_tokens
            if current.tokens_used >= self.per_run_tokens:
                exceeded.append(
                    CapViolation(
                        cap_type=CapType.TOKENS,
                        limit=self.per_run_tokens,
                        used=current.tokens_used,
                        message=f"Token cap exceeded: {current.tokens_used:,} / {self.per_run_tokens:,}",
                    )
                )
            elif usage_ratio >= self.emergency_stop_threshold:
                warnings.append(
                    f"Token usage at {usage_ratio:.1%} of cap"
                )

        # Check cost
        if self.per_run_cost:
            usage_ratio = current.cost_used / self.per_run_cost
            if current.cost_used >= self.per_run_cost:
                exceeded.append(
                    CapViolation(
                        cap_type=CapType.COST,
                        limit=self.per_run_cost,
                        used=current.cost_used,
                        message=f"Cost cap exceeded: ${current.cost_used:.2f} / ${self.per_run_cost:.2f}",
                    )
                )
            elif usage_ratio >= self.emergency_stop_threshold:
                warnings.append(
                    f"Cost usage at {usage_ratio:.1%} of cap"
                )

        # Check time
        if self.per_run_time:
            usage_ratio = current.time_used / self.per_run_time
            if current.time_used >= self.per_run_time:
                exceeded.append(
                    CapViolation(
                        cap_type=CapType.TIME,
                        limit=self.per_run_time,
                        used=current.time_used,
                        message=f"Time cap exceeded: {current.time_used:.1f}s / {self.per_run_time:.1f}s",
                    )
                )
            elif usage_ratio >= self.emergency_stop_threshold:
                warnings.append(
                    f"Time usage at {usage_ratio:.1%} of cap"
                )

        # Check retries
        if current.retries_used >= self.max_retries:
            exceeded.append(
                CapViolation(
                    cap_type=CapType.RETRIES,
                    limit=self.max_retries,
                    used=current.retries_used,
                    message=f"Retry cap exceeded: {current.retries_used} / {self.max_retries}",
                )
            )

        # Check parallel agents
        if current.parallel_agents > self.max_parallel_agents:
            exceeded.append(
                CapViolation(
                    cap_type=CapType.PARALLEL_AGENTS,
                    limit=self.max_parallel_agents,
                    used=current.parallel_agents,
                    message=f"Parallel agent cap exceeded: {current.parallel_agents} / {self.max_parallel_agents}",
                )
            )

        return CapCheckResult(
            passed=len(exceeded) == 0,
            exceeded=exceeded,
            warnings=warnings,
            usage=current,
            caps=self,
        )

    def remaining(self, current: Usage) -> Dict[str, Any]:
        """Calculate remaining budget."""
        return {
            "tokens": self.per_run_tokens - current.tokens_used if self.per_run_tokens else None,
            "cost": self.per_run_cost - current.cost_used if self.per_run_cost else None,
            "time": self.per_run_time - current.time_used if self.per_run_time else None,
            "retries": self.max_retries - current.retries_used,
            "parallel_agents": self.max_parallel_agents - current.parallel_agents,
        }


@dataclass
class CapViolation:
    """A single cap violation."""
    cap_type: CapType
    limit: float
    used: float
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cap_type": self.cap_type.name,
            "limit": self.limit,
            "used": self.used,
            "message": self.message,
        }


@dataclass
class CapCheckResult:
    """Result of checking budget caps."""
    passed: bool
    exceeded: List[CapViolation]
    warnings: List[str]
    usage: Usage
    caps: BudgetCaps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "exceeded": [e.to_dict() for e in self.exceeded],
            "warnings": self.warnings,
            "usage": self.usage.to_dict(),
        }

    @property
    def should_stop(self) -> bool:
        """Whether execution should stop immediately."""
        return len(self.exceeded) > 0

    @property
    def stop_reason(self) -> Optional[str]:
        """Reason for stopping, if any."""
        if self.exceeded:
            return "; ".join(e.message for e in self.exceeded)
        return None


class BudgetTracker:
    """
    Tracks resource usage across loop execution.

    Provides real-time monitoring and emergency stop capability.
    """

    def __init__(self, caps: BudgetCaps):
        self.caps = caps
        self.usage = Usage()
        self._start_time: Optional[float] = None
        self._history: List[Dict[str, Any]] = []

    def start(self) -> None:
        """Start tracking."""
        self._start_time = time.time()

    def record_tokens(self, tokens: int) -> CapCheckResult:
        """Record token usage and check caps."""
        self.usage.tokens_used += tokens
        return self._check_and_record("tokens", tokens)

    def record_cost(self, cost: float) -> CapCheckResult:
        """Record cost and check caps."""
        self.usage.cost_used += cost
        return self._check_and_record("cost", cost)

    def record_retry(self) -> CapCheckResult:
        """Record a retry attempt."""
        self.usage.retries_used += 1
        return self._check_and_record("retry", 1)

    def record_parallel_agent(self, delta: int = 1) -> CapCheckResult:
        """Record change in parallel agents."""
        self.usage.parallel_agents += delta
        return self._check_and_record("parallel_agents", delta)

    def update_time(self) -> CapCheckResult:
        """Update elapsed time and check caps."""
        if self._start_time:
            self.usage.time_used = time.time() - self._start_time
        return self.caps.check(self.usage)

    def _check_and_record(self, event_type: str, amount: float) -> CapCheckResult:
        """Check caps and record event."""
        result = self.caps.check(self.usage)
        self._history.append({
            "event_type": event_type,
            "amount": amount,
            "timestamp": time.time(),
            "total_usage": self.usage.to_dict(),
            "passed": result.passed,
        })
        return result

    def get_usage(self) -> Usage:
        """Get current usage (with updated time)."""
        self.update_time()
        return self.usage

    def get_history(self) -> List[Dict[str, Any]]:
        """Get usage history."""
        return self._history.copy()

    def get_summary(self) -> Dict[str, Any]:
        """Get usage summary."""
        self.update_time()
        return {
            "usage": self.usage.to_dict(),
            "caps": {
                "per_run_tokens": self.caps.per_run_tokens,
                "per_run_cost": self.caps.per_run_cost,
                "per_run_time": self.caps.per_run_time,
                "max_retries": self.caps.max_retries,
            },
            "remaining": self.caps.remaining(self.usage),
            "utilization": {
                "tokens": self.usage.tokens_used / self.caps.per_run_tokens if self.caps.per_run_tokens else 0,
                "cost": self.usage.cost_used / self.caps.per_run_cost if self.caps.per_run_cost else 0,
                "time": self.usage.time_used / self.caps.per_run_time if self.caps.per_run_time else 0,
                "retries": self.usage.retries_used / self.caps.max_retries,
            },
        }


# Pre-configured budget cap presets

class BudgetPresets:
    """Factory for common budget cap configurations."""

    @staticmethod
    def conservative() -> BudgetCaps:
        """Very conservative caps for safety."""
        return BudgetCaps(
            per_run_tokens=50_000,
            per_run_cost=5.0,
            per_run_time=180.0,
            max_retries=2,
            max_parallel_agents=3,
        )

    @staticmethod
    def standard() -> BudgetCaps:
        """Standard caps for normal usage."""
        return BudgetCaps(
            per_run_tokens=100_000,
            per_run_cost=10.0,
            per_run_time=300.0,
            max_retries=3,
            max_parallel_agents=5,
        )

    @staticmethod
    def generous() -> BudgetCaps:
        """Generous caps for complex tasks."""
        return BudgetCaps(
            per_run_tokens=500_000,
            per_run_cost=50.0,
            per_run_time=600.0,
            max_retries=5,
            max_parallel_agents=10,
        )

    @staticmethod
    def unlimited() -> BudgetCaps:
        """No caps (use with caution)."""
        return BudgetCaps(
            per_run_tokens=None,
            per_run_cost=None,
            per_run_time=None,
            max_retries=10,
            max_parallel_agents=20,
        )

    @staticmethod
    def ci_pipeline() -> BudgetCaps:
        """Optimized for CI/CD pipelines."""
        return BudgetCaps(
            per_run_tokens=200_000,
            per_run_cost=15.0,
            per_run_time=120.0,  # Fast CI
            max_retries=1,  # Fail fast in CI
            max_parallel_agents=10,
        )
