from typing import Protocol, cast

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient


class _HasContent(Protocol):
    content: object


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list: [{'type': 'text', 'text': '...'}]
    This normalizes to string for consistent downstream handling.
    """

    def _normalize_content(self, response: object) -> object:
        typed = cast("_HasContent", response)
        content = typed.content
        if isinstance(content, list):
            texts = [
                item.get("text", "")
                if isinstance(item, dict) and item.get("type") == "text"
                else item
                if isinstance(item, str)
                else ""
                for item in content
            ]
            typed.content = "\n".join(t for t in texts if t)
        return response

    def invoke(self, prompt_input: object, config: object = None, **kwargs: object) -> object:
        return self._normalize_content(super().invoke(prompt_input, config, **kwargs))


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, **kwargs: object) -> None:
        super().__init__(model, **kwargs)

    def get_llm(self) -> ChatGoogleGenerativeAI:
        """Return configured ChatGoogleGenerativeAI instance."""
        llm_kwargs: dict[str, object] = {"model": self.model}

        for key in ("timeout", "max_retries", "google_api_key", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        reasoning_effort = self.kwargs.get("reasoning_effort")
        if reasoning_effort:
            effort = str(reasoning_effort).lower()
            model_lower = self.model.lower()
            if "gemini-3" in model_lower:
                if effort == "max":
                    effort = "high"
                # Gemini 3 Pro API does not accept "medium"; clamp to "low".
                if "pro" in model_lower and effort == "medium":
                    effort = "low"
                llm_kwargs["thinking_level"] = effort
            else:
                # Gemini 2.5 only exposes thinking_budget (0=disabled, -1=dynamic)
                llm_kwargs["thinking_budget"] = -1 if effort in ("high", "max") else 0

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)
