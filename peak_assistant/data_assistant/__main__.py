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
import argparse
from typing import List
from dotenv import load_dotenv
import asyncio

from autogen_agentchat.messages import TextMessage

from . import identify_data_sources
from ..utils import find_dotenv_file
from ..utils.agent_callbacks import (
    preprocess_messages_logging,
    postprocess_messages_logging,
)


def main() -> None:
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
        "-l",
        "--local-data",
        help="Path to the local data document (markdown file)",
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
    parser.add_argument(
        "--no-feedback",
        action="store_true",
        help="Skip user feedback and automatically accept the generated data discovery report"
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

    # Read the contents of the ABLE information if provided
    able_info = ""
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

    # Read the contents of the local data document if provided
    local_data = ""
    if args.local_data:
        try:
            with open(args.local_data, "r", encoding="utf-8") as file:
                local_data = file.read()
        except FileNotFoundError:
            print(f"Error: Local data document '{args.local_data}' not found")
            exit(1)
        except Exception as e:
            print(f"Error reading local data document: {e}")
            exit(1)

    # Read the contents of the local context if provided
    local_context = ""
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
                local_data_document=local_data,
                able_info=able_info,
                local_context=local_context,
                verbose=args.verbose,
                previous_run=messages,
                msg_preprocess_callback=preprocess_messages_logging,
                msg_preprocess_kwargs={"agent_id": "data-discovery"},
                msg_postprocess_callback=postprocess_messages_logging,
                msg_postprocess_kwargs={"agent_id": "data-discovery"},
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
        
        if args.no_feedback:
            print("Skipping user feedback (--no-feedback enabled)")
            break
        
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


if __name__ == "__main__":
    main()
