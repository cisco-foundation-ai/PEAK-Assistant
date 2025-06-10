# PEAK Assistant Flask UI

This is a Flask implementation of the PEAK Assistant UI, which addresses the asyncio event loop issues that were occurring in the Streamlit version.

## Features

- **Research Phase**: Generate detailed research reports on cybersecurity topics
- **Hypothesis Phase**: Create and select hypotheses based on research findings
- **Refinement Phase**: Refine and improve your hypotheses
- **ABLE Table Phase**: Generate ABLE Tables to guide threat hunting activities
- **Data Discovery Phase**: Identify relevant Splunk data sources for testing hypotheses
- **Hunt Planning Phase**: Combine all components into a comprehensive hunt plan

## Local Context Support

The web interface automatically loads local context from a `context.txt` file if present in the `UI/` directory. This context is used across all phases to provide organization-specific information to the AI agents. The context file should contain information such as:

- Organizational structure and naming conventions
- Specific technologies and tools in use
- Known threat actors or campaigns relevant to your organization
- Infrastructure details and network topology

**Note**: The `context.txt` file is automatically ignored by Git to prevent accidental commit of sensitive information.

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

**Required for all features:**
```
AZURE_OPENAI_DEPLOYMENT=your_deployment_name
AZURE_OPENAI_MODEL=your_model_name
AZURE_OPENAI_API_VERSION=your_api_version
AZURE_OPENAI_ENDPOINT=your_endpoint_url
AZURE_OPENAI_API_KEY=your_api_key
```

**Required for Research phase:**
```
TAVILY_API_KEY=your_tavily_api_key
```

**Required for Data Discovery phase:**
```
SPLUNK_SERVER_URL=https://your-splunk-server:8089
SPLUNK_MCP_USER=your-splunk-username
SPLUNK_MCP_PASSWD=your-splunk-password
```

3. Create SSL certificates for HTTPS (development):

```bash
cd /Users/dabianco/projects/SURGe/PEAK-Assistant/UI
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

## Running the Application

Run the Flask app:

```bash
cd /Users/dabianco/projects/SURGe/PEAK-Assistant/UI
python app.py
```

By default, the application will run on `https://127.0.0.1:8000/` (note HTTPS).

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

## SSL Certificates

The Flask application runs with HTTPS by default and expects SSL certificates in the UI directory:
- `cert.pem` - SSL certificate
- `key.pem` - Private key

For development, create self-signed certificates using the command shown in the setup section above.

For production, use proper SSL certificates from a certificate authority.

## Deployment

For production deployment, we recommend using Gunicorn:

```bash
cd /Users/dabianco/projects/SURGe/PEAK-Assistant/UI
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## Server-Side Sessions

The application uses Flask-Session with SQLAlchemy to store session data on the server side rather than in browser cookies. This addresses the issue of cookie size limitations when storing large amounts of data (like research reports and ABLE tables).

Session data is stored in a SQLite database (`peak_sessions.db`) in the UI directory. For production environments, you might want to configure a more robust session storage backend like PostgreSQL or Redis.

## Troubleshooting

- **SSL Certificate Errors**: If you encounter SSL certificate errors, ensure `cert.pem` and `key.pem` exist in the UI directory. For development, you can create self-signed certificates as shown in the setup section.
- **OpenAI API 500 Errors**: Try increasing the retry count or use a simpler/shorter topic. This is typically an issue with OpenAI's servers.
- **Environment Variables**: Ensure all required environment variables are properly set in your `.env` file.
- **Azure API Issues**: Check that your Azure API key and endpoint are valid and correctly configured.
- **Data Discovery Errors**: Ensure Splunk environment variables are set and that the Splunk MCP server is accessible.
- **Session Issues**: 
  - Try clearing your browser cookies
  - Check that the SQLite database file has proper write permissions
  - Use the debug page to inspect and clear session data
- **Missing Features**: Some features require specific environment variables (e.g., TAVILY_API_KEY for research, Splunk variables for data discovery)
