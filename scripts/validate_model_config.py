#!/usr/bin/env python3
"""
Command-line tool to validate model_config.json.

Usage:
    python scripts/validate_model_config.py
    python scripts/validate_model_config.py --config /path/to/model_config.json
    python scripts/validate_model_config.py --check-env
    python scripts/validate_model_config.py --quiet
"""

import sys
from pathlib import Path

# Add parent directory to path to import peak_assistant
sys.path.insert(0, str(Path(__file__).parent.parent))

from peak_assistant.utils.validate_config import main

if __name__ == "__main__":
    main()
