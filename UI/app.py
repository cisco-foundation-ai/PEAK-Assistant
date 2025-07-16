#!/usr/bin/env python3
"""
PEAK Assistant - Modular Flask Application
Streamlined entry point using factory pattern
"""
import os
from app.factory import create_app

# Determine configuration based on environment
config_name = os.environ.get('FLASK_CONFIG', 'development')

# Create Flask application using factory pattern
app = create_app(config_name)

# Make INITIAL_LOCAL_CONTEXT available to route modules
from app.routes.api_routes import INITIAL_LOCAL_CONTEXT
import app.routes.api_routes as api_routes
api_routes.INITIAL_LOCAL_CONTEXT = app.config.get('INITIAL_LOCAL_CONTEXT', '')

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
    
    # TLS/SSL context: expects cert.pem and key.pem in the UI directory
    context = (os.path.join(os.path.dirname(__file__), 'cert.pem'),
               os.path.join(os.path.dirname(__file__), 'key.pem'))
    
    print("Note: You may see 'Task exception was never retrieved' errors related to HTTP client cleanup.")
    print("These are harmless and don't affect the application functionality.")
    print("")
    print("Starting PEAK Assistant with modular architecture...")
    
    # Run the application
    app.run(debug=True, port=8000, ssl_context=context)
