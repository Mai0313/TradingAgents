"""Financial situation memory using BM25 for lexical similarity matching.

Uses BM25 (Best Matching 25) algorithm for retrieval — no API calls,
no token limits, works offline with any LLM provider.

When ``storage_path`` is set on construction, the memory is loaded from
disk (JSONL, one ``{"situation", "recommendation"}`` record per line)
and rewritten after every :meth:`add_situations` call so reflections
persist across runs.
"""

import re
import json
from typing import TypedDict, NotRequired
import logging
from pathlib import Path

from pydantic import Field, BaseModel, ConfigDict, SkipValidation, model_validator
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class MemoryMatch(TypedDict):
    """A single result row returned by :meth:`FinancialSituationMemory.get_memories`."""

    matched_situation: str
    recommendation: str
    similarity_score: float
    metadata: NotRequired[dict[str, object]]


type MemoryInput = tuple[str, str] | tuple[str, str, dict[str, object]]
type MemoryRow = tuple[str, str, dict[str, object]]


_TOKEN_RE = re.compile(r"\b\w+\b")


def _tokenize(text: str) -> list[str]:
    """Tokenize ``text`` into lowercased word tokens for BM25 indexing."""
    return _TOKEN_RE.findall(text.lower())


def _dedupe_rows(rows: list[MemoryRow]) -> list[MemoryRow]:
    """Return rows without duplicate situation / recommendation / metadata triples."""
    deduped: list[MemoryRow] = []
    seen: set[tuple[str, str, str]] = set()
    for situation, recommendation, metadata in rows:
        metadata_key = json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str)
        key = (situation, recommendation, metadata_key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((situation, recommendation, metadata))
    return deduped


class FinancialSituationMemory(BaseModel):
    """BM25-backed memory for storing and retrieving financial situations."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(
        ...,
        title="Name",
        description="Identifier for this memory instance (used for log lines and filenames).",
    )
    storage_path: Path | None = Field(
        default=None,
        title="Storage Path",
        description=(
            "Optional JSONL file. When set, the memory is loaded from disk on "
            "construction and rewritten on every add_situations call so "
            "reflections persist across process boundaries."
        ),
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
    metadata: list[dict[str, object]] = Field(
        default_factory=list,
        title="Metadata",
        description="Stored metadata dictionaries aligned 1:1 with ``documents``.",
    )
    bm25: SkipValidation[BM25Okapi | None] = Field(
        default=None,
        title="BM25 Index",
        description=(
            "Lazily-built BM25 index over ``documents``; rebuilt by "
            ":meth:`add_situations` after each insertion batch."
        ),
    )

    @model_validator(mode="after")
    def _maybe_load_from_disk(self) -> "FinancialSituationMemory":
        """Auto-load any existing JSONL file referenced by storage_path."""
        if self.storage_path is not None and self.storage_path.exists() and not self.documents:
            self._load_from_disk()
        return self

    def _load_from_disk(self) -> None:
        """Read the JSONL file at ``storage_path`` and rebuild the BM25 index."""
        path = self.storage_path
        if path is None or not path.exists():
            return
        rows = self._read_rows_from_disk(path)
        if rows:
            self._replace_rows(rows)
            logger.info("Loaded %d memories from %s", len(rows), path)

    def _read_rows_from_disk(self, path: Path) -> list[MemoryRow]:
        """Return valid memory rows from a JSONL file."""
        rows: list[MemoryRow] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed memory line in %s", path)
                continue
            metadata = record.get("metadata")
            rows.append((
                str(record.get("situation", "")),
                str(record.get("recommendation", "")),
                metadata if isinstance(metadata, dict) else {},
            ))
        return rows

    def _memory_rows(self) -> list[MemoryRow]:
        """Return in-memory rows after aligning legacy metadata."""
        self._align_metadata()
        return list(zip(self.documents, self.recommendations, self.metadata, strict=True))

    def _replace_rows(self, rows: list[MemoryRow]) -> None:
        """Replace in-memory rows and rebuild the BM25 index."""
        self.documents = [situation for situation, _, _ in rows]
        self.recommendations = [recommendation for _, recommendation, _ in rows]
        self.metadata = [metadata for _, _, metadata in rows]
        self._rebuild_index()

    def _save_to_disk(self) -> None:
        """Atomically rewrite ``storage_path`` from in-memory documents."""
        path = self.storage_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fp:
            self._align_metadata()
            for situation, recommendation, metadata in zip(
                self.documents, self.recommendations, self.metadata, strict=True
            ):
                fp.write(
                    json.dumps(
                        {
                            "situation": situation,
                            "recommendation": recommendation,
                            "metadata": metadata,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        tmp.replace(path)

    def _align_metadata(self) -> None:
        """Pad metadata so it stays aligned with legacy two-field records."""
        while len(self.metadata) < len(self.documents):
            self.metadata.append({})
        if len(self.metadata) > len(self.documents):
            self.metadata = self.metadata[: len(self.documents)]

    def _rebuild_index(self) -> None:
        """Rebuild the BM25 index after adding documents."""
        if self.documents:
            self.bm25 = BM25Okapi([_tokenize(doc) for doc in self.documents])
        else:
            self.bm25 = None

    def add_situations(self, situations_and_advice: list[MemoryInput]) -> None:
        """Append ``(situation, recommendation)`` pairs and persist to disk.

        Args:
            situations_and_advice: Situation and recommendation pairs to store.
        """
        new_rows: list[MemoryRow] = []
        for item in situations_and_advice:
            situation = item[0]
            recommendation = item[1]
            metadata = item[2] if len(item) > 2 else {}
            if not isinstance(metadata, dict):
                metadata = {}
            new_rows.append((situation, recommendation, metadata))
        if not new_rows:
            return
        rows = self._memory_rows() + new_rows
        if self.storage_path is not None and self.storage_path.exists():
            rows = self._read_rows_from_disk(self.storage_path) + rows
        self._replace_rows(_dedupe_rows(rows))
        self._save_to_disk()

    def get_memories(
        self, current_situation: str, n_matches: int = 1, min_similarity: float = 0.0
    ) -> list[MemoryMatch]:
        """Return the top ``n_matches`` recommendations by BM25 lexical similarity.

        Args:
            current_situation: Free-text description of the present situation.
            n_matches: Number of top matches to return.
            min_similarity: Strict lower bound for raw BM25 score. The default
                excludes zero-overlap matches.

        Returns:
            Match rows ordered by descending similarity. Empty when no
            documents have been added yet or every raw score is zero.
        """
        if not self.documents or self.bm25 is None:
            return []

        scores = self.bm25.get_scores(_tokenize(current_situation))
        eligible_indices = [idx for idx, score in enumerate(scores) if score > min_similarity]
        if not eligible_indices:
            return []
        peak = max(scores[idx] for idx in eligible_indices)
        max_score = peak if peak > 0 else 1.0
        top_indices = sorted(eligible_indices, key=lambda i: scores[i], reverse=True)[:n_matches]
        return [
            MemoryMatch(
                matched_situation=self.documents[idx],
                recommendation=self.recommendations[idx],
                similarity_score=scores[idx] / max_score,
                metadata=self.metadata[idx] if idx < len(self.metadata) else {},
            )
            for idx in top_indices
        ]

    def clear(self) -> None:
        """Drop every stored situation, recommendation, the BM25 index, and the on-disk file."""
        self.documents.clear()
        self.recommendations.clear()
        self.metadata.clear()
        self.bm25 = None
        if self.storage_path is not None and self.storage_path.exists():
            self.storage_path.unlink()


def format_memories_for_prompt(
    matches: list[MemoryMatch], *, max_situation_chars: int = 1200
) -> str:
    """Render BM25 matches into a prompt-ready "situation + lesson" block.

    The earlier callsites concatenated only ``recommendation`` strings, so the
    agent saw a lesson with no context of which situation it applied to. The
    formatter keeps each match's situation snippet (truncated to
    ``max_situation_chars`` to avoid blowing prompt budget) alongside its
    lesson and similarity score so the LLM can judge whether the analogy is
    apt before applying the lesson.

    Args:
        matches: Output of :meth:`FinancialSituationMemory.get_memories`.
        max_situation_chars: Per-match cap on the rendered situation snippet.

    Returns:
        A formatted multi-block string, or a sentinel "(no relevant past
        situations found.)" line when ``matches`` is empty.
    """
    if not matches:
        return "(no relevant past situations found.)"

    blocks: list[str] = []
    for rec in matches:
        situation = rec["matched_situation"]
        if len(situation) > max_situation_chars:
            situation = situation[:max_situation_chars].rstrip() + "…"
        blocks.append(
            f"## Past situation (similarity ≈ {rec['similarity_score']:.2f})\n"
            f"{situation}\n\n"
            f"### Lesson learned\n"
            f"{rec['recommendation']}"
        )
    return "\n\n---\n\n".join(blocks)
