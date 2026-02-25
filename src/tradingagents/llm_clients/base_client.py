from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs: object) -> None:
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    @abstractmethod
    def get_llm(self) -> object:
        """Return the configured LLM instance."""
        raise NotImplementedError

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that the model is supported by this client."""
        raise NotImplementedError
