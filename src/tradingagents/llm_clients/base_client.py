from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, **kwargs: object) -> None:
        self.model = model
        self.kwargs = kwargs

    @abstractmethod
    def get_llm(self) -> object:
        """Return the configured LLM instance."""
        raise NotImplementedError
