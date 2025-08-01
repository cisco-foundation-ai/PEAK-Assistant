#!/usr/bin/env python3

import os
import sys
import asyncio
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils.azure_client import PEAKAssistantAzureOpenAIClient
from utils.assistant_auth import PEAKAssistantAuthManager


async def run_tests():
    auth_mgr = PEAKAssistantAuthManager()

    if auth_mgr.ensure_configured():
        print("✅ Authentication is configured.")
    else:
        print(
            "❌ Authentication is not configured. Please check your environment variables."
        )

    auth_params = await auth_mgr.get_auth_params()
    if auth_params:
        print(f"✅ Successfully retrieved authentication parameters.\n{auth_params}\n")
    else:
        print(
            "❌ Failed to retrieve authentication parameters. Please check your configuration."
        )

    llm_client = await PEAKAssistantAzureOpenAIClient().get_client(auth_mgr=auth_mgr)
    if llm_client:
        print("✅ Azure OpenAI client created successfully.")
        print(llm_client)
    else:
        print(
            "❌ Failed to create Azure OpenAI client. Please check your configuration."
        )


ENVFILE = ".env"
load_dotenv(ENVFILE)

asyncio.run(run_tests())
