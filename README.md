# PEAK-Assistant
PEAK-Assistant is an AI-powered threat hunting assistant designed to guide hunters quickly through the process of researching and planning a hypothesis-driven hunt. It aligns with the [PEAK Threat Hunting Framework](https://www.splunk.com/en_us/form/the-peak-threat-hunting-framework.html) and leverages large language models, teams of AI agents, and automated research tools to streamline the process of preparing for a hunt.

⛔️⛔️ **The PEAK Assistant is intended solely as a proof-of-concept project to demonstrate the potential of agentic security solutions. It has not undergone security testing. Be cautious when deploying this to anything but a local system environment.** ⛔️⛔️

<img src="research-screenshot.png" alt="A screenshot of the PEAK Assistant's topic research tab.">

## Features
The PEAK Assistant web app offers the following features:

- Generate detailed threat hunting research reports for specific techniques, tactics, or actors. It can access both Internet-based sources and local databases (ticket systems, wiki pages, threat intel platforms, etc).
- Suggest and refine threat hunting hypotheses based on the research it performed.
- Create PEAK ABLE tables to help scope the hunt.
- Automatically identify relevant indices, sourcetypes, and field names in your Splunk instance.
- Create step-by-step hunt plans, including guidance for how to analyze and interpret the results
- Export documents in Markdown format
- Upload documents that you have prepared yourself, so the AI doesn't have to regenerate them.
- Integration with research and Splunk data sources via either local or remote MCP servers, including OAuth2, API key, and bearer token authentication support.
- Most phases incorporate a chat-like interface so you can collaborate with the assistant to refine outputs until they exactly right

## Setting up the Python Environment
Clone the [GitHub repo] to a directory on your local system:
```bash
git clone https://github.com/cisco-foundation-ai/PEAK-Assistant
cd PEAK-Assistant
```

**I strongly recommend you use 'uv' to manage your python environment.** It will take care of creating a virtual environment and installing all the dependencies. 
```bash
uv sync
```

## Generate TLS Certificate
Once that's done, you'll need to generate the TLS certificate and private key. The files must be named `cert.pem` and `key.pem`, and reside in the local directory (or a directory specified by `--cert-dir` on startup). You can do this manually like so:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
```

If you prefer, you can use the `generate_certificates.sh` utility to do this for you. Just run the script and follow the prompts.

```bash
./generate_certificates.sh
```

## MCP Server Configuration
You will also need to configure the MCP servers the assistant uses to research topics and discover available data. Create a file called `mcp_servers.json` in the root of the repository. This file has the same format as you might be used to if you have configured MCP servers in Claude Desktop or other popular chat applications. You can use the following example as a template:

```json
{
  "mcpServers": {
    "tavily-search": {
      "transport": "stdio",
      "description": "Provides Internet searches",
      "command": "npx",
      "args": [
        "-y",
        "tavily-mcp@0.1.2"
      ],
      "env": {
        "TAVILY_API_KEY": "tvly-dev-YOUR-KEY"
      }
    },
    "splunk-mcp-official": {
      "description": "Connect to a running Splunk server and run searches.",
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://18.215.204.181:8089/services/mcp",
        "--header",
        "Authorization: Bearer splunk-mcp-YOUR-TOKEN"
      ],
    },
    "atlassian-remote-mcp": {
      "transport": "sse",
      "description": "Provides access to Jira and Confluence",
      "url": "https://mcp.atlassian.com/v1/sse"
    }
  },
  "serverGroups": {
    "research-external": [
      "tavily-search"
    ],
    "research-internal": [
      "atlassian-remote-mcp"
    ],
    "data_discovery": [
      "splunk-mcp-surge"
    ]
  }
}
```

At a minimum, you must provide the following types of MCP server (at least one of each):

* Internet search (e.g., Tavily)
* Splunk search (e.g., the official Splunk MCP server)

If you want to incorporate local data sources, for example to learn from the results of past hunts you may have performed on a topic, you may optionally also include MCP servers for those sources, though they are not required. In this example, we used:

* [Atlassian's offical MCP server](https://www.atlassian.com/platform/remote-mcp-server) to allow the Assistant to search Jira tickets and Confluence wiki pages.

Feel free to substitute MCP servers with functional equivalents. For example, if you have a different Internet search provider, replace the Tavily configuration with whatever you're using.

### Telling the Assistant Which MCP Servers to Use
In addition to defining the servers, you'll also have to add them to the appropriate MCP server groups, to let the different agents know which they should be using. 

The server groups are:

* `research-external`: Used for any Internet searches in the topic research phase
* `research-internal`: Used for searching any local data sources during the topic research phase
* `data-discovery`: Allows access to Splunk (or whatever other local data sources you use) for purposes of automated data discovery. 

You may add multiple MCP servers to each group if you would like the Assistant to have access to several sources, but you **must have at least one server in each group**.

### MCP Authentication

The PEAK Assistant supports OAuth2 authentication for remote MCP servers, as well as OAuth resource autodiscovery. If your MCP server also supports those, you should be automatically directed to the server's authentication provider when you connect the MCP server from the app's main page.

## Local Context Files

The Assistant supports an optional file for providing "local context". This provides a way for you to give the LLM hints and guidance about your environment or preferences so you can adapt the AI to your needs without having to edit the prompts. If present, this context file should be named `context.txt` and should be placed in the root of the repository. It should contain information that helps the AI agents understand your specific environment, such as:

- Organizational structure and naming conventions
- Specific technologies and tools in use
- Known threat actors or campaigns relevant to your organization
- Compliance requirements or regulatory considerations
- Previous hunting activities or findings

There is no specific format requirement, but you may find it helpful to have some sort of basic structure to help you maintain it easily over time. Here's a simple example:

```
Environmental hints:
    - We use primarily Splunk SIEM and Zeek NIDS.

