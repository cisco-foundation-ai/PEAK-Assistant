import os
from .app import app


def main() -> None:
    # Create templates directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

    # TLS/SSL context: expects cert.pem and key.pem in the UI directory
    context = (
        os.path.join(os.path.dirname(__file__), "cert.pem"),
        os.path.join(os.path.dirname(__file__), "key.pem"),
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
    app.run(debug=True, port=8000, ssl_context=context)


if __name__ == "__main__":
    main()
