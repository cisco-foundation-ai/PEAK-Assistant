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
Output formatting utilities for evaluation scripts.

Provides consistent output formatting, markdown rendering, and progress tracking
across all evaluation scripts.
"""

from __future__ import annotations

import sys
from io import StringIO
from typing import Optional, Any


def print_markdown(
    markdown_text: str,
    log_buffer: Optional[StringIO] = None,
    quiet: bool = False,
    rich_mode: bool = False,
    console: Optional[Any] = None,
    markdown_class: Optional[Any] = None,
) -> None:
    """Print markdown-formatted text with optional rich rendering.
    
    Args:
        markdown_text: The markdown text to print
        log_buffer: Optional StringIO buffer to write to
        quiet: If True, suppress console output
        rich_mode: If True and rich is available, render with rich
        console: Rich Console instance (required if rich_mode=True)
        markdown_class: Rich Markdown class (required if rich_mode=True)
    """
    # Always write to log buffer if provided
    if log_buffer is not None:
        log_buffer.write(markdown_text + "\n")
    
    # Print to console unless quiet
    if not quiet:
        if rich_mode and console and markdown_class:
            # Render with rich for beautiful output
            console.print(markdown_class(markdown_text))
        else:
            # Plain text output
            print(markdown_text)


def setup_rich_rendering(quiet: bool = False) -> tuple[bool, Optional[Any], Optional[Any]]:
    """Setup rich rendering if available.
    
    Args:
        quiet: If True, suppress warning messages
    
    Returns:
        Tuple of (rich_mode, console, Markdown_class)
        - rich_mode: True if rich is available
        - console: Rich Console instance or None
        - Markdown_class: Rich Markdown class or None
    """
    try:
        from rich.console import Console  # type: ignore
        from rich.markdown import Markdown  # type: ignore
        return True, Console(), Markdown
    except Exception:
        if not quiet:
            print(
                "Tip: Install rich for better formatted output: pip install rich",
                file=sys.stderr
            )
        return False, None, None
