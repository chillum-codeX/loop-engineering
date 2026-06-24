"""
Memory Systems

Three-tier memory architecture:
- Working Memory: Short-term, limited capacity, immediate context
- Episodic Memory: Event-based storage of past experiences
- Consolidated Memory: Long-term, semantic knowledge extracted from episodes
"""

from __future__ import annotations

import heapq
import json
import logging
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Callable
import numpy as np

from loop_engine.types import MemoryEntry, MemoryType, Observation

logger = logging.getLogger(__name__)


class Memory(ABC):
    """Abstract base class for memory systems."""

    @abstractmethod
    async def add(self, entry: MemoryEntry) -> bool:
        """Add an entry to memory."""
        pass

    @abstractmethod
    async def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        """Retrieve relevant entries."""
        pass

    @abstractmethod
    async def clear(self):
        """Clear all entries."""
        pass


class WorkingMemory(Memory):
    """
    Working memory with limited capacity (7±2 items).

    Implements a sliding window of recent observations and thoughts.
    """

    def __init__(self, capacity: int = 7):
        self.capacity = capacity
        self.entries: deque = deque(maxlen=capacity)
        self.current_context: Dict[str, Any] = {}

    async def add(self, entry: MemoryEntry) -> bool:
        """Add entry to working memory."""
        entry.memory_type = MemoryType.WORKING
        self.entries.append(entry)
        return True

    async def add_observation(self, observation: Observation) -> MemoryEntry:
        """Add an observation directly."""
        entry = MemoryEntry(
            content=observation.content,
            memory_type=MemoryType.WORKING,
            timestamp=observation.timestamp
        )
        await self.add(entry)
        return entry

    async def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        """Retrieve recent entries (LIFO)."""
        entries_list = list(self.entries)
        return entries_list[-k:][::-1]  # Most recent first

    async def get_context(self) -> Dict[str, Any]:
        """Get current working context."""
        return {
            "entries": [
                {"content": e.content, "timestamp": e.timestamp}
                for e in self.entries
            ],
            "context": self.current_context
        }

    async def update_context(self, key: str, value: Any):
        """Update context variable."""
        self.current_context[key] = value

    async def clear(self):
        """Clear working memory."""
        self.entries.clear()
        self.current_context.clear()

    def __len__(self) -> int:
        return len(self.entries)


class EpisodicMemory(Memory):
    """
    Episodic memory storing complete episodes/experiences.

    Stores events with temporal information and supports
    retrieval by recency, importance, and similarity.
    """

    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self.entries: Dict[str, MemoryEntry] = {}
        self.access_log: Dict[str, datetime] = {}

    async def add(self, entry: MemoryEntry) -> bool:
        """Add entry to episodic memory."""
        entry.memory_type = MemoryType.EPISODIC

        # Evict oldest if at capacity
        if len(self.entries) >= self.max_entries:
            oldest_id = min(self.access_log.keys(), key=lambda k: self.access_log[k])
            del self.entries[oldest_id]
            del self.access_log[oldest_id]

        self.entries[entry.id] = entry
        self.access_log[entry.id] = entry.timestamp
        return True

    async def add_episode(
        self,
        content: Any,
        importance: float = 0.5,
        tags: Optional[Set[str]] = None
    ) -> MemoryEntry:
        """Add an episode."""
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.EPISODIC,
            importance=importance,
            tags=tags or set()
        )
        await self.add(entry)
        return entry

    async def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        """Retrieve entries by relevance (simplified)."""
        # Simple retrieval: most important and recent
        scored = []
        for entry in self.entries.values():
            # Score based on importance and recency
            age_hours = (datetime.now() - entry.timestamp).total_seconds() / 3600
            recency_score = np.exp(-age_hours / 24)  # Decay over 24 hours
            score = entry.importance * 0.7 + recency_score * 0.3
            scored.append((score, entry))

        scored.sort(reverse=True)
        return [entry for _, entry in scored[:k]]

    async def retrieve_by_tag(self, tag: str, k: int = 10) -> List[MemoryEntry]:
        """Retrieve entries by tag."""
        matching = [e for e in self.entries.values() if tag in e.tags]
        matching.sort(key=lambda e: e.timestamp, reverse=True)
        return matching[:k]

    async def retrieve_by_time_range(
        self,
        start: datetime,
        end: datetime
    ) -> List[MemoryEntry]:
        """Retrieve entries within time range."""
        matching = [
            e for e in self.entries.values()
            if start <= e.timestamp <= end
        ]
        matching.sort(key=lambda e: e.timestamp)
        return matching

    async def consolidate(self, consolidation_func: Optional[Callable] = None) -> List[MemoryEntry]:
        """
        Consolidate episodic memories into semantic knowledge.

        Returns high-importance memories that should be retained.
        """
        if consolidation_func:
            return consolidation_func(list(self.entries.values()))

        # Default: keep high-importance and frequently accessed
        threshold = np.percentile([e.importance for e in self.entries.values()], 75)
        consolidated = [
            e for e in self.entries.values()
            if e.importance >= threshold or e.access_count >= 3
        ]
        return consolidated

    async def clear(self):
        """Clear episodic memory."""
        self.entries.clear()
        self.access_log.clear()

    def __len__(self) -> int:
        return len(self.entries)


