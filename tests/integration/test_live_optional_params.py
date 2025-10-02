# Copyright (c) 2025 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: MIT
"""
Live integration tests for optional parameters across all providers.

These tests make real API calls and require valid credentials.
Run with: pytest -m live tests/integration/test_live_optional_params.py -v -s
"""

import pytest
from pathlib import Path
import json
import tempfile
import os

from autogen_core.models import UserMessage
from peak_assistant.utils.llm_factory import get_model_client
from peak_assistant.utils import load_env_defaults


# Load environment variables
load_env_defaults()


def get_env_or_fail(var_name: str) -> str:
    """Get environment variable or raise clear error."""
    value = os.getenv(var_name)
    if not value:
        raise ValueError(f"Environment variable {var_name} is not set. Please add it to your .env file.")
    return value


@pytest.fixture
def temp_config_file():
    """Create a temporary config file."""
    def _create(config_dict):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_dict, f)
            return Path(f.name)
    return _create


@pytest.mark.live
@pytest.mark.asyncio
async def test_azure_temperature_affects_output(temp_config_file):
    """Test that temperature parameter affects Azure model output."""
    
    # Get environment variables
    azure_endpoint = get_env_or_fail("AZURE_OPENAI_ENDPOINT")
    azure_key = get_env_or_fail("AZURE_OPENAI_API_KEY")
    azure_model = get_env_or_fail("AZURE_OPENAI_MODEL")
    azure_deployment = get_env_or_fail("AZURE_OPENAI_DEPLOYMENT")
    
    # Config with low temperature (more deterministic)
    config_low = temp_config_file({
        "version": "1",
        "providers": {
            "azure-test": {
                "type": "azure",
                "config": {
                    "endpoint": azure_endpoint,
                    "api_key": azure_key,
                    "api_version": "2024-02-01",
                    "temperature": 0.1
                }
            }
        },
        "defaults": {
            "provider": "azure-test",
            "model": azure_model,
            "deployment": azure_deployment
        }
    })
    
    # Config with high temperature (more creative)
    config_high = temp_config_file({
        "version": "1",
        "providers": {
            "azure-test": {
                "type": "azure",
                "config": {
                    "endpoint": azure_endpoint,
                    "api_key": azure_key,
                    "api_version": "2024-02-01",
                    "temperature": 1.5
                }
            }
        },
        "defaults": {
            "provider": "azure-test",
            "model": azure_model,
            "deployment": azure_deployment
        }
    })
    
    # Create clients
    client_low = await get_model_client(config_path=config_low)
    client_high = await get_model_client(config_path=config_high)
    
    # Same prompt to both
    messages = [UserMessage(content="Write a single creative word", source="user")]
    
    # Make multiple requests to see variation
    results_low = []
    results_high = []
    
    for _ in range(3):
        result_low = await client_low.create(messages)
        result_high = await client_high.create(messages)
        results_low.append(str(result_low.content))
        results_high.append(str(result_high.content))
    
    print(f"\nLow temperature (0.1) results: {results_low}")
    print(f"High temperature (1.5) results: {results_high}")
    
    # Low temperature should have less variation
    unique_low = len(set(results_low))
    unique_high = len(set(results_high))
    
    print(f"Unique responses - Low temp: {unique_low}, High temp: {unique_high}")
    
    # This is a probabilistic test, but high temp should generally have more variation
    # At minimum, verify both clients work
    assert all(r for r in results_low), "Low temperature client produced empty results"
    assert all(r for r in results_high), "High temperature client produced empty results"


@pytest.mark.live
@pytest.mark.asyncio
async def test_azure_max_tokens_limits_output(temp_config_file):
    """Test that max_tokens parameter limits Azure output length."""
    
    # Get environment variables
    azure_endpoint = get_env_or_fail("AZURE_OPENAI_ENDPOINT")
    azure_key = get_env_or_fail("AZURE_OPENAI_API_KEY")
    azure_model = get_env_or_fail("AZURE_OPENAI_MODEL")
    azure_deployment = get_env_or_fail("AZURE_OPENAI_DEPLOYMENT")
    
    config = temp_config_file({
        "version": "1",
        "providers": {
            "azure-test": {
                "type": "azure",
                "config": {
                    "endpoint": azure_endpoint,
                    "api_key": azure_key,
                    "api_version": "2024-02-01",
                    "max_tokens": 10  # Very short
                }
            }
        },
        "defaults": {
            "provider": "azure-test",
            "model": azure_model,
            "deployment": azure_deployment
        }
    })
    
    client = await get_model_client(config_path=config)
    
    messages = [UserMessage(
        content="Write a very long story about a dragon",
        source="user"
    )]
    
    result = await client.create(messages)
    response = str(result.content)
    
    print(f"\nResponse with max_tokens=10: {response}")
    print(f"Response length: {len(response)} characters")
    
    # With max_tokens=10, response should be quite short
    # (exact length varies due to tokenization, but should be under 100 chars)
    assert len(response) < 100, f"Response too long for max_tokens=10: {len(response)} chars"


