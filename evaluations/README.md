# PEAK Assistant Evaluation Suite

Comprehensive evaluation tools for assessing the quality of PEAK Assistant outputs across different use cases.

## Overview

The PEAK Assistant evaluation suite consists of three specialized evaluators, each designed to assess different types of threat hunting outputs:

1. **[Research Evaluator](research-agent-team-eval/)** - Evaluates threat hunting research reports for depth, accuracy, and comprehensiveness (13 criteria)
2. **[Hypothesis Evaluator](hypothesis-eval/)** - Evaluates threat hunting hypotheses for quality, specificity, and actionability (8 criteria)
3. **[Hunt Plan Evaluator](hunt-plan-eval/)** - Evaluates complete hunt plans for technical accuracy, organization, and completeness (10 criteria)

Each evaluator uses LLM-based judges to provide detailed, consistent scoring across multiple quality dimensions.

## Quick Start

### Prerequisites

1. **Python Environment**: All dependencies are included in the main repository's `pyproject.toml`
2. **API Keys**: Set up API keys for your chosen LLM provider(s)
3. **Model Configuration**: Create a `model_config.json` file (see below)

### Basic Setup

1. **Create `.env` file** in the evaluations directory or any parent directory:
```bash
# For Anthropic
ANTHROPIC_API_KEY=your_key_here

# For OpenAI
OPENAI_API_KEY=your_key_here

# For Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your_key_here
```

If the evaluators use only models that are configured in the PEAK Assistant model configuration, you can skip this step. The `.env` file used by the Assistant app will be loaded automatically.

2. **Create `model_config.json`** - Simple default configuration that works for all evaluators:
```json
{
  "version": "1",
  "providers": {
    "openai": {
      "type": "openai",
      "config": {
        "api_key": "${OPENAI_API_KEY}"
      }
    }
  },
  "defaults": {
    "provider": "openai",
    "model": "gpt-4.1"
  }
}
```

This minimal configuration uses GPT-4.1 for all evaluation judges. For more advanced configurations with different models for different judge types, see the individual evaluator READMEs.

3. **Run an evaluator**:
```bash
cd hypothesis-eval
python hypothesis_evaluator.py hypotheses.txt
```

The evaluator will automatically:
- Load environment variables from `.env` in the current directory or any parent directory
- Use `model_config.json` in the current directory

## Common Configuration

### Model Configuration

All three evaluators use the same flexible model configuration system that supports:
- **Multiple providers**: Anthropic, OpenAI, Azure OpenAI, or any other OpenAI-compatible AI provider (e.g., models served by Ollama or LM Studio)
- **Per-judge configuration**: Different models for different evaluation criteria
- **Group-based configuration**: Assign models to groups of similar judges
- **Environment variable interpolation**: Keep API keys secure with `${ENV_VAR}` syntax

#### Configuration Structure

```json
{
  "version": "1",
  "providers": {
    "provider-name": {
      "type": "anthropic|openai|azure",
      "config": {
        "api_key": "${API_KEY_ENV_VAR}",
        // Provider-specific config
      }
    }
  },
  "defaults": {
    "provider": "provider-name",
    "model": "model-name"
  },
  "groups": {
    "group-name": {
      "match": ["judge1", "judge2"],
      "provider": "provider-name",
      "model": "model-name"
    }
  },
  "agents": {
    "specific-judge": {
      "provider": "provider-name",
      "model": "model-name"
    }
  }
}
```

#### Fallback Order

The configuration system resolves judge models in this order:
1. **Specific agent** (`agents` section) - Highest priority
2. **Group match** (`groups` section with wildcard matching)
3. **Defaults** (`defaults` section) - Fallback

#### Example: Multi-Provider Configuration

```json
{
  "version": "1",
  "providers": {
    "anthropic-main": {
      "type": "anthropic",
      "config": {
        "api_key": "${ANTHROPIC_API_KEY}",
        "max_tokens": 4096
      }
    },
    "openai-main": {
      "type": "openai",
      "config": {
        "api_key": "${OPENAI_API_KEY}"
      }
    }
  },
  "defaults": {
    "provider": "anthropic-main",
    "model": "claude-sonnet-4-20250514"
  },
  "groups": {
    "critical-judges": {
      "match": ["technical_accuracy", "assertion_quality"],
      "provider": "anthropic-main",
      "model": "claude-opus-4-1-20250805",
      "comment": "Use best model for critical evaluations"
    },
    "fast-judges": {
      "match": ["grammatical_clarity", "structure_compliance"],
      "provider": "anthropic-main",
      "model": "claude-3-5-haiku-20241022",
      "comment": "Use fast model for simple checks"
    }
  }
}
```

See individual evaluator READMEs for specific judge names and recommended groupings.

### Environment Variables

