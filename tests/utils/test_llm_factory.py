import os
import pytest
import asyncio

from typing import Any, Dict

import pytest_asyncio


class DummyClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@pytest_asyncio.fixture(autouse=True)
async def clear_env(monkeypatch):
    # Clear provider selection
    for k in [
        "LLM_PROVIDER",
        # Azure
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_MODEL",
        "AZURE_OPENAI_REASONING_DEPLOYMENT",
        "AZURE_OPENAI_REASONING_MODEL",
        # OpenAI
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_REASONING_MODEL",
        "OPENAI_BASE_URL",
    ]:
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.mark.asyncio
async def test_missing_provider(monkeypatch):
    from peak_assistant.utils import llm_factory
    # Patch placeholders to dummy to avoid real imports side effects
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    with pytest.raises(EnvironmentError):
        await llm_factory.get_model_client("chat")


@pytest.mark.asyncio
async def test_missing_required_envs_azure(monkeypatch):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "azure")
    # Intentionally omit required Azure envs
    with pytest.raises(EnvironmentError):
        await llm_factory.get_model_client("chat")


@pytest.mark.asyncio
async def test_missing_required_envs_openai(monkeypatch):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    # Missing OPENAI_API_KEY and OPENAI_MODEL
    with pytest.raises(EnvironmentError):
        await llm_factory.get_model_client("chat")


@pytest.mark.asyncio
async def test_azure_chat_and_reasoning_fallback(monkeypatch):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    # Set minimal Azure env for chat
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.azure.openai.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "chat-deploy")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-4o")
    # No reasoning env -> should fall back to chat

    chat_client = await llm_factory.get_model_client("chat")
    assert isinstance(chat_client, DummyClient)
    ck = chat_client.kwargs
    assert ck["azure_deployment"] == "chat-deploy"
    assert ck["model"] == "gpt-4o"
    assert ck["azure_endpoint"] == "https://example.azure.openai.com/"
    assert ck["api_version"] == "2025-04-01-preview"
    assert ck["api_key"] == "key"

    reasoning_client = await llm_factory.get_model_client("reasoning")
    rk = reasoning_client.kwargs
    assert rk["azure_deployment"] == "chat-deploy"  # fallback
    assert rk["model"] == "gpt-4o"  # fallback


@pytest.mark.asyncio
async def test_azure_reasoning_explicit(monkeypatch):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.azure.openai.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "chat-deploy")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-4o")
    # Explicit reasoning
    monkeypatch.setenv("AZURE_OPENAI_REASONING_DEPLOYMENT", "reason-deploy")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_MODEL", "o4-mini")

    reasoning_client = await llm_factory.get_model_client("reasoning")
    rk = reasoning_client.kwargs
    assert rk["azure_deployment"] == "reason-deploy"
    assert rk["model"] == "o4-mini"


@pytest.mark.asyncio
async def test_openai_chat_and_reasoning_fallback(monkeypatch):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "okey")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    # No reasoning model -> fallback

    chat_client = await llm_factory.get_model_client("chat")
    ck = chat_client.kwargs
    assert ck["model"] == "gpt-4o-mini"
    assert ck.get("base_url") is None
    assert ck["api_key"] == "okey"

    reasoning_client = await llm_factory.get_model_client("reasoning")
    rk = reasoning_client.kwargs
    assert rk["model"] == "gpt-4o-mini"  # fallback

@pytest.mark.asyncio
async def test_openai_reasoning_explicit(monkeypatch):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "okey")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_REASONING_MODEL", "gpt-4o")

    reasoning_client = await llm_factory.get_model_client("reasoning")
    rk = reasoning_client.kwargs
    assert rk["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_openai_with_base_url(monkeypatch):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "okey")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")

    chat_client = await llm_factory.get_model_client("chat")
    ck = chat_client.kwargs
    assert ck["model"] == "gpt-4o-mini"
    assert ck["base_url"] == "http://localhost:11434/v1"
    assert ck["api_key"] == "okey"


@pytest.mark.asyncio
async def test_openai_with_base_url_and_model_info(monkeypatch, tmp_path):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    import json as _json
    # Single file with TOP-LEVEL mapping: model_id -> ModelInfo
    model_info_map = {
        "local-model": {
            "id": "local-model",
            "family": "gpt-4o-mini",
            "vision": False,
            "audio": False,
            "function_calling": False,
            "json_output": False,
            "structured_output": False,
            "input": {"max_tokens": 131072},
            "output": {"max_tokens": 8192},
        }
    }
    model_info_file = tmp_path / "model_info.json"
    model_info_file.write_text(_json.dumps(model_info_map), encoding="utf-8")

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "okey")
    monkeypatch.setenv("OPENAI_MODEL", "local-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_MODEL_INFO_FILE", str(model_info_file))

    chat_client = await llm_factory.get_model_client("chat")
    ck = chat_client.kwargs
    assert ck["model"] == "local-model"
    assert ck["base_url"] == "http://localhost:11434/v1"
    assert ck["api_key"] == "okey"
    assert ck.get("model_info") == model_info_map["local-model"]


@pytest.mark.asyncio
async def test_openai_reasoning_with_model_info_mapping(monkeypatch, tmp_path):
    from peak_assistant.utils import llm_factory
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)

    import json as _json
    # Single file with TOP-LEVEL mapping including both chat and reasoning entries
    info_map = {
        "chat-model": {
            "id": "chat-model",
            "family": "gpt-4o-mini",
            "vision": False,
            "audio": False,
            "function_calling": False,
            "json_output": False,
            "structured_output": False,
            "input": {"max_tokens": 131072},
            "output": {"max_tokens": 8192},
        },
        "reason-model": {
            "id": "reason-model",
            "family": "gpt-4o-mini",
            "vision": False,
            "audio": False,
            "function_calling": False,
            "json_output": False,
            "structured_output": False,
            "input": {"max_tokens": 131072},
            "output": {"max_tokens": 8192},
        },
    }
    info_file = tmp_path / "models.json"
    info_file.write_text(_json.dumps(info_map), encoding="utf-8")

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "okey")
    monkeypatch.setenv("OPENAI_MODEL", "chat-model")
    monkeypatch.setenv("OPENAI_REASONING_MODEL", "reason-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_MODEL_INFO_FILE", str(info_file))

    chat_client = await llm_factory.get_model_client("chat")
    ck = chat_client.kwargs
    assert ck["model"] == "chat-model"
    assert ck.get("model_info") == info_map["chat-model"]

    reason_client = await llm_factory.get_model_client("reasoning")
    rk = reason_client.kwargs
    assert rk["model"] == "reason-model"
    assert rk.get("model_info") == info_map["reason-model"]
