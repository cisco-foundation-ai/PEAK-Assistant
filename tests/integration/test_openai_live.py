"""Live integration tests for OpenAI provider."""

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
async def test_openai_chat_live():
    """
    Live integration test for OpenAI provider.

    Prerequisites (env):
      - LLM_PROVIDER=openai
      - OPENAI_API_KEY
      - OPENAI_MODEL
    Optional:
      - Ensure OPENAI_BASE_URL is not set (this test targets native OpenAI).
    """
    if os.getenv("LLM_PROVIDER") != "openai":
        pytest.skip("Set LLM_PROVIDER=openai for this test")

    if os.getenv("OPENAI_BASE_URL"):
        pytest.skip("OPENAI_BASE_URL is set; run the base_url test instead")

    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
        pytest.skip("OPENAI_API_KEY and OPENAI_MODEL are required for this test")

    client = await get_model_client("chat")

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        UserMessage(content="Please introduce yourself.", source="user"),
    ]

    result = await client.create(messages)
    text = str(result.content).strip()
    assert text, "Expected non-empty response from OpenAI chat completion"
