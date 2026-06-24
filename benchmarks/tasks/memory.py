"""Memory-intensive benchmark task."""

from typing import Any, Dict, List, Optional

from ..base import BenchmarkResult, BenchmarkTask


class MemoryIntensiveTask(BenchmarkTask):
    """
    Memory-intensive task requiring information consolidation.
    Stress-tests: Memory systems, Consolidation, Long-horizon
    """

    def __init__(self):
        super().__init__(
            task_id="memory_001",
            name="Memory-Intensive Task",
            description="Accumulate and consolidate information over many steps"
        )
        self.difficulty = "hard"
        self.tags = ["memory", "consolidation", "long-horizon"]

        # Story with facts to remember
        self.story_parts = [
            "Alice works at TechCorp as a senior software engineer.",
            "She has a golden retriever named Max who just turned 5 years old.",
            "Her favorite color is deep blue.",
            "She lives in a house in Seattle with a view of Puget Sound.",
            "She graduated from MIT in 2019 with a degree in Computer Science.",
            "Her current project deadline is next Friday at 5 PM.",
            "She promised to call her mom tomorrow evening.",
            "She bought a new Tesla Model 3 last month.",
            "She enjoys hiking on weekends, especially at Mount Rainier.",
            "Her team has 8 members including herself."
        ]

        self.questions = [
            {"question": "What is Alice's job?", "answer": "senior software engineer", "keywords": ["engineer", "software"]},
            {"question": "How old is her dog?", "answer": "5", "keywords": ["5", "five"]},
            {"question": "Where did she graduate?", "answer": "MIT", "keywords": ["mit"]},
            {"question": "What car did she buy?", "answer": "Tesla Model 3", "keywords": ["tesla", "model 3"]},
            {"question": "What is her favorite color?", "answer": "blue", "keywords": ["blue"]},
            {"question": "Where does she live?", "answer": "Seattle", "keywords": ["seattle"]},
            {"question": "When is her project deadline?", "answer": "next Friday", "keywords": ["friday"]},
            {"question": "How many people are on her team?", "answer": "8", "keywords": ["8", "eight"]}
        ]

    def get_input(self) -> Dict[str, Any]:
        return {
            "story_parts": self.story_parts,
            "instruction": "Read and remember the following information. You will be asked questions about it later.",
            "questions": [q["question"] for q in self.questions]
        }

    def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
        """Evaluate memory retention."""
        metadata = metadata or {}
        output_str = str(output).lower()

        # Check answers to questions
        correct_count = 0
        question_results = []

        for q in self.questions:
            question_correct = False
            # Check for exact answer or keywords
            if q["answer"].lower() in output_str:
                question_correct = True
            else:
                for keyword in q["keywords"]:
                    if keyword.lower() in output_str:
                        question_correct = True
                        break

            if question_correct:
                correct_count += 1
            question_results.append({
                "question": q["question"],
                "expected": q["answer"],
                "correct": question_correct
            })

        score = correct_count / len(self.questions)
        success = score >= 0.5  # At least half correct

        return BenchmarkResult(
            task_id=self.task_id,
            success=success,
            score=score,
            execution_time=metadata.get("execution_time", 0.0),
            iterations=metadata.get("iterations", 1),
            token_usage=metadata.get("token_usage", 0),
            cost=metadata.get("cost", 0.0),
            metadata={
                "correct_answers": correct_count,
                "total_questions": len(self.questions),
                "question_results": question_results,
                "memory_consolidated": metadata.get("memory_consolidated", False)
            }
        )

    def get_expected_output(self) -> List[str]:
        return [q["answer"] for q in self.questions]
