#!/usr/bin/env python3
"""
PEAK Assistant - Modular Flask Application
Streamlined entry point using factory pattern
"""

import os
import sys
from .app.factory import create_app

# Determine configuration based on environment
config_name = os.environ.get("FLASK_CONFIG", "development")

# Create Flask application using factory pattern
app = create_app(config_name)

# Make INITIAL_LOCAL_CONTEXT available to route modules
from .app.routes.api_routes import INITIAL_LOCAL_CONTEXT  # type: ignore[unused-import] # noqa: E402, F401
from .app.routes import api_routes  # noqa: E402

api_routes.INITIAL_LOCAL_CONTEXT = app.config.get("INITIAL_LOCAL_CONTEXT", "")


def main() -> None:
    """
    Main entry point for the Flask application.
    Sets up the application context and runs the server.
    """
    # Create templates directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

    app.logger.info(
        "Note: You may see 'Task exception was never retrieved' errors related to HTTP client cleanup."
    )
    app.logger.info(
        "These are harmless and don't affect the application functionality."
    )
    app.logger.info("Starting PEAK Assistant with modular architecture...")

    warning_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_MODEL",
        "AZURE_OPENAI_API_VERSION",
    ]
    for var in warning_vars:
        if not os.getenv(var):
            app.logger.warning(
                f"Warning: Environment variable {var} is not set. This may cause issues."
            )

    # check for required environment variables
    required_env_vars = [
        "SPLUNK_SERVER_URL",
        "SPLUNK_MCP_USER",
        "SPLUNK_MCP_PASSWD",
        "SPLUNK_MCP_COMMAND",
        "SPLUNK_MCP_ARGS",
    ]

    failed = False
    for var in required_env_vars:
        if not os.getenv(var):
            app.logger.error(f"Error: Missing required environment variable: {var}")
            failed = True
    if failed:
        sys.exit(1)

    # TLS/SSL context: expects cert.pem and key.pem in the UI directory
    ssl_context = (
        os.path.join(os.path.dirname(__file__), "cert.pem"),
        os.path.join(os.path.dirname(__file__), "key.pem"),
    )
    for path in ssl_context:
        if not os.path.exists(path):
            app.logger.error(
                f"Error: SSL file '{path}' not found. Cannot start server."
            )
            sys.exit(1)
    # Run the application
    app.run(debug=True, port=8000, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
