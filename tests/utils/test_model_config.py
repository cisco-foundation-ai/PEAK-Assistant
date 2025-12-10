# Copyright (c) 2025 Cisco Systems, Inc. and its affiliates
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# SPDX-License-Identifier: MIT

import json
import pytest
from pathlib import Path
from typing import Any

import pytest_asyncio

from peak_assistant.utils.model_config_loader import (
    ModelConfigLoader,
    ModelConfigError,
    reset_loader,
)
from peak_assistant.utils import llm_factory


class DummyClient:
    """Dummy client for testing without real LLM dependencies."""
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary model_config.json file."""
    config_file = tmp_path / "model_config.json"
    
    def _create(config_dict):
        config_file.write_text(json.dumps(config_dict), encoding="utf-8")
        return config_file
    
    return _create


@pytest.fixture(autouse=True)
def reset_global_loader():
    """Reset the global loader before each test."""
    reset_loader()
    yield
    reset_loader()


@pytest.fixture(autouse=True)
def patch_client_classes(monkeypatch):
    """Patch client classes to avoid real imports."""
    monkeypatch.setattr(llm_factory, "AZURE_CLIENT_CLASS", DummyClient, raising=False)
    monkeypatch.setattr(llm_factory, "OPENAI_CLIENT_CLASS", DummyClient, raising=False)


# ============================================================================
# Config Loader Tests
# ============================================================================

def test_missing_config_file(tmp_path):
    """Test that missing config file raises appropriate error."""
    loader = ModelConfigLoader(tmp_path / "nonexistent.json")
    
    with pytest.raises(ModelConfigError, match="not found"):
        loader.load()


def test_invalid_json(temp_config_file):
    """Test that invalid JSON raises appropriate error."""
    config_file = temp_config_file({"version": "1"})
    config_file.write_text("{invalid json", encoding="utf-8")
    
    loader = ModelConfigLoader(config_file)
    with pytest.raises(ModelConfigError, match="Invalid JSON"):
        loader.load()


def test_missing_version(temp_config_file):
    """Test that missing version field raises error."""
    config_file = temp_config_file({
        "providers": {},
        "defaults": {}
    })
    
    loader = ModelConfigLoader(config_file)
    with pytest.raises(ModelConfigError, match="version"):
        loader.load()


def test_missing_providers(temp_config_file):
    """Test that missing providers section raises error."""
    config_file = temp_config_file({
        "version": "1",
        "defaults": {}
    })
    
    loader = ModelConfigLoader(config_file)
    with pytest.raises(ModelConfigError, match="providers"):
        loader.load()


def test_missing_defaults(temp_config_file):
    """Test that missing defaults section raises error."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {}
    })
    
    loader = ModelConfigLoader(config_file)
    with pytest.raises(ModelConfigError, match="defaults"):
        loader.load()


