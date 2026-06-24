"""
Safety Mechanisms

Security and safety components including:
- SafetyMonitor: Continuous safety checks
- Sandbox: Isolated execution environment
- CircuitBreaker: Fail-fast for repeated failures
- AnomalyDetector: Detects unusual patterns
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
import numpy as np

from loop_engine.types import Failure, FailureType, SafetyCheck

logger = logging.getLogger(__name__)


class SafetyMonitor:
    """
    Continuous safety monitoring for loop execution.

    Runs safety checks at regular intervals and can trigger
    circuit breaks or other protective measures.
    """

    def __init__(
        self,
        checks: Optional[List[Callable]] = None,
        check_interval: float = 1.0
    ):
        self.checks = checks or []
        self.check_interval = check_interval
        self.check_results: List[SafetyCheck] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def add_check(self, check: Callable):
        """Add a safety check."""
        self.checks.append(check)

    async def start(self):
        """Start continuous monitoring."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            await self._run_checks()
            await asyncio.sleep(self.check_interval)

    async def _run_checks(self):
        """Run all registered safety checks."""
        for check in self.checks:
            try:
                result = await check() if asyncio.iscoroutinefunction(check) else check()
                if isinstance(result, SafetyCheck):
                    self.check_results.append(result)
                    if not result.passed and result.severity == "critical":
                        logger.error(f"Critical safety check failed: {result.message}")
            except Exception as e:
                logger.error(f"Safety check failed with exception: {e}")

    def get_critical_issues(self) -> List[SafetyCheck]:
        """Get all critical safety issues."""
        return [c for c in self.check_results if not c.passed and c.severity == "critical"]

    def get_recent_checks(self, n: int = 10) -> List[SafetyCheck]:
        """Get recent safety checks."""
        return self.check_results[-n:]


class Sandbox:
    """
    Sandboxed execution environment.

    Provides isolation for potentially dangerous operations.
    """

    def __init__(
        self,
        allowed_modules: Optional[Set[str]] = None,
        blocked_functions: Optional[Set[str]] = None,
        max_memory_mb: int = 512,
        max_cpu_time: float = 30.0
    ):
        self.allowed_modules = allowed_modules or set()
        self.blocked_functions = blocked_functions or {
            "eval", "exec", "compile", "__import__", "open",
            "subprocess.run", "os.system", "os.exec"
        }
        self.max_memory_mb = max_memory_mb
        self.max_cpu_time = max_cpu_time
        self.execution_log: List[Dict] = []

    async def execute(self, code: str, context: Optional[Dict] = None) -> Any:
        """
        Execute code in sandboxed environment.

        Args:
            code: Code to execute
            context: Variables to provide in execution context

        Returns:
            Execution result
        """
        # Check for blocked functions
        for func in self.blocked_functions:
            if func in code:
                raise SecurityError(f"Blocked function detected: {func}")

        # Create restricted globals
        safe_globals = {
            "__builtins__": {
                "len": len, "range": range, "enumerate": enumerate,
                "zip": zip, "map": map, "filter": filter,
                "sum": sum, "min": min, "max": max, "abs": abs,
                "round": round, "pow": pow, "divmod": divmod,
                "str": str, "int": int, "float": float, "bool": bool,
                "list": list, "dict": dict, "set": set, "tuple": tuple,
                "print": self._safe_print, "Exception": Exception
            }
        }

        if context:
            safe_globals.update(context)

        start_time = time.time()

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._run_in_executor(code, safe_globals),
                timeout=self.max_cpu_time
            )

            execution_time = time.time() - start_time
            self.execution_log.append({
                "code": code[:100],
                "success": True,
                "execution_time": execution_time
            })

            return result

        except asyncio.TimeoutError:
            self.execution_log.append({
                "code": code[:100],
                "success": False,
                "error": "timeout"
            })
            raise SecurityError(f"Execution timed out after {self.max_cpu_time}s")

        except Exception as e:
            self.execution_log.append({
                "code": code[:100],
                "success": False,
                "error": str(e)
            })
            raise

    async def _run_in_executor(self, code: str, globals_dict: Dict):
        """Run code in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: exec(code, globals_dict))

    def _safe_print(self, *args, **kwargs):
        """Safe print function that logs instead."""
        output = " ".join(str(arg) for arg in args)
        logger.info(f"[Sandbox Output] {output}")

    def get_execution_log(self) -> List[Dict]:
        """Get execution log."""
        return self.execution_log.copy()


class CircuitBreaker:
    """
    Circuit breaker pattern for failure handling.

    Opens circuit after threshold failures to prevent cascade failures.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half_open
        self.half_open_calls = 0

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args, **kwargs: Arguments to function

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                self.half_open_calls = 0
                logger.info("Circuit breaker entering half-open state")
            else:
                raise CircuitBreakerOpen("Circuit breaker is open")

        if self.state == "half_open":
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpen("Circuit breaker half-open limit reached")
            self.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Async version of call."""
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                self.half_open_calls = 0
            else:
                raise CircuitBreakerOpen("Circuit breaker is open")

        if self.state == "half_open":
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpen("Circuit breaker half-open limit reached")
            self.half_open_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        if self.state == "half_open":
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self._reset()
                logger.info("Circuit breaker closed after successful recovery")
        else:
            self.failure_count = max(0, self.failure_count - 1)

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def _reset(self):
        """Reset circuit breaker."""
        self.failure_count = 0
        self.success_count = 0
        self.state = "closed"
        self.half_open_calls = 0
        self.last_failure_time = None

    def get_state(self) -> Dict[str, Any]:
        """Get current state."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time
        }


