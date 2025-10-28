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
Environment variable utilities for PEAK Assistant.

This module provides utilities for:
- Finding and loading .env files
- Interpolating environment variables in configuration files
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv


class ConfigInterpolationError(Exception):
    """Raised when environment variable interpolation fails."""
    pass


def find_dotenv_file() -> Optional[str]:
    """Search for a .env file in current directory and parent directories.
    
    Returns:
        Path to .env file if found, None otherwise
    """
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:  # Stop at root directory
        env_path = current_dir / ".env"
        if env_path.exists():
            return str(env_path)
        current_dir = current_dir.parent
    return None  # No .env file found


def load_env_defaults() -> None:
    """Load environment variables from .env file.
    
    Searches for a .env file using find_dotenv_file() and loads it.
    Prints a warning if no .env file is found.
    """
    dotenv_path = find_dotenv_file()
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        print("Warning: No .env file found in current or parent directories")


def interpolate_env_vars(obj: Any) -> Any:
    """Recursively interpolate ${ENV_VAR} in strings.
    
    Supports ${ENV_VAR|default} syntax for defaults.
    Special case: ${VAR|null} returns empty string.
    
    Args:
        obj: Object to interpolate (string, dict, list, or other)
    
    Returns:
        Object with environment variables interpolated
    
    Raises:
        ConfigInterpolationError: If environment variable not found and no default provided
    
    Examples:
        >>> os.environ['MY_VAR'] = 'value'
        >>> interpolate_env_vars("${MY_VAR}")
        'value'
        >>> interpolate_env_vars("${MISSING|default}")
        'default'
        >>> interpolate_env_vars({"key": "${MY_VAR}"})
        {'key': 'value'}
    """
    if isinstance(obj, str):
        # Match ${VAR} or ${VAR|default}
        pattern = r'\$\{([^}|]+)(?:\|([^}]*))?\}'
        
        def replacer(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else None
            
            value = os.getenv(var_name)
            if value is None:
                if default_value is not None:
                    # Handle special case: ${VAR|null} -> empty string
                    return "" if default_value == "null" else default_value
                else:
                    raise ConfigInterpolationError(
                        f"Environment variable {var_name} not found and no default provided"
                    )
            return value
        
        return re.sub(pattern, replacer, obj)
    elif isinstance(obj, dict):
        return {k: interpolate_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [interpolate_env_vars(item) for item in obj]
    else:
        return obj