def test_env_interpolation(temp_config_file, monkeypatch):
    """Test environment variable interpolation."""
    monkeypatch.setenv("TEST_API_KEY", "secret-key-123")
    monkeypatch.setenv("TEST_ENDPOINT", "https://example.com")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "test-provider": {
                "type": "openai",
                "config": {
                    "api_key": "${TEST_API_KEY}",
                    "base_url": "${TEST_ENDPOINT}/v1"
                }
            }
        },
        "defaults": {
            "provider": "test-provider",
            "model": "gpt-4"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    provider_config = loader.get_provider_config("test-provider")
    assert provider_config["config"]["api_key"] == "secret-key-123"
    assert provider_config["config"]["base_url"] == "https://example.com/v1"


def test_env_interpolation_missing_var(temp_config_file):
    """Test that missing env var without default raises error."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "test-provider": {
                "type": "openai",
                "config": {
                    "api_key": "${MISSING_VAR}"
                }
            }
        },
        "defaults": {
            "provider": "test-provider",
            "model": "gpt-4"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    with pytest.raises(ModelConfigError, match="MISSING_VAR"):
        loader.load()


def test_env_interpolation_with_default(temp_config_file):
    """Test environment variable interpolation with default value."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "test-provider": {
                "type": "openai",
                "config": {
                    "api_key": "${MISSING_VAR|default-key}"
                }
            }
        },
        "defaults": {
            "provider": "test-provider",
            "model": "gpt-4"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    provider_config = loader.get_provider_config("test-provider")
    assert provider_config["config"]["api_key"] == "default-key"


def test_resolve_defaults(temp_config_file, monkeypatch):
    """Test resolving configuration from defaults."""
    monkeypatch.setenv("API_KEY", "key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    # Resolve without agent name should use defaults
    config = loader.resolve_agent_config(None)
    assert config["provider"] == "azure-main"
    assert config["model"] == "gpt-4o"
    assert config["deployment"] == "gpt-4o-deployment"


def test_resolve_agent_exact_match(temp_config_file, monkeypatch):
    """Test resolving configuration with exact agent match."""
    monkeypatch.setenv("API_KEY", "key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        },
        "agents": {
            "summarizer_agent": {
                "provider": "azure-main",
                "model": "gpt-4o-mini",
                "deployment": "gpt-4o-mini-deployment"
            }
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    config = loader.resolve_agent_config("summarizer_agent")
    assert config["provider"] == "azure-main"
    assert config["model"] == "gpt-4o-mini"
    assert config["deployment"] == "gpt-4o-mini-deployment"


def test_resolve_agent_group_wildcard(temp_config_file, monkeypatch):
    """Test resolving configuration with wildcard group match."""
    monkeypatch.setenv("API_KEY", "key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        },
        "groups": {
            "critics": {
                "match": ["*_critic", "critic"],
                "provider": "azure-main",
                "model": "o4-mini",
                "deployment": "o4-mini-deployment"
            }
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    # Test wildcard match
    config = loader.resolve_agent_config("summary_critic")
    assert config["provider"] == "azure-main"
    assert config["model"] == "o4-mini"
    assert config["deployment"] == "o4-mini-deployment"
    
    # Test exact match in pattern list
    config = loader.resolve_agent_config("critic")
    assert config["model"] == "o4-mini"
    
    # Test non-matching agent falls back to defaults
    config = loader.resolve_agent_config("other_agent")
    assert config["model"] == "gpt-4o"


def test_resolve_precedence(temp_config_file, monkeypatch):
    """Test that agents > groups > defaults precedence works."""
    monkeypatch.setenv("API_KEY", "key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "default-model",
            "deployment": "default-deployment"
        },
        "groups": {
            "test-group": {
                "match": ["test_*"],
                "provider": "azure-main",
                "model": "group-model",
                "deployment": "group-deployment"
            }
        },
        "agents": {
            "test_agent": {
                "provider": "azure-main",
                "model": "agent-model",
                "deployment": "agent-deployment"
            }
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    # Agent exact match should win
    config = loader.resolve_agent_config("test_agent")
    assert config["model"] == "agent-model"
    
    # Group match should win over defaults
    config = loader.resolve_agent_config("test_other")
    assert config["model"] == "group-model"
    
    # Non-matching should use defaults
    config = loader.resolve_agent_config("other_agent")
    assert config["model"] == "default-model"


def test_get_provider_not_found(temp_config_file, monkeypatch):
    """Test that requesting non-existent provider raises error."""
    monkeypatch.setenv("API_KEY", "key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    with pytest.raises(ModelConfigError, match="Provider 'nonexistent' not found"):
        loader.get_provider_config("nonexistent")


def test_get_model_info(temp_config_file, monkeypatch):
    """Test retrieving model_info from provider."""
    monkeypatch.setenv("API_KEY", "key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "ollama-local": {
                "type": "openai",
                "config": {
                    "api_key": "${API_KEY}",
                    "base_url": "http://localhost:11434/v1"
                },
                "models": {
                    "llama-3.1-8b": {
                        "model_info": {
                            "id": "llama-3.1-8b",
                            "family": "llama-3",
                            "vision": False,
                            "audio": False,
                            "function_calling": False,
                            "json_output": False,
                            "structured_output": False,
                            "input": {"max_tokens": 131072},
                            "output": {"max_tokens": 8192}
                        }
                    }
                }
            }
        },
        "defaults": {
            "provider": "ollama-local",
            "model": "llama-3.1-8b"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    model_info = loader.get_model_info("ollama-local", "llama-3.1-8b")
    assert model_info is not None
    assert model_info["id"] == "llama-3.1-8b"
    assert model_info["family"] == "llama-3"
    
    # Non-existent model should return None
    model_info = loader.get_model_info("ollama-local", "nonexistent")
    assert model_info is None


# ============================================================================
# LLM Factory Tests
# ============================================================================

@pytest.mark.asyncio
async def test_factory_azure_defaults(temp_config_file, monkeypatch):
    """Test creating Azure client from defaults."""
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${AZURE_API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        }
    })
    
    client = await llm_factory.get_model_client(config_path=config_file)
    assert isinstance(client, DummyClient)
    assert client.kwargs["azure_deployment"] == "gpt-4o-deployment"
    assert client.kwargs["model"] == "gpt-4o"
    assert client.kwargs["azure_endpoint"] == "https://example.azure.openai.com/"
    assert client.kwargs["api_version"] == "2025-04-01-preview"
    assert client.kwargs["api_key"] == "test-key"


@pytest.mark.asyncio
async def test_factory_azure_per_agent(temp_config_file, monkeypatch):
    """Test creating Azure client with per-agent configuration."""
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${AZURE_API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        },
        "agents": {
            "summarizer_agent": {
                "provider": "azure-main",
                "model": "gpt-4o-mini",
                "deployment": "gpt-4o-mini-deployment"
            }
        }
    })
    
    client = await llm_factory.get_model_client(
        agent_name="summarizer_agent",
        config_path=config_file
    )
    assert isinstance(client, DummyClient)
    assert client.kwargs["azure_deployment"] == "gpt-4o-mini-deployment"
    assert client.kwargs["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_factory_openai_native(temp_config_file, monkeypatch):
    """Test creating OpenAI native client."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "openai-native": {
                "type": "openai",
                "config": {
                    "api_key": "${OPENAI_API_KEY}"
                }
            }
        },
        "defaults": {
            "provider": "openai-native",
            "model": "gpt-4o-mini"
        }
    })
    
    client = await llm_factory.get_model_client(config_path=config_file)
    assert isinstance(client, DummyClient)
    assert client.kwargs["model"] == "gpt-4o-mini"
    assert client.kwargs["api_key"] == "sk-test-key"
    assert "base_url" not in client.kwargs


@pytest.mark.asyncio
async def test_factory_openai_compatible(temp_config_file, monkeypatch):
    """Test creating OpenAI-compatible client with base_url."""
    monkeypatch.setenv("API_KEY", "sk-local")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "ollama-local": {
                "type": "openai",
                "config": {
                    "api_key": "${API_KEY}",
                    "base_url": "http://localhost:11434/v1"
                }
            }
        },
        "defaults": {
            "provider": "ollama-local",
            "model": "llama-3.1-8b"
        }
    })
    
    client = await llm_factory.get_model_client(config_path=config_file)
    assert isinstance(client, DummyClient)
    assert client.kwargs["model"] == "llama-3.1-8b"
    assert client.kwargs["api_key"] == "sk-local"
    assert client.kwargs["base_url"] == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_factory_openai_with_model_info(temp_config_file, monkeypatch):
    """Test creating OpenAI-compatible client with model_info."""
    monkeypatch.setenv("API_KEY", "sk-local")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "ollama-local": {
                "type": "openai",
                "config": {
                    "api_key": "${API_KEY}",
                    "base_url": "http://localhost:11434/v1"
                },
                "models": {
                    "llama-3.1-8b": {
                        "model_info": {
                            "id": "llama-3.1-8b",
                            "family": "llama-3",
                            "vision": False,
                            "audio": False,
                            "function_calling": False,
                            "json_output": False,
                            "structured_output": False,
                            "input": {"max_tokens": 131072},
                            "output": {"max_tokens": 8192}
                        }
                    }
                }
            }
        },
        "defaults": {
            "provider": "ollama-local",
            "model": "llama-3.1-8b"
        }
    })
    
    client = await llm_factory.get_model_client(config_path=config_file)
    assert isinstance(client, DummyClient)
    assert client.kwargs["model"] == "llama-3.1-8b"
    assert "model_info" in client.kwargs
    assert client.kwargs["model_info"]["id"] == "llama-3.1-8b"
    assert client.kwargs["model_info"]["family"] == "llama-3"


@pytest.mark.asyncio
async def test_factory_multiple_providers(temp_config_file, monkeypatch):
    """Test using multiple provider instances in same config."""
    monkeypatch.setenv("AZURE_API_KEY", "azure-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${AZURE_API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            },
            "openai-native": {
                "type": "openai",
                "config": {
                    "api_key": "${OPENAI_API_KEY}"
                }
            },
            "ollama-local": {
                "type": "openai",
                "config": {
                    "api_key": "sk-local",
                    "base_url": "http://localhost:11434/v1"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        },
        "agents": {
            "summarizer_agent": {
                "provider": "openai-native",
                "model": "gpt-4o-mini"
            },
            "able_table": {
                "provider": "ollama-local",
                "model": "llama-3.1-8b"
            }
        }
    })
    
    # Test Azure (defaults)
    client1 = await llm_factory.get_model_client(config_path=config_file)
    assert client1.kwargs["azure_deployment"] == "gpt-4o-deployment"
    
    # Test OpenAI native
    client2 = await llm_factory.get_model_client(
        agent_name="summarizer_agent",
        config_path=config_file
    )
    assert client2.kwargs["model"] == "gpt-4o-mini"
    assert client2.kwargs["api_key"] == "openai-key"
    
    # Test OpenAI-compatible
    client3 = await llm_factory.get_model_client(
        agent_name="able_table",
        config_path=config_file
    )
    assert client3.kwargs["model"] == "llama-3.1-8b"
    assert client3.kwargs["base_url"] == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_factory_missing_config_file(tmp_path):
    """Test that missing config file raises appropriate error."""
    with pytest.raises(ModelConfigError, match="not found"):
        await llm_factory.get_model_client(config_path=tmp_path / "nonexistent.json")


@pytest.mark.asyncio
async def test_factory_azure_missing_deployment(temp_config_file, monkeypatch):
    """Test that Azure config without deployment raises error."""
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-main": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_key": "${AZURE_API_KEY}",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-main",
            "model": "gpt-4o"
            # Missing deployment!
        }
    })
    
    with pytest.raises(ModelConfigError, match="deployment"):
        await llm_factory.get_model_client(config_path=config_file)


@pytest.mark.asyncio
async def test_factory_openai_missing_model(temp_config_file):
    """Test that OpenAI config without model raises error."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "openai-main": {
                "type": "openai",
                "config": {
                    "api_key": "test-key"
                }
            }
        },
        "defaults": {
            "provider": "openai-main"
            # Missing model
        }
    })
    
    with pytest.raises(ModelConfigError, match="must include 'model' field"):
        await llm_factory.get_model_client(config_path=config_file)


@pytest.mark.asyncio
async def test_factory_anthropic(temp_config_file):
    """Test Anthropic provider configuration."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "anthropic-test": {
                "type": "anthropic",
                "config": {
                    "api_key": "sk-ant-test-key",
                    "max_tokens": 4096
                }
            }
        },
        "defaults": {
            "provider": "anthropic-test",
            "model": "claude-3-5-sonnet-20241022"
        }
    })
    
    # Should create client successfully
    client = await llm_factory.get_model_client(config_path=config_file)
    assert client is not None
    assert client.__class__.__name__ == "AnthropicChatCompletionClient"


@pytest.mark.asyncio
async def test_factory_anthropic_missing_api_key(temp_config_file):
    """Test Anthropic provider with missing API key."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "anthropic-test": {
                "type": "anthropic",
                "config": {}  # Missing api_key
            }
        },
        "defaults": {
            "provider": "anthropic-test",
            "model": "claude-3-5-sonnet-20241022"
        }
    })
    
    with pytest.raises(ModelConfigError, match="Missing required field.*api_key"):
        await llm_factory.get_model_client(config_path=config_file)


