from tradingagents.agents.utils.memory import MemoryMatch, format_memories_for_prompt


def _match(situation: str, recommendation: str, score: float) -> MemoryMatch:
    return MemoryMatch(
        matched_situation=situation, recommendation=recommendation, similarity_score=score
    )


def test_format_memories_returns_sentinel_when_empty() -> None:
    assert format_memories_for_prompt([]) == "(no relevant past situations found.)"


def test_format_memories_emits_situation_recommendation_and_similarity() -> None:
    rendered = format_memories_for_prompt([
        _match("Past situation A details", "Lesson A details", 0.87)
    ])

    assert "Past situation (similarity ≈ 0.87)" in rendered
    assert "Past situation A details" in rendered
    assert "### Lesson learned" in rendered
    assert "Lesson A details" in rendered


def test_format_memories_separates_multiple_blocks() -> None:
    rendered = format_memories_for_prompt([
        _match("Situation A", "Lesson A", 0.91),
        _match("Situation B", "Lesson B", 0.42),
    ])

    assert rendered.count("## Past situation") == 2
    assert "---" in rendered
    assert "Situation A" in rendered
    assert "Situation B" in rendered


def test_format_memories_truncates_long_situation() -> None:
    long_situation = "x" * 5000
    rendered = format_memories_for_prompt(
        [_match(long_situation, "Lesson", 0.5)], max_situation_chars=200
    )

    # The truncated snippet plus ellipsis must replace the original long text.
    assert "xxxxx" in rendered
    assert "…" in rendered
    assert "x" * 5000 not in rendered
