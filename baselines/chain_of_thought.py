"""
Chain-of-thought baseline - adds reasoning steps without iteration.
"""

from typing import Any, Dict
import time

from benchmarks.base import BenchmarkResult
from loop_engine.llm_client import LLMClient


class ChainOfThoughtBaseline:
    """Chain-of-thought prompting baseline."""

    def __init__(self, llm_client: LLMClient, model: str = "gpt-3.5-turbo"):
        self.llm = llm_client
        self.model = model

    async def solve(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Solve task with chain-of-thought prompting."""
        start_time = time.time()

        # Extract task info
        if "question" in task_input:
            base_prompt = task_input["question"]
        elif "problem" in task_input:
            base_prompt = task_input["problem"]
        elif "goal" in task_input:
            base_prompt = task_input["goal"]
        else:
            base_prompt = str(task_input)

        # Add CoT instruction
        prompt = f"""{base_prompt}

Think through this step by step. Show your reasoning process clearly.
"""

        if "constraints" in task_input:
            prompt += f"\n\nConstraints: {task_input['constraints']}"

        try:
            response = await self.llm.generate(prompt, model=self.model)
            execution_time = time.time() - start_time

            return {
                "output": response,
                "execution_time": execution_time,
                "iterations": 1,
                "token_usage": len(prompt) + len(response),  # Approximation
                "success": True
            }
        except Exception as e:
            return {
                "output": str(e),
                "execution_time": time.time() - start_time,
                "iterations": 1,
                "token_usage": len(prompt),
                "success": False,
                "error": str(e)
            }
