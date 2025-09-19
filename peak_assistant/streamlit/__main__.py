#!/usr/bin/env python3
"""
PEAK Assistant Streamlit CLI Wrapper

This module provides a command-line interface to launch the PEAK Assistant Streamlit app.
It replaces the Flask-based CLI and maintains backward compatibility for the `peak-assistant` command.
"""

import os
import sys
import subprocess
import click
from pathlib import Path


@click.command()
@click.option("--cert-dir", default="./", help="Directory to find SSL certificates.")
@click.option("--host", default="0.0.0.0", help="Host to run the application on.")
@click.option("--port", default=8501, help="Port to run the application on.")
@click.option("--context", default="./context.txt", help="Path for context.txt (legacy compatibility)")
def main(
    cert_dir: str = "./",
    host: str = "0.0.0.0", 
    port: int = 8501,
    context: str = "./context.txt",
) -> None:
    """Launch the PEAK Assistant Streamlit application."""
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    app_path = script_dir / "app.py"
    
    if not app_path.exists():
        click.echo(f"Error: Streamlit app not found at {app_path}", err=True)
        sys.exit(1)
    
    # Build streamlit command
    cmd = [
        sys.executable, "-m", "streamlit", "run", 
        str(app_path),
        "--server.address", host,
        "--server.port", str(port),
        "--server.headless", "true",  # Don't auto-open browser in server mode
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false"
    ]
    
    # Add TLS if certificates exist
    cert_file = os.path.join(cert_dir, "cert.pem")
    key_file = os.path.join(cert_dir, "key.pem")
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        cmd.extend([
            "--server.sslCertFile", cert_file,
            "--server.sslKeyFile", key_file
        ])
        protocol = "https"
    else:
        protocol = "http"
        click.echo("Warning: SSL certificates not found. Running without HTTPS.")
    
    # Set context file environment variable for compatibility
    if context and os.path.exists(context):
        os.environ["PEAK_CONTEXT_FILE"] = context
    
    click.echo("Starting PEAK Assistant Streamlit application...")
    click.echo(f"Application will be available at: {protocol}://{host}:{port}")
    
    try:
        # Execute streamlit
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error: Failed to start Streamlit application: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down PEAK Assistant...")
        sys.exit(0)


if __name__ == "__main__":
    main()
