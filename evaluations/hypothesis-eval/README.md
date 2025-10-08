# Hypothesis Evaluator

Evaluates threat hunting hypotheses using 8 criteria with LLM-based scoring.

## Overview

This evaluator assesses threat hunting hypotheses against a comprehensive framework of 8 criteria:

1. **Assertion Quality** (0 or 100) - Clear, testable assertion vs question/investigation plan
2. **Specificity** (0-100) - Count of specific qualifiers (technique names, tools, protocols, etc.)
3. **Scope Appropriateness** (0, 50, or 100) - Neither too broad nor too narrow
4. **Technical Precision** (0, 50, or 100) - Specific terminology vs vague buzzwords
5. **Observable Focus** (0, 50, or 100) - Evidence-producing activities vs investigation methodology
6. **Detection Independence** (0 or 100) - Platform-agnostic vs mentions specific tools
7. **Grammatical Clarity** (0, 50, or 100) - Clear structure vs run-on/convoluted
8. **Logical Coherence** (0, 50, or 100) - Technically compatible vs contradictory

Each hypothesis receives a score (0-100) for each criterion, and the average determines its overall quality.

## Input Format

- **Text files** with one hypothesis per line
- Blank lines are skipped
- Each file represents one "run" to be evaluated and compared

Example input file (`run1.txt`):
```
Adversaries may be using Pass-the-Hash attacks via SMB to move laterally between domain controllers.
Threat actors might be dumping LSASS memory using procdump.exe to extract credentials on endpoints.
Attackers could be establishing persistence through scheduled tasks that execute malicious PowerShell scripts.
```

## Usage

### Basic Usage

```bash
python hypothesis_evaluator.py run1.txt run2.txt
```

### With Options

```bash
python hypothesis_evaluator.py run1.txt run2.txt \
  --output results.json \
  --log evaluation.log \
  --json-output detailed.json \
  --api-key YOUR_API_KEY
```

### Using Cheap Mode (Lower Cost)

```bash
python hypothesis_evaluator.py run1.txt run2.txt --cheap
```

### Quiet Mode (JSON Only)