@pytest.mark.asyncio
async def test_factory_anthropic_missing_model(temp_config_file):
    """Test Anthropic agent with missing model."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "anthropic-test": {
                "type": "anthropic",
                "config": {
                    "api_key": "sk-ant-test-key"
                }
            }
        },
        "defaults": {
            "provider": "anthropic-test"
            # Missing model
        }
    })
    
    with pytest.raises(ModelConfigError, match="must include 'model' field"):
        await llm_factory.get_model_client(config_path=config_file)


@pytest.mark.asyncio
async def test_factory_azure_with_optional_params(temp_config_file, monkeypatch):
    """Test Azure with optional parameters."""
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-test": {
                "type": "azure",
                "config": {
                    "endpoint": "https://test.openai.azure.com/",
                    "api_key": "${AZURE_API_KEY}",
                    "api_version": "2024-02-01",
                    "max_tokens": 2000,
                    "temperature": 0.5,
                    "top_p": 0.9,
                    "frequency_penalty": 0.2,
                    "presence_penalty": 0.1,
                    "seed": 42
                }
            }
        },
        "defaults": {
            "provider": "azure-test",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        }
    })
    
    client = await llm_factory.get_model_client(config_path=config_file)
    
    # Verify optional params were passed
    assert client.kwargs["max_tokens"] == 2000
    assert client.kwargs["temperature"] == 0.5
    assert client.kwargs["top_p"] == 0.9
    assert client.kwargs["frequency_penalty"] == 0.2
    assert client.kwargs["presence_penalty"] == 0.1
    assert client.kwargs["seed"] == 42


@pytest.mark.asyncio
async def test_factory_openai_with_optional_params(temp_config_file):
    """Test OpenAI with optional parameters."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "openai-test": {
                "type": "openai",
                "config": {
                    "api_key": "test-key",
                    "max_tokens": 1500,
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "frequency_penalty": 0.5,
                    "presence_penalty": 0.3,
                    "seed": 123,
                    "stop": ["END", "STOP"]
                }
            }
        },
        "defaults": {
            "provider": "openai-test",
            "model": "gpt-4o-mini"
        }
    })
    
    client = await llm_factory.get_model_client(config_path=config_file)
    
    # Verify optional params were passed
    assert client.kwargs["max_tokens"] == 1500
    assert client.kwargs["temperature"] == 0.7
    assert client.kwargs["top_p"] == 0.95
    assert client.kwargs["frequency_penalty"] == 0.5
    assert client.kwargs["presence_penalty"] == 0.3
    assert client.kwargs["seed"] == 123
    assert client.kwargs["stop"] == ["END", "STOP"]


