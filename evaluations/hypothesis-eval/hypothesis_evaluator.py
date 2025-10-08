#!/usr/bin/env python3
# Copyright (c) 2025 Cisco Systems, Inc. and its affiliates
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# SPDX-License-Identifier: MIT

"""
Hypothesis Evaluator – Evaluates threat hunting hypotheses using 8 criteria.
- Inputs: positional text files (one hypothesis per line)
- Outputs (default: current directory):
  * console summary with score distributions
  * JSON with comparison results
  * optional full JSON with all hypothesis details
  * log file capturing console output
- Models: Anthropic, with hybrid/cheap switches

Usage:
  hypothesis-eval file1.txt [file2.txt ...]
  [--output results.json] [--log eval.log] [--json-output full.json] [--no-json]
  [--cheap] [--raw] [-q] [--api-key KEY]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import statistics
import math
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

from anthropic import Anthropic

# ===================== Model Configuration =====================
# Higher quality (hybrid) models
ANTHROPIC_MODEL_CRITICAL = "claude-opus-4-1-20250805"  # For critical evaluation tasks
ANTHROPIC_MODEL_QUALITY = "claude-sonnet-4-20250514"   # For complex evaluation
ANTHROPIC_MODEL_FAST = "claude-3-5-haiku-20241022"     # For simple checks

# Cheaper alternatives
ANTHROPIC_MODEL_CRITICAL_CHEAP = "claude-3-5-sonnet-20241022"
ANTHROPIC_MODEL_QUALITY_CHEAP = "claude-3-5-sonnet-20241022"
ANTHROPIC_MODEL_FAST_CHEAP = "claude-3-haiku-20240307"

# Score interpretation thresholds
SCORE_EXCELLENT = 90
SCORE_GOOD = 75
SCORE_ACCEPTABLE = 60
SCORE_WEAK = 40


# ===================== Data Structures =====================
@dataclass
class HypothesisMetrics:
    """Metrics for a single hypothesis"""
    text: str
    line_number: int
    scores: Dict[str, int] = field(default_factory=dict)
    average_score: float = 0.0
    classification: str = ""  # "excellent", "good", "acceptable", "weak", "poor"

    def calculate_average(self) -> float:
        if not self.scores:
            return 0.0
        self.average_score = sum(self.scores.values()) / len(self.scores)
        self.classification = self._classify_score(self.average_score)
        return self.average_score

    @staticmethod
    def _classify_score(score: float) -> str:
        if score >= SCORE_EXCELLENT:
            return "excellent"
        elif score >= SCORE_GOOD:
            return "good"
        elif score >= SCORE_ACCEPTABLE:
            return "acceptable"
        elif score >= SCORE_WEAK:
            return "weak"
        else:
            return "poor"


@dataclass
class RunMetrics:
    """Metrics for a complete run (one file)"""
    filename: str
    hypotheses: List[HypothesisMetrics] = field(default_factory=list)
    total_hypotheses: int = 0
    mean_score: float = 0.0
    median_score: float = 0.0
    std_dev: float = 0.0
    score_distribution: Dict[str, int] = field(default_factory=dict)
    criterion_averages: Dict[str, float] = field(default_factory=dict)
    outliers: List[Tuple[int, float]] = field(default_factory=list)

    def calculate_aggregates(self) -> None:
        if not self.hypotheses:
            return

        self.total_hypotheses = len(self.hypotheses)
        scores = [h.average_score for h in self.hypotheses]

        self.mean_score = statistics.mean(scores)
        self.median_score = statistics.median(scores)
        self.std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0

        # Score distribution
        self.score_distribution = {
            "excellent": sum(1 for h in self.hypotheses if h.classification == "excellent"),
            "good": sum(1 for h in self.hypotheses if h.classification == "good"),
            "acceptable": sum(1 for h in self.hypotheses if h.classification == "acceptable"),
            "weak": sum(1 for h in self.hypotheses if h.classification == "weak"),
            "poor": sum(1 for h in self.hypotheses if h.classification == "poor"),
        }

        # Per-criterion averages
        if self.hypotheses and self.hypotheses[0].scores:
            for criterion in self.hypotheses[0].scores.keys():
                criterion_scores = [h.scores.get(criterion, 0) for h in self.hypotheses]
                self.criterion_averages[criterion] = statistics.mean(criterion_scores)

        # Detect outliers using IQR method
        self.outliers = self._detect_outliers(scores)

    def _detect_outliers(self, scores: List[float]) -> List[Tuple[int, float]]:
        """Detect outlier scores using IQR method"""
        if len(scores) < 4:
            return []

        sorted_scores = sorted(scores)
        q1 = sorted_scores[len(sorted_scores) // 4]
        q3 = sorted_scores[3 * len(sorted_scores) // 4]
        iqr = q3 - q1

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = []
        for h in self.hypotheses:
            if h.average_score < lower_bound or h.average_score > upper_bound:
                outliers.append((h.line_number, h.average_score))

        return outliers


# ===================== Evaluator =====================
class HypothesisEvaluator:
    def __init__(
        self,
        api_key: str,
        quiet: bool = False,
        log_file: Optional[str] = None,
        json_output_file: Optional[str] = None,
        cheap_mode: bool = False,
        rich_mode: bool = False,
    ):
        self.client = Anthropic(api_key=api_key)
        self.quiet = quiet
        self.log_file = log_file
        self.log_buffer = StringIO() if log_file else None
        self.json_output_file = json_output_file
        self.cheap_mode = cheap_mode
        self.rich_mode = rich_mode
        self.console = None
        self._Markdown = None

        if self.rich_mode:
            try:
                from rich.console import Console  # type: ignore
                from rich.markdown import Markdown  # type: ignore
                self.console = Console()
                self._Markdown = Markdown
            except Exception:
                self.rich_mode = False
                if not self.quiet:
                    print("Warning: rich is not installed. Falling back to plain console output.", file=sys.stderr)

        # Model selection
        if cheap_mode:
            self.model_critical = ANTHROPIC_MODEL_CRITICAL_CHEAP
            self.model_quality = ANTHROPIC_MODEL_QUALITY_CHEAP
            self.model_fast = ANTHROPIC_MODEL_FAST_CHEAP
        else:
            self.model_critical = ANTHROPIC_MODEL_CRITICAL
            self.model_quality = ANTHROPIC_MODEL_QUALITY
            self.model_fast = ANTHROPIC_MODEL_FAST

        # Metric registry: (function, model_to_use)
        self.metric_functions: Dict[str, Tuple[Any, str]] = {
            "assertion_quality": (self.evaluate_assertion_quality, self.model_critical),
            "specificity": (self.evaluate_specificity, self.model_quality),
            "scope_appropriateness": (self.evaluate_scope_appropriateness, self.model_quality),
            "technical_precision": (self.evaluate_technical_precision, self.model_quality),
            "observable_focus": (self.evaluate_observable_focus, self.model_quality),
            "detection_independence": (self.evaluate_detection_independence, self.model_fast),
            "grammatical_clarity": (self.evaluate_grammatical_clarity, self.model_fast),
            "logical_coherence": (self.evaluate_logical_coherence, self.model_quality),
        }

        # Full JSON object we can optionally save
        self.full_data: Dict[str, Any] = {
            "metadata": {
                "evaluation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model_mode": "cheap" if cheap_mode else "hybrid",
                "files": [],
            },
            "evaluations": [],
            "comparison": {},
        }

    # --------------- Utilities ---------------
    def print_output(self, message: str = "", end: str = "\n") -> None:
        """Print output (plain text, goes to log and console)"""
        if self.log_buffer is not None:
            self.log_buffer.write(message + end)
        if not self.quiet:
            print(message, end=end)
    
    def print_markdown(self, markdown_text: str) -> None:
        """Print markdown-formatted text (renders with rich if available)"""
        if self.log_buffer is not None:
            self.log_buffer.write(markdown_text + "\n")
        if not self.quiet:
            if self.rich_mode and self.console and self._Markdown:
                self.console.print(self._Markdown(markdown_text))
            else:
                print(markdown_text)

    def save_log_file(self) -> None:
        if self.log_file and self.log_buffer is not None:
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write(self.log_buffer.getvalue())
            if not self.quiet:
                self.print_output(f"\nLog saved to: {self.log_file}")

    def save_json_output(self) -> None:
        if self.json_output_file:
            with open(self.json_output_file, "w", encoding="utf-8") as f:
                json.dump(self.full_data, f, indent=2)
            if not self.quiet:
                self.print_output(f"Full JSON saved to: {self.json_output_file}")

    def evaluate_with_llm_retry(
        self,
        prompt: str,
        metric_name: str,
        model: str,
        max_retries: int = 2,
        max_tokens: int = 300,
    ) -> Optional[int]:
        """Evaluate with retry logic for LLM failures. Returns integer score or None."""
        json_instructions = (
            "\n\nCRITICAL: Respond with ONLY a single integer number.\n"
            "Do NOT include any text, explanations, or formatting.\n"
            "Output only the score number.\n"
            "Your response:"
        )
        full_prompt = prompt + json_instructions

        for attempt in range(max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0,
                    messages=[{"role": "user", "content": full_prompt}],
                )
                text = response.content[0].text.strip()
                
                # Extract first integer from response
                match = re.search(r'\b(\d+)\b', text)
                if match:
                    score = int(match.group(1))
                    return score
                else:
                    raise ValueError(f"No integer found in response: {text}")

            except (ValueError, json.JSONDecodeError) as e:
                if attempt < max_retries:
                    if self.log_buffer is not None:
                        self.log_buffer.write(
                            f"Retrying {metric_name} (attempt {attempt + 2}/{max_retries + 1})...\n"
                        )
                    full_prompt = (
                        prompt
                        + "\n\nRETRY: Previous response was not a valid integer. Return ONLY a number like: 100"
                        + json_instructions
                    )
            except Exception as e:
                if attempt == max_retries and self.log_buffer is not None:
                    self.log_buffer.write(
                        f"LLM API error for {metric_name}: {str(e)[:200]}\n"
                    )
        return None

    # --------------- Evaluation Criteria ---------------
    def evaluate_assertion_quality(self, hypothesis: str) -> int:
        """Criterion 1: Assertion Quality (0 or 100)"""
        prompt = f"""Evaluate whether this threat hunting hypothesis is stated as a clear, testable assertion.

