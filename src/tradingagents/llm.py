"""Chat model construction for the TradingAgents framework.

Wraps `langchain.chat_models.init_chat_model` so the project can specify
LLMs via a single `provider:model` string (e.g. `anthropic:claude-sonnet-4-6`,
`google_genai:gemini-3.1-pro-preview`) while still mapping a unified
`reasoning_effort` knob onto each provider's native parameter.

The concrete provider classes are imported explicitly so `ChatModel` is a
visible union of what the project actually supports, instead of leaning on
`BaseChatModel` everywhere.
"""

from typing import Any, Literal, cast

from langchain_xai import ChatXAI
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_litellm import ChatLiteLLM
from langchain_anthropic import ChatAnthropic
from langchain_openrouter import ChatOpenRouter
from langchain_huggingface import ChatHuggingFace
from langchain.chat_models import init_chat_model
from langchain_google_genai import ChatGoogleGenerativeAI

ChatModel = (
    ChatOpenAI
    | ChatAnthropic
    | ChatGoogleGenerativeAI
    | ChatXAI
    | ChatHuggingFace
    | ChatOpenRouter
    | ChatOllama
    | ChatLiteLLM
)

ReasoningEffort = Literal["low", "medium", "high", "max"]

_ANTHROPIC_THINKING_BUDGETS: dict[str, int] = {
    "low": 2000,
    "medium": 8000,
    "high": 16000,
    "max": 32000,
}


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """Flatten Gemini 3 list-content responses to a plain string.

    Gemini 3 returns `message.content` as `[{'type': 'text', 'text': '...'}]`;
    downstream prompt concatenation expects plain strings.
    """

    def invoke(
        self, prompt_input: Any, config: Any = None, **kwargs: Any
    ) -> Any:
        response = super().invoke(prompt_input, config, **kwargs)
        content = response.content
        if isinstance(content, list):
            response.content = "\n".join(
                item["text"]
                if isinstance(item, dict) and item.get("type") == "text"
                else item
                if isinstance(item, str)
                else ""
                for item in content
            ).strip()
        return response


def build_chat_model(
    model_id: str,
    *,
    reasoning_effort: ReasoningEffort | None = None,
    callbacks: list | None = None,
) -> ChatModel:
    """Construct a chat model from a `provider:model` identifier.

    Args:
        model_id: `<provider>:<model>` string, e.g. `anthropic:claude-sonnet-4-6`.
            Provider must match a `langchain.chat_models` registry key
            (openai, anthropic, google_genai, xai, huggingface, openrouter,
            ollama, litellm, ...).
        reasoning_effort: Unified reasoning level mapped per provider:
            Anthropic -> `thinking={'type': 'enabled', 'budget_tokens': N}`,
            OpenAI -> `reasoning_effort` (max -> xhigh),
            Google -> `thinking_level` (max -> high).
            Other providers do not expose a unified knob and ignore this.
        callbacks: Optional LangChain callback handlers attached to the model.
    """
    provider, model = model_id.split(":", 1)
    kwargs: dict[str, Any] = {}
    if callbacks:
        kwargs["callbacks"] = callbacks
    if reasoning_effort:
        _apply_reasoning(provider, reasoning_effort, kwargs)

    if provider == "google_genai":
        return NormalizedChatGoogleGenerativeAI(model=model, **kwargs)

    return cast(ChatModel, init_chat_model(model_id, **kwargs))


def _apply_reasoning(
    provider: str, effort: ReasoningEffort, kwargs: dict[str, Any]
) -> None:
    e = effort.lower()
    if provider == "anthropic":
        budget = _ANTHROPIC_THINKING_BUDGETS[e]
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
        kwargs.setdefault("max_tokens", budget + 4096)
    elif provider in ("openai", "azure_openai"):
        kwargs["reasoning_effort"] = "xhigh" if e == "max" else e
    elif provider == "google_genai":
        kwargs["thinking_level"] = "high" if e == "max" else e
