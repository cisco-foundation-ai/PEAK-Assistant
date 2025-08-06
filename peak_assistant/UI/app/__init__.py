"""
PEAK Assistant Flask Application Module
Modularized architecture for better maintainability
"""

import os

from .factory import create_app
from .routes import api_routes

# Determine configuration based on environment
config_name = os.environ.get("FLASK_CONFIG", "development")

# Create Flask application using factory pattern
app = create_app(config_name)

# Make INITIAL_LOCAL_CONTEXT available to route modules
api_routes.INITIAL_LOCAL_CONTEXT = app.config.get("INITIAL_LOCAL_CONTEXT", "")