Hypothesis: {hypothesis}

Score 100 if ALL of these are true:
- States what adversaries/attackers/threat actors "may be," "are," or "might be" DOING
- Describes adversary BEHAVIOR, not investigation methodology
- Is a declarative statement, not a question
- Does NOT use detection-focused language like "could indicate," "might suggest," "may uncover," "could point to," "might reveal," "evidence of X shows Y"
- Does NOT describe hunting activities like "cross-referencing," "investigation into," "systematic review," "hunting for," "detection of"

Score 0 if ANY of these are true:
- Phrased as a question
- Describes what hunters should do rather than what adversaries do
- Uses hypothetical/uncertain language about the hypothesis itself
- Focuses on detection outcomes rather than behaviors ("detection of X could indicate Y")

Output only: 0 or 100"""

        result = self.evaluate_with_llm_retry(prompt, "assertion_quality", self.model_critical)
        return result if result in [0, 100] else 0

    def evaluate_specificity(self, hypothesis: str) -> int:
        """Criterion 2: Specificity (0-100, increments of 20)"""
        prompt = f"""Count the number of specific qualifiers in this threat hunting hypothesis that narrow its scope.

Hypothesis: {hypothesis}

Count ONLY concrete specifics (maximum 5):
- Specific technique names (e.g., "Pass-the-Hash", "credential dumping", "DLL injection")
- Specific tool names (e.g., "mimikatz.exe", "procdump.exe", "Cobalt Strike")
- Specific protocols/mechanisms (e.g., "via SMB", "using WMI", "through DNS")
- Specific system types (e.g., "domain controllers", "endpoints", "privileged servers")
- Specific file patterns or indicators (e.g., "lsass.dmp", "0x1410", ".dmp files")

