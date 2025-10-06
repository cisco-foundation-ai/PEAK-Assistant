# Live Integration Tests

These tests make **real API calls** to configured LLM providers and may incur costs.

## Prerequisites

1. **Create `model_config.json`** in the repository root
   - Copy `model_config.json.example` as a starting point
   - Configure at least one provider with valid credentials
   - See `MODEL_CONFIGURATION.md` for full documentation

2. **Create `.env` file** with secrets (or set environment variables)
   - The test automatically loads `.env` from the current or parent directories (same as the app)
   - Example `.env`:
     ```bash
     AZURE_OPENAI_API_KEY=your-key
     AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
     OPENAI_API_KEY=sk-your-key
     ```
   - Or export environment variables directly in your shell

## Running Tests

### Test All Configured Providers

This discovers and tests every provider/model combination in your `model_config.json`:

```bash
# Run with verbose output showing each provider/model being tested
pytest -m live tests/integration/test_live_all_providers.py -v -s

# Or without -s (output still shows but may be captured)
pytest -m live tests/integration/test_live_all_providers.py -v
```

**The `-s` flag disables output capture** so you see status messages in real-time as each provider is tested.

**Output includes:**
- List of all provider/model combinations found
- Real-time status as each provider/model is tested
- Test result for each (PASS/FAIL/ERROR)
- Response preview for successful tests
- Summary with pass/fail/error counts

### Run All Live Tests

```bash
pytest -m live tests/integration/ -v
```

## Example Output

```
Testing 4 provider/model combinations
================================================================================

Testing: defaults (azure)
  Provider: azure-main
  Model: gpt-4o
  Agent: (defaults)
  ✓ Response: Hello...

Testing: able_table (openai)
  Provider: openai-native
  Model: gpt-4o-mini
  Agent: able_table
  ✓ Response: Hello...

Testing: group:reasoning-agents (azure)
  Provider: azure-main
  Model: o4-mini
  Agent: test_critic
  ✓ Response: Hello...

Testing: group:research-team (azure)
  Provider: azure-main
  Model: gpt-4o
  Agent: summarizer_agent
  ✓ Response: Hello...

================================================================================
SUMMARY
================================================================================

✓ defaults (azure)                                     PASS  
✓ able_table (openai)                                  PASS  
✓ group:reasoning-agents (azure)                       PASS  
✓ group:research-team (azure)                          PASS  

Total: 4 | Passed: 4 | Failed: 0 | Errors: 0
================================================================================
```

## Test Behavior

- **Skips** if `model_config.json` is not found
- **Skips** individual agents if not configured
- **Fails** if a configured provider returns an error
- **Deduplicates** provider/model combinations to avoid redundant tests
- **Tests** defaults, all agents, and one agent per group

## Cost Considerations

Each test makes one API call with a minimal prompt ("Say 'Hello' and nothing else").

- Azure OpenAI: ~$0.0001 per test (depending on model)
- OpenAI: ~$0.0001 per test (depending on model)
- Local models (Ollama, LM Studio): Free

Estimate: Testing 5 provider/model combinations ≈ $0.0005

## Legacy Tests (Deprecated)

The following test files use the old environment variable-based configuration and will be removed:

- `test_azure_live.py`
- `test_azure_reasoning_live.py`
- `test_openai_live.py`
- `test_openai_base_url_live.py`
- `test_openai_reasoning_base_url_live.py`

Use `test_live_all_providers.py` instead, which works with the new `model_config.json` system.
