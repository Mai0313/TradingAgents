from .base_client import BaseLLMClient
from .google_client import GoogleClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient


def create_llm_client(provider: str, model: str, **kwargs: object) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: LLM provider (openai, anthropic, google, xai, ollama, openrouter)
        model: Model name/identifier
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    if provider_lower in ("openai", "ollama", "openrouter", "xai"):
        return OpenAIClient(model, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        return AnthropicClient(model, **kwargs)

    if provider_lower == "google":
        return GoogleClient(model, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