Do NOT count:
- Generic terms like "custom tools", "suspicious", "various"
- The word "adversaries/attackers/threat actors"
- Tool categories (e.g., "detection tools") unless naming specific ones
- Vague qualifiers like "unusual", "predictable"

Count the qualifiers (0-5), then multiply by 20 for final score.
Output only: 0, 20, 40, 60, 80, or 100"""

        result = self.evaluate_with_llm_retry(prompt, "specificity", self.model_quality)
        return result if result in [0, 20, 40, 60, 80, 100] else 0

    def evaluate_scope_appropriateness(self, hypothesis: str) -> int:
        """Criterion 3: Scope Appropriateness (0, 50, or 100)"""
        prompt = f"""Evaluate whether this threat hunting hypothesis has appropriate scope.

Hypothesis: {hypothesis}

Score 100 if the hypothesis:
- Focuses on 1-2 specific related behaviors or techniques
- Is bounded enough to be actionable
- Is broad enough to be meaningful (not just a single IOC)

Score 50 if:
- Slightly too broad (covers multiple unrelated techniques)
- Slightly too narrow (very specific but still huntable)

Score 0 if:
- Too broad: uses words like "all", "any", "various types of", "general"
- Too narrow: single IP address, single file hash, single event
- Unbounded: no clear scope or focus

