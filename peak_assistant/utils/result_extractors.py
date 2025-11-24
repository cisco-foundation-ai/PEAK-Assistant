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
Centralized result extraction utilities for PEAK Assistant agents.

This module provides a unified interface for extracting final results from
agent outputs, ensuring consistency across CLI, Web UI, and MCP tool interfaces.
"""

from autogen_agentchat.base import TaskResult
from typing import Union, Optional

# Configuration mapping agent names to extraction parameters
# Format: (agent_source, cleanup_patterns, default_message)
AGENT_EXTRACTION_CONFIG = {
    "researcher": ("summarizer_agent", [], "no report generated"),
    "local_data_searcher": ("local_data_summarizer_agent", ["YYY-TERMINATE-YYY"], "no local data report generated"),
    "refiner": ("refiner", ["YYY-HYPOTHESIS-ACCEPTED-YYY"], "something went wrong"),
    "data_discovery": ("Data_Discovery_Agent", [], None),
    "hunt_planner": ("hunt_planner", [], "no plan was generated"),
}


def extract_agent_result(
    result: Union[TaskResult, str],
    agent_name: str
) -> str:
    """
    Extract the final result from an agent's output.
    
    This function handles both TaskResult objects (from multi-agent workflows)
    and direct string returns (from single-agent workflows like hypothesizer
    and able_table).
    
    Args:
        result: TaskResult from agent or string (for agents that return strings directly)
        agent_name: Name of the agent (key from AGENT_EXTRACTION_CONFIG)
    
    Returns:
        Extracted and cleaned string result
        
    Raises:
        ValueError: If agent_name is not recognized
    """
    # If result is already a string, return it directly
    if isinstance(result, str):
        return result
    
    # Get extraction configuration
    if agent_name not in AGENT_EXTRACTION_CONFIG:
        raise ValueError(f"Unknown agent name: {agent_name}")
    
    agent_source, cleanup_patterns, default_message = AGENT_EXTRACTION_CONFIG[agent_name]
    
    # Extract message from TaskResult
    extracted_content = next(
        (
            getattr(message, "content", None)
            for message in reversed(result.messages)
            if message.source == agent_source and hasattr(message, "content")
        ),
        default_message,
    )
    
    # If we got None and there's no default, return empty string
    if extracted_content is None:
        return ""
    
    # Clean up any termination markers
    for pattern in cleanup_patterns:
        extracted_content = extracted_content.replace(pattern, "")
    
    return extracted_content.strip()


# Convenience wrapper functions for better readability
def extract_research_report(result: TaskResult) -> str:
    """Extract research report from researcher agent result."""
    return extract_agent_result(result, "researcher")


def extract_local_data_report(result: TaskResult) -> str:
    """Extract local data report from local_data_searcher agent result."""
    return extract_agent_result(result, "local_data_searcher")


def extract_refined_hypothesis(result: TaskResult) -> str:
    """Extract refined hypothesis from refiner agent result."""
    return extract_agent_result(result, "refiner")


def extract_data_discovery_report(result: TaskResult) -> str:
    """Extract data discovery report from data_discovery agent result."""
    return extract_agent_result(result, "data_discovery")


def extract_hunt_plan(result: TaskResult) -> str:
    """Extract hunt plan from hunt_planner agent result."""
    return extract_agent_result(result, "hunt_planner")


def extract_hypotheses(result: str) -> str:
    """Pass-through for hypothesizer agent (already returns string)."""
    return extract_agent_result(result, "hypothesizer")


def extract_able_table(result: str) -> str:
    """Pass-through for able_table agent (already returns string)."""
    return extract_agent_result(result, "able_table")
