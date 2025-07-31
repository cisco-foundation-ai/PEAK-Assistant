"""
Azure OpenAI Client Factory with optional custom authentication
"""

import os
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from .assistant_auth import PEAKAssistantAuthManager


class PEAKAssistantAzureOpenAIClient:
    """
    Create an Azure OpenAI client with authentication.
    """

    async def get_client(
        self,
        auth_mgr: PEAKAssistantAuthManager,
        model_type: str = "chat",
        **extra_params,
    ):
        """
        Create an AzureOpenAIChatCompletionClient with optional authentication.

        Args:
            auth_mgr (PEAKAssistantAuthManager): Authentication manager instance. Required.
            model_type: Type of model to use ("chat", "reasoning"). Default is "chat"
            **extra_params: Additional parameters to pass to the client constructor.

        Returns:
            AzureOpenAIChatCompletionClient: Configured client instance.

        Raises:
            ValueError: If auth_mgr is not provided.
        """

        if not auth_mgr:
            raise ValueError(
                "auth_mgr must be provided to PEAKAssistantAzureOpenAIClient.get_client."
            )

        # Determine the model parameters based on model_type
        if model_type == "chat" or model_type is None:
            params = {
                "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                "model": os.getenv("AZURE_OPENAI_MODEL"),
            }
        elif model_type == "reasoning":
            # try and grab the specifics or fall back to the general ones
            params = {
                "azure_deployment": os.getenv(
                    "AZURE_OPENAI_REASONING_DEPLOYMENT",
                    os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                ),
                "model": os.getenv(
                    "AZURE_OPENAI_REASONING_MODEL", os.getenv("AZURE_OPENAI_MODEL")
                ),
            }
        else:
            raise ValueError(
                "Invalid model type. Must be 'chat', 'reasoning', or None."
            )

        # These parameters don't care which type of model you use.
        params.update(
            {
                "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
                "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            }
        )

        # Merge any extra parameters provided
        params.update(extra_params)

        auth_params = await auth_mgr.get_auth_params()
        if auth_params:
            params.update(auth_params)

        return AzureOpenAIChatCompletionClient(**params)  # type: ignore[arg-type]