Output only: 0, 50, or 100"""

        result = self.evaluate_with_llm_retry(prompt, "scope_appropriateness", self.model_quality)
        return result if result in [0, 50, 100] else 0

    def evaluate_technical_precision(self, hypothesis: str) -> int:
        """Criterion 4: Technical Precision (0, 50, or 100)"""
        prompt = f"""Evaluate whether this threat hunting hypothesis uses specific technical terminology.

Hypothesis: {hypothesis}

Score 100 if:
- Uses specific technical terms (process names, protocols, techniques)
- Avoids vague security buzzwords
- Terms would be understood by security practitioners
- No ambiguous or ill-defined language

Score 50 if:
- Mix of specific and vague language
- Some technical terms but also generic descriptions

Score 0 if hypothesis contains vague terms like:
- "suspicious activity" / "anomalous behavior" / "unusual patterns"
- "various methods" / "different ways" / "somehow"
- "things" / "stuff" / "issues"
- Generic security terms without specifics

Output only: 0, 50, or 100"""

        result = self.evaluate_with_llm_retry(prompt, "technical_precision", self.model_quality)
        return result if result in [0, 50, 100] else 0

    def evaluate_observable_focus(self, hypothesis: str) -> int:
        """Criterion 5: Observable Focus (0, 50, or 100)"""
        prompt = f"""Evaluate whether this threat hunting hypothesis describes observable, evidence-producing activities.

Hypothesis: {hypothesis}

Score 100 if the hypothesis describes activities that:
- Leave evidence (logs, files, network traffic, process artifacts)
- Can be directly observed in security data
- Focus on adversary actions, not detection/hunting methodology
- Describe technical behaviors (execution, access, creation, transfer)

Score 50 if:
- Partially describes observable activity
- Mixes observable behaviors with investigation methodology
- Some abstraction but still generally evidence-based

Score 0 if the hypothesis:
- Describes investigation/hunting processes ("cross-referencing", "systematic review")
- Focuses on analytic techniques rather than adversary behavior
- Describes detection tool operations ("Splunk logs might show", "could detect")
- Describes abstract states with no observable evidence

Output only: 0, 50, or 100"""

        result = self.evaluate_with_llm_retry(prompt, "observable_focus", self.model_quality)
        return result if result in [0, 50, 100] else 0

    def evaluate_detection_independence(self, hypothesis: str) -> int:
        """Criterion 6: Detection Independence (0 or 100)"""
        prompt = f"""Evaluate whether this threat hunting hypothesis is independent of specific detection platforms.

Hypothesis: {hypothesis}

Score 100 if:
- Does NOT mention specific detection products/platforms (Splunk, Zeek, QRadar, CrowdStrike, etc.)
- Does NOT mention specific log sources by product name (Windows Event Logs is OK, "Sysmon" is borderline)
- Describes behavior that exists independent of how it's detected
- Is portable across different detection environments

Score 0 if:
- Mentions specific SIEM, EDR, NDR, or logging platforms by name
- References product-specific features or data structures
- Ties the hypothesis to a particular vendor's ecosystem
- Uses phrases like "in Splunk", "using Zeek", "via [product name]"

Output only: 0 or 100"""

        result = self.evaluate_with_llm_retry(prompt, "detection_independence", self.model_fast)
        return result if result in [0, 100] else 0

    def evaluate_grammatical_clarity(self, hypothesis: str) -> int:
        """Criterion 7: Grammatical Clarity (0, 50, or 100)"""
        prompt = f"""Evaluate the grammatical clarity and sentence structure of this threat hunting hypothesis.

Hypothesis: {hypothesis}

Score 100 if:
- Clear, concise sentence structure
- No run-on sentences (generally under 30-35 words)
- Straightforward subject-verb-object construction
- Minimal nested clauses or parentheticals
- Easy to read and understand on first pass

