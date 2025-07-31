#!/usr/bin/env python3

import os
import sys
import argparse

from typing import List
from dotenv import load_dotenv
import asyncio

from autogen_core.models import UserMessage

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from . import able_table
from utils import find_dotenv_file


def main() -> None:
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Given a threat hunting technique dossier, generate potential hypotheses for the hunter."
    )
    parser.add_argument("-e", "--environment", help="Path to specific .env file to use")
    parser.add_argument(
        "-r",
        "--research",
        help="Path to the research document (markdown file)",
        required=True,
    )
    parser.add_argument(
        "-y", "--hypothesis", help="The hunting hypothesis", required=True, default=""
    )
    parser.add_argument(
        "-c",
        "--local_context",
        help="Additional local context to consider",
        required=False,
        default=None,
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

    messages: List[UserMessage] = list()
    while True:
        # Run the hypothesizer asynchronously
        able = asyncio.run(
            able_table(
                hypothesis=args.hypothesis,
                research_document=research_data,
                local_context=local_context,
                previous_run=messages,
            )
        )
        print(able)

        feedback = input(
            "Please provide your feedback on the ABLE table (or press Enter to approve it): "
        )

        if feedback.strip():
            # If feedback is provided, add it to the messages and loop back to
            # the research team for further refinement
            messages = [
                UserMessage(
                    content=f"The current ABLE draft is: {able}\n", source="user"
                ),
                UserMessage(content=f"User feedback: {feedback}\n", source="user"),
            ]
        else:
            break


# Example usage
if __name__ == "__main__":
    main()
