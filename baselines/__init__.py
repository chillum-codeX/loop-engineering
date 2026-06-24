"""Baseline methods for comparison."""

from .one_shot import OneShotBaseline
from .chain_of_thought import ChainOfThoughtBaseline

__all__ = [
    "OneShotBaseline",
    "ChainOfThoughtBaseline",
]
