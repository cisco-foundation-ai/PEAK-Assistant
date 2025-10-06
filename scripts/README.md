# Configuration Validation Tool

## Overview

The configuration validation tool validates your `model_config.json` file and provides a comprehensive report showing:

- **Syntax and structure validation** - Ensures JSON is valid and has required fields
- **Provider configuration** - Tree view of all providers with their settings
- **Agent assignments** - Table showing which model each agent will use
- **Provider usage summary** - Statistics on provider and model usage
- **Warnings and recommendations** - Unused providers, missing model_info, etc.

## Usage

### Basic Validation

```bash
# Using the installed command (recommended)
uv run validate-config

# Or using the script directly
python scripts/validate_model_config.py
```

### Options

```bash
# Validate specific file
uv run validate-config -c /path/to/model_config.json
uv run validate-config --config /path/to/model_config.json

# Quiet mode (only show errors/warnings)
uv run validate-config -q
uv run validate-config --quiet

# Combine options
uv run validate-config -c /path/to/config.json -q
```

**Note:** The tool automatically loads your `.env` file (searching current and parent directories) before validation, just like the application does.

## Example Output

```
================================================================================
Model Configuration Validation Report
================================================================================

✓ Configuration is valid

⚠ 1 warning(s):

  ⚠ Provider 'ollama-local' is defined but not used by any agent

Providers (3 defined)
--------------------------------------------------------------------------------
├─ azure-main (azure)
│   ├─ Endpoint: https://example.azure.openai.com/
│   ├─ API Version: 2025-04-01-preview
│   └─ Credentials: (from env var)
│
├─ openai-native (openai)
│   ├─ Credentials: (from env var)
│   └─ No models defined
│
└─ ollama-local (openai)
    ├─ Credentials: ✓
    ├─ Base URL: http://localhost:11434/v1
    └─ Models defined: llama-3.1-8b

Agent Model Assignments (12 agents)
================================================================================
┌───────────────────────────┬──────────────────┬──────────────────────┬────────────────────┐
│ Agent                     │ Provider         │ Model                │ Source             │
├───────────────────────────┼──────────────────┼──────────────────────┼────────────────────┤
│ external_search_agent     │ azure-main       │ gpt-4o (gpt-4o-de... │ group:research-... │
│ internal_search_agent     │ azure-main       │ gpt-4o (gpt-4o-de... │ group:research-... │
│ summarizer_agent          │ azure-main       │ gpt-4o (gpt-4o-de... │ group:research-... │
│ summary_critic            │ azure-main       │ gpt-4o (gpt-4o-de... │ group:research-... │
│ research_selector         │ azure-main       │ gpt-4o (gpt-4o-de... │ group:research-... │
│ hunt_planner              │ azure-main       │ o4-mini (o4-mini-... │ group:reasoning... │
│ hunt_plan_critic          │ azure-main       │ o4-mini (o4-mini-... │ group:reasoning... │
│ critic                    │ azure-main       │ o4-mini (o4-mini-... │ group:reasoning... │
│ able_table                │ openai-native    │ gpt-4o-mini          │ agent              │
│ refiner                   │ azure-main       │ gpt-4o (gpt-4o-de... │ defaults           │
│ Data_Discovery_Agent      │ azure-main       │ gpt-4o (gpt-4o-de... │ defaults           │
│ Discovery_Critic_Agent    │ azure-main       │ gpt-4o (gpt-4o-de... │ defaults           │
└───────────────────────────┴──────────────────┴──────────────────────┴────────────────────┘

Provider Usage Summary
================================================================================

Provider: azure-main (type: azure)
  • gpt-4o: 8 agent(s)
    external_search_agent, internal_search_agent, summarizer_agent, summary_critic, research_selector, ... (+3 more)
  • o4-mini: 3 agent(s)
    hunt_planner, hunt_plan_critic, critic

Provider: foundation-ai (type: openai)
  Total agents: 1
  • /model: 1 agent(s)
    able_table

================================================================================
✓ Validation complete: No errors or warnings found
================================================================================
- ✗ Missing or invalid JSON
- ✗ Missing required top-level fields (`version`, `providers`, `defaults`)
- ✗ Invalid provider types (must be `azure` or `openai`)
- ✗ Missing required provider config fields
- ✗ Missing required agent fields (`model`, `deployment` for Azure)
- ✗ Agent references non-existent provider
- ✗ Environment variables not found (when used without defaults)

### Warnings (won't fail validation)

- ⚠ Provider defined but not used by any agent
- ⚠ OpenAI-compatible provider without `models` section
- ⚠ Non-standard model without `model_info`

## Integration with CI/CD

You can use this in CI/CD pipelines:

```bash
# Exit code 0 if valid, 1 if invalid
uv run validate-config -q

# In GitHub Actions
- name: Validate model config
  run: uv run validate-config -q
```

## Tips

1. **Run before committing** - Catch configuration errors early
2. **Review warnings** - They often indicate configuration that could be improved
3. **Check the table** - Quickly see if agents are using the expected models
4. **Look for unused providers** - Clean up your configuration
5. **Use `--quiet` in scripts** - Get just errors/warnings for automation