Local Information Sources:
    - Always consult the following sources of information when you are preparing your research
      reports, using the Atlassian MCP server. You may also consult them any other time you
      believe it to be appropriate.
      - Hunt team documents hunts in Confluence wiki, under the "Threat Hunting" space
      - Hunt team tracks in-progress and upcoming hunts in Jira, under the "Threat Hunting" project
    - The Atlassian server is my-cloud-tenant.atlassian.net.

Splunk hints:
    - If you encounter base64-encoded data, and if you decide that you must decode it,
      you can use the following sample SPL as a reference:

        <your query>
        | code field=base64_encoded_field method=base64 action=decode destfield=decoded_field
        <the rest of your query>

      Where the "field" parameter is the name of the field that has base64 data in it, and
      the "destfield" parameter is the name of a new field you want to hold the decoded value.

    - Some of the indices are extremely large and have many events. You will need to check your
      SPL queries carefully to ensure that they are as efficient as possible. One good strategy
      is to use 'tstats' whenever possible, rather than normal searches.

    - Don't try to use accelerated datamodels. There are no datamodels on this server.
```

We strongly recommend you also include at least some basic information about your most important
Splunk indices, sourcetypes, and fields. This will help the AI agents understand your data better
and generate more accurate queries. It's not required, because the automated data discovery is actually pretty good, but it can be helpful.

## Model Configuration

The PEAK Assistant requires a `model_config.json` file to configure LLM providers and models. This file must be placed in the current working directory (the directory from which you run the application).

For complete documentation on model configuration, including:
- Detailed provider setup (Azure OpenAI, OpenAI, OpenAI-compatible, Anthropic)
- Per-agent model assignment
- Multiple configuration examples
- Environment variable interpolation
- Troubleshooting

See **[MODEL_CONFIGURATION.md](MODEL_CONFIGURATION.md)** for the full guide.

## Running the Assistant
Now that it is configured it's time to run the app. Since you installed this as a module, you can simpley run the assistant:

```bash
uv run peak-assistant
```

By default, the application will run on `http://127.0.0.1:8501/` (or HTTPS if you have a certificate configured).

## Accessing the Assistant
Once the app is running, you can access it by opening `http://127.0.0.1:8501/` (or HTTPS if configured) in your browser.

## Workflow

The PEAK-Assistant follows a structured workflow that aligns with the PEAK Threat Hunting Framework:

1. **Research Phase**: Generate comprehensive research reports on specified cybersecurity techniques or threat actors
2. **Hypothesis Generation**: Create testable hypotheses based on the research findings
3. **Hypothesis Refinement**: Improve and refine hypotheses through automated or human-guided feedback
4. **ABLE Table Creation**: Develop Actor, Behavior, Location, Evidence tables to scope the hunt
5. **Data Discovery**: Identify relevant data sources in your Splunk environment for testing hypotheses
6. **Hunt Planning**: Combine all components into a comprehensive threat hunting plan

## Live Integration Tests (optional)

This repository includes live integration tests that make real calls to the configured LLM provider. These tests are marked with `@pytest.mark.live` and require a properly configured `model_config.json` file in the test directory.

- Run all live tests:
  ```bash
  pytest -m live tests/integration -q
  ```

- OpenAI (native): ensure your `model_config.json` is configured with OpenAI provider and does not set `base_url`.
  ```bash
  pytest -m live tests/integration/test_openai_live.py -q
  ```

- OpenAI-compatible (custom base_url): ensure your `model_config.json` is configured with OpenAI provider and includes `base_url` (e.g., `http://localhost:11434/v1`).
  ```bash
  pytest -m live tests/integration/test_openai_base_url_live.py -q
  ```

- Azure OpenAI: ensure your `model_config.json` is configured with Azure provider.
  ```bash
  pytest -m live tests/integration/test_azure_live.py -q
  ```

Note: These tests make real network calls and may incur costs when using hosted providers.

## Docker Support

The PEAK Assistant can be run in a Docker container. To do this, you will need to have Docker installed on your system. Alternatives, such as `podman` or other container systems that use Docker images, work as well but are not officially supported. 

### Pulling the Docker image from the container registery
The project provides pre-built Docker images, which can be downloaded by running the following command:

```bash
docker pull ghcr.io/peak-assistant/peak-assistant:latest
```

### Building the Docker image from source
If you prefer to build the image from source, you can do so by running the following command from the root of the repository::