Score 50 if:
- Somewhat complex but still readable
- One moderately long sentence or minor structural issues
- Slightly awkward phrasing but meaning is clear

Score 0 if:
- Run-on sentences (40+ words)
- Multiple nested clauses or parentheticals
- Convoluted structure requiring multiple reads
- Unclear antecedents or ambiguous references

Output only: 0, 50, or 100"""

        result = self.evaluate_with_llm_retry(prompt, "grammatical_clarity", self.model_fast)
        return result if result in [0, 50, 100] else 0

    def evaluate_logical_coherence(self, hypothesis: str) -> int:
        """Criterion 8: Logical Coherence (0, 50, or 100)"""
        prompt = f"""Evaluate whether the components of this threat hunting hypothesis fit together logically.

Hypothesis: {hypothesis}

Score 100 if:
- All components are technically compatible
- The technique matches the described mechanism
- Target systems make sense for the technique
- No obvious technical contradictions
- Cause and effect relationships are logical

Score 50 if:
- Minor inconsistencies but generally coherent
- Slightly unusual combinations that are still plausible
- Some ambiguity but no clear contradictions

Score 0 if:
- Contains technical impossibilities (e.g., "DNS tunneling via SMB")
- Mechanism doesn't match the technique described
- Target systems incompatible with the attack method
- Clear logical contradictions or nonsensical combinations

