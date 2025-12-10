# Model Configuration

The PEAK Assistant uses a **required** `model_config.json` file to configure LLM providers and models for each AI agent. This file must be placed in the current working directory (the directory from which you run the application).

## Overview
The configuration system allows you to:
- Define multiple named provider instances (Azure OpenAI, OpenAI, OpenAI-compatible servers, Anthropic)
- Use multiple instances of the same provider type (e.g., multiple Ollama servers, multiple Azure subscriptions)
- Assign different models to different agents
- Group agents with wildcard matching for shared configurations
- Use environment variable interpolation for secrets

## Configuration File Structure

The `model_config.json` file has the following top-level structure:

```json
{
  "version": "1",
  "providers": { ... },
  "defaults": { ... },
  "groups": { ... },
  "agents": { ... }
}
```

### Top-Level Fields

- **`version`** (string, required): Configuration schema version. Currently `"1"`.
- **`providers`** (object, required): Named provider instances with connection details.
- **`defaults`** (object, required): Default provider and model used when no agent-specific or group configuration is found.
- **`groups`** (object, optional): Named configuration profiles that can match multiple agents using wildcards.
- **`agents`** (object, optional): Per-agent configuration overrides keyed by agent name.

### Provider Definition Structure

Each entry in `providers` defines a named provider instance:

```json
{
  "providers": {
    "my-provider-name": {
      "type": "azure | openai | anthropic",
      "config": {
        // Provider-type-specific connection fields
      },
      "models": {
        // Optional: model_info for OpenAI-compatible servers
      }
    }
  }
}
```

### Agent Configuration Structure

Each entry in `defaults`, `groups`, or `agents` references a provider by name:

```json
{
  "provider": "my-provider-name",
  "model": "model-identifier"
}
```

For `groups` entries, you must also include a `match` field. If the sub-agent matches any of the patterns in the `match` array, it will use the configuration in the group. The `match` field supports glob patterns:

```json
{
  "match": ["agent_name_pattern", "another_*"],
  "provider": "my-provider-name",
  "model": "model-identifier"
}
```

**Note on wildcard matching:** Pattern matching is case-sensitive and uses standard glob syntax (`*` matches any characters, `?` matches a single character). Be aware that agent names use different separators:
- Most agents use underscores: `summary_critic`, `hunt_plan_critic`
- Some agents use dashes: `hypothesis-refiner`, `hypothesis-refiner-critic`
- Some use mixed case: `Data_Discovery_Agent`, `Discovery_Critic_Agent`

For example, the pattern `*_critic` will match `summary_critic` and `hunt_plan_critic`, but not `hypothesis-refiner-critic` (which uses a dash).

### Resolution Precedence

When resolving configuration for an agent, the system follows this precedence order:

1. **`agents.<agent_name>`** - Exact agent name match
2. **`groups.*`** - First matching group (evaluated in order, supports wildcards)
3. **`defaults`** - Global fallback

### Environment Variable Interpolation

You can use `${ENV_VAR}` syntax in any string value to interpolate environment variables. This is the recommended way to handle secrets like API keys:

```json
{
  "config": {
    "api_key": "${AZURE_OPENAI_API_KEY}",
    "endpoint": "${AZURE_OPENAI_ENDPOINT}"
  }
}
```

If an environment variable is not set, you can provide a default using `${ENV_VAR|default_value}`. Use `${ENV_VAR|null}` to explicitly set null when the variable is missing.

## Agent Names

The following agent names are used in the PEAK Assistant codebase. 

**NOTE: Some agents need models which are capable of calling MCP servers, sometimes referred to as "tool-calling" models. These are marked on the table with a ✅.**

