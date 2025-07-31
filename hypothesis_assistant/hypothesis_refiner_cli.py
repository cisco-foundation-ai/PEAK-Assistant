#!/usr/bin/env python3

import os
import argparse
from typing import List
from dotenv import load_dotenv
import asyncio

from autogen_agentchat.messages import TextMessage
from utils import find_dotenv_file

from . import refiner


def main() -> None:
    """Hypothesis Refiner CLI"""
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Given a threat hunting technique dossier, generate potential hypotheses for the hunter."
    )
    parser.add_argument("-e", "--environment", help="Path to specific .env file to use")
    parser.add_argument(
        "-y", "--hypothesis", help="The hypothesis to be refined", required=True
    )
    parser.add_argument(
        "-r",
        "--research",
        help="Path to the research document (markdown file)",
        required=True,
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
        "-a",
        "--automated",
        action="store_true",
        help="Enable automated mode",
        default=False,
    )

    # Parse the arguments
    args = parser.parse_args()

    # Enforce verbose behavior based on the automated flag
    if not args.automated:
        # Force verbose to True if not in automated mode
        args.verbose = True

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

    messages: List[TextMessage] = list()
    current_hypothesis = args.hypothesis
    while True:
        # Run the hypothesizer asynchronously
        response = asyncio.run(
            refiner(
                hypothesis=current_hypothesis,
                local_context=local_context,
                research_document=research_data,
                verbose=args.verbose,
                previous_run=messages,
            )
        )

        # Find the final message from the "critic" agent using next() and a generator expression
        refined_hypothesis_message = next(
            (
                getattr(message, "content")
                for message in reversed(response.messages)
                if hasattr(message, "content") and message.source == "critic"
            ),
            "something went wrong",  # Default value if no "critic" message is found
        )

        # Remove the trailing "YYY-HYPOTHESIS-ACCEPTED-YYY" string
        current_hypothesis = refined_hypothesis_message.replace(
            "YYY-HYPOTHESIS-ACCEPTED-YYY", ""
        ).strip()

        # Print the refined hypothesis and ask for user feedback
        print(f"Hypothesis:\n\n{current_hypothesis}")

        if not args.automated:
            feedback = input(
                "Please provide your feedback on the refined hypothesis (or press Enter to approve it): "
            )

            if feedback.strip():
                # If feedback is provided, add it to the messages and loop back to the refiner
                messages.append(
                    TextMessage(content=f"User feedback: {feedback}\n", source="user")
                )
            else:
                break
        else:
            # In automated mode, just print the refined hypothesis and exit
            # print("Automated mode: No user feedback will be collected.")
            if "YYY-HYPOTHESIS-ACCEPTED-YYY" in refined_hypothesis_message:
                print("Automated mode: Hypothesis refinement completed.")
                break


# Example usage
if __name__ == "__main__":
    main()
