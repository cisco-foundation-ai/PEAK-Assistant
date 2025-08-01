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
            print(f"Warning: SSL file {file} not found.")
            context = None
            failed = True

    if failed:
        return

    print(
        "Note: You may see 'Task exception was never retrieved' errors related to HTTP client cleanup."
    )
    print("These are harmless and don't affect the application functionality.")
    print("")
    print("Starting PEAK Assistant with modular architecture...")

    # Run the application
    app.run(debug=True, port=8000, ssl_context=context)


if __name__ == "__main__":
    main()