@pytest.mark.asyncio
async def test_factory_anthropic_with_optional_params(temp_config_file):
    """Test Anthropic with optional parameters."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "anthropic-test": {
                "type": "anthropic",
                "config": {
                    "api_key": "sk-ant-test-key",
                    "max_tokens": 4096,
                    "temperature": 0.8,
                    "top_p": 0.9,
                    "top_k": 50,
                    "timeout": 30.0,
                    "max_retries": 3
                }
            }
        },
        "defaults": {
            "provider": "anthropic-test",
            "model": "claude-3-5-sonnet-20241022"
        }
    })
    
    # Client creation with optional params should succeed
    # (Anthropic client doesn't expose kwargs like Azure/OpenAI, but if params
    # are invalid, the client creation would fail)
    client = await llm_factory.get_model_client(config_path=config_file)
    assert client is not None
    assert client.__class__.__name__ == "AnthropicChatCompletionClient"


# ============================================================================
# Auth Module Tests
# ============================================================================

@pytest.mark.asyncio
async def test_factory_azure_with_auth_module(temp_config_file, tmp_path, monkeypatch):
    """Test Azure provider with custom auth_module."""
    # Create a temporary auth module
    auth_module_dir = tmp_path / "custom_auth"
    auth_module_dir.mkdir()
    (auth_module_dir / "__init__.py").write_text("")
    (auth_module_dir / "my_oauth.py").write_text('''
async def get_credentials(config):
    """Mock OAuth that returns credentials based on config."""
    return {
        "api_key": "oauth-token-12345",
        "user": '{"appkey": "test-app-key"}'
    }
''')
    
    # Add the temp path to sys.path so the module can be imported
    import sys
    sys.path.insert(0, str(tmp_path))
    
    try:
        config_file = temp_config_file({
            "version": "1",
            "providers": {
                "azure-oauth": {
                    "type": "azure",
                    "auth_module": "custom_auth.my_oauth",
                    "config": {
                        "endpoint": "https://example.azure.openai.com/",
                        "api_version": "2025-04-01-preview"
                        # Note: no api_key - auth_module provides it
                    }
                }
            },
            "defaults": {
                "provider": "azure-oauth",
                "model": "gpt-4o",
                "deployment": "gpt-4o-deployment"
            }
        })
        
        client = await llm_factory.get_model_client(config_path=config_file)
        assert isinstance(client, DummyClient)
        assert client.kwargs["api_key"] == "oauth-token-12345"
        assert client.kwargs["user"] == '{"appkey": "test-app-key"}'
        assert client.kwargs["azure_deployment"] == "gpt-4o-deployment"
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.asyncio
async def test_factory_azure_auth_module_missing_module(temp_config_file):
    """Test that missing auth_module raises appropriate error."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-oauth": {
                "type": "azure",
                "auth_module": "nonexistent.module",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_version": "2025-04-01-preview"
                }
            }
        },
        "defaults": {
            "provider": "azure-oauth",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        }
    })
    
    with pytest.raises(ModelConfigError, match="Failed to import auth_module"):
        await llm_factory.get_model_client(config_path=config_file)


