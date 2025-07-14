#!/usr/bin/env python3

import os
import sys
import asyncio
import httpx 

from dotenv import load_dotenv
from pathlib import Path

from mcp.server.fastmcp import FastMCP 

# Add the parent directory to sys.path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from research_assistant.research_assistant_cli import researcher as async_researcher
from hypothesis_assistant.hypothesis_assistant_cli import hypothesizer as async_hypothesizer
from hypothesis_assistant.hypothesis_refiner_cli import refiner as async_refiner
from able_assistant.able_assistant_cli import able_table as async_able_table
from data_assistant.data_asssistant_cli import identify_data_sources as async_identify_data_sources
from planning_assistant.planning_assistant_cli import plan_hunt as async_plan_hunt

mcp = FastMCP("peak-assistant")

def find_dotenv_file():
    """Search for a .env file in current directory and parent directories"""
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:  # Stop at root directory
        env_path = current_dir / '.env'
        if env_path.exists():
            return str(env_path)
        current_dir = current_dir.parent
    return None  # No .env file found

@mcp.tool()
async def researcher(
    technique: str = None, 
    local_context: str = None
) -> str:
    """
    Orchestrates a multi-agent, multi-stage research workflow to generate a 
    comprehensive cybersecurity threat hunting report for a specified 
    technique or behavior.

    Args:
        technique (str): The name or description of the threat actor
            technique or behavior to research.
        local_context (str, optional): Additional context or constraints to guide
            the research (e.g., environment, use case).

    Returns:
        str: A string containing the Markdown formatted research report, or an error 
            message if the process fails.
    """
    result = await async_researcher(technique, local_context)

    report = next(
        (message.content for message in reversed(result.messages) if message.source == "summarizer"),
        None
    )

    return report

#@mcp.tool()
#async def hypothesizer(technique: str = None, local_context: str = None, verbose: bool = False, previous_run: list = None) -> str:
#    return await async_hypothesizer(technique, local_context, verbose, previous_run)
#
#@mcp.tool()
#async def refiner(technique: str = None, local_context: str = None, verbose: bool = False, previous_run: list = None) -> str:
#    return await async_refiner(technique, local_context, verbose, previous_run)
#
#@mcp.tool()
#async def able_table(technique: str = None, local_context: str = None, verbose: bool = False, previous_run: list = None) -> str:
#    return await async_able_table(technique, local_context, verbose, previous_run)
#
#@mcp.tool()
#async def identify_data_sources(technique: str = None, local_context: str = None, verbose: bool = False, previous_run: list = None) -> str:
#    return await async_identify_data_sources(technique, local_context, verbose, previous_run)
#
#@mcp.tool()
#async def plan_hunt(technique: str = None, local_context: str = None, verbose: bool = False, previous_run: list = None) -> str:
    return await async_plan_hunt(technique, local_context, verbose, previous_run)

#### MAIN ####

if __name__ == "__main__":
    load_dotenv(find_dotenv_file())
    mcp.run(transport="stdio")

