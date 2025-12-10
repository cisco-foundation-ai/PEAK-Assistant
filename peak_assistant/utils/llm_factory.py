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
"""
Provider-agnostic LLM factory.

Usage:
    client = await get_model_client(agent_name="summarizer_agent")
    client = await get_model_client()  # Uses defaults

Configuration:
    Requires model_config.json in the current working directory.
    See MODEL_CONFIGURATION.md for details.
"""

from __future__ import annotations

import importlib
from typing import Optional, Any, Type
from pathlib import Path

from .model_config_loader import get_loader, ModelConfigError


async def _get_auth_module_credentials(auth_module: str, config: dict) -> dict:
    """Load credentials from an external auth module.
    
    The auth module must expose an async function `get_credentials(config)` that returns
    a dict with at least 'api_key'. It may also return 'user' or other parameters.
    
    Args:
        auth_module: Python module path (e.g., 'my_package.my_auth_module')
        config: Provider config dict to pass to the auth module
    
    Returns:
        Dict with credentials (at minimum 'api_key')
    
    Raises:
        ModelConfigError: If module cannot be loaded or doesn't have required function
    """
    try:
        module = importlib.import_module(auth_module)
    except ImportError as e:
        raise ModelConfigError(
            f"Failed to import auth_module '{auth_module}': {e}"
        ) from e
    
    if not hasattr(module, "get_credentials"):
        raise ModelConfigError(
            f"Auth module '{auth_module}' must expose an async 'get_credentials(config)' function"
        )
    
    get_credentials = getattr(module, "get_credentials")
    
    try:
        creds = await get_credentials(config)
    except Exception as e:
        raise ModelConfigError(
            f"Auth module '{auth_module}' get_credentials() failed: {e}"
        ) from e
    
    if not isinstance(creds, dict):
        raise ModelConfigError(
            f"Auth module '{auth_module}' get_credentials() must return a dict, got {type(creds).__name__}"
        )
    
    if "api_key" not in creds:
        raise ModelConfigError(
            f"Auth module '{auth_module}' get_credentials() must return a dict with 'api_key'"
        )
    
    return creds


async def get_model_client(agent_name: Optional[str] = None, config_path: Optional[Path] = None):
    """Return a configured model client for the specified agent.

    Args:
        agent_name: Name of the agent. If None, uses defaults from config.
        config_path: Path to model_config.json. If None, uses CWD.

    Returns:
        Configured LLM client instance.

    Raises:
        ModelConfigError: if configuration is missing or invalid.
        ValueError: for unsupported provider type.
    """
    try:
        loader = get_loader(config_path)
        
        # Resolve agent configuration
        agent_config = loader.resolve_agent_config(agent_name)
        
        # Get provider configuration
        provider_name = agent_config["provider"]
        provider_config = loader.get_provider_config(provider_name)
        
        provider_type = provider_config["type"]
        
        if provider_type == "azure":
            return await _build_azure_client(agent_config, provider_config, loader)
        elif provider_type == "openai":
            return await _build_openai_client(agent_config, provider_config, loader)
        elif provider_type == "anthropic":
            return await _build_anthropic_client(agent_config, provider_config, loader)
        else:
            raise ValueError(
                f"Unsupported provider type '{provider_type}'. Supported: azure, openai, anthropic."
            )
    except ModelConfigError:
        raise
    except Exception as e:
        raise ModelConfigError(
            f"Failed to create model client for agent '{agent_name or 'defaults'}': {e}"
        ) from e


# Lazy-loaded client classes
AZURE_CLIENT_CLASS: Optional[Type] = None
OPENAI_CLIENT_CLASS: Optional[Type] = None
ANTHROPIC_CLIENT_CLASS: Optional[Type] = None


