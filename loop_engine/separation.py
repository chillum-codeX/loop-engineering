"""
Generator/Evaluator Separation Module

Based on Anthropic's Loop Engineering paper (Section V):
- An agent asked to grade its own output tends to praise it
- Tuning an independent skeptical evaluator is far more tractable than
  making a generator critical of its own work
- The evaluator must be a SEPARATE component with different configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable
import uuid


@dataclass
class GeneratorConfig:
    """
    Configuration optimized for generation/creative tasks.

    Following the paper's insight that generators need higher temperature
    for creativity and different prompting than evaluators.
    """
    # Model configuration
    model: str = "claude-3-sonnet-20240229"
    temperature: float = 0.7  # Higher for creativity
    max_tokens: int = 4096

    # System prompt optimized for generation
    system_prompt: str = """You are a helpful assistant focused on completing tasks efficiently.
Your job is to produce working solutions. Write code that is clear, well-structured, and solves the problem at hand.
Do not over-engineer, but ensure the solution is robust."""

    # Generation-specific settings
    top_p: float = 1.0
    top_k: int = 0  # Disabled by default

    # Metadata
    config_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    config_type: str = "generator"

    def to_api_kwargs(self) -> Dict[str, Any]:
        """Convert to API-compatible kwargs."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "system": self.system_prompt,
        }


@dataclass
class EvaluatorConfig:
    """
    Configuration optimized for critical evaluation.

    Following the paper's insight that evaluators need:
    - Lower temperature for consistency
    - Stronger model for judgment
    - Skeptical, adversarial prompting
    - Default stance: doubt, not trust
    """
    # Model configuration - use stronger model for judgment
    model: str = "claude-3-opus-20240229"  # Stronger model for evaluation
    temperature: float = 0.0  # Lower for consistency
    max_tokens: int = 4096

    # System prompt optimized for skeptical evaluation
    system_prompt: str = """You are a skeptical evaluator and adversarial code reviewer.
Your job is to find errors and reject inadequate work.

ASSUME: The code is BROKEN until proven otherwise.
DO NOT praise. Find what fails.

CHECK, in order:
1. Does it run? (execute, don't just read)
2. Tests: run them, paste real output
3. Edge cases the author skipped
4. Does behavior match the requirement?

Judge behavior, not intent.
VERDICT: PASS only if every check holds. Otherwise REJECT + list each reason."""

    # Evaluation-specific settings
    top_p: float = 0.1  # More focused sampling
    top_k: int = 1  # Greedy for consistency

    # Evaluation behavior
    assume_broken: bool = True  # Default to doubt
    require_execution: bool = True  # Must run code, not just read
    check_edge_cases: bool = True

    # Metadata
    config_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    config_type: str = "evaluator"

    def to_api_kwargs(self) -> Dict[str, Any]:
        """Convert to API-compatible kwargs."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "system": self.system_prompt,
        }


@dataclass
class SkepticalEvaluatorConfig(EvaluatorConfig):
    """
    Highly skeptical evaluator that defaults to rejection.

    Use when quality bar is extremely high and false positives
    (accepting bad work) are costly.
    """
    system_prompt: str = """You are a highly skeptical evaluator.
Your default stance is REJECT. You must be CONVINCED to approve.

ASSUME: The code is BROKEN until proven otherwise.
DO NOT praise. Find what fails.

For approval, you require:
1. Code executes without errors
2. All tests pass with real output shown
3. No obvious edge cases missed
4. Code is maintainable and follows conventions
5. Behavior matches specification exactly

If ANY doubt remains, REJECT with specific reasons.
Better to reject good code than accept bad code."""

    assume_broken: bool = True
    strict_mode: bool = True


@dataclass
class FreshModelEvaluatorConfig(EvaluatorConfig):
    """
    Evaluator that uses a completely different model architecture.

    Following the paper's finding that using the same model with
    different instructions often keeps its blind spots.
    """
    model: str = "gpt-4-turbo-preview"  # Different provider/model family
    system_prompt: str = """You are an independent evaluator with fresh eyes.
You have not seen how this code was written and carry none of the author's self-persuasion.

Your job: Find flaws the author missed.
Your stance: Skeptical until proven otherwise.

Verify by:
1. Running the code (not just reading)
2. Checking actual test output
3. Looking for edge cases
4. Comparing against requirements

