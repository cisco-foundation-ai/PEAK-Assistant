"""
Azure OpenAI Client Factory with optional custom authentication
"""
import os
import asyncio
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from .assistant_auth import PEAKAssistantAuthManager

class PEAKAssistantAzureOpenAIClient:
    """
    Create an Azure OpenAI client with authentication.
    """

    async def get_client(self, auth_mgr: PEAKAssistantAuthManager = None, **extra_params):
        """
        Create an AzureOpenAIChatCompletionClient with optional authentication.

        Args:
            auth_mgr (PEAKAssistantAuthManager): Authentication manager instance. Required.
            **extra_params: Additional parameters to pass to the client constructor.

        Returns:
            AzureOpenAIChatCompletionClient: Configured client instance.

        Raises:
            ValueError: If auth_mgr is not provided.
        """
        if auth_mgr is None:
            raise ValueError("auth_mgr must be provided to create_azure_openai_client.")
        
        # Base parameters from environment
        params = {
            "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            "model": os.getenv("AZURE_OPENAI_MODEL"),
            "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
        }
        
        # Merge any extra parameters provided
        params.update(extra_params)
        
        auth_params = await auth_mgr.get_auth_params()
        if auth_params:
            params.update(auth_params)

    #    # Add additional authentication headers if configured
    #    if assistant_auth.is_enabled():
    #        circuit_token = await circuit_auth.get_access_token()
    #        params["api_key"] = circuit_token
    #        params["user"] = f'{{"appkey": "{circuit_auth.app_key}"}}'
    #    else:
    #        params["api_key"] = os.getenv("AZURE_OPENAI_API_KEY")
        
        return AzureOpenAIChatCompletionClient(**params)
