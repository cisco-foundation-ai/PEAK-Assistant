#!/usr/bin/env python3
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


import os
import sys
import argparse
import asyncio
from typing import List
from dotenv import load_dotenv

from autogen_agentchat.messages import TextMessage

from ..utils import find_dotenv_file
from ..utils.agent_callbacks import (
    preprocess_messages_logging,
    postprocess_messages_logging,
)

from . import local_data_searcher


def main() -> None:
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Search local data sources for information relevant to threat hunting"
    )
    parser.add_argument(
        "-t",
        "--technique",
        required=True,
        help="The cybersecurity technique to research",
    )
    parser.add_argument(
        "-r",
        "--research",
        required=True,
        help="Path to the research document for context (markdown file)",
    )
    parser.add_argument(
        "-c",
        "--local_context",
        help="Additional local context to consider",
        required=False,
        default=None,
    )
    parser.add_argument("-e", "--environment", help="Path to specific .env file to use")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--no-feedback",
        action="store_true",
        help="Skip user feedback and automatically accept the generated report"
    )
    parser.add_argument(
        "--debug-agents",
        action="store_true",
        help="Enable agent debug logging to msgs.txt and results.txt"
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

    debug_agents_opts = dict() 

    # If debug agents is enabled, add the debug options
    if args.debug_agents:
        debug_agents_opts = {
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "local_data_searcher"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "local_data_searcher"},
        }
    
    while True:
        try:
            # Run the local data searcher asynchronously
            task_result = asyncio.run(
                local_data_searcher(
                    technique=args.technique,
                    local_context=local_context or "",
                    research_document=research_data,
                    verbose=args.verbose,
                    previous_run=messages,
                    **debug_agents_opts
                )
            )
        except RuntimeError as e:
            # Handle case where no MCP servers are available
            if "No MCP workbenches available" in str(e):
                print("⚠️  No MCP servers available for local data search", file=sys.stderr)
                print("# Local Data Search Report\n\nNo local data sources available.")
                return
            raise

        # Find the final message from the "local_data_summarizer_agent" using next() and a generator expression
        report = next(
            (
                getattr(message, "content", None)
                for message in reversed(task_result.messages)
                if message.source == "local_data_summarizer_agent" and hasattr(message, "content")
            ),
            "no report generated",  # Default value if no "local_data_summarizer_agent" message is found
        )

        if not report:
            print("No report generated. Please check the input and try again.")
            return

        # Remove the termination string
        report = report.replace("YYY-TERMINATE-YYY", "").strip()

        # Display the report and ask for user feedback (unless skipped)
        print(f"Report:\n{report}\n")
        
        if args.no_feedback:
            print("Skipping user feedback (--no-feedback enabled)")
            break
        
        feedback = input(
            "Please provide your feedback on the report (or press Enter to approve it): "
        )

        if feedback.strip():
            # If feedback is provided, add it to the messages and loop back to
            # the research team for further refinement
            messages = [
                TextMessage(
                    content=f"The current report draft is: {report}\n", source="user"
                ),
                TextMessage(content=f"User feedback: {feedback}\n", source="user"),
            ]
        else:
            break

    # Output final report to stdout (already printed above)


if __name__ == "__main__":
    main()
