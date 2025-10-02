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

from typing import Optional, Any, Type
from pathlib import Path

from .model_config_loader import get_loader, ModelConfigError


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
        else:
            raise ValueError(
                f"Unsupported provider type '{provider_type}'. Supported: azure, openai."
            )
    except ModelConfigError:
        raise
    except Exception as e:
        raise ModelConfigError(
            f"Failed to create model client for agent '{agent_name or 'defaults'}': {e}"
        ) from e


"""Module-level placeholders for client classes to enable test monkeypatching
without importing heavy dependencies at import time."""
AZURE_CLIENT_CLASS: Type[Any] | None = None
OPENAI_CLIENT_CLASS: Type[Any] | None = None


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
    
    # Get connection config from provider
    conn_config = provider_config["config"]
    
    # Validate required provider fields
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