| Agent Name | Phase | Purpose | Needs MCP | MCP Group |
|------------|-------|---------|-----------|-----------|
| `external_search_agent` | Research | Searches external sources (Internet) | ✅ | `research-external` |
| `summarizer_agent` | Research | Creates research report summaries | | |
| `summary_critic` | Research | Reviews and critiques summaries | | |
| `research_team_lead` | Research | Team-level selector for research workflow | | |
| `local_data_search_agent` | Local Data | Searches internal sources (wikis, tickets) | ✅ | `local-data-search` |
| `local_data_summarizer_agent` | Local Data | Summarizes local data research findings | | |
| `hypothesizer_agent` | Hypothesis Generation | Generates threat hunting hypotheses | | |
| `hypothesis-refiner` | Hypothesis Refinement | Refines threat hunting hypotheses | | |
| `hypothesis-refiner-critic` | Hypothesis Refinement | Critiques refined hypothesis quality | | |
| `able_table` | ABLE Table | Generates ABLE tables | | |
| `Data_Discovery_Agent` | Data Discovery | Identifies relevant Splunk data sources | ✅ | `data_discovery` |
| `Discovery_Critic_Agent` | Data Discovery | Reviews data discovery results | | |
| `hunt_planner` | Hunt Plan | Creates detailed hunt plans | | |
| `hunt_plan_critic` | Hunt Plan | Reviews hunt plan quality | | |

## Provider Types

### Azure OpenAI Provider Type

**Type:** `"azure"`

**Required config fields:**
- `endpoint` (string): Azure OpenAI endpoint URL
- `api_key` (string): Azure OpenAI API key
- `api_version` (string): Azure OpenAI API version

**Example provider definition:**
```json
{
  "providers": {
    "azure-main": {
      "type": "azure",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_key": "${AZURE_OPENAI_API_KEY}",
        "api_version": "2025-04-01-preview"
      }
    }
  }
}
```

**Agent usage:**
```json
{
  "agents": {
    "summarizer_agent": {
      "provider": "azure-main",
      "model": "gpt-4o",
      "deployment": "gpt-4o-deployment"
    }
  }
}
```

**Note:** For Azure, you must specify both `model` (the model identifier like "gpt-4o") and `deployment` (your Azure deployment name) in the agent configuration.

### Azure with Custom Authentication (auth_module)

For Azure OpenAI deployments behind an authentication gateway (e.g., OAuth2 gateways, enterprise proxies), you can provide a custom authentication module instead of a static API key.

**Optional field:**
- `auth_module` (string): Python module path to a custom authentication module

When `auth_module` is specified, the `api_key` field becomes optional in the `config` section. The auth module provides credentials at runtime.

**Quick example:**
```json
{
  "providers": {
    "azure-enterprise": {
      "type": "azure",
      "auth_module": "my_auth.enterprise_oauth",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_version": "2025-04-01-preview",
        "client_id": "${OAUTH_CLIENT_ID}",
        "client_secret": "${OAUTH_CLIENT_SECRET}",
        "token_endpoint": "${OAUTH_TOKEN_ENDPOINT}"
      }
    }
  }
}
```

The auth module must expose an async function `get_credentials(config)` that returns a dict with at least `api_key`.

**📖 For complete documentation on implementing custom authentication, see [CUSTOM_AUTHENTICATION.md](CUSTOM_AUTHENTICATION.md).**

### OpenAI Provider Type

**Type:** `"openai"`

**Required config fields:**
- `api_key` (string): OpenAI API key

**Optional config fields:**
- `base_url` (string): Custom API base URL (for OpenAI-compatible servers like Ollama, vLLM, LM Studio)
- `organization` (string): OpenAI organization ID
- `project` (string): OpenAI project ID

