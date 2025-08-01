# PEAK-Assistant
PEAK-Assistant is an AI-powered threat hunting assistant designed to help cybersecurity professionals generate, refine, and document threat hunting hypotheses and research. It aligns with the [PEAK Threat Hunting Framework](https://www.splunk.com/en_us/form/the-peak-threat-hunting-framework.html) and leverages large language models and automated research tools to streamline the process of preparing for a hunt.

## Overview
This repository provides both a web-based UI and a suite of command-line tools to:
- Generate detailed threat hunting research reports for specific techniques.
- Suggest and refine threat hunting hypotheses.
- Create PEAK ABLE tables to help scope the hunt.
- Identify relevant data sources in Splunk for testing hypotheses.

## Web Interface
The PEAK-Assistant includes a Flask-based web interface that provides an intuitive way to work through the threat hunting workflow. The web interface includes:

- **Research Phase**: Generate detailed research reports on cybersecurity topics
- **Hypothesis Phase**: Create and select hypotheses based on research findings  
- **Refinement Phase**: Refine and improve your hypotheses
- **ABLE Table Phase**: Generate ABLE Tables to guide threat hunting activities
- **Data Discovery Phase**: Identify relevant Splunk data sources for testing hypotheses
- **Hunt Planning**: Combine all phases into a comprehensive hunt plan

### Running the Web Interface


```bash
pip install .
peak-assistant
```

By default, the application will run on `https://127.0.0.1:8000/` (note HTTPS - you'll need SSL certificates).

For more details on the web interface, see [UI/README.md](UI/README.md).

## Tools and CLI Scripts

### research-assistant
**Purpose:** Generate a comprehensive threat hunting research report for a given technique, using automated research and summarization agents.

**Arguments:**
- `-t`, `--technique` (required): The cybersecurity technique to research.
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-c`, `--local_context`: Path to a local context file to provide additional information.
- `-f`, `--format`: Output format (`pdf` or `markdown`). Default: `markdown`.
- `-v`, `--verbose`: Enable verbose output.
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
research-assistant -t "Kerberoasting" -f markdown -c context.txt
```

---

### hypothesis-assistant
**Purpose:** Suggest testable threat hunting hypotheses based on user input and a research document.

**Arguments:**
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-r`, `--research` (required): Path to the research document (markdown file).
- `-u`, `--user_input`: User input for hypothesis generation (optional).
- `-c`, `--local_context`: Path to a local context file to provide additional information.
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
hypothesis-assistant -r kerberoasting.md -u "Focus on use for lateral movement." -c context.txt
```

**Notes:**
Use the `-u` option to provide additional guidance or input (e.g., specific focus areas) to the hypothesis generation process.
Use the `-c` option to provide local context from a file that contains organization-specific information.

---

### hypothesis-refiner
**Purpose:** Refine and improve a threat hunting hypothesis using automated and/or human-in-the-loop feedback.

**Arguments:**
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-y`, `--hypothesis` (required): The hypothesis to be refined.
- `-r`, `--research` (required): Path to the research document (markdown file).
- `-c`, `--local_context`: Path to a local context file to provide additional information.
- `-v`, `--verbose`: Enable verbose output.
- `-a`, `--automated`: Enable automated mode (no human feedback).
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
hypothesis-refiner -y "threat actors are using kerberoasting for lateral movement by requesting user tickets and then using them shortly after" -r kerberoasting.md -a -c context.txt
```

**Notes:**
Hypothesis refinement is an interactive process with human involvement to steer things in the correct direction. By default, `hypothesis_refiner_cli.py` will prompt the user for their 
input/feedback after every refinement attempt. You can continue with as many rounds of refinement as you like; when you are finished, mention the string 
`YYY-HYPOTHESIS-ACCEPTED-YYY` to let the agent know you're finished. 

**I WILL be improving this experience later.**

If you prefer a completely automated refinement experience, use the `-a` option, as shown in the example. This will prevent all prompts for user input and simply output the refined hypothesis.

---

### able-assistant
**Purpose:** Generate a PEAK ABLE table (Actor, Behavior, Location, Evidence) for a given hypothesis and research document.

**Arguments:**
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-r`, `--research` (required): Path to the research document (markdown file).
- `-y`, `--hypothesis` (required): The hunting hypothesis.
- `-c`, `--local_context`: Path to a local context file to provide additional information.
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
able-assistant -r kerberoasting.md \
   -y "Adversaries seeking lateral movement via Kerberoasting will request Kerberos service tickets (TGS) for user-based SPNs associated with privileged or lateral-movement-enabled service accounts, followed shortly by successful authentication or remote access events (e.g., SMB, RDP, WinRM) using those accounts from previously unseen endpoints." \
   -c context.txt
```

---

### data-assistant
**Purpose:** Identify relevant Splunk indices and data sources for testing a threat hunting hypothesis.

**Arguments:**
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-r`, `--research` (required): Path to the research document (markdown file).
- `-y`, `--hypothesis` (required): The hunting hypothesis.
- `-a`, `--able_info`: Path to ABLE table information file (optional).
- `-c`, `--local_context`: Path to a local context file to provide additional information.
- `-v`, `--verbose`: Enable verbose output.
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
data-assistant -r kerberoasting.md -y "Adversaries seeking lateral movement via Kerberoasting will request Kerberos service tickets" -a able_table.md -c context.txt -v
```

**Notes:**
This tool requires additional Splunk-specific environment variables (see Environment Variables section below).
The data assistant uses an MCP (Model Context Protocol) server to interact with Splunk. You must specify the path to your MCP server command and any required arguments through the `SPLUNK_MCP_COMMAND` and `SPLUNK_MCP_ARGS` environment variables.

## Local Context Files

All CLI tools support a `-c` or `--local_context` parameter that allows you to provide additional context specific to your organization or environment. This context file should contain information that helps the AI agents understand your specific environment, such as:

- Organizational structure and naming conventions
- Specific technologies and tools in use
- Known threat actors or campaigns relevant to your organization
- Compliance requirements or regulatory considerations
- Previous hunting activities or findings

### Creating a context.txt File

Create a `context.txt` file in your project directory with relevant information. For example:

```markdown
# Organization Context
Organization: ACME Corporation
Environment: Mixed Windows/Linux environment with cloud infrastructure
Primary Technologies: Active Directory, AWS, Splunk Enterprise
Compliance: SOX, PCI DSS

# Known Threat Landscape
Recent Activity: Increased phishing attempts targeting finance department
Focus Areas: Lateral movement detection, privilege escalation
Previous Findings: Evidence of credential stuffing attacks in Q3 2024

# Infrastructure Details
Domain: acme.local
Key Servers: DC01, DC02, EXCH01
Network Segments: Corporate LAN (10.0.0.0/8), DMZ (192.168.1.0/24)
```

The context file is automatically ignored by Git (included in .gitignore) to prevent accidental commit of sensitive organizational information.

## Installation and Configuration

### 1. Clone the Repository
Clone this repository from GitHub:
```bash
git clone https://github.com/splunk/PEAK-Assistant.git
cd PEAK-Assistant
```

### 2. Environment Variables

Create a `.env` file in the project root with the following variables:

#### Required for All Tools:

```shell
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_ENDPOINT=https://your-azure-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_MODEL=gpt-4
AZURE_OPENAI_API_VERSION=2023-05-15
```

## If you want to use specific model details for the reasoning model, you can set:

```shell
AZURE_OPENAI_REASONING_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_REASONING_MODEL=gpt-4
```

It'll fall back to the above variables otherwise.

#### Required for Research Assistant:

```shell
TAVILY_API_KEY=your-tavily-api-key
```

#### Required for Data Assistant:

```shell
SPLUNK_SERVER_URL=https://your-splunk-server:8089
SPLUNK_MCP_USER=your-splunk-username
SPLUNK_MCP_PASSWD=your-splunk-password
SPLUNK_MCP_COMMAND=/path/to/python3
SPLUNK_MCP_ARGS=/path/to/splunk-mcp/splunk-mcp.py
```

The assistant primarily supports Azure OpenAI as an LLM backend. You may use any model available in your Azure deployment.

#### MCP Server Configuration (Data Assistant Only)

The data assistant requires a Model Context Protocol (MCP) server to interact with Splunk. The MCP server acts as a bridge between the AI agents and your Splunk instance. It is designed to work with the [`splunk-mcp` server](https://github.com/splunk/splunk-mcp).

- `SPLUNK_MCP_COMMAND`: Full path to the executable or script that starts your Splunk MCP server
- `SPLUNK_MCP_ARGS`: Arguments to pass to the MCP server command (can be multiple arguments separated by spaces)

Example configuration:

```bash
# Use a version of python3 that has the MCP module in it, such as the one
# that the PEAK-Assistant app is using
SPLUNK_MCP_COMMAND=/home/user/.pyenv/versions/peak-assistant/bin/python3
SPLUNK_MCP_ARGS=/home/user/splunk-mcp/splunk-mcp.py
```

### 3. Set Up a Python Environment
These instructions assume you are using `pyenv` to manage your Python environment.
If you are using another tool (e.g., `conda` or some other method of creating virtual
environments), adjust accordingly.

1. Install [pyenv](https://github.com/pyenv/pyenv) if not already installed. Configure
   your shell integration as per their instructions.
2. Install Python 3.13.2:

   ```bash
   pyenv install 3.13.2
   ```

3. Create and activate a virtual environment:
   ```bash
   pyenv virtualenv 3.13.2 peak-assistant
   pyenv local peak-assistant
   ```

### 4. Install Required Python Modules

Install dependencies using pip:

```bash
pip install -e .
```

### 5. SSL Certificates (Web Interface Only)

If you plan to use the web interface, you'll need SSL certificates. The Flask app expects `cert.pem` and `key.pem` files in the `UI/` directory.

For development, you can create self-signed certificates by running `generate_certificates.sh` and filling in the prompts.

## Quick Start

### Using the Web Interface (Recommended for beginners):

1. Complete the installation steps above
2. Create SSL certificates for the web interface:

   ```bash
   ./generate_certificates.sh
   ```

3. Start the web interface:
   ```bash
   peak-assistant
   ```
4. Open your browser to `https://127.0.0.1:8000/`
5. Follow the guided workflow through each phase

### Using CLI Tools (For automation/scripting):

1. Generate a research report:
   ```bash
   research-assistant -t "Kerberoasting" -f markdown
   ```

2. Generate hypotheses from the research:
   ```bash
   hypothesis-assistant -r kerberoasting.md
   ```

3. Refine a hypothesis:
   ```bash
   hypothesis-refiner -y "Your hypothesis here" -r kerberoasting.md -a
   ```

4. Create an ABLE table:
   ```bash
   able-assistant -r kerberoasting.md -y "Your refined hypothesis"
   ```

## Workflow

The PEAK-Assistant follows a structured workflow that aligns with the PEAK Threat Hunting Framework:

1. **Research Phase**: Generate comprehensive research reports on specific cybersecurity techniques or threat actors
2. **Hypothesis Generation**: Create testable hypotheses based on the research findings
3. **Hypothesis Refinement**: Improve and refine hypotheses through automated or human-guided feedback
4. **ABLE Table Creation**: Develop Actor, Behavior, Location, Evidence tables to scope the hunt
5. **Data Discovery**: Identify relevant data sources in your Splunk environment for testing hypotheses
6. **Hunt Planning**: Combine all components into a comprehensive threat hunting plan

You can use either the web interface for a guided experience or the CLI tools for automation and scripting.

See `requirements.txt` for the full list of required Python modules.

## Project Structure

```
PEAK-Assistant/
├── README.md                  # This file
├── pyproject.toml             # Python project definition
├── .env                       # Environment variables (create this)
├── context.txt                # Local context file (optional, ignored by git)
├── research_assistant/        # Research report generation
├── hypothesis_assistant/      # Hypothesis generation and refinement
├── able_assistant/            # ABLE table creation
├── data_assistant/            # Splunk data source discovery
└── UI/                        # Flask web interface
    ├── context.txt            # UI-specific context file (optional)
    ├── cert.pem & key.pem     # SSL certificates (create these)
    └── templates/             # HTML templates
```

## Notes

- All generated files (PDF reports, markdown files) are automatically ignored by Git to prevent repository bloat
- Context file (`context.txt`) is ignored by Git to protect sensitive organizational information
- The assistant is designed to work with Azure OpenAI and requires proper API credentials
- Some features (research, data discovery) require additional API keys and services
- The web interface provides a more user-friendly experience while CLI tools are better for automation

## Troubleshooting

### Common Issues:

1. **Missing Environment Variables**: Ensure your `.env` file contains all required variables for the features you want to use
2. **OpenAI API Errors**: Usually indicates rate limiting or server issues - try increasing retry counts or waiting
3. **SSL Certificate Issues**: For the web interface, ensure you've created the required SSL certificates
4. **Splunk Connection Issues**: Verify your Splunk credentials and server URL for data discovery features
5. **MCP Server Issues**: Ensure the `SPLUNK_MCP_COMMAND` points to a valid executable and that the MCP server can connect to your Splunk instance
6. **Permission Issues**: Ensure the application has write permissions for session storage

### Getting Help:

- Check the web interface's built-in help page for detailed usage instructions
- Review the CLI tool help with `<tool_name> --help`
- Examine error messages in the debug page of the web interface

## Contributing

When contributing to this project:
- Follow the existing code structure and naming conventions
- Test both CLI and web interface functionality
- Update documentation for any new features
- Be mindful of sensitive information in context files

## License
See the [LICENSE](LICENSE) for details.
