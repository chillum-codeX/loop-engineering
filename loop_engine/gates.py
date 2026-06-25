"""
Deterministic Gates Module

Based on Anthropic's Loop Engineering paper (Section VII.B - Stripe's Minions):
- "Deterministic gates (blue) and LLM steps (green) interlock"
- "Anything rule-bound is kept out of the probabilistic model"
- "Reliability comes from the constraints, not model size"
- "Anything deterministic logic can solve never goes to a probabilistic model"

Gates run BEFORE LLM steps to validate preconditions.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class GateResult:
    """Result of a deterministic gate check."""
    passed: bool
    gate_name: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    severity: str = "error"  # "error", "warning", "info"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "gate_name": self.gate_name,
            "message": self.message,
            "details": self.details,
            "severity": self.severity,
        }


@dataclass
class GateContext:
    """Context for gate execution."""
    work_dir: Path = field(default_factory=lambda: Path("."))
    file_path: Optional[Path] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DeterministicGate(ABC):
    """
    Abstract base class for deterministic gates.

    Gates are hard-coded checks that must pass before LLM involvement.
    They provide reliability through constraints, not model size.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def check(self, context: GateContext) -> GateResult:
        """
        Execute the gate check.

        Returns:
            GateResult with pass/fail status
        """
        pass

    def __call__(self, context: GateContext) -> GateResult:
        """Allow gates to be called as functions."""
        return self.check(context)


class LintGate(DeterministicGate):
    """
    Run linter before accepting code changes.

    Following Stripe's pattern: lint errors block the LLM step.
    """

    def __init__(self, linter: str = "ruff", args: Optional[List[str]] = None):
        super().__init__("lint")
        self.linter = linter
        self.args = args or ["check", "--quiet"]

    def check(self, context: GateContext) -> GateResult:
        """Run linter on the working directory."""
        try:
            result = subprocess.run(
                [self.linter] + self.args,
                cwd=context.work_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return GateResult(
                    passed=True,
                    gate_name=self.name,
                    message=f"{self.linter} passed",
                )
            else:
                return GateResult(
                    passed=False,
                    gate_name=self.name,
                    message=f"{self.linter} found issues",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
        except FileNotFoundError:
            return GateResult(
                passed=True,  # Pass if linter not installed
                gate_name=self.name,
                message=f"{self.linter} not installed, skipping",
                severity="warning",
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message=f"{self.linter} timed out",
            )


class TypeCheckGate(DeterministicGate):
    """Run type checker before accepting code changes."""

    def __init__(self, type_checker: str = "mypy", args: Optional[List[str]] = None):
        super().__init__("type_check")
        self.type_checker = type_checker
        self.args = args or ["--ignore-missing-imports"]

    def check(self, context: GateContext) -> GateResult:
        """Run type checker on the working directory."""
        try:
            result = subprocess.run(
                [self.type_checker] + self.args,
                cwd=context.work_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return GateResult(
                    passed=True,
                    gate_name=self.name,
                    message=f"{self.type_checker} passed",
                )
            else:
                return GateResult(
                    passed=False,
                    gate_name=self.name,
                    message=f"{self.type_checker} found type errors",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
        except FileNotFoundError:
            return GateResult(
                passed=True,
                gate_name=self.name,
                message=f"{self.type_checker} not installed, skipping",
                severity="warning",
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message=f"{self.type_checker} timed out",
            )


class SchemaGate(DeterministicGate):
    """Validate output matches expected schema."""

    def __init__(self, schema: Dict[str, Any]):
        super().__init__("schema")
        self.schema = schema

    def check(self, context: GateContext) -> GateResult:
        """Validate content against schema."""
        if context.content is None:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message="No content to validate",
            )

        try:
            data = json.loads(context.content)
        except json.JSONDecodeError as e:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message=f"Invalid JSON: {e}",
            )

        errors = self._validate_schema(data, self.schema)

        if errors:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message=f"Schema validation failed: {len(errors)} errors",
                details={"errors": errors},
            )

        return GateResult(
            passed=True,
            gate_name=self.name,
            message="Schema validation passed",
        )

    def _validate_schema(self, data: Any, schema: Dict[str, Any], path: str = "") -> List[str]:
        """Recursively validate data against schema."""
        errors = []

        if schema.get("type") == "object" and isinstance(data, dict):
            required = schema.get("required", [])
            for field in required:
                if field not in data:
                    errors.append(f"{path}.{field}: required field missing")

            properties = schema.get("properties", {})
            for field, field_schema in properties.items():
                if field in data:
                    errors.extend(
                        self._validate_schema(data[field], field_schema, f"{path}.{field}")
                    )

        elif schema.get("type") == "array" and isinstance(data, list):
            items_schema = schema.get("items", {})
            for i, item in enumerate(data):
                errors.extend(
                    self._validate_schema(item, items_schema, f"{path}[{i}]")
                )

        elif schema.get("type") == "string" and not isinstance(data, str):
            errors.append(f"{path}: expected string, got {type(data).__name__}")

        elif schema.get("type") == "number" and not isinstance(data, (int, float)):
            errors.append(f"{path}: expected number, got {type(data).__name__}")

        elif schema.get("type") == "boolean" and not isinstance(data, bool):
            errors.append(f"{path}: expected boolean, got {type(data).__name__}")

        return errors


class BudgetGate(DeterministicGate):
    """Check budget before expensive operations."""

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        max_cost: Optional[float] = None,
        current_usage: Optional[Dict[str, Any]] = None,
    ):
        super().__init__("budget")
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self.current_usage = current_usage or {}

    def check(self, context: GateContext) -> GateResult:
        """Check if budget is exceeded."""
        details = {}

        if self.max_tokens:
            used = self.current_usage.get("tokens_used", 0)
            if used >= self.max_tokens:
                return GateResult(
                    passed=False,
                    gate_name=self.name,
                    message=f"Token budget exceeded: {used}/{self.max_tokens}",
                    details={"tokens_used": used, "max_tokens": self.max_tokens},
                )
            details["tokens_remaining"] = self.max_tokens - used

        if self.max_cost:
            used = self.current_usage.get("cost_used", 0.0)
            if used >= self.max_cost:
                return GateResult(
                    passed=False,
                    gate_name=self.name,
                    message=f"Cost budget exceeded: ${used:.2f}/${self.max_cost:.2f}",
                    details={"cost_used": used, "max_cost": self.max_cost},
                )
            details["cost_remaining"] = self.max_cost - used

        return GateResult(
            passed=True,
            gate_name=self.name,
            message="Budget check passed",
            details=details,
        )


