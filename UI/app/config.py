"""
Configuration management for PEAK Assistant Flask application
"""

import os
import tempfile
from datetime import timedelta


class Config:
    """Base configuration class"""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-key-change-in-production"

    # Session configuration
    SESSION_TYPE = "sqlalchemy"
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "peak_assistant_"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # Database configuration
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL") or "sqlite:///peak_assistant.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_SQLALCHEMY_TABLE = "sessions"

    # File upload configuration
    ALLOWED_UPLOAD_EXTENSIONS = {".md", ".txt"}
    UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "peak_uploads")

    # AI service configuration
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

    # MCP configuration now handled by mcp_servers.json configuration file

    @staticmethod
    def init_app(app):
        """Initialize application with configuration"""
        # Create upload folder if it doesn't exist
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True
    SSL_DISABLE = True


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    SSL_DISABLE = False

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)

        # Production-specific initialization
        import logging
        from logging.handlers import RotatingFileHandler

        if not app.debug:
            file_handler = RotatingFileHandler(
                "logs/peak_assistant.log", maxBytes=10240, backupCount=10
            )
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
                )
            )
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info("PEAK Assistant startup")


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
