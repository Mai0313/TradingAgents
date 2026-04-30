"""Chat model construction for the TradingAgents framework.

Wraps `langchain.chat_models.init_chat_model` so the project can specify
LLMs via an explicit `provider` (one of `LLMProvider`) plus a model name
(e.g. `gpt-5.4`, `claude-sonnet-4-6`, `gemini-3.1-pro-preview`) while still
mapping a unified `reasoning_effort` knob onto each provider's native
parameter.

The concrete provider classes are imported explicitly so `ChatModel` is a
visible union of what the project actually supports, instead of leaning on
`BaseChatModel` everywhere.
"""

from typing import Any, Literal, cast

from langchain_xai import ChatXAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_litellm import ChatLiteLLM
from langchain_anthropic import ChatAnthropic
from langchain_openrouter import ChatOpenRouter
from langchain.chat_models import init_chat_model
from langchain_huggingface import ChatHuggingFace
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.callbacks import BaseCallbackHandler

type ChatModel = (
    ChatOpenAI
    | ChatAnthropic
    | ChatGoogleGenerativeAI
    | ChatXAI
    | ChatHuggingFace
    | ChatOpenRouter
    | ChatOllama
    | ChatLiteLLM
)

LLMProvider = Literal[
    "openai", "anthropic", "google_genai", "xai", "huggingface", "openrouter", "ollama", "litellm"
]

ReasoningEffort = Literal["low", "medium", "high", "xhigh", "max"]


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """Flatten Gemini 3 list-content responses to a plain string.

    Gemini 3 returns `message.content` as `[{'type': 'text', 'text': '...'}]`;
    downstream prompt concatenation expects plain strings.
    """

    def invoke(self, prompt_input: object, config: object = None, **kwargs: object) -> object:
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
    provider: LLMProvider,
    model: str,
    *,
    reasoning_effort: ReasoningEffort | None = None,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> ChatModel:
    """Construct a chat model from an explicit provider + model name.

    Args:
        provider: Langchain `init_chat_model` registry key (one of `LLMProvider`).
        model: Model name as accepted by the provider (e.g. `gpt-5.4`,
            `claude-sonnet-4-6`, `gemini-3.1-pro-preview`). Any model name
            containing `gemini` or `google` is routed through
            `NormalizedChatGoogleGenerativeAI` regardless of provider.
        reasoning_effort: Unified reasoning level mapped per provider:
            Anthropic -> `effort` (native low/medium/high/xhigh/max),
            OpenAI -> `reasoning_effort` (max -> xhigh; xhigh native),
            Google -> `thinking_level` (xhigh and max both clamped to high).
            Other providers do not expose a unified knob and ignore this.
        callbacks: Optional LangChain callback handlers attached to the model.
    """
    kwargs: dict[str, Any] = {}
    if callbacks:
        kwargs["callbacks"] = callbacks
    if reasoning_effort:
        _apply_reasoning(provider, reasoning_effort, kwargs)

    model_lower = model.lower()
    if "gemini" in model_lower or "google" in model_lower:
        return NormalizedChatGoogleGenerativeAI(model=model, **kwargs)

    return cast("ChatModel", init_chat_model(model, model_provider=provider, **kwargs))


def _apply_reasoning(
    provider: LLMProvider, effort: ReasoningEffort, kwargs: dict[str, Any]
) -> None:
    e = effort.lower()
    if provider == "anthropic":
        kwargs["effort"] = e
    elif provider == "openai":
        kwargs["reasoning_effort"] = "xhigh" if e == "max" else e
    elif provider == "google_genai":
        kwargs["thinking_level"] = "high" if e in ("xhigh", "max") else e
