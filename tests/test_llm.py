from types import SimpleNamespace
from typing import Any

import pytest

from tradingagents import llm as llm_module


@pytest.mark.parametrize(
    ("provider", "effort", "expected"),
    [
        ("anthropic", "max", {"effort": "max"}),
        ("openai", "max", {"reasoning_effort": "xhigh"}),
        ("openai", "medium", {"reasoning_effort": "medium"}),
        ("ionos", "max", {"reasoning_effort": "xhigh"}),
        ("ionos", "medium", {"reasoning_effort": "medium"}),
        ("google_genai", "xhigh", {"thinking_level": "high"}),
        ("google_genai", "low", {"thinking_level": "low"}),
        ("ollama", "high", {}),
    ],
)
def test_apply_reasoning_maps_unified_effort_to_provider_kwargs(
    provider: llm_module.LLMProvider, effort: llm_module.ReasoningEffort, expected: dict[str, str]
) -> None:
    kwargs: dict[str, Any] = {}

    llm_module._apply_reasoning(provider, effort, kwargs)

    assert kwargs == expected


def test_build_chat_model_passes_callbacks_and_reasoning_to_init_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    fake_model = SimpleNamespace(name="fake")
    callback = object()

    def fake_init_chat_model(model: str, **kwargs: Any) -> SimpleNamespace:  # noqa: ANN401
        calls.append({"model": model, "kwargs": kwargs})
        return fake_model

    monkeypatch.setattr(llm_module, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(llm_module, "init_chat_model", fake_init_chat_model)

    result = llm_module.build_chat_model(
        "openai", "gpt-offline", reasoning_effort="max", callbacks=[callback]
    )

    assert result is fake_model
    assert calls == [
        {
            "model": "gpt-offline",
            "kwargs": {
                "model_provider": "openai",
                "callbacks": [callback],
                "reasoning_effort": "xhigh",
            },
        }
    ]


def test_build_chat_model_remaps_ionos_to_openai_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    fake_model = SimpleNamespace(name="fake")

    def fake_init_chat_model(model: str, **kwargs: Any) -> SimpleNamespace:  # noqa: ANN401
        calls.append({"model": model, "kwargs": kwargs})
        return fake_model

    monkeypatch.setenv("IONOS_API_KEY", "ionos-key")
    monkeypatch.delenv("IONOS_API_TOKEN", raising=False)
    monkeypatch.delenv("IONOS_API_BASE_URL", raising=False)
    monkeypatch.setattr(llm_module, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(llm_module, "init_chat_model", fake_init_chat_model)

    result = llm_module.build_chat_model("ionos", "qwen3-235b", reasoning_effort="max")

    assert result is fake_model
    assert calls == [
        {
            "model": "qwen3-235b",
            "kwargs": {
                "model_provider": "openai",
                "reasoning_effort": "xhigh",
                "base_url": "https://openai.inference.de-txl.ionos.com/v1",
                "api_key": "ionos-key",
            },
        }
    ]


def test_build_chat_model_ionos_uses_token_and_custom_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    fake_model = SimpleNamespace(name="fake")

    def fake_init_chat_model(model: str, **kwargs: Any) -> SimpleNamespace:  # noqa: ANN401
        calls.append({"model": model, "kwargs": kwargs})
        return fake_model

    monkeypatch.delenv("IONOS_API_KEY", raising=False)
    monkeypatch.setenv("IONOS_API_TOKEN", "ionos-token")
    monkeypatch.setenv("IONOS_API_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setattr(llm_module, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(llm_module, "init_chat_model", fake_init_chat_model)

    result = llm_module.build_chat_model("ionos", "llama3")

    assert result is fake_model
    assert calls == [
        {
            "model": "llama3",
            "kwargs": {
                "model_provider": "openai",
                "base_url": "https://example.invalid/v1",
                "api_key": "ionos-token",
            },
        }
    ]


def test_build_chat_model_ionos_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IONOS_API_KEY", raising=False)
    monkeypatch.delenv("IONOS_API_TOKEN", raising=False)
    monkeypatch.setattr(llm_module, "load_dotenv_if_present", lambda: None)

    with pytest.raises(ValueError, match="IONOS_API_KEY or IONOS_API_TOKEN"):
        llm_module.build_chat_model("ionos", "qwen3-235b")


def test_build_chat_model_routes_gemini_names_to_normalized_google_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[dict[str, Any]] = []
    callback = object()

    class FakeNormalizedGoogle:
        def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
            constructed.append(kwargs)

    def forbidden_init_chat_model(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        raise AssertionError("gemini models must not call init_chat_model")

    monkeypatch.setattr(llm_module, "load_dotenv_if_present", lambda: None)
    monkeypatch.setattr(llm_module, "NormalizedChatGoogleGenerativeAI", FakeNormalizedGoogle)
    monkeypatch.setattr(llm_module, "init_chat_model", forbidden_init_chat_model)

    result = llm_module.build_chat_model(
        "google_genai", "gemini-3.1-pro-preview", reasoning_effort="max", callbacks=[callback]
    )

    assert isinstance(result, FakeNormalizedGoogle)
    assert constructed == [
        {"model": "gemini-3.1-pro-preview", "callbacks": [callback], "thinking_level": "high"}
    ]