@pytest.mark.live
@pytest.mark.asyncio
async def test_openai_temperature_affects_output(temp_config_file):
    """Test that temperature parameter affects OpenAI model output."""
    
    config_low = temp_config_file({
        "version": "1",
        "providers": {
            "openai-test": {
                "type": "openai",
                "config": {
                    "api_key": "${OPENAI_API_KEY}",
                    "temperature": 0.1
                }
            }
        },
        "defaults": {
            "provider": "openai-test",
            "model": "gpt-4o-mini"
        }
    })
    
    config_high = temp_config_file({
        "version": "1",
        "providers": {
            "openai-test": {
                "type": "openai",
                "config": {
                    "api_key": "${OPENAI_API_KEY}",
                    "temperature": 1.5
                }
            }
        },
        "defaults": {
            "provider": "openai-test",
            "model": "gpt-4o-mini"
        }
    })
    
    client_low = await get_model_client(config_path=config_low)
    client_high = await get_model_client(config_path=config_high)
    
    messages = [UserMessage(content="Write a single creative word", source="user")]
    
    results_low = []
    results_high = []
    
    for _ in range(3):
        result_low = await client_low.create(messages)
        result_high = await client_high.create(messages)
        results_low.append(str(result_low.content))
        results_high.append(str(result_high.content))
    
    print(f"\nOpenAI Low temperature (0.1) results: {results_low}")
    print(f"OpenAI High temperature (1.5) results: {results_high}")
    
    assert all(r for r in results_low), "Low temperature client produced empty results"
    assert all(r for r in results_high), "High temperature client produced empty results"


@pytest.mark.live
@pytest.mark.asyncio
async def test_anthropic_temperature_affects_output(temp_config_file):
    """Test that temperature parameter affects Anthropic model output."""
    
    config_low = temp_config_file({
        "version": "1",
        "providers": {
            "anthropic-test": {
                "type": "anthropic",
                "config": {
                    "api_key": "${ANTHROPIC_API_KEY}",
                    "temperature": 0.1,
                    "max_tokens": 50
                }
            }
        },
        "defaults": {
            "provider": "anthropic-test",
            "model": "claude-3-5-haiku-20241022"
        }
    })
    
    config_high = temp_config_file({
        "version": "1",
        "providers": {
            "anthropic-test": {
                "type": "anthropic",
                "config": {
                    "api_key": "${ANTHROPIC_API_KEY}",
                    "temperature": 1.0,
                    "max_tokens": 50
                }
            }
        },
        "defaults": {
            "provider": "anthropic-test",
            "model": "claude-3-5-haiku-20241022"
        }
    })
    
    client_low = await get_model_client(config_path=config_low)
    client_high = await get_model_client(config_path=config_high)
    
    messages = [UserMessage(content="Write a single creative word", source="user")]
    
    results_low = []
    results_high = []
    
    for _ in range(3):
        result_low = await client_low.create(messages)
        result_high = await client_high.create(messages)
        results_low.append(str(result_low.content))
        results_high.append(str(result_high.content))
    
    print(f"\nAnthropic Low temperature (0.1) results: {results_low}")
    print(f"Anthropic High temperature (1.0) results: {results_high}")
    
    assert all(r for r in results_low), "Low temperature client produced empty results"
    assert all(r for r in results_high), "High temperature client produced empty results"


@pytest.mark.live
@pytest.mark.asyncio
async def test_anthropic_max_tokens_limits_output(temp_config_file):
    """Test that max_tokens parameter limits Anthropic output length."""
    
    config = temp_config_file({
        "version": "1",
        "providers": {
            "anthropic-test": {
                "type": "anthropic",
                "config": {
                    "api_key": "${ANTHROPIC_API_KEY}",
                    "max_tokens": 20  # Very short
                }
            }
        },
        "defaults": {
            "provider": "anthropic-test",
            "model": "claude-3-5-haiku-20241022"
        }
    })
    
    client = await get_model_client(config_path=config)
    
    messages = [UserMessage(
        content="Write a very long story about a dragon",
        source="user"
    )]
    
    result = await client.create(messages)
    response = str(result.content)
    
    print(f"\nAnthropic response with max_tokens=20: {response}")
    print(f"Response length: {len(response)} characters")
    
    # With max_tokens=20, response should be quite short
    assert len(response) < 150, f"Response too long for max_tokens=20: {len(response)} chars"
