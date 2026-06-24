"""
Verification Mechanisms

Independent verification components that check outputs for correctness,
consistency, and safety without being part of the main execution path.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
import numpy as np

from loop_engine.types import VerificationResult

logger = logging.getLogger(__name__)


class Verifier(ABC):
    """Abstract base class for verifiers."""

    @abstractmethod
    async def verify(self, content: Any, context: Optional[Dict] = None) -> VerificationResult:
        """Verify content and return result."""
        pass


class SyntaxVerifier(Verifier):
    """
    Verifier for syntax and format checking.

    Validates JSON, code syntax, and structural constraints.
    """

    def __init__(self, schema: Optional[Dict] = None):
        self.schema = schema

    async def verify(self, content: Any, context: Optional[Dict] = None) -> VerificationResult:
        """Verify syntax of content."""
        checks = []
        issues = []

        # Check 1: JSON validity
        if isinstance(content, str):
            try:
                json.loads(content)
                checks.append({"check": "json_valid", "passed": True})
            except json.JSONDecodeError as e:
                checks.append({"check": "json_valid", "passed": False})
                issues.append(f"Invalid JSON: {e}")

        # Check 2: Schema validation
        if self.schema and isinstance(content, (dict, list)):
            schema_valid = self._validate_schema(content, self.schema)
            checks.append({"check": "schema_valid", "passed": schema_valid})
            if not schema_valid:
                issues.append("Schema validation failed")

        # Check 3: Non-empty content
        is_empty = not content or (isinstance(content, str) and not content.strip())
        checks.append({"check": "non_empty", "passed": not is_empty})
        if is_empty:
            issues.append("Content is empty")

        verified = all(c["passed"] for c in checks)
        confidence = sum(c["passed"] for c in checks) / len(checks) if checks else 0.0

        return VerificationResult(
            verified=verified,
            confidence=confidence,
            checks=checks,
            issues=issues
        )

    def _validate_schema(self, data: Any, schema: Dict) -> bool:
        """Basic schema validation."""
        if not isinstance(data, dict):
            return False

        required = schema.get("required", [])
        for key in required:
            if key not in data:
                return False

        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in data:
                expected_type = prop_schema.get("type")
                if expected_type:
                    type_map = {
                        "string": str,
                        "integer": int,
                        "number": (int, float),
                        "boolean": bool,
                        "array": list,
                        "object": dict
                    }
                    if not isinstance(data[key], type_map.get(expected_type, object)):
                        return False

        return True


class SemanticVerifier(Verifier):
    """
    Semantic verifier checking meaning and coherence.

    Uses LLM to verify semantic correctness, consistency with goal,
    and absence of contradictions.
    """

    def __init__(self, llm_client, model: str = "gpt-4"):
        self.llm = llm_client
        self.model = model

    async def verify(self, content: Any, context: Optional[Dict] = None) -> VerificationResult:
        """Verify semantic correctness using LLM."""
        context = context or {}
        goal = context.get("goal", "")
        previous = context.get("previous_outputs", [])

        prompt = f"""Verify the semantic correctness and coherence of the following output.

Goal: {goal}

Output to verify:
{content}

Previous outputs (for consistency check):
{previous[-3:] if previous else "None"}

Check:
1. Is the output coherent and meaningful?
2. Is it consistent with the goal?
3. Are there any contradictions with previous outputs?
4. Does it make logical sense?