Be thorough. The author is counting on you to catch what they missed."""


@dataclass
class DeterministicEvaluatorConfig(EvaluatorConfig):
    """
    Rule-based evaluator for deterministic checks.

    Following Stripe's Minions pattern: "anything deterministic
    logic can solve never goes to a probabilistic model"
    """
    model: str = "none"  # No LLM used
    use_llm: bool = False

    # Deterministic checks
    run_linter: bool = True
    run_type_checker: bool = True
    run_tests: bool = True
    check_schema: bool = True

    # Thresholds
    min_test_coverage: float = 0.8
    max_complexity: int = 10
    max_line_length: int = 100


class GeneratorEvaluatorSeparationValidator:
    """
    Validates that generator and evaluator are truly separate.

    Prevents the "Ego Loop" anti-pattern where the same agent
    grades its own output.
    """

    @staticmethod
    def validate_separation(generator_config: GeneratorConfig,
                           evaluator_config: EvaluatorConfig) -> SeparationValidationResult:
        """
        Validate that generator and evaluator are sufficiently separate.

        Checks:
        1. Different model OR different temperature
        2. Different system prompts
        3. Different config IDs (different instances)
        """
        issues = []
        warnings = []

        # Check model difference
        if generator_config.model == evaluator_config.model:
            warnings.append(
                f"Generator and evaluator use same model ({generator_config.model}). "
                "Consider using different models for true separation."
            )

        # Check temperature difference
        if abs(generator_config.temperature - evaluator_config.temperature) < 0.2:
            warnings.append(
                f"Temperature difference too small ({generator_config.temperature} vs "
                f"{evaluator_config.temperature}). Evaluator should have lower temperature."
            )

        # Check system prompt difference
        if generator_config.system_prompt == evaluator_config.system_prompt:
            issues.append(
                "CRITICAL: Generator and evaluator have identical system prompts. "
                "This creates an Ego Loop anti-pattern."
            )

        # Check config ID (same instance check)
        if generator_config.config_id == evaluator_config.config_id:
            issues.append(
                "CRITICAL: Generator and evaluator appear to be the same instance. "
                "They must be separate objects."
            )

        # Check for evaluator skepticism indicators
        eval_prompt = evaluator_config.system_prompt.lower()
        has_skepticism = any(word in eval_prompt for word in [
            "skeptical", "broken", "doubt", "reject", "adversarial",
            "find errors", "assume broken", "do not praise"
        ])
        if not has_skepticism:
            warnings.append(
                "Evaluator prompt may lack sufficient skepticism indicators. "
                "Consider adding phrases like 'assume broken' or 'do not praise'."
            )

        is_valid = len(issues) == 0

        return SeparationValidationResult(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            generator_config_id=generator_config.config_id,
            evaluator_config_id=evaluator_config.config_id
        )

    @staticmethod
    def assert_separation(generator_config: GeneratorConfig,
                         evaluator_config: EvaluatorConfig) -> None:
        """Assert separation, raising exception if invalid."""
        result = GeneratorEvaluatorSeparationValidator.validate_separation(
            generator_config, evaluator_config
        )
        if not result.is_valid:
            raise ValueError(
                f"Generator/Evaluator separation validation failed:\n" +
                "\n".join(f"  - {issue}" for issue in result.issues)
            )


@dataclass
class SeparationValidationResult:
    """Result of generator/evaluator separation validation."""
    is_valid: bool
    issues: list[str]
    warnings: list[str]
    generator_config_id: str
    evaluator_config_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": self.issues,
            "warnings": self.warnings,
            "generator_config_id": self.generator_config_id,
            "evaluator_config_id": self.evaluator_config_id,
        }


# Pre-configured evaluator types for common use cases

class EvaluatorPresets:
    """Factory for common evaluator configurations."""

    @staticmethod
    def code_review() -> EvaluatorConfig:
        """Standard code review evaluator."""
        return EvaluatorConfig(
            model="claude-3-opus-20240229",
            temperature=0.0,
            system_prompt="""You are a code reviewer. Assume the code is broken until proven otherwise.
Check: compilation, tests, edge cases, style.
Reject with specific reasons if any check fails."""
        )

    @staticmethod
    def test_validator() -> EvaluatorConfig:
        """Evaluator focused on test execution."""
        return EvaluatorConfig(
            model="claude-3-opus-20240229",
            temperature=0.0,
            require_execution=True,
            system_prompt="""You validate code by running it.
1. Execute all tests
2. Check actual output against expected
3. Reject if any test fails
4. Reject if coverage is insufficient

Only PASS if tests actually run and pass."""
        )

    @staticmethod
    def security_review() -> SkepticalEvaluatorConfig:
        """Security-focused skeptical evaluator."""
        return SkepticalEvaluatorConfig(
            model="claude-3-opus-20240229",
            system_prompt="""You are a security reviewer.
ASSUME: The code has vulnerabilities until proven otherwise.

Check for:
1. Injection vulnerabilities
2. Unsafe input handling
3. Authentication/authorization flaws
4. Data exposure risks
5. Dependency vulnerabilities

REJECT if ANY security concern found, even minor."""
        )