class SyntaxGate(DeterministicGate):
    """Validate Python syntax without execution."""

    def __init__(self):
        super().__init__("syntax")

    def check(self, context: GateContext) -> GateResult:
        """Check Python syntax."""
        if context.content is None:
            # Try to read from file
            if context.file_path and context.file_path.exists():
                content = context.file_path.read_text()
            else:
                return GateResult(
                    passed=True,
                    gate_name=self.name,
                    message="No content to check",
                    severity="warning",
                )
        else:
            content = context.content

        try:
            ast.parse(content)
            return GateResult(
                passed=True,
                gate_name=self.name,
                message="Python syntax valid",
            )
        except SyntaxError as e:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message=f"Syntax error: {e.msg} at line {e.lineno}",
                details={
                    "line": e.lineno,
                    "column": e.offset,
                    "text": e.text,
                },
            )


class TestGate(DeterministicGate):
    """Run tests before accepting changes."""

    def __init__(
        self,
        test_command: str = "pytest",
        args: Optional[List[str]] = None,
        min_coverage: Optional[float] = None,
    ):
        super().__init__("test")
        self.test_command = test_command
        self.args = args or ["-xvs", "--tb=short"]
        self.min_coverage = min_coverage

    def check(self, context: GateContext) -> GateResult:
        """Run tests."""
        try:
            cmd = [self.test_command] + self.args
            if self.min_coverage:
                cmd.extend([f"--cov-fail-under={self.min_coverage}"])

            result = subprocess.run(
                cmd,
                cwd=context.work_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                return GateResult(
                    passed=True,
                    gate_name=self.name,
                    message="All tests passed",
                )
            else:
                return GateResult(
                    passed=False,
                    gate_name=self.name,
                    message="Tests failed",
                    details={"stdout": result.stdout[-2000:], "stderr": result.stderr[-1000:]},
                )
        except FileNotFoundError:
            return GateResult(
                passed=True,
                gate_name=self.name,
                message=f"{self.test_command} not installed, skipping",
                severity="warning",
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message="Tests timed out",
            )


class SecurityGate(DeterministicGate):
    """Basic security checks for common vulnerabilities."""

    # Patterns that indicate potential security issues
    DANGEROUS_PATTERNS = [
        (r'eval\s*\(', "Use of eval() detected"),
        (r'exec\s*\(', "Use of exec() detected"),
        (r'subprocess\.call\s*\([^)]*shell\s*=\s*True', "shell=True in subprocess"),
        (r'input\s*\(', "Unvalidated input() call"),
        (r'\.format\s*\([^)]*%', "Potential format string vulnerability"),
        (r'os\.system\s*\(', "Use of os.system() detected"),
        (r'pickle\.loads?\s*\(', "Use of pickle (insecure deserialization)"),
        (r'yaml\.load\s*\([^)]*Loader\s*=\s*yaml\.Loader', "Unsafe YAML loading"),
    ]

    def __init__(self):
        super().__init__("security")

    def check(self, context: GateContext) -> GateResult:
        """Check for common security issues."""
        if context.content is None:
            if context.file_path and context.file_path.exists():
                content = context.file_path.read_text()
            else:
                return GateResult(
                    passed=True,
                    gate_name=self.name,
                    message="No content to check",
                    severity="warning",
                )
        else:
            content = context.content

        issues = []
        for pattern, message in self.DANGEROUS_PATTERNS:
            if re.search(pattern, content):
                issues.append(message)

        if issues:
            return GateResult(
                passed=False,
                gate_name=self.name,
                message=f"Security issues found: {len(issues)}",
                details={"issues": issues},
            )

        return GateResult(
            passed=True,
            gate_name=self.name,
            message="No obvious security issues found",
        )


class GateRunner:
    """
    Runs multiple gates in sequence.

    All gates must pass for the runner to pass.
    """

    def __init__(self, gates: Optional[List[DeterministicGate]] = None):
        self.gates = gates or []

    def add_gate(self, gate: DeterministicGate) -> None:
        """Add a gate to the runner."""
        self.gates.append(gate)

    def run_all(self, context: GateContext) -> GateRunnerResult:
        """Run all gates and return combined result."""
        results = []

        for gate in self.gates:
            result = gate.check(context)
            results.append(result)

            # Stop on first failure (fail-fast)
            if not result.passed and result.severity == "error":
                break

        return GateRunnerResult(
            passed=all(r.passed for r in results),
            results=results,
        )


@dataclass
class GateRunnerResult:
    """Result of running multiple gates."""
    passed: bool
    results: List[GateResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "results": [r.to_dict() for r in self.results],
        }

    @property
    def failed_gates(self) -> List[GateResult]:
        """Get list of failed gates."""
        return [r for r in self.results if not r.passed]


# Pre-configured gate sets

class StandardGates:
    """Standard gate configurations."""

    @staticmethod
    def python_code() -> GateRunner:
        """Standard gates for Python code changes."""
        runner = GateRunner()
        runner.add_gate(SyntaxGate())
        runner.add_gate(LintGate())
        runner.add_gate(SecurityGate())
        return runner

    @staticmethod
    def python_with_tests() -> GateRunner:
        """Gates for Python code with tests."""
        runner = GateRunner()
        runner.add_gate(SyntaxGate())
        runner.add_gate(LintGate())
        runner.add_gate(TypeCheckGate())
        runner.add_gate(TestGate())
        runner.add_gate(SecurityGate())
        return runner

    @staticmethod
    def json_output(schema: Dict[str, Any]) -> GateRunner:
        """Gates for JSON output validation."""
        runner = GateRunner()
        runner.add_gate(SchemaGate(schema))
        return runner

    @staticmethod
    def budget_protected(max_tokens: int, max_cost: float) -> GateRunner:
        """Gates with budget protection."""
        runner = GateRunner()
        runner.add_gate(BudgetGate(max_tokens=max_tokens, max_cost=max_cost))
        return runner
