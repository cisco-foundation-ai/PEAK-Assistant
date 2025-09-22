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
