#!/usr/bin/env python3

import os
import sys
import argparse
from dotenv import load_dotenv
import asyncio

from autogen_agentchat.messages import TextMessage

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils import find_dotenv_file

from . import plan_hunt

def main() -> None:
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Given the outputs of all the other Prepare-phase agents, create an actionable plan for the hunt."
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
        "-d",
        "--data_discovery",
        help="Data discovery information from previous agents",
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

    # Read the contents of the data discovery information if provided
    data_discovery = None
    if args.data_discovery:
        try:
            with open(args.data_discovery, "r", encoding="utf-8") as file:
                data_discovery = file.read()
        except FileNotFoundError:
            print(f"Error: Data discovery file '{args.data_discovery}' not found")
            exit(1)
        except Exception as e:
            print(f"Error reading data discovery information: {e}")
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

    messages = list()
    while True:
        # Run the hypothesizer asynchronously
        data_sources = asyncio.run(
            plan_hunt(
                hypothesis=args.hypothesis,
                research_document=research_data,
                able_info=able_info,
                data_discovery=data_discovery,
                local_context=local_context,
                verbose=args.verbose,
                previous_run=messages,
            )
        )

        # Find the final message from the "hunt_planner" agent using next() and a generator expression
        hunt_plan = next(
            (
                message.content
                for message in reversed(data_sources.messages)
                if message.source == "hunt_planner"
            ),
            None,  # Default value if no "hunt_planner" message is found
        )

        print(hunt_plan)
        feedback = input(
            "Please provide your feedback on the plan (or press Enter to approve it): "
        )

        if feedback.strip():
            # If feedback is provided, add it to the messages and loop back to
            # the research team for further refinement
            messages = [
                TextMessage(
                    content=f"The current plan draft is: {hunt_plan}\n", source="user"
                ),
                TextMessage(content=f"User feedback: {feedback}\n", source="user"),
            ]
        else:
            break


if __name__ == "__main__":
    main()