class ConsolidatedMemory(Memory):
    """
    Consolidated long-term memory.

    Stores distilled knowledge extracted from episodic memories.
    Supports semantic search and knowledge retrieval.
    """

    def __init__(self):
        self.knowledge: Dict[str, Any] = {}
        self.facts: List[Dict[str, Any]] = []
        self.embeddings: Dict[str, np.ndarray] = {}

    async def add(self, entry: MemoryEntry) -> bool:
        """Add consolidated knowledge."""
        entry.memory_type = MemoryType.CONSOLIDATED

        if isinstance(entry.content, dict) and "key" in entry.content:
            # Structured knowledge
            self.knowledge[entry.content["key"]] = entry.content.get("value")
        else:
            # Fact storage
            self.facts.append({
                "content": entry.content,
                "timestamp": entry.timestamp,
                "importance": entry.importance
            })

        return True

    async def add_knowledge(self, key: str, value: Any, importance: float = 0.5):
        """Add structured knowledge."""
        entry = MemoryEntry(
            content={"key": key, "value": value},
            memory_type=MemoryType.CONSOLIDATED,
            importance=importance
        )
        await self.add(entry)

    async def add_fact(self, fact: str, importance: float = 0.5):
        """Add a fact."""
        entry = MemoryEntry(
            content=fact,
            memory_type=MemoryType.CONSOLIDATED,
            importance=importance
        )
        await self.add(entry)

    async def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        """Retrieve relevant knowledge."""
        results = []

        # Search in structured knowledge
        for key, value in self.knowledge.items():
            if query.lower() in key.lower() or query.lower() in str(value).lower():
                results.append(MemoryEntry(
                    content={"key": key, "value": value},
                    memory_type=MemoryType.CONSOLIDATED
                ))

        # Search in facts
        for fact in self.facts:
            if query.lower() in str(fact["content"]).lower():
                results.append(MemoryEntry(
                    content=fact["content"],
                    memory_type=MemoryType.CONSOLIDATED,
                    importance=fact["importance"]
                ))

        # Sort by importance
        results.sort(key=lambda e: e.importance, reverse=True)
        return results[:k]

    async def get_knowledge(self, key: str) -> Optional[Any]:
        """Get specific knowledge by key."""
        return self.knowledge.get(key)

    async def query_facts(self, keywords: List[str]) -> List[str]:
        """Query facts by keywords."""
        matching = []
        for fact in self.facts:
            content = str(fact["content"]).lower()
            if any(kw.lower() in content for kw in keywords):
                matching.append(fact["content"])
        return matching

    async def consolidate_from_episodic(
        self,
        episodic_memory: EpisodicMemory,
        strategy: str = "importance"
    ) -> int:
        """
        Consolidate memories from episodic to long-term.

        Args:
            episodic_memory: Source episodic memory
            strategy: Consolidation strategy ("importance", "recency", "all")

        Returns:
            Number of memories consolidated
        """
        episodes = list(episodic_memory.entries.values())

        if strategy == "importance":
            threshold = np.percentile([e.importance for e in episodes], 50)
            to_consolidate = [e for e in episodes if e.importance >= threshold]
        elif strategy == "recency":
            cutoff = datetime.now() - timedelta(hours=24)
            to_consolidate = [e for e in episodes if e.timestamp >= cutoff]
        else:
            to_consolidate = episodes

        # Extract knowledge from episodes
        for episode in to_consolidate:
            # Simple extraction: store important content
            if episode.importance >= 0.7:
                await self.add_fact(
                    str(episode.content),
                    importance=episode.importance
                )

        return len(to_consolidate)

    async def clear(self):
        """Clear consolidated memory."""
        self.knowledge.clear()
        self.facts.clear()
        self.embeddings.clear()

    def __len__(self) -> int:
        return len(self.knowledge) + len(self.facts)


class MultiTierMemory:
    """
    Multi-tier memory system combining working, episodic, and consolidated memory.
    """

    def __init__(
        self,
        working_capacity: int = 7,
        episodic_capacity: int = 1000
    ):
        self.working = WorkingMemory(capacity=working_capacity)
        self.episodic = EpisodicMemory(max_entries=episodic_capacity)
        self.consolidated = ConsolidatedMemory()

    async def observe(self, content: Any, importance: float = 0.5):
        """Process a new observation through all memory tiers."""
        # Add to working memory immediately
        entry = MemoryEntry(content=content, importance=importance)
        await self.working.add(entry)

        # Add to episodic if important enough
        if importance >= 0.3:
            await self.episodic.add_episode(content, importance=importance)

    async def retrieve(
        self,
        query: str,
        k: int = 5,
        tiers: Optional[List[str]] = None
    ) -> Dict[str, List[MemoryEntry]]:
        """
        Retrieve from specified memory tiers.

        Args:
            query: Search query
            k: Number of results per tier
            tiers: List of tiers to search ("working", "episodic", "consolidated")
        """
        tiers = tiers or ["working", "episodic", "consolidated"]
        results = {}

        if "working" in tiers:
            results["working"] = await self.working.retrieve(query, k)
        if "episodic" in tiers:
            results["episodic"] = await self.episodic.retrieve(query, k)
        if "consolidated" in tiers:
            results["consolidated"] = await self.consolidated.retrieve(query, k)

        return results

    async def consolidate(self) -> int:
        """Run consolidation from episodic to consolidated memory."""
        return await self.consolidated.consolidate_from_episodic(self.episodic)

    async def get_full_context(self) -> Dict[str, Any]:
        """Get full memory context."""
        return {
            "working": await self.working.get_context(),
            "episodic_count": len(self.episodic),
            "consolidated_count": len(self.consolidated)
        }

    async def clear_all(self):
        """Clear all memory tiers."""
        await self.working.clear()
        await self.episodic.clear()
        await self.consolidated.clear()
