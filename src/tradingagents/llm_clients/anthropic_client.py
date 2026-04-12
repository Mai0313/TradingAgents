from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient

# Extended thinking token budgets per unified reasoning effort level.
# Anthropic requires budget_tokens >= 1024 and max_tokens > budget_tokens.
_THINKING_BUDGET_TOKENS: dict[str, int] = {
    "low": 2000,
    "medium": 8000,
    "high": 16000,
    "max": 32000,
}


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, **kwargs: object) -> None:
        super().__init__(model, **kwargs)

    def get_llm(self) -> ChatAnthropic:
        """Return configured ChatAnthropic instance."""
        llm_kwargs: dict[str, object] = {"model": self.model}

        for key in ("timeout", "max_retries", "api_key", "max_tokens", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        reasoning_effort = self.kwargs.get("reasoning_effort")
        if reasoning_effort:
            budget = _THINKING_BUDGET_TOKENS.get(str(reasoning_effort).lower())
            if budget is not None:
                llm_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
                # Anthropic requires max_tokens > budget_tokens. Bump if too low.
                current_max = llm_kwargs.get("max_tokens")
                if not isinstance(current_max, int) or current_max <= budget:
                    llm_kwargs["max_tokens"] = budget + 4096

        return ChatAnthropic(**llm_kwargs)
