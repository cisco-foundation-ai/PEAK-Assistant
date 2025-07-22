"""
Flask application factory for PEAK Assistant
"""
import os
import sys
import logging
import warnings
from flask import Flask
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy

from .config import config
from .utils.helpers import load_env_defaults

# Initialize extensions
db = SQLAlchemy()
session_manager = Session()

# Global variables
INITIAL_LOCAL_CONTEXT = None


def load_initial_context():
    """Load initial local context from context.txt file"""
    global INITIAL_LOCAL_CONTEXT
    context_file_path = os.path.join(os.path.dirname(__file__), '..', 'context.txt')
    
    if os.path.exists(context_file_path):
        try:
            with open(context_file_path, 'r', encoding='utf-8') as f:
                INITIAL_LOCAL_CONTEXT = f.read()
            print(f"Successfully loaded initial context from {context_file_path}")
        except Exception as e:
            print(f"Warning: Could not load context file: {e}")
            INITIAL_LOCAL_CONTEXT = ""
    else:
        print(f"Warning: Context file not found at {context_file_path}")
        INITIAL_LOCAL_CONTEXT = ""


def create_app(config_name='default'):
    """
    Flask application factory
    
    Args:
        config_name: Configuration name ('development', 'production', 'default')
    
    Returns:
        Flask application instance
    """
    # Load environment variables first
    load_env_defaults()
    
    # Load initial context
    load_initial_context()
    
    # Create Flask app
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Initialize extensions
    db.init_app(app)
    app.config['SESSION_SQLALCHEMY'] = db
    session_manager.init_app(app)
    
    # Add the parent directory to sys.path for imports
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
    
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
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Make INITIAL_LOCAL_CONTEXT available to routes
    app.config['INITIAL_LOCAL_CONTEXT'] = INITIAL_LOCAL_CONTEXT
    
    return app
