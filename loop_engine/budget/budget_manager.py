"""
Budget Management

Resource budgeting and constraint enforcement for loop execution.
Supports token limits, step limits, time limits, and cost tracking.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """Current status of budget consumption."""
    tokens_used: int = 0
    tokens_remaining: Optional[int] = None
    steps_used: int = 0
    steps_remaining: Optional[int] = None
    time_used: float = 0.0
    time_remaining: Optional[float] = None
    cost_used: float = 0.0
    cost_remaining: Optional[float] = None
    exhausted: bool = False
    utilization: Dict[str, float] = field(default_factory=dict)


class Budget(ABC):
    """Abstract budget constraint."""

    @abstractmethod
    def check(self) -> bool:
        """Check if budget is still valid."""
        pass

    @abstractmethod
    def consume(self, amount: Any):
        """Consume budget resources."""
        pass

    @abstractmethod
    def remaining(self) -> Any:
        """Get remaining budget."""
        pass

    @abstractmethod
    def utilization(self) -> float:
        """Get utilization ratio (0.0 to 1.0)."""
        pass


class TokenBudget(Budget):
    """Budget constraint based on token consumption."""

    def __init__(self, max_tokens: int, cost_per_token: float = 0.0):
        self.max_tokens = max_tokens
        self.cost_per_token = cost_per_token
        self.used = 0

    def check(self) -> bool:
        return self.used < self.max_tokens

    def consume(self, tokens: int):
        self.used += tokens
        if self.used > self.max_tokens:
            logger.warning(f"Token budget exceeded: {self.used}/{self.max_tokens}")

    def remaining(self) -> int:
        return max(0, self.max_tokens - self.used)

    def utilization(self) -> float:
        return self.used / self.max_tokens if self.max_tokens > 0 else 0.0

    def estimate_cost(self) -> float:
        return self.used * self.cost_per_token


class StepBudget(Budget):
    """Budget constraint based on number of steps/iterations."""

    def __init__(self, max_steps: int):
        self.max_steps = max_steps
        self.used = 0

    def check(self) -> bool:
        return self.used < self.max_steps

    def consume(self, steps: int = 1):
        self.used += steps
        if self.used > self.max_steps:
            logger.warning(f"Step budget exceeded: {self.used}/{self.max_steps}")

    def remaining(self) -> int:
        return max(0, self.max_steps - self.used)

    def utilization(self) -> float:
        return self.used / self.max_steps if self.max_steps > 0 else 0.0


class TimeBudget(Budget):
    """Budget constraint based on elapsed time."""

    def __init__(self, max_seconds: float):
        self.max_seconds = max_seconds
        self.start_time: Optional[float] = None
        self.paused_duration = 0.0
        self._pause_start: Optional[float] = None

    def start(self):
        """Start the timer."""
        self.start_time = time.time()

    def pause(self):
        """Pause the timer."""
        if self.start_time and not self._pause_start:
            self._pause_start = time.time()

    def resume(self):
        """Resume the timer."""
        if self._pause_start:
            self.paused_duration += time.time() - self._pause_start
            self._pause_start = None

    def check(self) -> bool:
        return self.elapsed() < self.max_seconds

    def consume(self, seconds: float = 0):
        """Time is consumed automatically; this method exists for interface compatibility."""
        pass

    def elapsed(self) -> float:
        if not self.start_time:
            return 0.0
        pause_time = (time.time() - self._pause_start) if self._pause_start else 0.0
        return time.time() - self.start_time - self.paused_duration - pause_time

    def remaining(self) -> float:
        return max(0.0, self.max_seconds - self.elapsed())

    def utilization(self) -> float:
        return self.elapsed() / self.max_seconds if self.max_seconds > 0 else 0.0


class CostBudget(Budget):
    """Budget constraint based on monetary cost."""

    def __init__(self, max_cost: float):
        self.max_cost = max_cost
        self.used = 0.0
        self.cost_breakdown: Dict[str, float] = {}

    def check(self) -> bool:
        return self.used < self.max_cost

    def consume(self, cost: float, category: str = "general"):
        self.used += cost
        self.cost_breakdown[category] = self.cost_breakdown.get(category, 0.0) + cost
        if self.used > self.max_cost:
            logger.warning(f"Cost budget exceeded: ${self.used:.4f}/${self.max_cost:.4f}")

    def remaining(self) -> float:
        return max(0.0, self.max_cost - self.used)

    def utilization(self) -> float:
        return self.used / self.max_cost if self.max_cost > 0 else 0.0

    def get_breakdown(self) -> Dict[str, float]:
        return self.cost_breakdown.copy()


class BudgetManager:
    """
    Manages multiple budget constraints simultaneously.

    Coordinates token, step, time, and cost budgets during execution.
    """

    def __init__(
        self,
        token_budget: Optional[TokenBudget] = None,
        step_budget: Optional[StepBudget] = None,
        time_budget: Optional[TimeBudget] = None,
        cost_budget: Optional[CostBudget] = None
    ):
        self.token_budget = token_budget
        self.step_budget = step_budget
        self.time_budget = time_budget
        self.cost_budget = cost_budget

        # Start time budget if present
        if self.time_budget:
            self.time_budget.start()

        # Callbacks for budget events
        self._on_budget_exhausted: Optional[Callable] = None
        self._on_threshold: Optional[Callable] = None
        self._threshold = 0.9

    def set_callbacks(
        self,
        on_exhausted: Optional[Callable] = None,
        on_threshold: Optional[Callable] = None,
        threshold: float = 0.9
    ):
        """Set callbacks for budget events."""
        self._on_budget_exhausted = on_exhausted
        self._on_threshold = on_threshold
        self._threshold = threshold

    def check_all(self) -> bool:
        """Check all budgets are still valid."""
        budgets = [
            ("token", self.token_budget),
            ("step", self.step_budget),
            ("time", self.time_budget),
            ("cost", self.cost_budget)
        ]

        for name, budget in budgets:
            if budget and not budget.check():
                logger.warning(f"Budget exhausted: {name}")
                if self._on_budget_exhausted:
                    self._on_budget_exhausted(name, budget)
                return False

        return True

    def consume(
        self,
        tokens: int = 0,
        steps: int = 0,
        cost: float = 0.0,
        cost_category: str = "general"
    ):
        """Consume resources across all budgets."""
        if tokens and self.token_budget:
            self.token_budget.consume(tokens)
        if steps and self.step_budget:
            self.step_budget.consume(steps)
        if cost and self.cost_budget:
            self.cost_budget.consume(cost, cost_category)

        # Check thresholds
        self._check_thresholds()

    def _check_thresholds(self):
        """Check if any budget crossed the warning threshold."""
        budgets = [
            ("token", self.token_budget),
            ("step", self.step_budget),
            ("time", self.time_budget),
            ("cost", self.cost_budget)
        ]

        for name, budget in budgets:
            if budget and budget.utilization() >= self._threshold:
                if self._on_threshold:
                    self._on_threshold(name, budget)

    def get_status(self) -> BudgetStatus:
        """Get current budget status."""
        status = BudgetStatus()

        if self.token_budget:
            status.tokens_used = self.token_budget.used
            status.tokens_remaining = self.token_budget.remaining()
            status.utilization["token"] = self.token_budget.utilization()

        if self.step_budget:
            status.steps_used = self.step_budget.used
            status.steps_remaining = self.step_budget.remaining()
            status.utilization["step"] = self.step_budget.utilization()

        if self.time_budget:
            status.time_used = self.time_budget.elapsed()
            status.time_remaining = self.time_budget.remaining()
            status.utilization["time"] = self.time_budget.utilization()

        if self.cost_budget:
            status.cost_used = self.cost_budget.used
            status.cost_remaining = self.cost_budget.remaining()
            status.utilization["cost"] = self.cost_budget.utilization()

        status.exhausted = not self.check_all()
        return status

    def get_most_constrained(self) -> Optional[str]:
        """Get the most constrained (highest utilization) budget."""
        utilizations = []

        if self.token_budget:
            utilizations.append(("token", self.token_budget.utilization()))
        if self.step_budget:
            utilizations.append(("step", self.step_budget.utilization()))
        if self.time_budget:
            utilizations.append(("time", self.time_budget.utilization()))
        if self.cost_budget:
            utilizations.append(("cost", self.cost_budget.utilization()))

        if utilizations:
            return max(utilizations, key=lambda x: x[1])[0]
        return None

    def get_efficiency_report(self) -> Dict[str, Any]:
        """Generate an efficiency report."""
        status = self.get_status()

        return {
            "utilization": status.utilization,
            "most_constrained": self.get_most_constrained(),
            "cost_breakdown": self.cost_budget.get_breakdown() if self.cost_budget else {},
            "projected_total_cost": self._project_cost(),
            "efficiency_score": self._calculate_efficiency()
        }

    def _project_cost(self) -> float:
        """Project final cost based on current utilization."""
        if not self.cost_budget:
            return 0.0

        utilizations = [v for v in self.get_status().utilization.values() if v > 0]
        if utilizations:
            avg_util = sum(utilizations) / len(utilizations)
            if avg_util > 0:
                return self.cost_budget.used / avg_util
        return self.cost_budget.used

    def _calculate_efficiency(self) -> float:
        """Calculate an efficiency score (0-1)."""
        status = self.get_status()

        # Ideal: balanced utilization across budgets
        utils = [v for v in status.utilization.values() if v > 0]
        if not utils:
            return 1.0

        # Variance from balanced utilization
        avg_util = sum(utils) / len(utils)
        variance = sum((u - avg_util) ** 2 for u in utils) / len(utils)

        # Lower variance = higher efficiency
        return max(0.0, 1.0 - variance)

    def pause(self):
        """Pause time budget."""
        if self.time_budget:
            self.time_budget.pause()

    def resume(self):
        """Resume time budget."""
        if self.time_budget:
            self.time_budget.resume()

    def reset(self):
        """Reset all budgets."""
        if self.token_budget:
            self.token_budget.used = 0
        if self.step_budget:
            self.step_budget.used = 0
        if self.time_budget:
            self.time_budget = TimeBudget(self.time_budget.max_seconds)
            self.time_budget.start()
        if self.cost_budget:
            self.cost_budget.used = 0.0
            self.cost_budget.cost_breakdown.clear()


class AdaptiveBudgetManager(BudgetManager):
    """
    Budget manager that adapts allocation based on task progress.

    Dynamically adjusts budgets based on task complexity and progress.
    """

    def __init__(
        self,
        token_budget: Optional[TokenBudget] = None,
        step_budget: Optional[StepBudget] = None,
        time_budget: Optional[TimeBudget] = None,
        cost_budget: Optional[CostBudget] = None,
        adaptation_strategy: str = "proportional"
    ):
        super().__init__(token_budget, step_budget, time_budget, cost_budget)
        self.adaptation_strategy = adaptation_strategy
        self.progress_history: List[float] = []

    def update_progress(self, progress: float):
        """Update with current progress (0.0 to 1.0)."""
        self.progress_history.append(progress)

    def get_recommended_allocation(self) -> Dict[str, Any]:
        """Get recommended resource allocation adjustments."""
        if not self.progress_history:
            return {}

        current_progress = self.progress_history[-1]
        status = self.get_status()

        # Calculate expected progress vs actual utilization
        avg_util = sum(status.utilization.values()) / len(status.utilization) if status.utilization else 0

        if current_progress < avg_util * 0.5:
            # Progress is slower than expected
            return {
                "recommendation": "increase_budget",
                "reason": "progress slower than expected",
                "progress": current_progress,
                "avg_utilization": avg_util
            }
        elif current_progress > avg_util * 1.5:
            # Progress is faster than expected
            return {
                "recommendation": "decrease_budget_safe",
                "reason": "progress faster than expected",
                "progress": current_progress,
                "avg_utilization": avg_util
            }
        else:
            return {
                "recommendation": "maintain",
                "reason": "progress on track",
                "progress": current_progress,
                "avg_utilization": avg_util
            }
