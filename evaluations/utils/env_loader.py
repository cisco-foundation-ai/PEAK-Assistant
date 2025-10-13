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
Environment variable loading utilities for evaluation scripts.

Provides automatic .env file discovery and loading for environment variable
interpolation in model_config.json files.
"""

from __future__ import annotations

import sys
from typing import Optional

from dotenv import load_dotenv

# Import find_dotenv_file from centralized location
from peak_assistant.utils import find_dotenv_file


def load_environment(quiet: bool = False) -> None:
    """Load environment variables from .env file if found.
    
    Searches for a .env file in the current directory and parent directories,
    loading any environment variables it finds. Prints status messages to stderr
    unless quiet mode is enabled.
    
    Args:
        quiet: If True, suppress status messages.
    """
    dotenv_path = find_dotenv_file()
    if dotenv_path:
        load_dotenv(dotenv_path)
        if not quiet:
            print(f"Loaded environment variables from {dotenv_path}", file=sys.stderr)
    else:
        if not quiet:
            print("Warning: No .env file found. Environment variables must be set manually.", file=sys.stderr)
