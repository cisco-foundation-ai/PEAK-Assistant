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

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def find_dotenv_file() -> Optional[str]:
    """Search for a .env file in current directory and parent directories"""
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:  # Stop at root directory
        env_path = current_dir / ".env"
        if env_path.exists():
            return str(env_path)
        current_dir = current_dir.parent
    return None  # No .env file found


def load_env_defaults() -> None:
    """Load environment variables from .env file"""
    dotenv_path = find_dotenv_file()
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        print("Warning: No .env file found in current or parent directories")
