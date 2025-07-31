#!/usr/bin/env python3

import os
import sys
import argparse
from typing import List
from dotenv import load_dotenv
import asyncio

from autogen_agentchat.messages import TextMessage

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_assistant import identify_data_sources
from utils import find_dotenv_file


def main() -> None:
    """Data Assistant CLI"""

    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Given a threat hunting technique dossier and a hypothesis, determine what relevant data is present on the Splunk server."
    )
    parser.add_argument("-e", "--environment", help="Path to specific .env file to use")
    parser.add_argument(
        "-r",
        "--research",
        help="Path to the research document (markdown file)",
        required=True,
    )
    parser.add_argument(
        "-y", "--hypothesis", help="The hunting hypothesis", required=True
    )
    parser.add_argument(
        "-a",
        "--able_info",
        help="The Actor, Behavior, Location and Evidence (ABLE) information",
        required=False,
        default=None,
    )
    parser.add_argument(
        "-c",
        "--local_context",
        help="Additional local context to consider",
        required=False,
        default=None,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
        default=False,
    )
    args = parser.parse_args()

    # Load environment variables
    if args.environment:
        # Use the specified .env file
        dotenv_path = args.environment
        if not os.path.exists(dotenv_path):
            print(f"Error: Specified environment file '{dotenv_path}' not found")
            exit(1)
        load_dotenv(dotenv_path)
    else:
        # Search for .env file
        dotenv_path = find_dotenv_file()
        if dotenv_path:
            load_dotenv(dotenv_path)
        else:
            print("Warning: No .env file found in current or parent directories")

    mcp_command = os.getenv("SPLUNK_MCP_COMMAND")
    mcp_args = os.getenv("SPLUNK_MCP_ARGS")
    # Get the MCP command and arguments from environment variables
    if not mcp_command or not mcp_args:
        print(
            "Error: SPLUNK_MCP_COMMAND and SPLUNK_MCP_ARGS environment variables must be set"
        )
        exit(1)

    # Read the contents of the research document
    try:
        with open(args.research, "r", encoding="utf-8") as file:
            research_data = file.read()
    except FileNotFoundError:
        print(f"Error: Research document '{args.research}' not found")
        exit(1)
    except Exception as e:
        print(f"Error reading research document: {e}")
        exit(1)

    # Read the contents of the ABLE information if provided
    able_info = None
    if args.able_info:
        try:
            with open(args.able_info, "r", encoding="utf-8") as file:
                able_info = file.read()
        except FileNotFoundError:
            print(f"Error: ABLE information file '{args.able_info}' not found")
            exit(1)
        except Exception as e:
            print(f"Error reading ABLE information: {e}")
            exit(1)

    # Read the contents of the local context if provided
    local_context = None
    if args.local_context:
        try:
            with open(args.local_context, "r", encoding="utf-8") as file:
                local_context = file.read()
        except FileNotFoundError:
            print(f"Error: Local context file '{args.local_context}' not found")
            exit(1)
        except Exception as e:
            print(f"Error reading local context: {e}")
            exit(1)

    messages: List[TextMessage] = list()
    while True:
        # Run the hypothesizer asynchronously
        data_sources = asyncio.run(
            identify_data_sources(
                hypothesis=args.hypothesis,
                research_document=research_data,
                able_info=able_info or "",
                local_context=local_context or "",
                mcp_command=mcp_command,
                mcp_args=mcp_args.split(),
                verbose=args.verbose,
                previous_run=messages,
            )
        )

        # Find the final message from the "critic" agent using next() and a generator expression
        data_sources_message = next(
            (
                getattr(message, "content", None)
                for message in reversed(data_sources.messages)
                if hasattr(message, "content")
                and message.source == "Data_Discovery_Agent"
            ),
            None,  # Default value if no "critic" message is found
        )

        # Display the data sources and ask for user feedback
        print(data_sources_message)
        feedback = input(
            "Please provide your feedback on the data sources (or press Enter to approve it): "
        )

        if feedback.strip():
            # If feedback is provided, add it to the messages and loop back to
            # the data discovery team for further refinement
            messages = [
                TextMessage(
                    content=f"The current data sources draft is: {data_sources_message}\n",
                    source="user",
                ),
                TextMessage(content=f"User feedback: {feedback}\n", source="user"),
            ]
        else:
            break


# Example usage
if __name__ == "__main__":
    main()
