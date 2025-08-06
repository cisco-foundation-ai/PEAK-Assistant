"""
Flask application factory for PEAK Assistant
"""

import os
import logging
import warnings
from flask import Flask, g
from flask_session import Session  # type: ignore[import-untyped]
from flask_sqlalchemy import SQLAlchemy

from .config import config
from peak_assistant.utils import load_env_defaults


# Initialize OAuth manager for MCP server authentication
from peak_assistant.utils.authlib_oauth import init_oauth_manager

# Initialize extensions
db = SQLAlchemy()
session_manager = Session()


def load_initial_context(context_file_path: str) -> str:
    """Load initial local context from context.txt file"""

    if os.path.exists(context_file_path):
        try:
            with open(context_file_path, "r", encoding="utf-8") as f:
                return f.read()
            print(f"Successfully loaded initial context from {context_file_path}")
        except Exception as e:
            print(f"Warning: Could not load context file: {e}")
            return ""
    else:
        print(f"Warning: Context file not found at {context_file_path}")
        return ""


def configure_session(app):
    """Configure the Flask session for robust cross-site handling."""
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_PATH"] = "/"


def create_app(config_name="default", context_path: str = "./context.txt"):
    # Configure logging to show INFO messages
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    """
    Flask application factory
    
    Args:
        config_name: Configuration name ('development', 'production', 'default')
    
    Returns:
        Flask application instance
    """
    # Load environment variables first
    load_env_defaults()

    # Create Flask app
    app = Flask(__name__, template_folder="../templates", static_folder="../static")


    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    # Initialize extensions
    db.init_app(app)

    # Configure and initialize session management
    configure_session(app)
    app.config["SESSION_SQLALCHEMY"] = db
    session_manager.init_app(app)

    oauth_manager = init_oauth_manager(app)

    # Suppress asyncio event loop closure warnings from background HTTP cleanup
    logging.getLogger("httpx").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="asyncio")

    # Register blueprints
    from .routes.api_routes import api_bp
    from .routes.upload_routes import upload_bp
    from .routes.page_routes import page_bp
    from .routes.oauth_routes import oauth_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(page_bp)
    app.register_blueprint(oauth_bp)

    @app.before_request
    def load_context():
        g.context = load_initial_context(context_path)

    # Create database tables
    with app.app_context():
        db.create_all()

    return app

