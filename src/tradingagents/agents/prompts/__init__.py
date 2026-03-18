from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory.

    Returns the raw string with ``{placeholder}`` markers so callers can
    fill values via ``str.format()`` or pass it directly to
    ``ChatPromptTemplate``.
    """
    return (_PROMPT_DIR / f"{name}.md").read_text()
