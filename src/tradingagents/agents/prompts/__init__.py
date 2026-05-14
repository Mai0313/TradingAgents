from pathlib import Path

from tradingagents.config import get_config

_PROMPT_DIR = Path(__file__).parent

# Standardised notice that the downstream signal extractor regex-matches
# BUY / SELL / HOLD tokens in English. Three prompts (risk_manager,
# research_manager, trader_system) used to embed almost-identical
# variations of this sentence; centralising it removes drift risk.
_CANONICAL_SIGNAL_NOTICE = (
    "Keep `BUY`, `SELL`, or `HOLD` in English even when the rest of your "
    "response is in another language — downstream tooling regex-matches "
    "these tokens."
)
_CANONICAL_SIGNAL_MARKER = "{{require_canonical_signal}}"


def _response_language() -> str:
    """Get the preferred response language from the configuration.

    Returns:
        str: The response language BCP 47 tag, defaults to "en-US" if
        configuration is unavailable.
    """
    try:
        return get_config().response_language
    except RuntimeError:
        return "en-US"


def _language_instruction() -> str:
    """Generate the language instruction string to append to prompts.

    Returns:
        str: The language instruction string to be appended to prompts.
    """
    language = _response_language().strip() or "en-US"
    language = language.replace("{", "{{").replace("}", "}}")
    return f"\n\nPlease respond in {language}."


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory.

    Returns the raw string with ``{placeholder}`` markers so callers can
    fill values via ``str.format()`` or pass it directly to
    ``ChatPromptTemplate``. Two pre-format substitutions happen here:

    - ``{{require_canonical_signal}}`` (opt-in marker) is replaced with
      the centralised BUY/SELL/HOLD-in-English notice so the wording stays
      consistent across the trader / research-manager / risk-manager prompts.
    - The configured response language is appended as a final line.

    Args:
        name (str): The name of the prompt template file to load (without .md extension).

    Returns:
        str: The loaded prompt template content with language instructions appended.

    Raises:
        FileNotFoundError: If the prompt template file does not exist.
    """
    text = (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    text = text.replace(_CANONICAL_SIGNAL_MARKER, _CANONICAL_SIGNAL_NOTICE)
    return text + _language_instruction()
