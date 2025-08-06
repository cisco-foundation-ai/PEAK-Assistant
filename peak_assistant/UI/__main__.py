import os
import click

from peak_assistant.UI.app.factory import create_app


@click.command()
@click.option("--cert-dir", default="./", help="Directory to find SSL certificates.")
@click.option("--host", default="localhost", help="Host to run the application on.")
@click.option("--port", default=8000, help="Port to run the application on.")
@click.option("--context", default="./context.txt", help="Path for context.txt")
def main(
    cert_dir: str = "./",
    host: str = "localhost",
    port: int = 8000,
    context: str = "./context.txt",
) -> None:
    # Create templates directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

    config_name = os.environ.get("FLASK_CONFIG", "development")

    # Create Flask application using factory pattern
    app = create_app(config_name, context)

    ssl_context = (
        os.path.join(cert_dir, "cert.pem"),
        os.path.join(cert_dir, "key.pem"),
    )
    failed = False
    for file in ssl_context:
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
    app.run(debug=True, host=host, port=port, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