Output only: 0, 50, or 100"""

        result = self.evaluate_with_llm_retry(prompt, "logical_coherence", self.model_quality)
        return result if result in [0, 50, 100] else 0

    # --------------- Orchestration ---------------
    def evaluate_hypothesis(self, hypothesis: str, line_number: int) -> HypothesisMetrics:
        """Evaluate a single hypothesis against all criteria"""
        metrics = HypothesisMetrics(text=hypothesis, line_number=line_number)

        for criterion_name, (func, model) in self.metric_functions.items():
            try:
                score = func(hypothesis)
                metrics.scores[criterion_name] = score if score is not None else 0
            except Exception as e:
                if self.log_buffer:
                    self.log_buffer.write(f"Error evaluating {criterion_name} for line {line_number}: {e}\n")
                metrics.scores[criterion_name] = 0

        metrics.calculate_average()
        return metrics

    def read_hypotheses_from_file(self, filepath: str) -> List[Tuple[int, str]]:
        """Read hypotheses from a file, returning list of (line_number, text) tuples"""
        hypotheses_text = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if line:  # Skip blank lines
                        hypotheses_text.append((line_num, line))
        except Exception as e:
            self.print_output(f"Error reading {filepath}: {e}")
        return hypotheses_text

    def evaluate_file(self, filepath: str, hypotheses_text: List[Tuple[int, str]], pbar=None) -> RunMetrics:
        """Evaluate all hypotheses in a file"""
        filename = os.path.basename(filepath)
        run_metrics = RunMetrics(filename=filename)

        if not hypotheses_text:
            return run_metrics

        # Evaluate each hypothesis
        for line_num, hypothesis in hypotheses_text:
            if not self.quiet and self.log_buffer:
                self.log_buffer.write(f"  Evaluating {filename} line {line_num}...\n")
            
            metrics = self.evaluate_hypothesis(hypothesis, line_num)
            run_metrics.hypotheses.append(metrics)
            
            # Update progress bar after each hypothesis
            if pbar:
                pbar.update(1)

        # Calculate aggregates
        run_metrics.calculate_aggregates()
        return run_metrics

    def process_files(self, files: List[str], output_file: str) -> None:
        """Process all files and generate comparison"""
        # Populate metadata
        self.full_data["metadata"]["files"] = [
            {"path": os.path.abspath(p), "name": os.path.basename(p)} for p in files
        ]

        # Prepare progress bar (tqdm optional)
        tqdm = None
        try:
            from tqdm.auto import tqdm as _tqdm  # type: ignore
            tqdm = _tqdm
        except Exception:
            if not self.quiet:
                self.print_output("(Tip: install tqdm for a progress bar: pip install tqdm)")

        # First pass: read all files to count total hypotheses
        file_hypotheses: List[Tuple[str, List[Tuple[int, str]]]] = []
        total_hypotheses = 0
        
        for filepath in files:
            hypotheses = self.read_hypotheses_from_file(filepath)
            file_hypotheses.append((filepath, hypotheses))
            total_hypotheses += len(hypotheses)
            if not hypotheses:
                self.print_output(f"Warning: No hypotheses found in {os.path.basename(filepath)}")

        # Create progress bar based on total hypotheses
        pbar = None
        if tqdm and not self.quiet and total_hypotheses > 0:
            pbar = tqdm(total=total_hypotheses, desc="Evaluating hypotheses", dynamic_ncols=True, unit="hyp")

        # Second pass: evaluate all hypotheses
        run_metrics_list: List[RunMetrics] = []
        
        for filepath, hypotheses in file_hypotheses:
            run_metrics = self.evaluate_file(filepath, hypotheses, pbar)
            run_metrics_list.append(run_metrics)

            # Add to full data
            self.full_data["evaluations"].append({
                "file": run_metrics.filename,
                "total_hypotheses": run_metrics.total_hypotheses,
                "mean_score": round(run_metrics.mean_score, 2),
                "median_score": round(run_metrics.median_score, 2),
                "std_dev": round(run_metrics.std_dev, 2),
                "score_distribution": run_metrics.score_distribution,
                "criterion_averages": {k: round(v, 2) for k, v in run_metrics.criterion_averages.items()},
                "hypotheses": [
                    {
                        "line": h.line_number,
                        "text": h.text,
                        "scores": h.scores,
                        "average": round(h.average_score, 2),
                        "classification": h.classification,
                    }
                    for h in run_metrics.hypotheses
                ],
            })

        if pbar:
            pbar.close()

        # Now print all summaries after evaluation is complete
        for run_metrics in run_metrics_list:
            self.print_markdown(f"\n## {run_metrics.filename}")
            self._print_run_summary(run_metrics)

        # Comparison logic
        self._generate_comparison(run_metrics_list)

        # Save combined result JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.full_data, f, indent=2)
        self.print_output(f"\nResults written to: {output_file}")

        # Save optional artifacts
        self.save_log_file()
        self.save_json_output()

    def _print_run_summary(self, run: RunMetrics) -> None:
        """Print summary for a single run"""
        if run.total_hypotheses == 0:
            self.print_output("No hypotheses evaluated.\n")
            return

        # Build complete markdown for this run
        lines = []
        lines.append(f"Total Hypotheses: {run.total_hypotheses}")
        lines.append("")

        # Score distribution
        lines.append("### Score Distribution")
        total = run.total_hypotheses
        for category in ["excellent", "good", "acceptable", "weak", "poor"]:
            count = run.score_distribution.get(category, 0)
            pct = (count / total * 100) if total > 0 else 0
            lines.append(f"- **{category.capitalize()} ({self._score_range(category)})**: {count} ({pct:.1f}%)")
        lines.append("")

        # Aggregate metrics
        lines.append("### Aggregate Metrics")
        lines.append(f"- **Mean Score**: {run.mean_score:.2f}")
        lines.append(f"- **Median Score**: {run.median_score:.2f}")
        lines.append(f"- **Std Dev**: {run.std_dev:.2f}")
        lines.append("")

        # Per-criterion averages table
        if run.criterion_averages:
            lines.append("### Per-Criterion Averages")
            lines.append("")
            lines.append("| Criterion | Avg Score |")
            lines.append("|-----------|-----------|")
            for criterion, avg in sorted(run.criterion_averages.items()):
                criterion_display = criterion.replace("_", " ").title()
                lines.append(f"| {criterion_display} | {avg:.1f} |")
            lines.append("")

        # Outliers
        if run.outliers:
            lines.append("### Outliers")
            for line_num, score in run.outliers[:5]:  # Show top 5
                hyp = next((h for h in run.hypotheses if h.line_number == line_num), None)
                if hyp:
                    text_preview = hyp.text[:60] + "..." if len(hyp.text) > 60 else hyp.text
                    lines.append(f"- **Line {line_num}** (score: {score:.1f}): \"{text_preview}\"")
            lines.append("")

        # Print as single markdown block
        self.print_markdown("\n".join(lines))

    def _score_range(self, category: str) -> str:
        """Get score range for a category"""
        ranges = {
            "excellent": "90-100",
            "good": "75-89",
            "acceptable": "60-74",
            "weak": "40-59",
            "poor": "<40",
        }
        return ranges.get(category, "")

    def _generate_comparison(self, runs: List[RunMetrics]) -> None:
        """Generate comparison between runs"""
        if len(runs) < 2:
            # Single file mode
            if runs:
                self.full_data["comparison"] = {
                    "winner": runs[0].filename,
                    "rankings": [{"file": runs[0].filename, "mean_score": round(runs[0].mean_score, 2)}],
                    "key_differences": [],
                }
            return

        # Rank by mean score
        rankings = sorted(
            [(r.filename, r.mean_score, r.total_hypotheses) for r in runs],
            key=lambda x: x[1],
            reverse=True
        )
        winner = rankings[0][0]

        # Build complete comparison markdown
        comp_lines = []
        comp_lines.append("\n## Comparison")
        comp_lines.append(f"**Winner:** {winner}")
        comp_lines.append("")

        # Rankings table
        comp_lines.append("### Rankings")
        comp_lines.append("")
        comp_lines.append("| File | Mean Score | Median | Hypotheses |")
        comp_lines.append("|------|------------|--------|------------|")
        for filename, mean, count in rankings:
            run = next(r for r in runs if r.filename == filename)
            comp_lines.append(f"| {filename} | {mean:.2f} | {run.median_score:.2f} | {count} |")
        comp_lines.append("")

        # Key differences
        winner_run = next(r for r in runs if r.filename == winner)
        differences = []

        for other_run in runs:
            if other_run.filename == winner:
                continue

            # Compare per-criterion averages
            for criterion in winner_run.criterion_averages.keys():
                winner_avg = winner_run.criterion_averages.get(criterion, 0)
                other_avg = other_run.criterion_averages.get(criterion, 0)
                diff = abs(winner_avg - other_avg)

                if diff >= 5:  # Only show meaningful differences
                    better = winner if winner_avg > other_avg else other_run.filename
                    criterion_display = criterion.replace("_", " ").title()
                    differences.append((diff, f"{criterion_display}: {better} better by {diff:.1f} points"))

        # Sort by magnitude
        differences.sort(key=lambda x: x[0], reverse=True)

        if differences:
            comp_lines.append("### Key Differences")
            for _, msg in differences[:10]:  # Top 10
                comp_lines.append(f"- {msg}")
            comp_lines.append("")

        # Print complete comparison as markdown
        self.print_markdown("\n".join(comp_lines))

        # Store in comparison data
        self.full_data["comparison"] = {
            "winner": winner,
            "rankings": [
                {"file": f, "mean_score": round(m, 2), "hypotheses": c}
                for f, m, c in rankings
            ],
            "key_differences": [msg for _, msg in differences[:10]],
        }


# ===================== CLI =====================
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Evaluate threat hunting hypotheses from text files (one hypothesis per line)"
    )
    ap.add_argument("files", nargs="+", help="One or more text files to evaluate")
    ap.add_argument("--output", default="hypothesis-eval.json", help="Output JSON file (summary)")
    ap.add_argument("--log", default="hypothesis-eval.log", help="Log file capturing console output")
    ap.add_argument("-j", "--json-output", default="hypothesis-eval.full.json", help="Full JSON with all hypothesis details")
    ap.add_argument("--no-json", action="store_true", help="Disable saving the full JSON details file")
    ap.add_argument("--api-key", help="Anthropic API key (or ANTHROPIC_API_KEY env)")
    ap.add_argument("--cheap", action="store_true", help="Use cheaper models (Claude 3/3.5)")
    ap.add_argument("--raw", action="store_true", help="Print raw Markdown instead of rendering it")
    ap.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (no console output)")
    args = ap.parse_args()

    if not args.files:
        print("Error: at least one text file is required", file=sys.stderr)
        return 1

    # Verify files exist
    missing = [p for p in args.files if not os.path.exists(p)]
    if missing:
        print(f"Error: missing files: {', '.join(missing)}", file=sys.stderr)
        return 1

    # API key
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: Anthropic API key required (use --api-key or ANTHROPIC_API_KEY)", file=sys.stderr)
        return 1

    # Determine full JSON setting
    json_output_file = None if args.no_json else args.json_output

    evaluator = HypothesisEvaluator(
        api_key=api_key,
        quiet=args.quiet,
        log_file=args.log,
        json_output_file=json_output_file,
        cheap_mode=args.cheap,
        rich_mode=(not args.raw),
    )

    evaluator.process_files(args.files, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
