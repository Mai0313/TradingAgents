"""Shared helpers for the three risk-management debator nodes."""

_FIRST_TURN_SENTINEL = "(no response yet — you are the first speaker on this round)"


def first_turn_or(text: str) -> str:
    """Return ``text`` or an explicit first-speaker sentinel if it is empty.

    Risk-debate prompts splice in peers' previous responses via
    ``{current_*_response}`` placeholders. On the opening turn those values
    are empty strings, and LLMs frequently respond by inventing rebuttals to
    nonexistent prior arguments unless explicitly told the debate has not
    started yet.
    """
    return text or _FIRST_TURN_SENTINEL
