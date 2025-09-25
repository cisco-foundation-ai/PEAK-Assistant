"""Live integration tests for OpenAI-compatible endpoints (custom base_url)."""

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
async def test_openai_chat_live_with_base_url():
    """
    Live integration test for OpenAI-compatible endpoints via custom base_url.

    Prerequisites (env):
      - LLM_PROVIDER=openai
      - OPENAI_API_KEY (some servers accept any string; set if required)
      - OPENAI_MODEL (must exist on the target server)
      - OPENAI_BASE_URL (e.g., http://localhost:11434/v1)
    """
    if os.getenv("LLM_PROVIDER") != "openai":
        pytest.skip("Set LLM_PROVIDER=openai for this test")

    base_url = os.getenv("OPENAI_BASE_URL")
    if not base_url:
        pytest.skip("OPENAI_BASE_URL is required for this test")

    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
        pytest.skip("OPENAI_API_KEY and OPENAI_MODEL are required for this test")

    client = await get_model_client("chat")

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        UserMessage(content="Please introduce yourself.", source="user"),
    ]

    result = await client.create(messages)
    text = str(result.content).strip()
    assert text, "Expected non-empty response from OpenAI-compatible chat completion"