async def _build_azure_client(agent_config: dict, provider_config: dict, loader: Any):
    """Build Azure OpenAI client from configuration.
    
    Args:
        agent_config: Resolved agent configuration (must include 'model' and 'deployment')
        provider_config: Provider configuration (must include 'config' with connection details)
        loader: ModelConfigLoader instance
    
    Returns:
        AzureOpenAIChatCompletionClient instance
    """
    # Validate required agent fields
    if "model" not in agent_config:
        raise ModelConfigError("Azure agent configuration must include 'model' field")
    if "deployment" not in agent_config:
        raise ModelConfigError("Azure agent configuration must include 'deployment' field")
    
    # Get connection config from provider (make a copy so we can modify it)
    conn_config = dict(provider_config["config"])
    
    # Check for custom auth module
    if "auth_module" in provider_config:
        auth_creds = await _get_auth_module_credentials(
            provider_config["auth_module"], 
            conn_config
        )
        conn_config.update(auth_creds)
    
    # Validate required provider fields (api_key should now be present either from config or auth_module)
    required_fields = ["endpoint", "api_key", "api_version"]
    missing = [f for f in required_fields if f not in conn_config]
    if missing:
        raise ModelConfigError(
            f"Azure provider configuration missing required fields: {', '.join(missing)}"
        )
    
    params = {
        "azure_deployment": agent_config["deployment"],
        "model": agent_config["model"],
        "api_version": conn_config["api_version"],
        "azure_endpoint": conn_config["endpoint"],
        "api_key": conn_config["api_key"],
    }
    
    # Optional: user parameter (typically from auth_module for gateway authentication)
    if "user" in conn_config:
        params["user"] = conn_config["user"]
    
    # Optional parameters - common
    if "max_tokens" in conn_config:
        params["max_tokens"] = conn_config["max_tokens"]
    if "temperature" in conn_config:
        params["temperature"] = conn_config["temperature"]
    if "top_p" in conn_config:
        params["top_p"] = conn_config["top_p"]
    if "timeout" in conn_config:
        params["timeout"] = conn_config["timeout"]
    if "max_retries" in conn_config:
        params["max_retries"] = conn_config["max_retries"]
    if "stop" in conn_config:
        params["stop"] = conn_config["stop"]
    
    # Optional parameters - Azure/OpenAI specific
    if "frequency_penalty" in conn_config:
        params["frequency_penalty"] = conn_config["frequency_penalty"]
    if "presence_penalty" in conn_config:
        params["presence_penalty"] = conn_config["presence_penalty"]
    if "seed" in conn_config:
        params["seed"] = conn_config["seed"]
    
    global AZURE_CLIENT_CLASS
    if AZURE_CLIENT_CLASS is None:
        # Lazy import to avoid requiring dependency at module import time
        from autogen_ext.models.openai import AzureOpenAIChatCompletionClient as _AZ
        AZURE_CLIENT_CLASS = _AZ
    
    return AZURE_CLIENT_CLASS(**params)  # type: ignore[misc]


