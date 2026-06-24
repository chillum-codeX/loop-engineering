"""
LLM Client Abstraction

Unified interface for interacting with language models.
Supports multiple backends and provides consistent error handling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM."""
    text: str
    model: str
    tokens_used: int = 0
    cost: float = 0.0
    latency: float = 0.0
    raw_response: Optional[Dict] = None


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate text from prompt."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate structured output."""
        pass


class MockLLMClient(LLMClient):
    """
    Mock LLM client for testing without API calls.

    Returns deterministic responses based on prompt patterns.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.call_count = 0
        self.token_estimate_per_call = 100

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate mock response."""
        self.call_count += 1

        # Simulate latency
        await asyncio.sleep(0.01)

        # Pattern-based responses
        if "plan" in prompt.lower():
            return json.dumps({
                "steps": [
                    {"description": "Analyze the problem", "dependencies": []},
                    {"description": "Break down into subtasks", "dependencies": [0]},
                    {"description": "Execute each subtask", "dependencies": [1]},
                    {"description": "Verify results", "dependencies": [2]}
                ]
            })

        elif "verify" in prompt.lower() or "evaluate" in prompt.lower():
            return json.dumps({
                "score": 0.85,
                "complete": True,
                "feedback": "Task completed successfully"
            })

        elif "calculate" in prompt.lower() or "math" in prompt.lower():
            # Extract numbers and perform simple operations
            import re
            numbers = [int(n) for n in re.findall(r'\d+', prompt)]
            if numbers:
                result = sum(numbers)
                return json.dumps({"result": result})
            return json.dumps({"result": 42})

        else:
            return f"Mock response {self.call_count}: Acknowledged task."

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate mock structured response."""
        text = await self.generate(prompt, model, **kwargs)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Return default based on schema
            return {k: self._default_value(v) for k, v in schema.get("properties", {}).items()}

    def _default_value(self, schema: Dict) -> Any:
        """Generate default value from schema."""
        type_map = {
            "string": "",
            "integer": 0,
            "number": 0.0,
            "boolean": False,
            "array": [],
            "object": {}
        }
        return type_map.get(schema.get("type"), None)


class AnthropicClient(LLMClient):
    """Anthropic Claude client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key required")

        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("anthropic package required. Install with: pip install anthropic")

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate with Claude."""
        model = model or "claude-3-haiku-20240307"
        max_tokens = max_tokens or 1000

        start_time = time.time()

        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )

            latency = time.time() - start_time
            text = response.content[0].text if response.content else ""

            logger.debug(f"Claude response: {len(text)} chars in {latency:.2f}s")
            return text

        except Exception as e:
            logger.error(f"Claude generation failed: {e}")
            raise

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate structured output."""
        # Add schema to prompt
        structured_prompt = f"""{prompt}

Respond with a JSON object matching this schema:
{json.dumps(schema, indent=2)}

Respond with ONLY the JSON object, no other text.
"""
        response = await self.generate(structured_prompt, model, **kwargs)

        # Extract JSON
        try:
            # Try to parse directly
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
                return json.loads(json_str)
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
                return json.loads(json_str)
            else:
                raise ValueError(f"Could not parse JSON from response: {response[:200]}")


class OpenAIClient(LLMClient):
    """OpenAI GPT client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required")

        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate with GPT."""
        model = model or "gpt-3.5-turbo"
        max_tokens = max_tokens or 1000

        start_time = time.time()

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            latency = time.time() - start_time
            text = response.choices[0].message.content or ""

            logger.debug(f"GPT response: {len(text)} chars in {latency:.2f}s")
            return text

        except Exception as e:
            logger.error(f"GPT generation failed: {e}")
            raise

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate structured output using function calling or JSON mode."""
        model = model or "gpt-3.5-turbo"

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                **kwargs
            )

            text = response.choices[0].message.content or ""
            return json.loads(text)

        except Exception as e:
            logger.error(f"Structured generation failed: {e}")
            raise


def create_llm_client(
    provider: str = "mock",
    api_key: Optional[str] = None,
    **kwargs
) -> LLMClient:
    """
    Factory function to create LLM clients.

    Args:
        provider: "mock", "anthropic", or "openai"
        api_key: API key (optional, will use env var if not provided)
        **kwargs: Additional arguments for client

    Returns:
        Configured LLM client
    """
    if provider == "mock":
        return MockLLMClient(**kwargs)
    elif provider == "anthropic":
        return AnthropicClient(api_key=api_key)
    elif provider == "openai":
        return OpenAIClient(api_key=api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")