class AnomalyDetector:
    """
    Detects anomalous patterns in loop execution.

    Uses statistical methods to identify unusual behavior.
    """

    def __init__(
        self,
        window_size: int = 10,
        z_threshold: float = 3.0,
        pattern_history_size: int = 100
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.pattern_history_size = pattern_history_size

        self.metrics_history: Dict[str, List[float]] = {}
        self.pattern_history: List[Dict] = []
        self.anomaly_count = 0

    def record_metric(self, name: str, value: float):
        """Record a metric for anomaly detection."""
        if name not in self.metrics_history:
            self.metrics_history[name] = []
        self.metrics_history[name].append(value)

        # Keep history bounded
        if len(self.metrics_history[name]) > self.pattern_history_size:
            self.metrics_history[name] = self.metrics_history[name][-self.window_size:]

    def check_anomaly(self, name: str, value: float) -> Optional[Dict]:
        """
        Check if value is anomalous for given metric.

        Returns:
            Anomaly info if detected, None otherwise
        """
        history = self.metrics_history.get(name, [])
        if len(history) < self.window_size:
            return None

        window = history[-self.window_size:]
        mean = np.mean(window)
        std = np.std(window)

        if std == 0:
            return None

        z_score = (value - mean) / std

        if abs(z_score) > self.z_threshold:
            self.anomaly_count += 1
            return {
                "metric": name,
                "value": value,
                "expected_range": (mean - self.z_threshold * std, mean + self.z_threshold * std),
                "z_score": z_score,
                "severity": "high" if abs(z_score) > 5 else "medium"
            }

        return None

    def check_pattern_anomaly(self, current_pattern: Dict) -> Optional[Dict]:
        """Check for pattern-based anomalies."""
        self.pattern_history.append(current_pattern)

        if len(self.pattern_history) < 10:
            return None

        # Check for repeating patterns (possible loop)
        recent = self.pattern_history[-10:]
        if self._is_repeating(recent):
            return {
                "type": "repeating_pattern",
                "description": "Detected repeating pattern - possible infinite loop",
                "severity": "high"
            }

        # Check for rapid pattern changes (instability)
        if len(self.pattern_history) >= 20:
            older = self.pattern_history[-20:-10]
            if self._is_unstable(recent, older):
                return {
                    "type": "instability",
                    "description": "High pattern variance detected - possible instability",
                    "severity": "medium"
                }

        return None

    def _is_repeating(self, patterns: List[Dict]) -> bool:
        """Check if patterns are repeating."""
        if len(patterns) < 4:
            return False

        # Simple check: compare first half with second half
        mid = len(patterns) // 2
        first_half = patterns[:mid]
        second_half = patterns[mid:]

        # Check if pattern types match
        first_types = [p.get("type") for p in first_half]
        second_types = [p.get("type") for p in second_half]

        return first_types == second_types

    def _is_unstable(self, recent: List[Dict], older: List[Dict]) -> bool:
        """Check for instability between pattern sets."""
        recent_types = set(p.get("type") for p in recent)
        older_types = set(p.get("type") for p in older)

        # High variance if sets are completely different
        return len(recent_types.intersection(older_types)) == 0

    def get_stats(self) -> Dict[str, Any]:
        """Get detection statistics."""
        return {
            "anomaly_count": self.anomaly_count,
            "metrics_tracked": list(self.metrics_history.keys()),
            "pattern_history_size": len(self.pattern_history)
        }


class SecurityError(Exception):
    """Security-related error."""
    pass


class CircuitBreakerOpen(Exception):
    """Circuit breaker is open."""
    pass