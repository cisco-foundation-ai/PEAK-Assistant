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
    client = await get_model_client(kind="chat")
    reasoning_client = await get_model_client(kind="reasoning")

Configuration (env-only, enforced):
    - LLM_PROVIDER: azure | openai

Azure:
    - AZURE_OPENAI_API_KEY
    - AZURE_OPENAI_ENDPOINT
    - AZURE_OPENAI_API_VERSION
    - AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_MODEL
    - AZURE_OPENAI_REASONING_DEPLOYMENT (optional)
    - AZURE_OPENAI_REASONING_MODEL (optional)

OpenAI (native and OpenAI-compatible):
    - OPENAI_API_KEY
    - OPENAI_MODEL
    - OPENAI_REASONING_MODEL (optional)
    - OPENAI_BASE_URL (optional; enables OpenAI-compatible endpoints)
    - OPENAI_MODEL_INFO_FILE (optional; JSON file path to a TOP-LEVEL MAPPING of
      model_id -> ModelInfo for non-OpenAI model names when using a custom base_url)
"""

from __future__ import annotations

import os
import json
from typing import Literal, Any, Type

from .assistant_auth import LLMAuthManager


Kind = Literal["chat", "reasoning"]


async def get_model_client(kind: Kind = "chat"):
    """Return a configured model client for the selected provider.

    Args:
        kind: "chat" or "reasoning". If reasoning is not configured for the
              provider, this will fall back to the chat configuration.

    Raises:
        EnvironmentError: if provider selection or required env vars are missing.
        ValueError: for unsupported provider.
    """
    auth_mgr = LLMAuthManager()
    auth_mgr.ensure_configured()

    provider = (os.getenv("LLM_PROVIDER") or "").lower().strip()

    if provider == "azure":
        return await _build_azure_client(kind, auth_mgr)
    elif provider == "openai":
        return await _build_openai_client(kind, auth_mgr)
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Supported: azure, openai."
        )


"""Module-level placeholders for client classes to enable test monkeypatching
without importing heavy dependencies at import time."""
AZURE_CLIENT_CLASS: Type[Any] | None = None
OPENAI_CLIENT_CLASS: Type[Any] | None = None


async def _build_azure_client(kind: Kind, auth_mgr: LLMAuthManager):
    # Determine model/deployment based on kind, with fallback for reasoning
    if kind == "reasoning":
        azure_deployment = os.getenv(
            "AZURE_OPENAI_REASONING_DEPLOYMENT", os.getenv("AZURE_OPENAI_DEPLOYMENT")
        )
        model = os.getenv(
            "AZURE_OPENAI_REASONING_MODEL", os.getenv("AZURE_OPENAI_MODEL")
        )
    else:
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        model = os.getenv("AZURE_OPENAI_MODEL")

    params: dict[str, str | None] = {
        "azure_deployment": azure_deployment,
        "model": model,
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
        "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
    }

    params.update(await auth_mgr.get_auth_params())

    global AZURE_CLIENT_CLASS
    if AZURE_CLIENT_CLASS is None:
        # Lazy import to avoid requiring dependency at module import time
        from autogen_ext.models.openai import AzureOpenAIChatCompletionClient as _AZ

        AZURE_CLIENT_CLASS = _AZ

    return AZURE_CLIENT_CLASS(**params)  # type: ignore[misc]


async def _build_openai_client(kind: Kind, auth_mgr: LLMAuthManager):
    # Determine model based on kind, with fallback for reasoning
    if kind == "reasoning":
        model = os.getenv("OPENAI_REASONING_MODEL", os.getenv("OPENAI_MODEL"))
    else:
        model = os.getenv("OPENAI_MODEL")

    params: dict[str, str | None] = {
        "model": model,
    }

    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        params["base_url"] = base_url

    # Optional: provide model_info for OpenAI-compatible servers when model name
    # is not a recognized OpenAI model. We expect a top-level mapping of model_id -> ModelInfo.
    model_info_file = os.getenv("OPENAI_MODEL_INFO_FILE")
    if model_info_file:
        try:
            with open(model_info_file, "r", encoding="utf-8") as f:
                info_map = json.load(f)
            if not isinstance(info_map, dict):
                raise ValueError(
                    "OPENAI_MODEL_INFO_FILE must be a JSON object mapping model_id -> ModelInfo"
                )
            entry = info_map.get(model)
            if entry is None:
                available = ", ".join(sorted(k for k in info_map.keys() if isinstance(k, str)))
                raise KeyError(
                    f"Model '{model}' not found in OPENAI_MODEL_INFO_FILE mapping. Available: {available}"
                )
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Entry for model '{model}' must be a JSON object containing ModelInfo fields"
                )
            # Ensure 'id' is present and matches the model name
            entry = dict(entry)  # shallow copy in case we need to set id
            entry.setdefault("id", model)
            params["model_info"] = entry
        except Exception as e:
            raise EnvironmentError(
                f"Failed to process OPENAI_MODEL_INFO_FILE '{model_info_file}': {e}"
            ) from e

    params.update(await auth_mgr.get_auth_params())

    global OPENAI_CLIENT_CLASS
    if OPENAI_CLIENT_CLASS is None:
        # Lazy import to avoid requiring dependency at module import time
        from autogen_ext.models.openai import OpenAIChatCompletionClient as _OC

        OPENAI_CLIENT_CLASS = _OC

    try:
        return OPENAI_CLIENT_CLASS(**params)  # type: ignore[misc]
    except ValueError as e:  # Improve guidance for model_info-related errors
        msg = str(e)
        if "model_info" in msg or "ModelInfo" in msg:
            # Provide actionable guidance with required fields
            required_fields = (
                "family, vision, audio, function_calling, json_output, structured_output, "
                "input.max_tokens, output.max_tokens"
            )
            hint_env = (
                "Set OPENAI_MODEL_INFO_FILE to a JSON file that contains a TOP-LEVEL mapping "
                "of model_id -> ModelInfo. Include an entry for the configured model name. "
                "Each ModelInfo must include: " + required_fields + ". The 'id' inside each entry "
                "should match the model_id key. See README 'OpenAI-compatible' section."
            )
            raise EnvironmentError(
                f"OpenAI-compatible model '{model}' appears to require model_info. {hint_env}\nOriginal error: {msg}"
            ) from e
        raise
