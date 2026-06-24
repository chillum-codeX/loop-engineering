"""
Loop Engineering Framework

A research-grade framework for constructing reliable iterative AI systems.

This framework transforms language models from one-shot response generators
into reliable systems that repeatedly plan, act, observe, evaluate, recover,
and terminate.
"""

__version__ = "0.1.0"
__author__ = "Loop Engineering Research Project"

from .core import LoopEngine, LoopConfig, LoopState
from .types import LoopContext, Budget
from .components import (
    Planner, Actor, Observer, Evaluator, Recovery, Terminator,
    LLMPlanner, LLMActor, SimpleObserver, LLMEvaluator, AdaptiveRecovery, CombinedTerminator
)
from .memory import WorkingMemory, EpisodicMemory, ConsolidatedMemory, MultiTierMemory
from .verification import Verifier, CrossVerifier, SemanticVerifier
from .budget import BudgetManager, TokenBudget, StepBudget, TimeBudget
from .safety import SafetyMonitor, Sandbox, CircuitBreaker
from .llm_client import create_llm_client

__all__ = [
    "LoopEngine",
    "LoopConfig",
    "LoopState",
    "Planner",
    "Actor",
    "Observer",
    "Evaluator",
    "Recovery",
    "Terminator",
    "WorkingMemory",
    "EpisodicMemory",
    "ConsolidatedMemory",
    "Verifier",
    "CrossVerifier",
    "SemanticVerifier",
    "BudgetManager",
    "TokenBudget",
    "StepBudget",
    "TimeBudget",
    "SafetyMonitor",
    "Sandbox",
    "CircuitBreaker",
]
