"""Live integration tests for OpenAI-compatible endpoints (custom base_url) reasoning model."""

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
async def test_openai_reasoning_live_with_base_url():
    """
    Live integration test for OpenAI-compatible endpoints via custom base_url (reasoning model).

    Prerequisites (env):
      - LLM_PROVIDER=openai
      - OPENAI_BASE_URL (e.g., http://localhost:11434/v1)
      - OPENAI_REASONING_MODEL
      - OPENAI_API_KEY (if your server requires it)
      - OPENAI_MODEL_INFO_FILE (required if your reasoning model name is not a valid OpenAI model; file must be a top-level mapping of model_id -> ModelInfo)
    """
    if os.getenv("LLM_PROVIDER") != "openai":
        pytest.skip("Set LLM_PROVIDER=openai for this test")

    base_url = os.getenv("OPENAI_BASE_URL")
    if not base_url:
        pytest.skip("OPENAI_BASE_URL is required for this test")

    if not os.getenv("OPENAI_REASONING_MODEL"):
        pytest.skip("OPENAI_REASONING_MODEL is required for this test")

    # If model name is non-OpenAI, the client will require model_info; we validate presence
    # of the env so developers get an early, helpful skip instead of a runtime ValueError.
    reason_model = os.getenv("OPENAI_REASONING_MODEL", "")
    info_file = os.getenv("OPENAI_MODEL_INFO_FILE")
    if (not reason_model.startswith("gpt-")) and not info_file:
        pytest.skip(
            "Provide OPENAI_MODEL_INFO_FILE (top-level mapping) when using a non-OpenAI reasoning model name"
        )

    client = await get_model_client("reasoning")

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        UserMessage(content="Briefly describe how you approach multi-step reasoning.", source="user"),
    ]

    result = await client.create(messages)
    text = str(result.content).strip()
    assert text, "Expected non-empty response from OpenAI-compatible reasoning completion"
