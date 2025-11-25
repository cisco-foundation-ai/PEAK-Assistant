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

### Full Workflow Tests

#### CLI Tool Workflow Test

Tests the complete workflow using command-line tools (subprocess calls):

```bash
# Basic usage
python tests/integration/test_full_workflow.py "PowerShell Empire"

# With local context file
python tests/integration/test_full_workflow.py "T1055 Process Injection" \
    -c /path/to/local_context.txt

# Keep output files for inspection
python tests/integration/test_full_workflow.py "Cobalt Strike" --keep-files

# Save to specific directory
python tests/integration/test_full_workflow.py "APT29" \
    --temp-dir ./test_outputs --keep-files
```

#### MCP Server Workflow Test

Tests the complete workflow using the MCP server interface (FastMCP client):

```bash
# Basic usage (ERROR level logs only - cleanest output)
python tests/integration/test_mcp_full_workflow.py "PowerShell Empire"

# With warnings (WARNING level)
python tests/integration/test_mcp_full_workflow.py "PowerShell Empire" -v

# With verbose output (INFO level)
python tests/integration/test_mcp_full_workflow.py "PowerShell Empire" -vv

# With debug output (DEBUG level)
python tests/integration/test_mcp_full_workflow.py "PowerShell Empire" -vvv

# With local context file
python tests/integration/test_mcp_full_workflow.py "T1055 Process Injection" \
    -c /path/to/local_context.txt

# Keep output files for inspection
python tests/integration/test_mcp_full_workflow.py "Cobalt Strike" --keep-files

# Save to specific directory
python tests/integration/test_mcp_full_workflow.py "APT29" \
    --temp-dir ./test_outputs --keep-files
```

**Verbosity Levels:**
- Default (no -v): Shows only ERROR messages (cleanest output)
- `-v`: Shows WARNING and ERROR messages
- `-vv`: Shows INFO, WARNING, and ERROR messages (detailed progress)
- `-vvv`: Shows DEBUG, INFO, WARNING, and ERROR messages (full debugging)

**Both workflow tests:**
- Execute all 7 workflow steps in order
- Show timing for each step
- Save outputs to temporary files
- Display preview of each output
- Clean up temp files on success (unless --keep-files specified)
- Test with **real agents and real API calls**

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

### Provider Tests

Each provider test makes one API call with a minimal prompt ("Say 'Hello' and nothing else").

- Azure OpenAI: ~$0.0001 per test (depending on model)
- OpenAI: ~$0.0001 per test (depending on model)
- Local models (Ollama, LM Studio): Free

Estimate: Testing 5 provider/model combinations ≈ $0.0005

### Workflow Tests

**Full workflow tests are significantly more expensive** as they run all 7 agents with real research/analysis tasks:

1. Internet Research (multi-agent with search)
2. Local Data Search (optional, may require MCP servers)
3. Hypothesis Generation
4. Hypothesis Refinement
5. ABLE Table Generation
6. Data Discovery (may require MCP servers)
7. Hunt Planning

**Estimated costs per workflow run:**
- **Time:** 5-10 minutes total (varies by model speed)
- **API Cost:** $0.10 - $0.50 per run (depends on models and topic complexity)
- **Token Usage:** ~50,000-200,000 tokens across all steps

**Recommendations:**
- Run workflow tests sparingly (before releases, after major changes)
- Use `--keep-files` to preserve outputs for inspection
- Test with smaller/cheaper models first (e.g., gpt-4o-mini)
- Consider local models for development testing

## Legacy Tests (Deprecated)

The following test files use the old environment variable-based configuration and will be removed:

- `test_azure_live.py`
- `test_azure_reasoning_live.py`
- `test_openai_live.py`
- `test_openai_base_url_live.py`
- `test_openai_reasoning_base_url_live.py`

Use `test_live_all_providers.py` instead, which works with the new `model_config.json` system.
