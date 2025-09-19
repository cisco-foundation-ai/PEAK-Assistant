#!/usr/bin/env python3

import os
import argparse
import asyncio
import re
from typing import List
from dotenv import load_dotenv

from autogen_agentchat.messages import TextMessage

from markdown_pdf import MarkdownPdf, Section


from ..utils import find_dotenv_file
from ..utils.agent_callbacks import (
    preprocess_messages_logging,
    postprocess_messages_logging,
)

from . import researcher


def generate_unique_filename(title, extension):
    """Generate a unique filename based on the title and extension."""
    sanitized_title = re.sub(r"[^a-zA-Z0-9_]", "_", title.lower().strip())
    base_filename = f"{sanitized_title}{extension}"
    counter = 0

    while os.path.exists(base_filename):
        counter += 1
        base_filename = f"{sanitized_title} ({counter}){extension}"

    return base_filename


def get_input_function():
    # Always use standard input (Flask integration removed)
    return input


def main() -> None:
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Generate a threat hunting report for a specific technique"
    )
    parser.add_argument(
        "-t",
        "--technique",
        required=True,
        help="The cybersecurity technique to research",
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
        "-f",
        "--format",
        choices=["pdf", "markdown"],
        default="markdown",
        help="Output report format: pdf or markdown",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-s",
        "--skip-feedback",
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
            "msg_preprocess_kwargs": {"agent_id": "researcher"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "researcher"},
        }
    while True:
        # Run the researcher asynchronously
        task_result = asyncio.run(
            researcher(
                technique=args.technique,
                local_context=local_context or "",
                verbose=args.verbose,
                previous_run=messages,
                **debug_agents_opts
            )
        )

        # Find the final message from the "summarizer_agent" using next() and a generator expression
        report = next(
            (
                getattr(message, "content", None)
                for message in reversed(task_result.messages)
                if message.source == "summarizer_agent" and hasattr(message, "content")
            ),
            "no report generated",  # Default value if no "summarizer_agent" message is found
        )

        if not report:
            print("No report generated. Please check the input and try again.")
            return

        # Display the report and ask for user feedback (unless skipped)
        print(f"Report:\n{report}\n")
        
        if args.skip_feedback:
            print("Skipping user feedback (--skip-feedback enabled)")
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

    # Extract the title from the report (assuming the first line is the title)
    title = report.splitlines()[0] if report else "untitled_report"

    # Remove any markdown or extraneous whitespace from the title
    title = re.sub(r"^[#\s]+", "", title).strip()  # Sanitize the title

    # Determine the file extension based on the selected format
    if args.format == "pdf":
        extension = ".pdf"
    elif args.format == "markdown":
        extension = ".md"
    else:
        print(f"Error: Unsupported format '{args.format}'")
        return

    filename = generate_unique_filename(title, extension)

    # Save the report in the selected format
    if args.format == "pdf":
        pdf = MarkdownPdf(toc_level=1)
        pdf.add_section(Section(report))
        pdf.save(filename)
    else:
        with open(filename, "w") as file:
            file.write(report)

    print(f"Report saved as {filename}")


if __name__ == "__main__":
    main()