All evaluators automatically load environment variables from a `.env` file. The file is searched in:
1. Current working directory
2. Parent directories (up the tree)

#### Supported Variables

**Anthropic:**
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

**OpenAI:**
```bash
OPENAI_API_KEY=sk-...
```

**Azure OpenAI:**
```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_API_VERSION=2025-04-01-preview  # Optional, has default
```

### Common Command-Line Options

All evaluators support these common options:

- `-c, --model-config PATH` - Path to model_config.json (default: `model_config.json` in current directory)
- `-q, --quiet` - Quiet mode (no console output, only files)
- `--log FILE` - Save console output to log file
- `-j, --json-output FILE` - Save detailed JSON results
- `--no-json` - Disable JSON output file
- `--raw` - Print raw Markdown instead of rendering with rich (if rich is installed)

See individual evaluator READMEs for evaluator-specific options.

## Output Formats

### Console Output

All evaluators provide:
- **Progress tracking** (with tqdm if installed)
- **Rich markdown rendering** (with rich if installed, disable with `--raw`)
- **Summary statistics** at completion
- **Verbose mode** for detailed per-item results (use `-v` where available)

### JSON Output

Each evaluator produces structured JSON output with:
- Metadata (evaluation date, models used, configuration)
- Individual evaluation results with scores and feedback
- Summary statistics and comparisons (where applicable)

### Log Files

Console output can be captured to log files for:
- Audit trails
- Debugging
- Sharing results

## Individual Evaluators

### [Research Evaluator](research-agent-team-eval/)

Evaluates threat hunting research reports with comprehensive quality metrics.

**Use cases:**
- Comparing research agent configurations
- Assessing report quality across multiple topics
- A/B testing different model combinations

**Key features:**
- 13 evaluation criteria
- Report generation workflow
- Multi-backend comparison mode
- Statistical analysis and outlier detection

[→ Full Documentation](research-agent-team-eval/README.md)

### [Hypothesis Evaluator](hypothesis-eval/)

Evaluates threat hunting hypotheses from text files.

**Use cases:**
- Assessing hypothesis quality before hunt planning
- Comparing hypotheses generated by different models
- Training and calibration

**Key features:**
- 8 evaluation criteria
- Batch processing of multiple files
- Per-hypothesis detailed scoring

[→ Full Documentation](hypothesis-eval/README.md)

### [Hunt Plan Evaluator](hunt-plan-eval/)

Evaluates complete hunt plans in Markdown format.

**Use cases:**
- Validating hunt plan completeness and quality
- Comparing plans generated by different configurations
- Quality assurance before hunt execution

**Key features:**
- 10 evaluation criteria with tiered weights
- Side-by-side comparison of two plans
- Template conformance checking

[→ Full Documentation](hunt-plan-eval/README.md)

## Best Practices

### Model Selection

1. **Use tiered models**: Assign expensive models (e.g., Claude Opus) to critical criteria, cheaper models (e.g., Haiku) to simple checks
2. **Test configurations**: Run small evaluations to validate your model config before large batches
3. **Monitor costs**: Track API usage, especially with expensive models

### Evaluation Workflow

1. **Start small**: Test with 1-2 items before running large batches
2. **Use verbose mode**: Add `-v` flag to see detailed per-item results
3. **Save logs**: Always use `--log` for audit trails
4. **Version control configs**: Keep your `model_config.json` in version control

### Rate Limiting

All evaluators include retry logic with exponential backoff:
- **429 errors**: Automatic retry with 5s, 10s, 20s delays
- **Other errors**: Automatic retry with 1s, 2s, 4s delays
- **Max retries**: 2 retries (3 total attempts)

If you hit rate limits frequently:
1. Reduce concurrent evaluations
2. Use cheaper/faster models
3. Add delays between batches
4. Check your API tier limits

## Troubleshooting

### "model_config.json not found"

**Solution**: Create a `model_config.json` file in your working directory or specify path with `-c`

### "API key required" or "401 Unauthorized"

**Solution**: 
1. Check your `.env` file exists and has correct API keys
2. Verify environment variable names match your `model_config.json`
3. Ensure API keys are valid and have sufficient credits

### "429 Rate Limit" errors

**Solution**:
1. Wait a few minutes and retry
2. Use slower/cheaper models
3. Reduce batch size
4. Check your API tier limits

### Progress bar not showing

**Solution**: Install tqdm: `pip install tqdm` or `uv add tqdm`

### Markdown not rendering nicely

**Solution**: Install rich: `pip install rich` or `uv add rich`

## Contributing

When adding new evaluators or modifying existing ones:

1. Follow the established patterns for configuration and CLI
2. Update this README with overview information
3. Create a detailed README in the evaluator's directory
4. Include example configurations
5. Document all evaluation criteria with scoring rubrics
