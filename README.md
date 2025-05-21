# PEAK-Assistant
PEAK-Assistant is an AI-powered threat hunting assistant designed to help cybersecurity professionals generate, refine, and document threat hunting hypotheses and research. It aligns with the [PEAK Threat Hunting Framework](https://www.splunk.com/en_us/form/the-peak-threat-hunting-framework.html) and leverages large language models and automated research tools to streamline the process of preparing for a hunt.

## Overview
This repository provides a suite of command-line tools to:
- Generate detailed threat hunting research reports for specific techniques.
- Suggest and refine threat hunting hypotheses.
- Create PEAK ABLE tables to help scope the hunt.

## Tools and CLI Scripts

### 1. `research_assistant_cli.py`
**Purpose:** Generate a comprehensive threat hunting research report for a given technique, using automated research and summarization agents.

**Arguments:**
- `-t`, `--technique` (required): The cybersecurity technique to research.
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-f`, `--format`: Output format (`pdf` or `markdown`). Default: `markdown`.
- `-v`, `--verbose`: Enable verbose output.
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
python research_assistant/research_assistant_cli.py -t "Kerberoasting" -f markdown
```

---

### 2. `hypothesis_assistant_cli.py`
**Purpose:** Suggest testable threat hunting hypotheses based on user input and a research document.

**Arguments:**
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-r`, `--research` (required): Path to the research document (markdown file).
- `-u`, `--user_input`: User input for hypothesis generation (optional).
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
python hypothesis_assistant/hypothesis_assistant_cli.py -r kerberoasting.md -u "Focus on use for lateral movement."
```

**Notes:**
Use the `-u` option to provide additional guidance or input (e.g., local context) to the hypothesis generation process. 
---

### 3. `hypothesis_refiner_cli.py`
**Purpose:** Refine and improve a threat hunting hypothesis using automated and/or human-in-the-loop feedback.

**Arguments:**
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-y`, `--hypothesis` (required): The hypothesis to be refined.
- `-r`, `--research` (required): Path to the research document (markdown file).
- `-c`, `--context`: Additional context or guidelines (optional).
- `-v`, `--verbose`: Enable verbose output.
- `-a`, `--automated`: Enable automated mode (no human feedback).
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
python hypothesis_assistant/hypothesis_refiner_cli.py -y "threat actors are using kerberoasting for lateral movement by requesting user tickets and then using them shortly after" -r kerberoasting.md -a
```

**Notes:**
Hypothesis refinement is an interactive process with human involvement to steer things in the correct direction. By default, `hypothesis_refiner_cli.py` will prompt the user for their 
input/feedback after every refinement attempt. You can continue with as many rounds of refinement as you like; when you are finished, mention the string 
`YYY-HYPOTHESIS-ACCEPTED-YYY` to let the agent know you're finished. 

**I WILL be improving this experience later.**

If you prefer a completely automated refinement experience, use the `-a` option, as shown in the example. This will prevent all prompts for user input and simply output the refined hypothesis.

---

### 4. `able_assistant_cli.py`
**Purpose:** Generate a PEAK ABLE table (Actor, Behavior, Location, Evidence) for a given hypothesis and research document.

**Arguments:**
- `-e`, `--environment`: Path to a specific `.env` file to use.
- `-r`, `--research` (required): Path to the research document (markdown file).
- `-y`, `--hypothesis` (required): The hunting hypothesis.
- `-h`, `--help`: Show help message and exit.

**Example:**
```bash
python able_assistant/able_assistant_cli.py -r kerberoasting.md -y "Adversaries seeking lateral movement via Kerberoasting will request Kerberos service tickets (TGS) for user-based SPNs associated with privileged or lateral-movement-enabled service accounts, followed shortly by successful authentication or remote access events (e.g., SMB, RDP, WinRM) using those accounts from previously unseen endpoints."
```

## Installation and Configuration

### 1. Clone the Repository
Clone this repository from GitHub:
```bash
git clone https://github.com/splunk/PEAK-Assistant.git
cd PEAK-Assistant
```

### 2. Create a `.env` File
Create a `.env` file in the project root with the following variables (example):

```
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_ENDPOINT=https://your-azure-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_MODEL=gpt-4
AZURE_OPENAI_API_VERSION=2023-05-15
# TAVILY_API_KEY is only required for the research agent
TAVILY_API_KEY=your-tavily-api-key
```

The assistant only supports Azure as an LLM backend. You may use any model available in your Azure deployment.

### 3. Set Up a Python Environment
These instructions assume you are using `pyenv` to manage your Python environment.
If you are using another tool (e.g., `conda` or some other method of creating virtual
environments, adjust accordingly).

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
pip install -r requirements.txt
```

## Requirements
See `requirements.txt` for the full list of required Python modules.

## License
See the [LICENSE](LICENSE) for details.