```bash
python hypothesis_evaluator.py run1.txt run2.txt -q
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `files` | One or more text files to evaluate (positional) | Required |
| `--output` | Output JSON file with summary results | `hypothesis-eval.json` |
| `--log` | Log file capturing console output | `hypothesis-eval.log` |
| `-j, --json-output` | Full JSON with all hypothesis details | `hypothesis-eval.full.json` |
| `--no-json` | Disable saving the full JSON details file | False |
| `--api-key` | Anthropic API key (or use `ANTHROPIC_API_KEY` env var) | From environment |
| `--cheap` | Use cheaper models (Claude 3/3.5 instead of Claude 4) | False |
| `--raw` | Print raw Markdown instead of rendering with rich | False |
| `-q, --quiet` | Quiet mode (no console output, JSON only) | False |

## Output Formats

### Console Output (Markdown)

For each file:
- Total hypotheses evaluated
- Score distribution (excellent/good/acceptable/weak/poor)
- Aggregate metrics (mean, median, standard deviation)
- Per-criterion averages
- Outliers (statistically unusual scores)

Comparison section:
- Winner (highest mean score)
- Rankings table
- Key differences between runs

### Summary JSON (`--output`)

```json
{
  "metadata": {
    "evaluation_date": "2025-01-08 10:30:00",
    "model_mode": "hybrid",
    "files": [...]
  },
  "evaluations": [
    {
      "file": "run1.txt",
      "total_hypotheses": 25,
      "mean_score": 78.4,
      "median_score": 80.0,
      "std_dev": 12.3,
      "score_distribution": {
        "excellent": 5,
        "good": 12,
        "acceptable": 6,
        "weak": 2,
        "poor": 0
      },
      "criterion_averages": {
        "assertion_quality": 92.0,
        "specificity": 64.0,
        ...
      }
    }
  ],
  "comparison": {
    "winner": "run2.txt",
    "rankings": [...],
    "key_differences": [...]
  }
}
```

### Full JSON (`--json-output`)

Includes all individual hypothesis scores and details:

```json
{
  "evaluations": [
    {
      "file": "run1.txt",
      "hypotheses": [
        {
          "line": 1,
          "text": "Adversaries may be using...",
          "scores": {
            "assertion_quality": 100,
            "specificity": 80,
            "scope_appropriateness": 100,
            "technical_precision": 100,
            "observable_focus": 100,
            "detection_independence": 100,
            "grammatical_clarity": 100,
            "logical_coherence": 100
          },
          "average": 97.5,
          "classification": "excellent"
        },
        ...
      ]
    }
  ]
}
```

## Score Interpretation

| Score Range | Classification | Description |
|-------------|----------------|-------------|
| 90-100 | Excellent | Production ready |
| 75-89 | Good | Minor improvements possible |
| 60-74 | Acceptable | Some issues to address |
| 40-59 | Weak | Significant problems |
| <40 | Poor | Requires major revision |

## Evaluation Criteria Details

### 1. Assertion Quality (0 or 100)

**Score 100 if:**
- States what adversaries "may be," "are," or "might be" DOING
- Describes adversary BEHAVIOR, not investigation methodology
- Is a declarative statement, not a question
- Does NOT use detection-focused language ("could indicate," "might suggest")
- Does NOT describe hunting activities ("cross-referencing," "investigation into")

**Score 0 if:**
- Phrased as a question
- Describes what hunters should do
- Focuses on detection outcomes rather than behaviors

### 2. Specificity (0-100, increments of 20)

Counts specific qualifiers (0-5) and multiplies by 20:
- Specific technique names (e.g., "Pass-the-Hash", "credential dumping")
- Specific tool names (e.g., "mimikatz.exe", "procdump.exe")
- Specific protocols/mechanisms (e.g., "via SMB", "using WMI")
- Specific system types (e.g., "domain controllers", "endpoints")
- Specific file patterns (e.g., "lsass.dmp", ".dmp files")

Does NOT count generic terms like "custom tools", "suspicious", "various"

### 3. Scope Appropriateness (0, 50, or 100)

**Score 100:** Focuses on 1-2 specific related behaviors, actionable and meaningful  
**Score 50:** Slightly too broad or slightly too narrow  
**Score 0:** Too broad ("all malware") or too narrow (single IOC/hash)

### 4. Technical Precision (0, 50, or 100)

**Score 100:** Specific technical terms, no vague buzzwords  
**Score 50:** Mix of specific and vague language  
**Score 0:** Contains vague terms like "suspicious activity", "various methods"

### 5. Observable Focus (0, 50, or 100)

**Score 100:** Describes activities that leave evidence (logs, files, network traffic)  
**Score 50:** Partially observable, some abstraction  
**Score 0:** Describes investigation processes or abstract states

### 6. Detection Independence (0 or 100)

**Score 100:** Platform-agnostic, no mention of specific detection products  
**Score 0:** Mentions specific SIEM, EDR, NDR, or logging platforms by name

### 7. Grammatical Clarity (0, 50, or 100)

**Score 100:** Clear, concise structure (under 30-35 words)  
**Score 50:** Somewhat complex but readable  
**Score 0:** Run-on sentences (40+ words), convoluted structure

### 8. Logical Coherence (0, 50, or 100)

**Score 100:** All components technically compatible, no contradictions  
**Score 50:** Minor inconsistencies but generally coherent  
**Score 0:** Technical impossibilities or clear contradictions

## Model Selection

### Hybrid Mode (Default)
- **Critical tasks** (Assertion Quality): Claude Opus 4
- **Complex tasks** (Specificity, Scope, Technical Precision, Observable Focus, Logical Coherence): Claude Sonnet 4
- **Simple tasks** (Detection Independence, Grammatical Clarity): Claude Haiku 3.5

### Cheap Mode (`--cheap`)
- **Critical tasks**: Claude Sonnet 3.5
- **Complex tasks**: Claude Sonnet 3.5
- **Simple tasks**: Claude Haiku 3

## Requirements

```bash
pip install anthropic
pip install tqdm  # Optional, for progress bar
pip install rich  # Optional, for formatted console output
```

## Environment Setup

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

Or pass it via command line:

```bash
python hypothesis_evaluator.py run1.txt --api-key your_api_key_here
```

## Examples

### Example 1: Single File Evaluation

```bash
python hypothesis_evaluator.py hypotheses.txt
```

Output shows score distribution, aggregates, and per-criterion averages for the single file.

### Example 2: Comparing Two Runs

```bash
python hypothesis_evaluator.py baseline.txt improved.txt
```

Output shows evaluation for each file plus a comparison section identifying the winner and key differences.

### Example 3: Batch Evaluation with Custom Output

```bash
python hypothesis_evaluator.py run*.txt \
  --output comparison.json \
  --log detailed.log \
  --json-output full-results.json
```

Evaluates all files matching `run*.txt`, saves summary to `comparison.json`, full details to `full-results.json`, and logs to `detailed.log`.

### Example 4: Quiet Mode for Automation

```bash
python hypothesis_evaluator.py run1.txt run2.txt -q --output results.json
```

No console output, only JSON files created. Useful for CI/CD pipelines.

## Tips

1. **Use cheap mode for iteration**: When developing hypotheses, use `--cheap` to reduce costs during rapid iteration.

2. **Review outliers**: Pay special attention to hypotheses flagged as outliers - they often reveal systematic issues.

3. **Compare criterion averages**: When comparing runs, look at per-criterion averages to identify specific areas of improvement.

4. **Batch processing**: Evaluate multiple runs at once to get comparative rankings automatically.

5. **Log files**: Keep log files for debugging LLM evaluation issues or understanding scoring decisions.

## Troubleshooting

### "No integer found in response"

The LLM returned text instead of a number. The evaluator will retry automatically. If this persists, check your API key and model availability.

### "Error reading file"

Ensure your input files are UTF-8 encoded text files with one hypothesis per line.

### High standard deviation

Indicates inconsistent hypothesis quality within a run. Review outliers to identify problematic hypotheses.

### All scores are 0

Check that your API key is valid and you have sufficient credits. Review the log file for detailed error messages.

## License

MIT License - See LICENSE file for details.