@pytest.mark.asyncio
async def test_factory_azure_auth_module_missing_function(temp_config_file, tmp_path):
    """Test that auth_module without get_credentials function raises error."""
    # Create a module without get_credentials
    auth_module_dir = tmp_path / "bad_auth"
    auth_module_dir.mkdir()
    (auth_module_dir / "__init__.py").write_text("")
    (auth_module_dir / "no_func.py").write_text('''
# This module is missing the required get_credentials function
def other_function():
    pass
''')
    
    import sys
    sys.path.insert(0, str(tmp_path))
    
    try:
        config_file = temp_config_file({
            "version": "1",
            "providers": {
                "azure-oauth": {
                    "type": "azure",
                    "auth_module": "bad_auth.no_func",
                    "config": {
                        "endpoint": "https://example.azure.openai.com/",
                        "api_version": "2025-04-01-preview"
                    }
                }
            },
            "defaults": {
                "provider": "azure-oauth",
                "model": "gpt-4o",
                "deployment": "gpt-4o-deployment"
            }
        })
        
        with pytest.raises(ModelConfigError, match="must expose.*get_credentials"):
            await llm_factory.get_model_client(config_path=config_file)
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.asyncio
async def test_factory_azure_auth_module_returns_invalid(temp_config_file, tmp_path):
    """Test that auth_module returning invalid data raises error."""
    # Create a module that returns wrong type
    auth_module_dir = tmp_path / "invalid_auth"
    auth_module_dir.mkdir()
    (auth_module_dir / "__init__.py").write_text("")
    (auth_module_dir / "wrong_return.py").write_text('''
async def get_credentials(config):
    return "not a dict"
''')
    
    import sys
    sys.path.insert(0, str(tmp_path))
    
    try:
        config_file = temp_config_file({
            "version": "1",
            "providers": {
                "azure-oauth": {
                    "type": "azure",
                    "auth_module": "invalid_auth.wrong_return",
                    "config": {
                        "endpoint": "https://example.azure.openai.com/",
                        "api_version": "2025-04-01-preview"
                    }
                }
            },
            "defaults": {
                "provider": "azure-oauth",
                "model": "gpt-4o",
                "deployment": "gpt-4o-deployment"
            }
        })
        
        with pytest.raises(ModelConfigError, match="must return a dict"):
            await llm_factory.get_model_client(config_path=config_file)
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.asyncio
async def test_factory_azure_auth_module_missing_api_key(temp_config_file, tmp_path):
    """Test that auth_module returning dict without api_key raises error."""
    # Create a module that returns dict without api_key
    auth_module_dir = tmp_path / "nokey_auth"
    auth_module_dir.mkdir()
    (auth_module_dir / "__init__.py").write_text("")
    (auth_module_dir / "no_api_key.py").write_text('''
async def get_credentials(config):
    return {"user": "some-user"}  # Missing api_key
''')
    
    import sys
    sys.path.insert(0, str(tmp_path))
    
    try:
        config_file = temp_config_file({
            "version": "1",
            "providers": {
                "azure-oauth": {
                    "type": "azure",
                    "auth_module": "nokey_auth.no_api_key",
                    "config": {
                        "endpoint": "https://example.azure.openai.com/",
                        "api_version": "2025-04-01-preview"
                    }
                }
            },
            "defaults": {
                "provider": "azure-oauth",
                "model": "gpt-4o",
                "deployment": "gpt-4o-deployment"
            }
        })
        
        with pytest.raises(ModelConfigError, match="must return a dict with 'api_key'"):
            await llm_factory.get_model_client(config_path=config_file)
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.asyncio
async def test_factory_azure_auth_module_receives_config(temp_config_file, tmp_path):
    """Test that auth_module receives the provider config."""
    # Create a module that echoes back config values
    auth_module_dir = tmp_path / "echo_auth"
    auth_module_dir.mkdir()
    (auth_module_dir / "__init__.py").write_text("")
    (auth_module_dir / "echo.py").write_text('''
async def get_credentials(config):
    """Return api_key based on config to prove we received it."""
    return {
        "api_key": f"token-for-{config.get('custom_field', 'unknown')}",
    }
''')
    
    import sys
    sys.path.insert(0, str(tmp_path))
    
    try:
        config_file = temp_config_file({
            "version": "1",
            "providers": {
                "azure-oauth": {
                    "type": "azure",
                    "auth_module": "echo_auth.echo",
                    "config": {
                        "endpoint": "https://example.azure.openai.com/",
                        "api_version": "2025-04-01-preview",
                        "custom_field": "my-app-id"
                    }
                }
            },
            "defaults": {
                "provider": "azure-oauth",
                "model": "gpt-4o",
                "deployment": "gpt-4o-deployment"
            }
        })
        
        client = await llm_factory.get_model_client(config_path=config_file)
        assert client.kwargs["api_key"] == "token-for-my-app-id"
    finally:
        sys.path.remove(str(tmp_path))


