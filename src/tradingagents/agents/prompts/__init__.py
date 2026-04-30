from pathlib import Path

from tradingagents.config import get_config

_PROMPT_DIR = Path(__file__).parent


def _response_language() -> str:
    """Get the preferred response language from the configuration.

    Returns:
        str: The response language, defaults to "en" if configuration is unavailable.
    """
    try:
        return get_config().response_language
    except RuntimeError:
        return "en"


def _language_instruction() -> str:
    """Generate the language instruction string to append to prompts.

    Returns:
        str: The language instruction string to be appended to prompts.
    """
    language = _response_language().strip() or "en"
    language = language.replace("{", "{{").replace("}", "}}")
    return f"\n\nPlease respond in {language}."


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory.

    Returns the raw string with ``{placeholder}`` markers so callers can
    fill values via ``str.format()`` or pass it directly to
    ``ChatPromptTemplate``.

    Args:
        name (str): The name of the prompt template file to load (without .md extension).

    Returns:
        str: The loaded prompt template content with language instructions appended.
    """
    return (_PROMPT_DIR / f"{name}.md").read_text() + _language_instruction()