```bash
docker build -t peak-assistant .
```

### Running the Docker container
Once you have the image downloaded, you can run the container by running the following command:

```bash
	docker run --rm -it \
		--mount "type=bind,src=$(PWD)/cert.pem,target=/certs/cert.pem" \
		--mount "type=bind,src=$(PWD)/key.pem,target=/certs/key.pem" \
		--mount "type=bind,src=$(PWD)/context.txt,target=/home/peakassistant/context.txt" \
		--mount "type=bind,src=$(PWD)/.env,target=/home/peakassistant/.env" \
		--mount "type=bind,src=$(PWD)/mcp_servers.json,target=/home/peakassistant/mcp_servers.json" \
		-p "127.0.0.1:8501:8501" \
		ghcr.io/cisco-foundation-ai/peak-assistant:latest
```

Note that you will still need to provide the same configuration files as you would if you were running the app natively:
* `context.txt`
* `model_config.json`
* `mcp_servers.json`
* `cert.pem` & `key.pem`

The sample command mounts the current directory as `/certs`, and maps the other files into the working directory of the app running in the container. It assumes these files are in the current directory, but you can adjust the paths as needed. Don't forget to add a mount for `model_config.json`:

```bash
--mount "type=bind,src=$(PWD)/model_config.json,target=/home/peakassistant/model_config.json"
```

### Accessing the Assistant via Docker
Once the container is running, you can access it just as though it were running natively. Open `http://127.0.0.1:8501/` (or HTTPS if configured) in your browser.

## FAQ
### What if I want to use Podman instead of Docker to run the containers?
Podman commands are generally very compatible with Docker commands, so you should be able to use them interchangeably. The only difference is that you will need to use `podman` instead of `docker` in the commands above.

### What if I want to use a different LLM provider?
The Assistant supports multiple providers via the `model_config.json` file:

- Azure OpenAI
- OpenAI (native)
- OpenAI-compatible servers (e.g., Ollama, vLLM, LM Studio)

You can configure different models for different agents, or use a single model for all agents. See [MODEL_CONFIGURATION.md](MODEL_CONFIGURATION.md) for detailed configuration examples and provider-specific requirements.

## Troubleshooting

### My MCP servers aren't working/can't authenticate. What do I do?

If you're having issues with MCP servers or want to verify your configuration, use the `mcp-status` command to check the status of all configured servers:

```bash
uv run mcp-status
```

This command will:
- Display all configured MCP servers organized by server group
- Show authentication status for each server
- Identify missing OAuth2 environment variables
- Provide exact `export` commands to set required credentials

**Example output:**
```
✓ tavily-search
  Transport: stdio
  Auth: none
  Status: Ready

✗ atlassian-remote-mcp
  Transport: sse
  Auth: oauth2_authorization_code (requires user authentication)
  Status: Missing credentials
  
  Missing environment variable(s):
    ✗ PEAK_MCP_ATLASSIAN_REMOTE_MCP_TOKEN
    ✗ PEAK_MCP_ATLASSIAN_REMOTE_MCP_USER_ID
  
  To enable, set:
    export PEAK_MCP_ATLASSIAN_REMOTE_MCP_TOKEN="your_token_here"
    export PEAK_MCP_ATLASSIAN_REMOTE_MCP_USER_ID="your_user_id"
```

**Verbose mode** shows additional details like commands, URLs, and descriptions:
```bash
uv run mcp-status --verbose
# or
uv run mcp-status -v
```

**Note:** The `mcp-status` command only checks configuration and environment variables—it does not attempt to connect to servers. This makes it fast and safe to run at any time.

### Using OAuth2 MCP Servers in CLI Mode

OAuth2-authenticated MCP servers require browser-based authentication and are primarily designed for use with the Streamlit web interface. However, you can use them in CLI mode (e.g., with `research-assistant`) by providing OAuth tokens via environment variables:

```bash
# For servers without user authentication
export PEAK_MCP_SERVER_NAME_TOKEN="your_access_token"

# For servers requiring user authentication (e.g., Atlassian)
export PEAK_MCP_ATLASSIAN_REMOTE_MCP_TOKEN="your_access_token"
export PEAK_MCP_ATLASSIAN_REMOTE_MCP_USER_ID="your_user_id"
```

**To obtain tokens:**
1. Authenticate via the Streamlit web interface (`uv run peak-assistant`)
2. Use the server's developer portal to generate a personal access token
3. Set the environment variables before running CLI commands

**Note:** OAuth2 servers without environment variables will be automatically skipped in CLI mode with a clear warning message.

### The application is working, but I get network errors when I try to download any of the files.
The most likely cause is that you are using self-signed TLS certificates and, while Chrome may allow you to access the app's pages, it will not allow you to download any files. If you can, use a recognized certificate authority to issue your TLS certificates. If this isn't feasible (e.g., if you are running on a local development machine), you will need to add your CA to the system's root certificate store as a trusted CA. The easiest way to do this is to use the [mkcert](https://github.com/FiloSottile/mkcert) tool to create the local CA, install it on your system, and then use it to create the TLS certificates for the app.

## License
See the [LICENSE](LICENSE) for details.
