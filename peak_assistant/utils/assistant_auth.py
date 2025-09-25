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
PEAK Assistant Authentication Manager
"""

import os
from typing import Optional


class PEAKAssistantAuthManager:
    """Manages PEAK Assistant authentication."""

    def __init__(self) -> None:
        self._api_key = os.getenv("AZURE_OPENAI_API_KEY")

    def ensure_configured(self) -> bool:
        """
        Ensure all required authentication environment variables are set,
        else raise exception
        """
        missing = []
        if not self._api_key:
            missing.append("AZURE_OPENAI_API_KEY")

        if missing:
            raise EnvironmentError(
                f"Missing required environment variable(s): {', '.join(missing)}"
            )
        else:
            return True

    async def get_auth_params(self) -> dict[str, Optional[str]]:
        """
        Get authentication parameters for API requests

        Returns:
            dict: Contains authentication parameters
        """

        auth_params = dict()
        auth_params["api_key"] = self._api_key

        return auth_params


class LLMAuthManager:
    """Provider-aware authentication manager for the LLM factory.

    Reads environment variables based on the selected provider and exposes
    provider-agnostic auth parameters (e.g., api_key).
    """

    def __init__(self) -> None:
        self._provider = os.getenv("LLM_PROVIDER")
        # Defer reading provider-specific keys until validation to keep state simple

    def ensure_configured(self) -> bool:
        """Validate that required env vars for the selected provider are present.

        Raises:
            EnvironmentError: if LLM_PROVIDER is missing or required values are missing.
        """

        if not self._provider:
            raise EnvironmentError(
                "LLM_PROVIDER is required. Set it to 'azure' or 'openai'."
            )

        prov = self._provider.lower().strip()
        missing: list[str] = []

        if prov == "azure":
            # Required for Azure
            if not os.getenv("AZURE_OPENAI_API_KEY"):
                missing.append("AZURE_OPENAI_API_KEY")
            if not os.getenv("AZURE_OPENAI_ENDPOINT"):
                missing.append("AZURE_OPENAI_ENDPOINT")
            if not os.getenv("AZURE_OPENAI_API_VERSION"):
                missing.append("AZURE_OPENAI_API_VERSION")
            # Chat model/deployment required; reasoning is optional
            if not os.getenv("AZURE_OPENAI_DEPLOYMENT"):
                missing.append("AZURE_OPENAI_DEPLOYMENT")
            if not os.getenv("AZURE_OPENAI_MODEL"):
                missing.append("AZURE_OPENAI_MODEL")
        elif prov == "openai":
            # Required for OpenAI/OpenAI-compatible
            if not os.getenv("OPENAI_API_KEY"):
                missing.append("OPENAI_API_KEY")
            if not os.getenv("OPENAI_MODEL"):
                missing.append("OPENAI_MODEL")
            # OPENAI_BASE_URL is optional for OpenAI-compatible endpoints
        else:
            raise EnvironmentError(
                f"Unsupported LLM_PROVIDER '{self._provider}'. Supported: azure, openai."
            )

        if missing:
            raise EnvironmentError(
                f"Missing required environment variable(s) for provider '{prov}': {', '.join(missing)}"
            )

        return True

    async def get_auth_params(self) -> dict[str, Optional[str]]:
        """Return provider-agnostic authentication params for the model client."""

        prov = (self._provider or "").lower().strip()
        if prov == "azure":
            return {"api_key": os.getenv("AZURE_OPENAI_API_KEY")}
        elif prov == "openai":
            return {"api_key": os.getenv("OPENAI_API_KEY")}
        # Should not reach here due to ensure_configured
        return {"api_key": None}
