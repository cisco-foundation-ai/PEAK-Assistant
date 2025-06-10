# PEAK Assistant Flask UI

This is a Flask implementation of the PEAK Assistant UI, which addresses the asyncio event loop issues that were occurring in the Streamlit version.

## Features

- Research Phase: Generate detailed research reports on cybersecurity topics
- Hypothesis Phase: Create and select hypotheses based on research findings
- Refinement Phase: Refine and improve your hypotheses
- ABLE Table Phase: Generate ABLE Tables to guide threat hunting activities

## Benefits of the Flask Implementation

- Better asyncio handling with proper event loops
- Improved error handling and recovery
- Cleaner separation of UI and backend logic
- More reliable API communication
- Debug tools and diagnostics built in

## Setup

1. Install all required packages (from the project root):

```bash
cd /Users/dabianco/projects/SURGe/PEAK-Assistant
pip install -r requirements.txt
```

> **Note:** You no longer need to install from `requirements_flask.txt` separately; all dependencies are now in the top-level `requirements.txt`.

2. Ensure your `.env` file is properly set up with the required API keys:

```
AZURE_OPENAI_DEPLOYMENT=your_deployment_name
AZURE_OPENAI_MODEL=your_model_name
AZURE_OPENAI_API_VERSION=your_api_version
AZURE_OPENAI_ENDPOINT=your_endpoint_url
AZURE_OPENAI_API_KEY=your_api_key
TAVILY_API_KEY=your_tavily_api_key
```

## TLS/SSL Setup (Required)

All access to the Flask UI must be via HTTPS. You must generate a TLS certificate and key before running the app.

### Generate a Self-Signed Certificate (for development)

From the `UI` directory, run:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
```

- This will create `cert.pem` (certificate) and `key.pem` (private key) in the `UI` directory.
- The app will refuse to start if these files are missing.
- For production, use a certificate signed by a trusted CA.

### Running the Application (with TLS)

Run the Flask app:

```bash
cd /Users/dabianco/projects/SURGe/PEAK-Assistant/UI
python app_flask.py
```

The application will run on `https://127.0.0.1:8000/` (note the `https`).

If you use Gunicorn for production, you must also provide the `--keyfile` and `--certfile` options:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 app_flask:app --keyfile key.pem --certfile cert.pem
```

## Running the Application

Run the Flask app:

```bash
cd /Users/dabianco/projects/SURGe/PEAK-Assistant/UI
python app_flask.py
```

By default, the application will run on `http://127.0.0.1:8000/`.

## Debugging

The application includes a debug mode that can be enabled in the UI. When enabled, it provides:

1. Connection testing for the Azure OpenAI API
2. Detailed error information
3. Environment variable status
4. Session data inspection

## Verbose Mode

The application includes a verbose mode option that can be enabled in the sidebar. When enabled:

- The detailed processing steps of the research and refinement phases will be displayed.
- You'll see the actual conversation between the agent components (where supported).
- Helps with understanding how the application is processing information.
- Useful for debugging and educational purposes.

> **Note:** Verbose mode has no effect on the Hypothesis or ABLE Table phases, as those do not support verbose output.

Note that verbose mode may make processing slower and consume more API tokens.

## Deployment

For production deployment, we recommend using Gunicorn:

```bash
cd /Users/dabianco/projects/SURGe/PEAK-Assistant/UI
gunicorn -w 4 -b 0.0.0.0:8000 app_flask:app
```

## Server-Side Sessions

The application uses Flask-Session to store session data on the server side rather than in browser cookies. This addresses the issue of cookie size limitations when storing large amounts of data (like research reports and ABLE tables).

Session data is stored in the filesystem by default in a temporary directory. For production environments, you might want to configure a more robust session storage backend like Redis.

## Troubleshooting

- If you encounter OpenAI API 500 errors, try increasing the retry count or try a simpler/shorter topic.
- Ensure all environment variables are properly set.
- Check that your Azure API key and endpoint are valid and correctly configured.
- If you encounter issues with specific features, check the Flask logs for detailed error information.
- If you encounter session-related issues:
  - Try clearing your browser cookies
  - Check that the Flask-Session temp directory has proper write permissions
  - Use the debug page to inspect and clear session data
