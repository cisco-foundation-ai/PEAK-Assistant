# Evaluation Utilities

Shared utilities for PEAK Assistant evaluation scripts.

## Modules

### `env_loader.py`

Provides environment variable loading utilities for evaluation scripts.

**Functions:**
- `find_dotenv_file()` - Search for .env file in current and parent directories
- `load_environment(quiet=False)` - Load environment variables from .env file

**Usage:**
```python
from utils import load_environment

# Load .env file at script startup
load_environment()

# Or suppress status messages
load_environment(quiet=True)
```

**Features:**
- Automatic .env file discovery (searches up directory tree)
- Status messages to stderr (can be suppressed with `quiet=True`)
- Enables `${ENV_VAR}` interpolation in model_config.json

### `eval_model_client.py`

Provides `EvaluatorModelClient` - a synchronous wrapper around PEAK Assistant's async model factory for use in evaluation scripts.

**Features:**
- Synchronous LLM calls for sequential evaluation workflows
- Supports all PEAK Assistant providers (Azure OpenAI, OpenAI, Anthropic, etc.)
- Model client caching for performance
- Provider-agnostic API

**Usage:**
```python
from utils import EvaluatorModelClient

# Initialize with model_config.json path
client = EvaluatorModelClient(config_path=Path("model_config.json"))

# Make LLM calls with judge roles
response = client.call_llm(
    judge_role="assertion_quality",
    prompt="Evaluate this hypothesis...",
    max_tokens=300,
    temperature=0.0
)

# Get model info
model_name = client.get_model_name("assertion_quality")
provider = client.get_provider_type("assertion_quality")
```

**Judge Roles:**
Judge roles map to agent names in `model_config.json`. Each evaluation script defines its own set of judge roles based on its evaluation criteria.

## Adding New Utilities

When adding new shared utilities for evaluation scripts:

1. Create the module in this directory
2. Add it to `__init__.py` exports
3. Document it in this README
4. Ensure it follows the same patterns (sync API, model config integration)

## Design Principles

- **Synchronous API**: Evaluation scripts make many sequential LLM calls, so sync APIs are more natural
- **Provider Agnostic**: Support all PEAK Assistant providers without evaluation scripts needing provider-specific code
- **Configuration Driven**: Use `model_config.json` for all LLM configuration
- **Reusable**: Design utilities to work across multiple evaluation scripts