**Example provider definition (OpenAI native):**
```json
{
  "providers": {
    "openai-native": {
      "type": "openai",
      "config": {
        "api_key": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

**Example provider definition (OpenAI-compatible server):**
```json
{
  "providers": {
    "ollama-local": {
      "type": "openai",
      "config": {
        "api_key": "sk-local",
        "base_url": "http://localhost:11434/v1"
      }
    }
  }
}
```

**Agent usage:**
```json
{
  "agents": {
    "summarizer_agent": {
      "provider": "openai-native",
      "model": "gpt-4o-mini"
    },
    "able_table": {
      "provider": "ollama-local",
      "model": "llama-3.1-8b"
    }
  }
}
```

### Model Info for OpenAI-Compatible Servers

When using non-OpenAI model names with OpenAI-compatible servers, you should provide `model_info` for each model in the provider's `models` section. This describes the model's capabilities to the client library.

**Required `model_info` fields:**
- `id` (string): Model identifier (should match the model name)
- `family` (string): Model family (e.g., "gpt-4o-mini", "llama-3")
- `vision` (boolean): Whether the model supports vision/image inputs
- `audio` (boolean): Whether the model supports audio inputs
- `function_calling` (boolean): Whether the model supports function calling
- `json_output` (boolean): Whether the model supports JSON mode
- `structured_output` (boolean): Whether the model supports structured outputs
- `input` (object): Input token limits
  - `max_tokens` (integer): Maximum input tokens
- `output` (object): Output token limits
  - `max_tokens` (integer): Maximum output tokens

**Optional `model_info` fields:**
- `object` (string): Object type (typically "model")
- `owned_by` (string): Model owner/provider
- `tokenizer` (string): Tokenizer identifier

**Example provider with model_info:**
```json
{
  "providers": {
    "ollama-local": {
      "type": "openai",
      "config": {
        "api_key": "sk-local",
        "base_url": "http://localhost:11434/v1"
      },
      "models": {
        "llama-3.1-8b": {
          "model_info": {
            "id": "llama-3.1-8b",
            "object": "model",
            "owned_by": "local",
            "family": "llama-3",
            "vision": false,
            "audio": false,
            "function_calling": false,
            "json_output": false,
            "structured_output": false,
            "input": { "max_tokens": 131072 },
            "output": { "max_tokens": 8192 },
            "tokenizer": "tiktoken-gpt-4o"
          }
        },
        "qwen-2.5-72b": {
          "model_info": {
            "id": "qwen-2.5-72b",
            "family": "qwen-2",
            "vision": false,
            "audio": false,
            "function_calling": true,
            "json_output": true,
            "structured_output": false,
            "input": { "max_tokens": 32768 },
            "output": { "max_tokens": 8192 }
          }
        }
      }
    }
  }
}
```

**Agent usage:**
```json
{
  "agents": {
    "able_table": {
      "provider": "ollama-local",
      "model": "llama-3.1-8b"
    },
    "hunt_planner": {
      "provider": "ollama-local",
      "model": "qwen-2.5-72b"
    }
  }
}
```

The system will automatically look up the `model_info` for each model when creating the client.

### Anthropic Provider Type

**Type:** `"anthropic"`

The Anthropic provider connects to Anthropic's Claude models via their API.

**Required Fields:**
- `api_key` (string): Your Anthropic API key

**Optional Fields:**
- `max_tokens` (integer): Maximum tokens in response (default: model-specific)
- `temperature` (float): Sampling temperature 0.0-1.0 (default: 1.0)
- `top_p` (float): Nucleus sampling parameter (default: 1.0)
- `base_url` (string): Custom API endpoint (for proxies)
- `timeout` (float): Request timeout in seconds
- `max_retries` (integer): Number of retry attempts

**Example Configuration:**

```json
{
  "providers": {
    "anthropic-main": {
      "type": "anthropic",
      "config": {
        "api_key": "${ANTHROPIC_API_KEY}",
        "max_tokens": 4096,
        "temperature": 0.7
      }
    }
  }
}
```

**Agent Configuration:**

Anthropic agents require only the `model` field:

```json
{
  "agents": {
    "summarizer_agent": {
      "provider": "anthropic-main",
      "model": "claude-3-5-sonnet-20241022"
    },
    "hunt_planner": {
      "provider": "anthropic-main",
      "model": "claude-3-5-haiku-20241022"
    }
  }
}
```

## Configuration Examples

### Example 1: Single Model for All Agents (Defaults Only)

This is the simplest configuration where every agent uses the same model:

```json
{
  "version": "1",
  "providers": {
    "azure-main": {
      "type": "azure",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_key": "${AZURE_OPENAI_API_KEY}",
        "api_version": "2025-04-01-preview"
      }
    }
  },
  "defaults": {
    "provider": "azure-main",
    "model": "gpt-4o",
    "deployment": "gpt-4o-deployment"
  }
}
```

### Example 2: Mixed Models (GPT-4o and o4-mini)

This configuration uses GPT-4o for most agents but assigns o4-mini to specific reasoning-focused agents:

```json
{
  "version": "1",
  "providers": {
    "azure-main": {
      "type": "azure",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_key": "${AZURE_OPENAI_API_KEY}",
        "api_version": "2025-04-01-preview"
      }
    }
  },
  "defaults": {
    "provider": "azure-main",
    "model": "gpt-4o",
    "deployment": "gpt-4o-deployment"
  },
  "groups": {
    "reasoning-agents": {
      "match": ["*_critic", "hunt_planner"],
      "provider": "azure-main",
      "model": "o4-mini",
      "deployment": "o4-mini-deployment"
    }
  }
}
```

In this example:
- Most agents use GPT-4o (from `defaults`)
- Agents matching `*_critic` or `hunt_planner` use o4-mini
- Both use the same Azure provider instance (`azure-main`)

### Example 3: Azure OpenAI (Complete Configuration)

Full Azure OpenAI configuration with all possible fields:

```json
{
  "version": "1",
  "providers": {
    "azure-main": {
      "type": "azure",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_key": "${AZURE_OPENAI_API_KEY}",
        "api_version": "2025-04-01-preview"
      }
    }
  },
  "defaults": {
    "provider": "azure-main",
    "model": "gpt-4o",
    "deployment": "gpt-4o-deployment"
  },
  "agents": {
    "hunt_planner": {
      "provider": "azure-main",
      "model": "o4-mini",
      "deployment": "o4-mini-deployment"
    }
  }
}
```

### Example 4: OpenAI Native (Complete Configuration)

Full OpenAI native configuration with all possible fields:

```json
{
  "version": "1",
  "providers": {
    "openai-native": {
      "type": "openai",
      "config": {
        "api_key": "${OPENAI_API_KEY}",
        "organization": "${OPENAI_ORG_ID}",
        "project": "${OPENAI_PROJECT_ID}"
      }
    }
  },
  "defaults": {
    "provider": "openai-native",
    "model": "gpt-4o-mini"
  },
  "agents": {
    "hunt_planner": {
      "provider": "openai-native",
      "model": "gpt-4o"
    }
  }
}
```

### Example 5: OpenAI-Compatible Server (Complete Configuration)

Full OpenAI-compatible configuration with model_info for a local Ollama server:

```json
{
  "version": "1",
  "providers": {
    "ollama-local": {
      "type": "openai",
      "config": {
        "api_key": "sk-local",
        "base_url": "http://localhost:11434/v1"
      },
      "models": {
        "llama-3.1-8b": {
          "model_info": {
            "id": "llama-3.1-8b",
            "object": "model",
            "owned_by": "local",
            "family": "llama-3",
            "vision": false,
            "audio": false,
            "function_calling": false,
            "json_output": false,
            "structured_output": false,
            "input": { "max_tokens": 131072 },
            "output": { "max_tokens": 8192 },
            "tokenizer": "tiktoken-gpt-4o"
          }
        },
        "llama-3.1-70b": {
          "model_info": {
            "id": "llama-3.1-70b",
            "object": "model",
            "owned_by": "local",
            "family": "llama-3",
            "vision": false,
            "audio": false,
            "function_calling": false,
            "json_output": false,
            "structured_output": false,
            "input": { "max_tokens": 131072 },
            "output": { "max_tokens": 16384 },
            "tokenizer": "tiktoken-gpt-4o"
          }
        }
      }
    }
  },
  "defaults": {
    "provider": "ollama-local",
    "model": "llama-3.1-8b"
  },
  "agents": {
    "hunt_planner": {
      "provider": "ollama-local",
      "model": "llama-3.1-70b"
    }
  }
}
```

### Example 6: Complex Multi-Provider Configuration

This example demonstrates a sophisticated setup using multiple provider instances, groups, and per-agent overrides:

```json
{
  "version": "1",
  "providers": {
    "azure-main": {
      "type": "azure",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_key": "${AZURE_OPENAI_API_KEY}",
        "api_version": "2025-04-01-preview"
      }
    },
    "openai-native": {
      "type": "openai",
      "config": {
        "api_key": "${OPENAI_API_KEY}"
      }
    },
    "ollama-local": {
      "type": "openai",
      "config": {
        "api_key": "sk-local",
        "base_url": "http://localhost:11434/v1"
      },
      "models": {
        "llama-3.1-8b": {
          "model_info": {
            "id": "llama-3.1-8b",
            "family": "llama-3",
            "vision": false,
            "audio": false,
            "function_calling": false,
            "json_output": false,
            "structured_output": false,
            "input": { "max_tokens": 131072 },
            "output": { "max_tokens": 8192 }
          }
        }
      }
    },
    "lmstudio-local": {
      "type": "openai",
      "config": {
        "api_key": "sk-local",
        "base_url": "http://localhost:1234/v1"
      }
    }
  },
  "defaults": {
    "provider": "azure-main",
    "model": "gpt-4o",
    "deployment": "gpt-4o-deployment"
  },
  "groups": {
    "research-team": {
      "match": ["external_search_*", "research_team_lead"],
      "provider": "azure-main",
      "model": "gpt-4o",
      "deployment": "gpt-4o-deployment"
    },
    "reasoning-agents": {
      "match": ["*_critic", "hunt_planner", "hunt_plan_critic"],
      "provider": "azure-main",
      "model": "o4-mini",
      "deployment": "o4-mini-deployment"
    }
  },
  "agents": {
    "summarizer_agent": {
      "provider": "openai-native",
      "model": "gpt-4.1-mini"
    },
    "able_table": {
      "provider": "ollama-local",
      "model": "llama-3.1-8b"
    }
  }
}
```

In this configuration:
- Most agents use Azure GPT-4o (from `defaults`)
- Research agents (`external_search_agent` and `research_team_lead`) use Azure GPT-4o via the `research-team` group
- Critic and planner agents use Azure o4-mini via the `reasoning-agents` group
- `summarizer_agent` uses OpenAI native GPT-4.1-mini
- `able_table` uses Ollama (local) with Llama 3.1 8B

This demonstrates mixing three different provider instances and four different models in a single configuration: Azure OpenAI, OpenAI native, and Ollama (OpenAI-compatible).


## Troubleshooting

### Missing Configuration File

**Error:** `model_config.json not found in current working directory`

**Solution:** Create a `model_config.json` file in the directory from which you run the PEAK Assistant. Use one of the examples above as a starting point.

### Missing Environment Variables

**Error:** `Environment variable AZURE_OPENAI_API_KEY not found`

**Solution:** Ensure all environment variables referenced with `${VAR}` syntax are set. You can set them in your shell or in a `.env` file.

### Invalid Provider Type

**Error:** `Unsupported provider type 'xyz'`

**Solution:** The provider `type` field must be one of: `"azure"`, `"openai"`, `"anthropic"`. Check for typos in your provider definitions.

### Missing Required Fields

**Error:** `Missing required field 'deployment' for Azure agent`

**Solution:** Ensure all required fields for your chosen provider type are present. For Azure agents, you must specify both `model` and `deployment` in the agent configuration. See the provider-specific sections above for required fields.

### Provider Not Found

**Error:** `Provider 'my-provider' not found in providers section`

**Solution:** Ensure the provider name referenced in `defaults`, `groups`, or `agents` exists in the `providers` section. Check for typos in provider names.

### Agent Not Found

If an agent name is not found in the configuration, the system will use the `defaults` configuration. If you want to verify which configuration an agent is using, check the application logs during startup.

## Future Extensions

The configuration system is designed to be extensible. Future versions may support:
- Additional providers 
- Per-request generation parameters (temperature, max_tokens, etc.)
- Model-specific tool/function calling configurations
- Hot-reloading of configuration changes

These extensions will be backward-compatible with the current schema version.
