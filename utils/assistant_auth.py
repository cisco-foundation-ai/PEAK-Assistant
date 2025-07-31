"""
PEAK Assistant Authentication Manager
"""

import os


class PEAKAssistantAuthManager:
    """Manages PEAK Assistant authentication."""

    def __init__(self):
        self._api_key = os.getenv("AZURE_OPENAI_API_KEY")

    def ensure_configured(self):
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

    async def get_auth_params(self) -> dict:
        """
        Get authentication parameters for API requests

        Returns:
            dict: Contains authentication parameters
        """

        auth_params = dict()
        auth_params["api_key"] = self._api_key

        return auth_params