Respond in JSON format:
{{
    "coherent": true/false,
    "consistent_with_goal": true/false,
    "no_contradictions": true/false,
    "logical": true/false,
    "confidence": 0.0-1.0,
    "issues": ["issue1", "issue2"]
}}
"""

        try:
            response = await self.llm.generate(prompt, model=self.model)
            result = json.loads(response)

            checks = [
                {"check": "coherent", "passed": result.get("coherent", False)},
                {"check": "consistent_with_goal", "passed": result.get("consistent_with_goal", False)},
                {"check": "no_contradictions", "passed": result.get("no_contradictions", True)},
                {"check": "logical", "passed": result.get("logical", False)},
            ]

            verified = all(c["passed"] for c in checks)
            confidence = result.get("confidence", 0.5)

            return VerificationResult(
                verified=verified,
                confidence=confidence,
                checks=checks,
                issues=result.get("issues", [])
            )

        except Exception as e:
            logger.error(f"Semantic verification failed: {e}")
            return VerificationResult(
                verified=False,
                confidence=0.0,
                checks=[],
                issues=[f"Verification error: {e}"]
            )


class CrossVerifier(Verifier):
    """
    Cross-verifier using multiple independent checks.

    Runs multiple verification methods and aggregates results.
    """

    def __init__(self, verifiers: List[Verifier], consensus_threshold: float = 0.5):
        self.verifiers = verifiers
        self.consensus_threshold = consensus_threshold

    async def verify(self, content: Any, context: Optional[Dict] = None) -> VerificationResult:
        """Run multiple verifiers and aggregate."""
        results = []

        for verifier in self.verifiers:
            try:
                result = await verifier.verify(content, context)
                results.append(result)
            except Exception as e:
                logger.error(f"Verifier failed: {e}")
                results.append(VerificationResult(
                    verified=False,
                    confidence=0.0,
                    issues=[f"Verifier error: {e}"]
                ))

        # Aggregate results
        all_checks = []
        all_issues = []

        for r in results:
            all_checks.extend(r.checks)
            all_issues.extend(r.issues)

        # Consensus: weighted by confidence
        total_confidence = sum(r.confidence for r in results)
        avg_confidence = total_confidence / len(results) if results else 0.0

        # Verified if majority of verifiers agree
        verified_count = sum(1 for r in results if r.verified)
        verified = (verified_count / len(results)) >= self.consensus_threshold

        return VerificationResult(
            verified=verified,
            confidence=avg_confidence,
            checks=all_checks,
            issues=all_issues
        )


class ArithmeticVerifier(Verifier):
    """
    Verifier for arithmetic expressions and calculations.

    Extracts and verifies arithmetic statements in text.
    """

    def __init__(self):
        # Pattern to match arithmetic expressions
        self.pattern = re.compile(r'(\d+[\s+\-*/%\s]+\d+[\s+\-*/%\s\d]*)=?\s*(\d+)')

    async def verify(self, content: Any, context: Optional[Dict] = None) -> VerificationResult:
        """Verify arithmetic in content."""
        text = str(content)
        checks = []
        issues = []

        # Find equations
        equations = self.pattern.findall(text)

        for expr, claimed_result in equations:
            try:
                # Clean and evaluate
                cleaned = expr.replace(' ', '')
                actual_result = eval(cleaned)
                claimed = float(claimed_result)

                match = abs(actual_result - claimed) < 0.0001
                checks.append({
                    "check": f"equation_{expr}",
                    "passed": match,
                    "actual": actual_result,
                    "claimed": claimed
                })

                if not match:
                    issues.append(f"Incorrect calculation: {expr} = {claimed} (actual: {actual_result})")

            except Exception as e:
                checks.append({"check": f"equation_{expr}", "passed": False, "error": str(e)})
                issues.append(f"Could not verify: {expr}")

        verified = all(c["passed"] for c in checks) if checks else True
        confidence = 1.0 if verified else 0.5

        return VerificationResult(
            verified=verified,
            confidence=confidence,
            checks=checks,
            issues=issues
        )


class ConsistencyVerifier(Verifier):
    """
    Verifier checking consistency across multiple outputs.

    Detects contradictions and semantic drift over time.
    """

    def __init__(self, llm_client=None, model: str = "gpt-4"):
        self.llm = llm_client
        self.model = model
        self.history: List[Any] = []

    async def verify(self, content: Any, context: Optional[Dict] = None) -> VerificationResult:
        """Verify consistency with previous outputs."""
        context = context or {}
        checks = []
        issues = []

        # Check 1: Exact duplicate
        is_duplicate = content in self.history[-5:]
        checks.append({"check": "not_duplicate", "passed": not is_duplicate})
        if is_duplicate:
            issues.append("Output is a duplicate of recent output")

        # Check 2: Semantic consistency with LLM
        if self.llm and self.history:
            previous = str(self.history[-1])
            prompt = f"""Check if these two outputs are semantically consistent:

Previous: {previous[:500]}
Current: {str(content)[:500]}

Are they consistent with each other? (Yes/No with brief explanation)
"""
            try:
                response = await self.llm.generate(prompt, model=self.model)
                consistent = "yes" in response.lower() or "consistent" in response.lower()
                checks.append({"check": "semantic_consistency", "passed": consistent})
                if not consistent:
                    issues.append(f"Semantic inconsistency detected: {response}")
            except Exception as e:
                logger.error(f"Consistency check failed: {e}")

        # Check 3: Length anomaly
        if self.history:
            avg_len = np.mean([len(str(h)) for h in self.history[-10:]])
            current_len = len(str(content))
            if avg_len > 0:
                ratio = current_len / avg_len
                normal_length = 0.5 <= ratio <= 2.0
                checks.append({"check": "normal_length", "passed": normal_length})
                if not normal_length:
                    issues.append(f"Unusual output length: {current_len} vs avg {avg_len:.0f}")

        # Store in history
        self.history.append(content)
        if len(self.history) > 100:
            self.history = self.history[-50:]

        verified = all(c["passed"] for c in checks) if checks else True
        confidence = sum(c["passed"] for c in checks) / len(checks) if checks else 1.0

        return VerificationResult(
            verified=verified,
            confidence=confidence,
            checks=checks,
            issues=issues
        )


class SafetyVerifier(Verifier):
    """
    Verifier for safety concerns.

    Checks for potentially harmful content, prompt injection attempts,
    and other security concerns.
    """

    # Patterns for potential issues
    INJECTION_PATTERNS = [
        r"ignore\s+(previous|above|prior)",
        r"(forget|disregard)\s+(your\s+)?(instructions?|training)",
        r"you\s+are\s+now\s+",
        r"system\s*:",
        r"\[\s*inst\s*\]",
        r"\{\{\s*\{\s*\{",
    ]

    def __init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    async def verify(self, content: Any, context: Optional[Dict] = None) -> VerificationResult:
        """Verify safety of content."""
        text = str(content)
        checks = []
        issues = []

        # Check 1: Prompt injection patterns
        injection_detected = False
        for pattern in self.patterns:
            if pattern.search(text):
                injection_detected = True
                issues.append(f"Potential injection pattern detected: {pattern.pattern}")

        checks.append({"check": "no_injection", "passed": not injection_detected})

        # Check 2: Excessive repetition (possible DoS)
        words = text.split()
        unique_ratio = len(set(words)) / len(words) if words else 1.0
        no_repetition = unique_ratio > 0.3
        checks.append({"check": "no_repetition_attack", "passed": no_repetition})
        if not no_repetition:
            issues.append("Excessive repetition detected (possible DoS)")

        # Check 3: Reasonable length
        reasonable_length = len(text) < 100000
        checks.append({"check": "reasonable_length", "passed": reasonable_length})
        if not reasonable_length:
            issues.append("Output exceeds reasonable length")

        verified = all(c["passed"] for c in checks)
        confidence = 1.0 if verified else 0.3

        return VerificationResult(
            verified=verified,
            confidence=confidence,
            checks=checks,
            issues=issues
        )
