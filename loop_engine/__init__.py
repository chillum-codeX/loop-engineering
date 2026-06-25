"""
Loop Engineering Framework

A research-grade framework for constructing reliable iterative AI systems.

This framework transforms language models from one-shot response generators
into reliable systems that repeatedly plan, act, observe, evaluate, recover,
and terminate.

Based on Anthropic's Loop Engineering paper (2026):
- Generator/Evaluator Separation
- SKILL.md System
- Deterministic Gates (Stripe Minions pattern)
- Worktree Isolation
- Budget Caps
- Human Checkpoints
"""

__version__ = "0.4.0"
__author__ = "Loop Engineering Research Project"

from .core import LoopEngine, LoopConfig, LoopState, MultiAgentOrchestrator
from .types import LoopContext, Budget

# Anthropic Loop Engineering: Generator/Evaluator Separation
from .separation import (
    GeneratorConfig,
    EvaluatorConfig,
    SkepticalEvaluatorConfig,
    FreshModelEvaluatorConfig,
    DeterministicEvaluatorConfig,
    GeneratorEvaluatorSeparationValidator,
    EvaluatorPresets,
)

# Anthropic Loop Engineering: SKILL.md System
from .skills import (
    SkillDefinition,
    SkillParser,
    SkillLoader,
    SkillValidator,
    create_example_skills,
)

# Anthropic Loop Engineering: State Persistence
from .persistence import (
    LoopStatePersistence,
    PersistenceConfig,
)

# Anthropic Loop Engineering: Deterministic Gates (Stripe Minions pattern)
from .gates import (
    DeterministicGate,
    GateResult,
    GateContext,
    LintGate,
    TypeCheckGate,
    SchemaGate,
    BudgetGate,
    SyntaxGate,
    TestGate,
    SecurityGate,
    GateRunner,
    StandardGates,
)

# Anthropic Loop Engineering: Worktree Isolation
from .worktree import (
    WorktreeManager,
    Worktree,
    MergeResult,
)

# Anthropic Loop Engineering: Budget Caps
from .budget_caps import (
    BudgetCaps,
    Usage,
    BudgetTracker,
    BudgetPresets,
)

# Anthropic Loop Engineering: Human Checkpoints
from .checkpoint import (
    HumanCheckpoint,
    CheckpointConfig,
    ReviewRequest,
    ReviewResponse,
    HumanDecision,
    CheckpointPresets,
)

__all__ = [
    # Core
    "LoopEngine",
    "LoopConfig",
    "LoopState",
    "MultiAgentOrchestrator",
    "LoopContext",
    "Budget",

    # Generator/Evaluator Separation
    "GeneratorConfig",
    "EvaluatorConfig",
    "SkepticalEvaluatorConfig",
    "FreshModelEvaluatorConfig",
    "DeterministicEvaluatorConfig",
    "GeneratorEvaluatorSeparationValidator",
    "EvaluatorPresets",

    # SKILL.md System
    "SkillDefinition",
    "SkillParser",
    "SkillLoader",
    "SkillValidator",
    "create_example_skills",

    # State Persistence
    "LoopStatePersistence",
    "PersistenceConfig",

    # Deterministic Gates
    "DeterministicGate",
    "GateResult",
    "GateContext",
    "LintGate",
    "TypeCheckGate",
    "SchemaGate",
    "BudgetGate",
    "SyntaxGate",
    "TestGate",
    "SecurityGate",
    "GateRunner",
    "StandardGates",

    # Worktree Isolation
    "WorktreeManager",
    "Worktree",
    "MergeResult",

    # Budget Caps
    "BudgetCaps",
    "Usage",
    "BudgetTracker",
    "BudgetPresets",

    # Human Checkpoints
    "HumanCheckpoint",
    "CheckpointConfig",
    "ReviewRequest",
    "ReviewResponse",
    "HumanDecision",
    "CheckpointPresets",
]
