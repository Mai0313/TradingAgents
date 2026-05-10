"""Financial situation memory using BM25 for lexical similarity matching.

Uses BM25 (Best Matching 25) algorithm for retrieval — no API calls,
no token limits, works offline with any LLM provider.
"""

import re
from typing import TypedDict

from pydantic import Field, BaseModel, ConfigDict, SkipValidation
from rank_bm25 import BM25Okapi


class MemoryMatch(TypedDict):
    """A single result row returned by :meth:`FinancialSituationMemory.get_memories`."""

    matched_situation: str
    recommendation: str
    similarity_score: float


_TOKEN_RE = re.compile(r"\b\w+\b")


def _tokenize(text: str) -> list[str]:
    """Tokenize ``text`` into lowercased word tokens for BM25 indexing."""
    return _TOKEN_RE.findall(text.lower())


class FinancialSituationMemory(BaseModel):
    """BM25-backed memory for storing and retrieving financial situations."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(
        ...,
        title="Name",
        description="Identifier for this memory instance (used for log lines and filenames).",
    )
    documents: list[str] = Field(
        default_factory=list,
        title="Documents",
        description="Stored situation snapshots (one entry per remembered observation).",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        title="Recommendations",
        description="Stored recommendations aligned 1:1 with ``documents``.",
    )
    bm25: SkipValidation[BM25Okapi | None] = Field(
        default=None,
        title="BM25 Index",
        description=(
            "Lazily-built BM25 index over ``documents``; rebuilt by "
            ":meth:`add_situations` after each insertion batch."
        ),
    )

    def _rebuild_index(self) -> None:
        """Rebuild the BM25 index after adding documents."""
        if self.documents:
            self.bm25 = BM25Okapi([_tokenize(doc) for doc in self.documents])
        else:
            self.bm25 = None

    def add_situations(self, situations_and_advice: list[tuple[str, str]]) -> None:
        """Append ``(situation, recommendation)`` pairs and rebuild the BM25 index.

        Args:
            situations_and_advice: Situation and recommendation pairs to store.
        """
        for situation, recommendation in situations_and_advice:
            self.documents.append(situation)
            self.recommendations.append(recommendation)
        self._rebuild_index()

    def get_memories(self, current_situation: str, n_matches: int = 1) -> list[MemoryMatch]:
        """Return the top ``n_matches`` recommendations by BM25 lexical similarity.

        Args:
            current_situation: Free-text description of the present situation.
            n_matches: Number of top matches to return.

        Returns:
            Match rows ordered by descending similarity. Empty when no
            documents have been added yet.
        """
        if not self.documents or self.bm25 is None:
            return []

        scores = self.bm25.get_scores(_tokenize(current_situation))
        peak = max(scores)
        max_score = peak if peak > 0 else 1.0
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_matches]
        return [
            MemoryMatch(
                matched_situation=self.documents[idx],
                recommendation=self.recommendations[idx],
                similarity_score=scores[idx] / max_score,
            )
            for idx in top_indices
        ]

    def clear(self) -> None:
        """Drop every stored situation, recommendation, and the BM25 index."""
        self.documents.clear()
        self.recommendations.clear()
        self.bm25 = None
