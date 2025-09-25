"""Live integration tests for Azure OpenAI reasoning model."""

import os
import pytest

from autogen_core.models import UserMessage, SystemMessage
from peak_assistant.utils.llm_factory import get_model_client
from peak_assistant.utils import load_env_defaults


@pytest.fixture(autouse=True)
def _load_env_defaults():
    # Ensure .env is loaded (searching up the directory tree) before each test
    load_env_defaults()


@pytest.mark.live
@pytest.mark.asyncio
async def test_azure_reasoning_live():
    """
    Live integration test for Azure OpenAI reasoning model.

    Prerequisites (env):
      - LLM_PROVIDER=azure
      - AZURE_OPENAI_API_KEY
      - AZURE_OPENAI_ENDPOINT
      - AZURE_OPENAI_API_VERSION
      - AZURE_OPENAI_REASONING_DEPLOYMENT
      - AZURE_OPENAI_REASONING_MODEL
    """
    if os.getenv("LLM_PROVIDER") != "azure":
        pytest.skip("Set LLM_PROVIDER=azure for this test")

    required = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_REASONING_DEPLOYMENT",
        "AZURE_OPENAI_REASONING_MODEL",
    ]
    if any(not os.getenv(k) for k in required):
        pytest.skip("Azure reasoning environment variables are required for this test")

    client = await get_model_client("reasoning")

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        UserMessage(content="Please briefly describe your reasoning capabilities.", source="user"),
    ]

    result = await client.create(messages)
    text = str(result.content).strip()
    assert text, "Expected non-empty response from Azure OpenAI reasoning completion"
