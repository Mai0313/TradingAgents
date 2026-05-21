"""Small date helpers used by prompt assembly."""

from datetime import date, timedelta


def days_before(date_text: str, days: int) -> str:
    """Return ``date_text - days`` formatted as YYYY-MM-DD."""
    return (date.fromisoformat(date_text) - timedelta(days=days)).isoformat()