def test_loader_azure_allows_missing_api_key_with_auth_module(temp_config_file):
    """Test that loader allows missing api_key when auth_module is present."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-oauth": {
                "type": "azure",
                "auth_module": "some.module",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_version": "2025-04-01-preview"
                    # No api_key - should be allowed
                }
            }
        },
        "defaults": {
            "provider": "azure-oauth",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    # Should not raise - api_key is optional when auth_module is present
    provider_config = loader.get_provider_config("azure-oauth")
    assert provider_config["auth_module"] == "some.module"
    assert "api_key" not in provider_config["config"]


def test_loader_azure_requires_api_key_without_auth_module(temp_config_file):
    """Test that loader requires api_key when no auth_module is present."""
    config_file = temp_config_file({
        "version": "1",
        "providers": {
            "azure-standard": {
                "type": "azure",
                "config": {
                    "endpoint": "https://example.azure.openai.com/",
                    "api_version": "2025-04-01-preview"
                    # No api_key and no auth_module - should fail
                }
            }
        },
        "defaults": {
            "provider": "azure-standard",
            "model": "gpt-4o",
            "deployment": "gpt-4o-deployment"
        }
    })
    
    loader = ModelConfigLoader(config_file)
    loader.load()
    
    with pytest.raises(ModelConfigError, match="Missing required fields.*api_key"):
        loader.get_provider_config("azure-standard")