async def _build_openai_client(agent_config: dict, provider_config: dict, loader: Any):
    """Build OpenAI client from configuration.
    
    Args:
        agent_config: Resolved agent configuration (must include 'model')
        provider_config: Provider configuration (must include 'config' with connection details)
        loader: ModelConfigLoader instance
    
    Returns:
        OpenAIChatCompletionClient instance
    """
    # Validate required agent fields
    if "model" not in agent_config:
        raise ModelConfigError("OpenAI agent configuration must include 'model' field")
    
    # Get connection config from provider
    conn_config = provider_config["config"]
    
    # Validate required provider fields
    if "api_key" not in conn_config:
        raise ModelConfigError("OpenAI provider configuration missing required 'api_key' field")
    
    params = {
        "model": agent_config["model"],
        "api_key": conn_config["api_key"],
    }
    
    # Optional: base_url for OpenAI-compatible servers
    if "base_url" in conn_config:
        params["base_url"] = conn_config["base_url"]
    
    # Optional: organization and project
    if "organization" in conn_config:
        params["organization"] = conn_config["organization"]
    if "project" in conn_config:
        params["project"] = conn_config["project"]
    
    # Optional parameters - common
    if "max_tokens" in conn_config:
        params["max_tokens"] = conn_config["max_tokens"]
    if "temperature" in conn_config:
        params["temperature"] = conn_config["temperature"]
    if "top_p" in conn_config:
        params["top_p"] = conn_config["top_p"]
    if "timeout" in conn_config:
        params["timeout"] = conn_config["timeout"]
    if "max_retries" in conn_config:
        params["max_retries"] = conn_config["max_retries"]
    if "stop" in conn_config:
        params["stop"] = conn_config["stop"]
    
    # Optional parameters - Azure/OpenAI specific
    if "frequency_penalty" in conn_config:
        params["frequency_penalty"] = conn_config["frequency_penalty"]
    if "presence_penalty" in conn_config:
        params["presence_penalty"] = conn_config["presence_penalty"]
    if "seed" in conn_config:
        params["seed"] = conn_config["seed"]
    
    # Optional: model_info for OpenAI-compatible servers
    model_info = loader.get_model_info(agent_config["provider"], agent_config["model"])
    if model_info:
        params["model_info"] = model_info
    
    global OPENAI_CLIENT_CLASS
    if OPENAI_CLIENT_CLASS is None:
        # Lazy import to avoid requiring dependency at module import time
        from autogen_ext.models.openai import OpenAIChatCompletionClient as _OC
        OPENAI_CLIENT_CLASS = _OC
    
    try:
        return OPENAI_CLIENT_CLASS(**params)  # type: ignore[misc]
    except ValueError as e:
        msg = str(e)
        if "model_info" in msg or "ModelInfo" in msg:
            required_fields = (
                "family, vision, audio, function_calling, json_output, structured_output, "
                "input.max_tokens, output.max_tokens"
            )
            hint = (
                f"OpenAI-compatible model '{agent_config['model']}' requires model_info. "
                f"Add a 'models' section to your provider configuration with model_info for this model. "
                f"Required fields: {required_fields}. See MODEL_CONFIGURATION.md for examples."
            )
            raise ModelConfigError(f"{hint}\nOriginal error: {msg}") from e
        raise


async def _build_anthropic_client(agent_config: dict, provider_config: dict, loader: Any):
    """Build Anthropic client from configuration.
    
    Args:
        agent_config: Resolved agent configuration (must include 'model')
        provider_config: Provider configuration (must include 'config' with connection details)
        loader: ModelConfigLoader instance
    
    Returns:
        AnthropicChatCompletionClient instance
    """
    # Validate required agent fields
    if "model" not in agent_config:
        raise ModelConfigError("Anthropic agent configuration must include 'model' field")
    
    # Get connection config from provider
    conn_config = provider_config["config"]
    
    # Validate required provider fields
    if "api_key" not in conn_config:
        raise ModelConfigError("Anthropic provider configuration missing required 'api_key' field")
    
    params = {
        "model": agent_config["model"],
        "api_key": conn_config["api_key"],
    }
    
    # Optional parameters
    if "max_tokens" in conn_config:
        params["max_tokens"] = conn_config["max_tokens"]
    if "temperature" in conn_config:
        params["temperature"] = conn_config["temperature"]
    if "top_p" in conn_config:
        params["top_p"] = conn_config["top_p"]
    if "base_url" in conn_config:
        params["base_url"] = conn_config["base_url"]
    if "timeout" in conn_config:
        params["timeout"] = conn_config["timeout"]
    if "max_retries" in conn_config:
        params["max_retries"] = conn_config["max_retries"]
    
    global ANTHROPIC_CLIENT_CLASS
    if ANTHROPIC_CLIENT_CLASS is None:
        # Lazy import to avoid requiring dependency at module import time
        from autogen_ext.models.anthropic import AnthropicChatCompletionClient as _AC
        ANTHROPIC_CLIENT_CLASS = _AC
    
    return ANTHROPIC_CLIENT_CLASS(**params)  # type: ignore[misc]
