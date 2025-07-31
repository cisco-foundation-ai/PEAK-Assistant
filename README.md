# PEAK-Assistant
PEAK-Assistant is an AI-powered threat hunting assistant designed to guide hunters quickly through the process of researching and planning a hypothesis-driven hunt. It aligns with the [PEAK Threat Hunting Framework](https://www.splunk.com/en_us/form/the-peak-threat-hunting-framework.html) and leverages large language models, agents, and automated research tools to streamline the process of preparing for a hunt.

⛔️⛔️ **The PEAK Assistant is intended solely as a proof-of-concept project to demonstrate the potential of agentic security solutions. It has not undergone security testing. Be cautious when deploying this to anything but a local system environment.** ⛔️⛔️

## Features
The PEAK Assistant offers the following features:

- Generate detailed threat hunting research reports for specific techniques, tactics, or actors. It can access both Internet-based sources and local databases (ticket systems, wiki pages, threat intel platforms, etc).
- Suggest and refine threat hunting hypotheses based on the research it performed.
- Create PEAK ABLE tables to help scope the hunt.
- Automatically identify relevant data sources in your Splunk instance.
- Create step-by-step hunt plans, including guidance for how to analyze and interpret the results
- Export any documents in Markdown or PDF format
- Upload documents that you have prepared yourself, so the AI doesn't have to regenerate them.
- Integration with research and Splunk data sources via either local or remote MCP servers, including OAuth2 support for authenticating to the MCP servers.
- Each phase incorporates user feedback so you can collaborate with the assistant to refine outputs until they exactly right
- Dark / Light mode UI

## Setting up the Python Environment
Clone the [GitHub repo] to a directory on your local system:
```bash
git clone https://github.com/splunk/PEAK-Assistant
```

**I strongly recommend you use a python virtualenv to run this app.**

Inside your virtualenv, install the required Python modules:
```bash
pip install -r requirements.txt
```

## Web App Configuration
Once that's done, you'll need to generate the SSL certificate and private key. The files must be named `cert.pem` and `key.pem`, and reside in the `UI` directory of the repository:
```bash
cd PEAK-Assistant
openssl req -x509 -newkey rsa:2048 -keyout UI/key.pem -out UI/cert.pem -days 365 -nodes -subj "/C=US/ST=CA/L=My Town/O=PEAK Assistant/OU=Threat Hunting Team/CN=localhost"
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
    "splunk-mcp-surge": {
      "transport": "stdio",
      "description": null,
      "timeout": 300,
      "command": "/home/user/.pyenv/versions/peak-assistant/bin/python3",
      "args": [
        "/home/user/splunk-mcp/splunk-mcp.py"
      ],
      "env": {
        "SPLUNK_SERVER_URL": "https://1.1.1.1:8089",
        "SPLUNK_MCP_USER": "mcpuser",
        "SPLUNK_MCP_PASSWD": "mcp_p4ss47"
      }
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

* [Atlassian's offical MCP server](https://www.atlassian.com/platform/remote-mcp-server) (provides access to Jira and Confluence)

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

### Local Context Files

The Assistant supports an optional file for providing "local context". This provides a way for you to give the LLM clues and guidance about your local environment or preferences so you can adapt the AI to your needs without having to edit the prompts. If present, this context file lives at `UI/context.txt` and should contain information that helps the AI agents understand your specific environment, such as:

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

### 2. Environment Variables
The rest of the Assistant configuration has to do with the LLM configuration, and is held in environment variables. Create a `.env` file in the project root with the following variables:

```
# Note that the PEAK Assistant only supports Azure OpenAI at this time.
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_ENDPOINT=https://your-azure-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_VERSION=2023-05-15

# Use this model for most tasks
AZURE_OPENAI_MODEL=gpt-4o

# Use this model when you need extended thinking (some of the research, data discovery, and planning tasks).
# If you prefer not to use a reasoning model, simply set it to whatever model you're using above
AZURE_OPENAI_REASONING_MODEL=o4-mini
```

## Running the Assistant
Now that it is configured it's time to run the app. From the root of the repository, issue the following command:

```bash
python UI/app.py
```

By default, the application will run on `https://127.0.0.1:8000/` (note HTTPS - if you're using self-signed certificates as in the examples above, you'll also need to tell the browser to accept the certificate before you can proceed).



## Workflow

The PEAK-Assistant follows a structured workflow that aligns with the PEAK Threat Hunting Framework:

1. **Research Phase**: Generate comprehensive research reports on specific cybersecurity techniques or threat actors
2. **Hypothesis Generation**: Create testable hypotheses based on the research findings
3. **Hypothesis Refinement**: Improve and refine hypotheses through automated or human-guided feedback
4. **ABLE Table Creation**: Develop Actor, Behavior, Location, Evidence tables to scope the hunt
5. **Data Discovery**: Identify relevant data sources in your Splunk environment for testing hypotheses
6. **Hunt Planning**: Combine all components into a comprehensive threat hunting plan

## License
See the [LICENSE](LICENSE) for details.
