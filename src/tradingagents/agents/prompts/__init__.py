from pathlib import Path

from tradingagents.config import get_config

_PROMPT_DIR = Path(__file__).parent


def _response_language() -> str:
    try:
        return get_config().response_language
    except RuntimeError:
        return "en"


def _language_instruction() -> str:
    language = _response_language().strip() or "en"
    language = language.replace("{", "{{").replace("}", "}}")
    return f"\n\nPlease respond in {language}."


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory.

    Returns the raw string with ``{placeholder}`` markers so callers can
    fill values via ``str.format()`` or pass it directly to
    ``ChatPromptTemplate``.
    """
    return (_PROMPT_DIR / f"{name}.md").read_text() + _language_instruction()
