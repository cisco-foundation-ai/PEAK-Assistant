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
