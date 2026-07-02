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
from math import ceil
from typing import Any, Callable, Dict, List, Optional

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


@dataclass(frozen=True)
class UsageRecord:
    """Provider-neutral usage emitted after every successful model call."""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float = 0.0
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class TokenPricing:
    """Explicit model pricing in USD per one million tokens."""
    input_per_million: float
    output_per_million: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million
            + output_tokens * self.output_per_million
        ) / 1_000_000


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self) -> None:
        self.usage_records: List[UsageRecord] = []
        self._usage_callback: Optional[Callable[[UsageRecord], None]] = None

    def set_usage_callback(
        self,
        callback: Optional[Callable[[UsageRecord], None]],
    ) -> None:
        self._usage_callback = callback

    def _record_usage(self, record: UsageRecord) -> None:
        self.usage_records.append(record)
        if self._usage_callback:
            self._usage_callback(record)

    @property
    def total_tokens(self) -> int:
        return sum(record.total_tokens for record in self.usage_records)

    @property
    def total_cost(self) -> float:
        return sum(record.cost for record in self.usage_records)

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
        super().__init__()
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
            text = json.dumps({
                "steps": [
                    {"description": "Analyze the problem", "dependencies": []},
                    {"description": "Break down into subtasks", "dependencies": [0]},
                    {"description": "Execute each subtask", "dependencies": [1]},
                    {"description": "Verify results", "dependencies": [2]}
                ]
            })

        elif "verify" in prompt.lower() or "evaluate" in prompt.lower():
            text = json.dumps({
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
                text = json.dumps({"result": result})
            else:
                text = json.dumps({"result": 42})

        else:
            text = f"Mock response {self.call_count}: Acknowledged task."

        self._record_usage(
            UsageRecord(
                provider="mock",
                model=model or "mock-deterministic",
                input_tokens=ceil(len(prompt) / 4),
                output_tokens=ceil(len(text) / 4),
                estimated=True,
            )
        )
        return text

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

    def __init__(
        self,
        api_key: Optional[str] = None,
        pricing: Optional[TokenPricing] = None,
    ):
        super().__init__()
        self.pricing = pricing
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
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0))
            output_tokens = int(getattr(usage, "output_tokens", 0))
            self._record_usage(
                UsageRecord(
                    provider="anthropic",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=self.pricing.cost(input_tokens, output_tokens)
                    if self.pricing else 0.0,
                )
            )

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

    def __init__(
        self,
        api_key: Optional[str] = None,
        pricing: Optional[TokenPricing] = None,
    ):
        super().__init__()
        self.pricing = pricing
        self.provider_name = "openai"
        self.default_model = "gpt-3.5-turbo"
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
        model = model or self.default_model
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
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0))
            output_tokens = int(getattr(usage, "completion_tokens", 0))
            reported_cost = float(getattr(usage, "cost", 0.0) or 0.0)
            self._record_usage(
                UsageRecord(
                    provider=self.provider_name,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=self.pricing.cost(input_tokens, output_tokens)
                    if self.pricing else reported_cost,
                )
            )

            logger.debug(f"GPT response: {len(text)} chars in {latency:.2f}s")
            return text

        except Exception as e:
            logger.error("%s generation failed: %s", self.provider_name, e)
            raise

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate structured output using JSON mode."""
        model = model or self.default_model
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            **kwargs
        )
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0))
        output_tokens = int(getattr(usage, "completion_tokens", 0))
        reported_cost = float(getattr(usage, "cost", 0.0) or 0.0)
        self._record_usage(
            UsageRecord(
                provider=self.provider_name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=self.pricing.cost(input_tokens, output_tokens)
                if self.pricing else reported_cost,
            )
        )
        return json.loads(text)


class OpenRouterClient(OpenAIClient):
    """OpenRouter adapter using its OpenAI-compatible chat API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: Optional[str] = None,
        pricing: Optional[TokenPricing] = None,
        app_name: str = "Loop Engineering",
        app_url: Optional[str] = None,
    ):
        LLMClient.__init__(self)
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key required")
        self.default_model = model or os.environ.get("OPENROUTER_MODEL")
        if not self.default_model:
            raise ValueError(
                "OpenRouter model required via model= or OPENROUTER_MODEL"
            )
        self.pricing = pricing
        self.provider_name = "openrouter"
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package required for OpenRouter. Install with: pip install openai"
            ) from exc
        headers = {"X-Title": app_name}
        if app_url:
            headers["HTTP-Referer"] = app_url
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=headers,
        )


class ScriptedLLMClient(LLMClient):
    """Deterministic provider for reproducible scenarios and benchmarks."""

    def __init__(
        self,
        responses: List[str],
        *,
        input_tokens_per_call: int = 10,
        output_tokens_per_call: int = 10,
        cost_per_call: float = 0.0,
    ):
        super().__init__()
        if not responses:
            raise ValueError("ScriptedLLMClient requires at least one response")
        self.responses = list(responses)
        self.input_tokens_per_call = input_tokens_per_call
        self.output_tokens_per_call = output_tokens_per_call
        self.cost_per_call = cost_per_call
        self.call_count = 0

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        if self.call_count >= len(self.responses):
            raise RuntimeError("Scripted response sequence exhausted")
        text = self.responses[self.call_count]
        self.call_count += 1
        self._record_usage(
            UsageRecord(
                provider="scripted",
                model=model or "scripted",
                input_tokens=self.input_tokens_per_call,
                output_tokens=self.output_tokens_per_call,
                cost=self.cost_per_call,
            )
        )
        return text

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return json.loads(await self.generate(prompt, model=model, **kwargs))


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
    elif provider == "scripted":
        return ScriptedLLMClient(**kwargs)
    elif provider == "anthropic":
        return AnthropicClient(api_key=api_key, **kwargs)
    elif provider == "openai":
        return OpenAIClient(api_key=api_key, **kwargs)
    elif provider == "openrouter":
        return OpenRouterClient(api_key=api_key, **kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")
