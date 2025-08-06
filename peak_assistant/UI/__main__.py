import os
import click
from .app import app


@click.command()
@click.option("--cert-dir", default="./", help="Directory to find SSL certificates.")
@click.option("--host", default="localhost", help="Host to run the application on.")
@click.option("--port", default=8000, help="Port to run the application on.")
def main(cert_dir: str = "./", host: str = "localhost", port: int = 8000) -> None:
    # Create templates directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

    # TLS/SSL context: expects cert.pem and key.pem in the UI directory
    context = (
        os.path.join(cert_dir, "cert.pem"),
        os.path.join(cert_dir, "key.pem"),
    )

    failed = False
    for file in context:
        if not os.path.exists(file):
            app.logger.error(f"Warning: SSL file {file} not found.")
            failed = True

    if failed:
        return
    app.logger.info(
        "Note: You may see 'Task exception was never retrieved' errors related to HTTP client cleanup."
    )
    app.logger.info(
        "These are harmless and don't affect the application functionality."
    )
    app.logger.info(
        "Starting PEAK Assistant with modular architecture... accessible on https://localhost:8000"
    )

    # Run the application
    app.run(debug=True, host=host, port=port, ssl_context=context)


if __name__ == "__main__":
    main()
