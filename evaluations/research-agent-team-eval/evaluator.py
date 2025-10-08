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
Modular LLM-Based Threat Hunting Report Evaluator
Compares and evaluates cybersecurity threat hunting reports using flexible LLM configuration.

Usage:
  evaluator.py file1.md [file2.md ...] -c model_config.json
  [--output results.json] [--log eval.log] [--json-output full.json]
  [-q] [--verbose]
"""

import json
import re
import argparse
import asyncio
import aiohttp
from typing import Any, Dict, List, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse
import sys
import os
import time
import statistics
import math
from io import StringIO
from pathlib import Path

# Add parent directory to path to import evaluation utilities
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import EvaluatorModelClient, load_environment, print_markdown as print_md, setup_rich_rendering

REQUIRED_SECTIONS = [
    "Overview",
    "Threat Actors",
    "Technique Details",
    "Detection",
    "Typical Datasets",
    "Published Hunts",
    "Previous Hunting Information",
    "Commonly-Used Tools",
    "References",
    "Other Information",
]


@dataclass
class MetricResult:
    """Result from a single metric evaluation"""

    score: float  # 0-100
    weight: float = 1.0  # Importance multiplier
    details: Dict = field(default_factory=dict)
    feedback: str = ""
    confidence: float = 1.0  # For LLM-based metrics


@dataclass
class ReportMetrics:
    """Complete metrics for a single report"""

    topic: str
    backend: str
    metric_results: Dict[str, MetricResult] = field(default_factory=dict)
    total_score: float = 0.0

    def calculate_total_score(self):
        """Calculate weighted total score"""
        total_weighted = 0
        total_weight = 0
        for metric_name, result in self.metric_results.items():
            total_weighted += result.score * result.weight
            total_weight += result.weight
        self.total_score = total_weighted / total_weight if total_weight > 0 else 0
        return self.total_score


@dataclass
class ComparisonResult:
    """Comparison between two reports on the same topic"""

    topic: str
    old_metrics: ReportMetrics
    new_metrics: ReportMetrics
    winner: str  # "OLD", "NEW", or "TIE"
    confidence: float
    key_differences: List[str]


class ReportEvaluator:
    """Modular report evaluator using LLM for intelligent assessment"""

    def __init__(
        self,
        model_config_path: Path,
        verbose: bool = False,
        quiet: bool = False,
        log_file: str = "",
        json_output_file: str = "",
        rich_mode: bool = True,
    ):
        self.model_client = EvaluatorModelClient(model_config_path)
        self.verbose = verbose
        self.quiet = quiet
        self.log_file = log_file
        self.log_buffer = StringIO() if log_file else None
        self.json_output_file = json_output_file

        # Setup rich rendering
        self.rich_mode, self.console, self._Markdown = setup_rich_rendering(quiet=quiet)
        if not rich_mode:
            # User explicitly disabled rich mode
            self.rich_mode = False

        # Cache for extracted sections to avoid redundant LLM calls
        self.section_cache: Dict[str, Any] = {}
        
        # Buffer for verbose output (printed at end)
        self._verbose_buffer: List[str] = []

        # Define all metric functions, judge roles, and their weights
        self.metric_functions = {
            "structure_compliance": (self.evaluate_structure_compliance, "structure_compliance", 1.5),
            "technical_depth": (self.evaluate_technical_depth, "technical_depth", 2.0),
            "technical_accuracy": (self.evaluate_technical_accuracy, "technical_accuracy", 2.0),
            "mitre_coverage": (self.evaluate_mitre_coverage, "mitre_coverage", 1.5),
            "detection_quality": (self.evaluate_detection_quality, "detection_quality", 2.0),
            "dataset_documentation": (self.evaluate_dataset_documentation, "dataset_documentation", 1.8),
            "threat_actor_specificity": (self.evaluate_threat_actor_specificity, "threat_actor_specificity", 1.0),
            "reference_quality": (self.evaluate_reference_quality, "reference_quality", 1.3),
            "url_validity": (self.evaluate_url_validity, "url_validity", 1.5),
            "log_example_quality": (self.evaluate_log_example_quality, "log_example_quality", 1.7),
            "instruction_clarity": (self.evaluate_instruction_clarity, "instruction_clarity", 1.8),
            "cross_section_consistency": (self.evaluate_cross_section_consistency, "cross_section_consistency", 1.2),
            "tool_documentation": (self.evaluate_tool_documentation, "tool_documentation", 1.0),
        }

        # Collect model info for metadata
        model_info = {}
        for metric_name, (_, judge_role, _) in self.metric_functions.items():
            model_name = self.model_client.get_model_name(judge_role)
            provider = self.model_client.get_provider_type(judge_role)
            model_info[metric_name] = f"{provider}:{model_name}"

        self.full_evaluation_data = {
            "metadata": {
                "evaluation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_reports": 0,
                "evaluation_mode": None,
                "backends": [],
                "model_config": str(model_config_path),
                "models_used": model_info,
            },
            "evaluations": [],
            "comparisons": [],
            "summary": {},
        }

    def print_output(self, message: str = "", end: str = "\n"):
        """Print to console and/or log file based on quiet mode"""
        if self.log_buffer:
            self.log_buffer.write(message + end)
        if not self.quiet:
            print(message, end=end)
    
    def print_markdown(self, markdown_text: str) -> None:
        """Print markdown-formatted text (renders with rich if available)"""
        print_md(
            markdown_text,
            log_buffer=self.log_buffer,
            quiet=self.quiet,
            rich_mode=self.rich_mode,
            console=self.console,
            markdown_class=self._Markdown,
        )

    def save_log_file(self):
        """Save the log buffer to file if specified"""
        if self.log_file and self.log_buffer:
            with open(self.log_file, "w") as f:
                f.write(self.log_buffer.getvalue())
            if not self.quiet:
                print(f"\nLog saved to: {self.log_file}")

    def save_json_output(self):
        """Save the full evaluation data to JSON file"""
        if self.json_output_file:
            with open(self.json_output_file, "w") as f:
                json.dump(self.full_evaluation_data, f, indent=2)
            if not self.quiet:
                print(f"Full evaluation data saved to: {self.json_output_file}")

    # ============== Helper Methods for LLM Evaluation ==============

    def evaluate_with_llm_retry(
        self,
        prompt: str,
        metric_name: str,
        judge_role: str,
        max_retries: int = 2,
        max_tokens: int = 500,
    ) -> Optional[Dict]:
        """Evaluate with retry logic for LLM failures"""

        # Add strong JSON formatting instructions
        json_instructions = """

CRITICAL: Respond with ONLY a valid JSON object.
DO NOT include any text before or after the JSON.
DO NOT include markdown formatting or backticks.
START your response with { and END with }
DO NOT provide explanations or additional text.

Your JSON response:"""

        full_prompt = prompt + json_instructions

        for attempt in range(max_retries + 1):
            try:
                response_text = self.model_client.call_llm(
                    judge_role=judge_role,
                    prompt=full_prompt,
                    max_tokens=max_tokens,
                    temperature=0.0,
                )

                # Try to parse the JSON directly
                result = json.loads(response_text)
                return result

            except json.JSONDecodeError:
                if attempt < max_retries:
                    if self.verbose:
                        self.print_output(
                            f"    Retrying {metric_name} (attempt {attempt + 2}/{max_retries + 1})..."
                        )
                    # Make instructions even stronger for retry
                    full_prompt = (
                        prompt
                        + '\n\nRETRY: Previous response was not valid JSON. Return ONLY a JSON object like {"score": 50, "feedback": "example"}'
                        + json_instructions
                    )
                    # Brief delay before retry
                    time.sleep(1)
                else:
                    if self.verbose:
                        self.print_output(
                            f"    ⚠️ Failed to get valid JSON for {metric_name} after {max_retries + 1} attempts"
                        )

            except Exception as e:
                if attempt < max_retries:
                    # Exponential backoff with more conservative timing for rate limits
                    if "429" in str(e):
                        wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s for rate limits
                    else:
                        wait_time = 2 ** attempt  # 1s, 2s, 4s for other errors
                    
                    if self.verbose:
                        self.print_output(
                            f"    ⚠️ {metric_name} error (attempt {attempt + 1}/{max_retries + 1}): {str(e)[:50]}"
                        )
                        self.print_output(f"    Retrying in {wait_time}s...")
                    
                    time.sleep(wait_time)
                else:
                    # Final attempt failed
                    if self.verbose:
                        self.print_output(
                            f"    ⚠️ LLM API error for {metric_name} after {max_retries + 1} attempts: {str(e)[:50]}"
                        )

        return None

    def extract_section_with_llm(
        self,
        report: str,
        section_name: str,
        section_description: str,
        variations: List[str] = list(),
    ) -> str:
        """Extract a section from the report using LLM to handle naming variations"""

        # Create cache key
        cache_key = f"{hash(report)}_{section_name}"

        # Check cache first
        if cache_key in self.section_cache:
            return self.section_cache[cache_key]

        # Build variations list
        if variations is None:
            variations = []
        variations_str = (
            ", ".join([f'"{v}"' for v in variations])
            if variations
            else f'variations of "{section_name}"'
        )

        prompt = f"""Extract the content of a specific section from this threat hunting report.

You are looking for the section that contains {section_description}.

This section might be titled "{section_name}" or similar variations like {variations_str}.

Important:
- Look for section headers that start with # or ## followed by the section name
- The section ends when you encounter another # or ## header, or the end of the document
- Return ONLY the content of that section (excluding the section header itself)
- If no such section exists, return exactly: "SECTION_NOT_FOUND"
- Do not include any other text or explanation

Report:
{report}

Return the extracted section content:"""

        try:
            extracted_content = self.model_client.call_llm(
                judge_role="section_extractor",
                prompt=prompt,
                max_tokens=4000,
                temperature=0.0,
            )

            if extracted_content == "SECTION_NOT_FOUND":
                extracted_content = ""

            # Cache the result
            self.section_cache[cache_key] = extracted_content

            return extracted_content

        except Exception as e:
            if self.verbose:
                self.print_output(
                    f"    Failed to extract section {section_name}: {str(e)[:50]}"
                )
            # Cache empty result to avoid retrying
            self.section_cache[cache_key] = ""
            return ""

    # ============== Statistical Methods ==============

    def detect_outliers(
        self, scores: List[float], backend_name: str = ""
    ) -> List[Tuple[int, float]]:
        """Detect outlier scores using IQR method. Returns list of (index, score) tuples."""
        if len(scores) < 4:
            return []

        q1 = sorted(scores)[len(scores) // 4]
        q3 = sorted(scores)[3 * len(scores) // 4]
        iqr = q3 - q1

        # Use standard 1.5 * IQR rule
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = [
            (i, s) for i, s in enumerate(scores) if s < lower_bound or s > upper_bound
        ]

        return outliers

    def calculate_median(self, scores: List[float]) -> float:
        """Calculate median of scores"""
        if not scores:
            return 0
        return statistics.median(scores)

    def calculate_trimmed_mean(
        self, scores: List[float], trim_percent: float = 0.1
    ) -> float:
        """Calculate mean after removing top/bottom percentiles"""
        if not scores:
            return 0
        if len(scores) < 3:
            return statistics.mean(scores)

        sorted_scores = sorted(scores)
        trim_count = max(1, int(len(sorted_scores) * trim_percent))

        # Don't trim everything
        if trim_count * 2 >= len(sorted_scores):
            return statistics.mean(sorted_scores)

        trimmed = (
            sorted_scores[trim_count:-trim_count] if trim_count > 0 else sorted_scores
        )
        return statistics.mean(trimmed) if trimmed else statistics.mean(sorted_scores)

    def calculate_consistency_score(self, scores: List[float]) -> float:
        """Calculate consistency score (inverse of coefficient of variation)"""
        if not scores or len(scores) < 2:
            return 100.0

        mean = statistics.mean(scores)
        if mean == 0:
            return 0

        stdev = statistics.stdev(scores)
        cv = stdev / mean  # Coefficient of variation

        # Convert to percentage (0-100), where 100 is perfectly consistent
        consistency = max(0, min(100, (1 - cv) * 100))
        return consistency

    def calculate_confidence_interval(
        self, scores: List[float], confidence: float = 0.95
    ) -> Tuple[float, float]:
        """Calculate confidence interval for scores"""
        if not scores:
            return (0, 0)
        if len(scores) == 1:
            return (scores[0], scores[0])

        mean = statistics.mean(scores)
        stdev = statistics.stdev(scores) if len(scores) > 1 else 0
        n = len(scores)

        # Use t-distribution for small samples
        # Approximate t-value (for 95% confidence)
        t_value = 2.262 if n <= 10 else 1.96

        margin = t_value * (stdev / math.sqrt(n)) if n > 1 else 0

        return (mean - margin, mean + margin)

    def format_statistical_summary(
        self,
        scores: List[float],
        backend_name: str,
        topic_score_map: Dict[str, float] = dict(),
    ) -> Dict:
        """Generate comprehensive statistical summary for a set of scores"""
        if not scores:
            return {
                "mean": 0,
                "median": 0,
                "trimmed_mean": 0,
                "consistency": 0,
                "confidence_interval": (0, 0),
                "outliers": [],
            }

        outliers = self.detect_outliers(scores, backend_name)
        outlier_details = []

        if outliers and topic_score_map:
            topics = list(topic_score_map.keys())
            for idx, score in outliers:
                if idx < len(topics):
                    topic = topics[idx]
                    median = self.calculate_median(scores)
                    deviation = score - median
                    outlier_details.append(
                        {"topic": topic, "score": score, "deviation": deviation}
                    )

        return {
            "mean": statistics.mean(scores),
            "median": self.calculate_median(scores),
            "trimmed_mean": self.calculate_trimmed_mean(scores),
            "consistency": self.calculate_consistency_score(scores),
            "confidence_interval": self.calculate_confidence_interval(scores),
            "outliers": outlier_details,
            "has_outliers": len(outliers) > 0,
        }

    # ============== Individual Metric Functions ==============

    def evaluate_structure_compliance(
        self, report: str, topic: str = ""
    ) -> MetricResult:
        """Check if all required sections exist with proper formatting"""
        details = {"missing_sections": [], "empty_sections": [], "sections_found": []}

        for section in REQUIRED_SECTIONS:
            # Look for section header (## Section or # Section)
            pattern = rf"^##?\s+{re.escape(section)}\s*$"
            if re.search(pattern, report, re.MULTILINE | re.IGNORECASE):
                details["sections_found"].append(section)

                # Check if section only contains N/A
                section_pattern = (
                    rf"^##?\s+{re.escape(section)}\s*\n(.*?)(?=^##?\s+|\Z)"
                )
                match = re.search(
                    section_pattern, report, re.MULTILINE | re.IGNORECASE | re.DOTALL
                )
                if match:
                    content = match.group(1).strip()
                    if content.lower() in ["n/a", "n/a.", "not applicable", ""]:
                        details["empty_sections"].append(section)
            else:
                details["missing_sections"].append(section)

        # Calculate score
        total_sections = len(REQUIRED_SECTIONS)
        missing_penalty = len(details["missing_sections"]) * 10
        empty_penalty = len(details["empty_sections"]) * 5
        score = max(0, 100 - missing_penalty - empty_penalty)

        feedback = f"Found {len(details['sections_found'])}/{total_sections} sections. "
        if details["missing_sections"]:
            feedback += f"Missing: {', '.join(details['missing_sections'][:3])}. "
        if details["empty_sections"]:
            feedback += f"Empty: {', '.join(details['empty_sections'][:3])}."

        return MetricResult(score=score, details=details, feedback=feedback)

    def evaluate_technical_depth(self, report: str, topic: str = "") -> MetricResult:
        """Assess technical detail level using LLM"""
        prompt = f"""Evaluate the technical depth of this threat hunting report about {topic or "this technique"}.
        
Score (0-100) based on:
1. Presence of specific technical details (commands, code, configurations)
2. Step-by-step instructions that could be followed
3. Specific artifacts, file paths, registry keys mentioned
4. Technical accuracy and completeness

Report to evaluate:
{report}

Respond with ONLY a JSON object in this exact format:
{{
    "score": 75,
    "code_blocks_found": 5,
    "commands_found": 3,
    "specific_artifacts": 8,
    "feedback": "Good technical detail with code examples",
    "confidence": 0.9
}}"""

        result = self.evaluate_with_llm_retry(prompt, "technical_depth", "technical_depth")

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={
                    "code_blocks": result.get("code_blocks_found", 0),
                    "commands": result.get("commands_found", 0),
                    "artifacts": result.get("specific_artifacts", 0),
                },
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.8),
            )
        else:
            # Fallback to simple counting
            code_blocks = len(re.findall(r"```[\s\S]*?```", report))
            score = min(100, code_blocks * 10 + 30)
            return MetricResult(
                score=score,
                feedback="Fallback: counted code blocks only",
                confidence=0.3,
            )

    def evaluate_technical_accuracy(self, report: str, topic: str = "") -> MetricResult:
        """Evaluate the technical accuracy of commands, paths, and code in the report"""
        # Find all code blocks and technical content
        code_blocks = re.findall(r"```[\s\S]*?```", report)

        # Also look for inline technical content (commands not in code blocks)
        technical_patterns = [
            r"(?:^|\s)([A-Z]:\\[^\s]+)",  # Windows paths
            r"(?:^|\s)(\/[^\s]+\/[^\s]+)",  # Unix paths
            r"(?:^|\s)(HKLM\\[^\s]+)",  # Registry paths
            r"(?:^|\s)(HKCU\\[^\s]+)",  # Registry paths
            r"(?:^|\s)(Get-[A-Za-z]+)",  # PowerShell cmdlets
            r"(?:^|\s)(\$[A-Za-z_][A-Za-z0-9_]*)",  # Variables
        ]

        inline_technical = []
        for pattern in technical_patterns:
            inline_technical.extend(re.findall(pattern, report))

        prompt = f"""Evaluate the TECHNICAL ACCURACY of commands, code, and technical details in this threat hunting report about {topic or "this technique"}.

Code blocks found: {len(code_blocks)}
Inline technical elements found: {len(inline_technical)}

First few code blocks:
{chr(10).join(code_blocks[:3]) if code_blocks else "No code blocks found"}

Sample inline technical content:
{str(inline_technical[:10]) if inline_technical else "No inline technical content found"}

Full report for context:
{report[:5000]}

Critically evaluate:
1. Are commands syntactically correct for their respective systems (Windows/Linux/PowerShell/Bash)?
2. Do file paths and registry keys follow correct formatting and likely exist?
3. Are API calls, function names, and parameters accurate?
4. Would the provided queries (Splunk, KQL, SQL) actually work?
5. Are there obvious technical impossibilities or errors?
6. Do code examples have correct syntax for their language?

Be strict - even small syntax errors should reduce the score. Look for:
- Incorrect PowerShell cmdlet names or parameters
- Invalid Windows registry paths
- Malformed file paths
- Incorrect command syntax
- Impossible technical claims

Respond with ONLY a JSON object in this exact format:
{{
    "score": 75,
    "syntax_errors_found": 2,
    "invalid_paths_found": 1,
    "impossible_claims": 0,
    "accuracy_assessment": "mostly_accurate",
    "specific_errors": ["Get-ProcessHandle is not a real cmdlet", "Registry path missing key"],
    "feedback": "Generally accurate with minor PowerShell syntax errors",
    "confidence": 0.85
}}"""

        result = self.evaluate_with_llm_retry(
            prompt, "technical_accuracy", "technical_accuracy", max_tokens=800
        )

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={
                    "syntax_errors": result.get("syntax_errors_found", 0),
                    "invalid_paths": result.get("invalid_paths_found", 0),
                    "impossible_claims": result.get("impossible_claims", 0),
                    "specific_errors": result.get("specific_errors", []),
                    "assessment": result.get("accuracy_assessment", "unknown"),
                },
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.85),
            )
        else:
            # Fallback - if we can't evaluate, give a neutral score
            return MetricResult(
                score=50,
                feedback="Could not evaluate technical accuracy",
                confidence=0.2,
            )

    def evaluate_mitre_coverage(self, report: str, topic: str = "") -> MetricResult:
        """Evaluate MITRE ATT&CK reference quality"""
        # Find all MITRE IDs
        mitre_pattern = r"T\d{4}(?:\.\d{3})?"
        mitre_ids = re.findall(mitre_pattern, report)

        # Check for MITRE URLs
        mitre_urls = re.findall(r"https?://attack\.mitre\.org/\S+", report)

        prompt = f"""Evaluate the MITRE ATT&CK coverage in this report.

Check for:
1. Are MITRE technique IDs present and correctly formatted?
2. Do the IDs match the described technique?
3. Are techniques ordered by attack lifecycle?
4. Are URLs to MITRE pages included?

MITRE IDs found: {mitre_ids}
MITRE URLs found: {len(mitre_urls)}

Full report:
{report}

Respond with ONLY a JSON object in this exact format:
{{
    "score": 85,
    "valid_ids": 3,
    "has_urls": true,
    "proper_ordering": false,
    "feedback": "Good MITRE coverage with valid IDs",
    "confidence": 0.8
}}"""

        result = self.evaluate_with_llm_retry(prompt, "mitre_coverage", "mitre_coverage")

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={
                    "mitre_ids_found": len(mitre_ids),
                    "valid_ids": result.get("valid_ids", 0),
                    "has_urls": result.get("has_urls", False),
                },
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.8),
            )
        else:
            # Fallback scoring
            score = min(100, len(mitre_ids) * 20 + len(mitre_urls) * 10)
            return MetricResult(
                score=score,
                feedback=f"Found {len(mitre_ids)} MITRE IDs",
                confidence=0.3,
            )

    def evaluate_detection_quality(self, report: str, topic: str = "") -> MetricResult:
        """Evaluate the quality of detection methods provided"""
        # Use LLM to extract Detection section with variations
        detection_content = self.extract_section_with_llm(
            report,
            "Detection",
            "detection methods, rules, and strategies for identifying this threat",
            variations=[
                "Detections",
                "Detection Methods",
                "Detection Strategies",
                "How to Detect",
                "Detection Rules",
            ],
        )

        # If no content found, try fallback regex (for backwards compatibility)
        if not detection_content:
            detection_pattern = r"^##?\s+Detection\s*\n(.*?)(?=^##?\s+|\Z)"
            match = re.search(
                detection_pattern, report, re.MULTILINE | re.IGNORECASE | re.DOTALL
            )
            detection_content = match.group(1) if match else ""

        prompt = f"""Evaluate the quality of detection methods for this threat hunting report about {topic or "this technique"}.

Detection section:
{detection_content[:3000] if detection_content else "No detection section found"}

Score based on:
1. Presence of specific detection rules/queries (Splunk, KQL, Sigma, YARA, etc.)
2. Actionable detection logic that could be implemented
3. Coverage of multiple detection approaches
4. Discussion of false positives or detection gaps
5. Practical applicability

Respond with ONLY a JSON object in this exact format:
{{
    "score": 75,
    "has_queries": true,
    "query_types": ["Splunk", "KQL"],
    "actionable": true,
    "discusses_false_positives": false,
    "feedback": "Has actionable queries but lacks false positive discussion",
    "confidence": 0.9
}}"""

        result = self.evaluate_with_llm_retry(prompt, "detection_quality", "detection_quality")

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details=result,
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.9),
            )
        else:
            # Fallback
            has_queries = bool(
                re.search(
                    r"(index=|SELECT|EventID|rule:|detection:)", detection_content
                )
            )
            score = 50 if detection_content else 0
            if has_queries:
                score += 30
            return MetricResult(
                score=score, feedback="Detection section evaluated", confidence=0.3
            )

    def evaluate_dataset_documentation(
        self, report: str, topic: str = ""
    ) -> MetricResult:
        """Evaluate the quality of dataset documentation"""
        # Use LLM to extract Typical Datasets section with variations
        dataset_content = self.extract_section_with_llm(
            report,
            "Typical Datasets",
            "datasets, log sources, and data types needed for hunting this threat",
            variations=[
                "Datasets",
                "Required Datasets",
                "Data Sources",
                "Log Sources",
                "Required Data",
                "Hunt Datasets",
            ],
        )

        # If no content found, try fallback regex
        if not dataset_content:
            dataset_pattern = r"^##?\s+Typical Datasets\s*\n(.*?)(?=^##?\s+|\Z)"
            match = re.search(
                dataset_pattern, report, re.MULTILINE | re.IGNORECASE | re.DOTALL
            )
            dataset_content = match.group(1) if match else ""

        prompt = f"""Evaluate the dataset documentation quality in this threat hunting report.

Typical Datasets section:
{dataset_content[:3000] if dataset_content else "No dataset section found"}

Score based on:
1. Are specific log sources identified (Sysmon, Windows Security, EDR, etc.)?
2. Are example log entries provided?
3. Are important fields explained?
4. Are links to documentation provided?
5. Is it clear how to use these datasets for hunting?

Respond with ONLY a JSON object in this exact format:
{{
    "score": 80,
    "log_sources_count": 3,
    "has_examples": true,
    "has_field_explanations": true,
    "has_doc_links": false,
    "feedback": "Good log sources with examples but missing documentation links",
    "confidence": 0.9
}}"""

        result = self.evaluate_with_llm_retry(
            prompt, "dataset_documentation", "dataset_documentation"
        )

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details=result,
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.9),
            )
        else:
            score = 30 if dataset_content else 0
            return MetricResult(
                score=score, feedback="Dataset section present", confidence=0.3
            )

    def evaluate_threat_actor_specificity(
        self, report: str, topic: str = ""
    ) -> MetricResult:
        """Evaluate how specific threat actor information is"""
        # Use LLM to extract Threat Actors section with variations
        ta_content = self.extract_section_with_llm(
            report,
            "Threat Actors",
            "threat actors, APT groups, or adversaries known to use this technique",
            variations=[
                "Threat Actor Groups",
                "Known Threat Actors",
                "Adversaries",
                "APT Groups",
                "Threat Groups",
                "Actors",
            ],
        )

        # If no content found, try fallback regex
        if not ta_content:
            ta_pattern = r"^##?\s+Threat Actors\s*\n(.*?)(?=^##?\s+|\Z)"
            match = re.search(
                ta_pattern, report, re.MULTILINE | re.IGNORECASE | re.DOTALL
            )
            ta_content = match.group(1) if match else ""

        prompt = f"""Evaluate threat actor specificity in this report.

Threat Actors section:
{ta_content[:2000] if ta_content else "No threat actors section found"}

Score based on:
1. Are specific threat actor groups named (not just "many actors")?
2. Is there detail about HOW these actors use this technique?
3. Are there references to specific campaigns or incidents?

Respond with ONLY a JSON object in this exact format:
{{
    "score": 65,
    "named_groups_count": 2,
    "has_usage_details": true,
    "generic_only": false,
    "feedback": "Names specific groups with usage details",
    "confidence": 0.8
}}"""

        result = self.evaluate_with_llm_retry(
            prompt, "threat_actor_specificity", "threat_actor_specificity"
        )

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details=result,
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.8),
            )
        else:
            score = 30 if ta_content and "many" not in ta_content.lower() else 10
            return MetricResult(
                score=score, feedback="Threat actor section evaluated", confidence=0.3
            )

    def evaluate_reference_quality(self, report: str, topic: str = "") -> MetricResult:
        """Evaluate reference quality and diversity"""
        # Use LLM to extract References section with variations
        ref_content = self.extract_section_with_llm(
            report,
            "References",
            "references, sources, citations, and external links used in this report",
            variations=[
                "Sources",
                "Citations",
                "External References",
                "Bibliography",
                "Links",
                "Further Reading",
            ],
        )

        # If no content found, try fallback regex
        if not ref_content:
            ref_pattern = r"^##?\s+References\s*\n(.*?)(?=^##?\s+|\Z)"
            match = re.search(
                ref_pattern, report, re.MULTILINE | re.IGNORECASE | re.DOTALL
            )
            ref_content = match.group(1) if match else ""

        # Count URLs
        urls = re.findall(r"https?://[^\s\)]+", ref_content)

        # Check diversity
        domains = [urlparse(url).netloc for url in urls]
        unique_domains = set(domains)

        details = {
            "total_references": len(urls),
            "unique_domains": len(unique_domains),
            "has_mitre": any("mitre.org" in d for d in domains),
            "has_vendor_docs": any(
                d for d in domains if "microsoft.com" in d or "docs." in d
            ),
            "has_github": any("github.com" in d for d in domains),
        }

        # Score based on quantity and diversity
        score = min(100, len(urls) * 5 + len(unique_domains) * 10)
        if details["has_mitre"]:
            score = min(100, score + 10)

        # Check if references have descriptions
        has_descriptions = bool(re.search(r"\[.+?\]\(.+?\)\s*[-:]?\s*\w+", ref_content))
        if not has_descriptions:
            score *= 0.7

        feedback = (
            f"Found {len(urls)} references from {len(unique_domains)} unique domains"
        )

        return MetricResult(score=score, details=details, feedback=feedback)

    async def evaluate_url_validity_async(
        self, report: str, topic: str = ""
    ) -> MetricResult:
        """Asynchronously check URL validity and relevance"""
        import random

        urls = re.findall(r"https?://[^\s\)]+", report)

        results = {
            "total_urls": len(urls),
            "valid_urls": 0,
            "invalid_urls": 0,
            "timeout_urls": 0,
            "broken_links": [],
            "sample_size": 0,
        }

        # Decide which URLs to check
        if len(urls) <= 20:
            # Check all URLs if 20 or fewer
            urls_to_check = urls
            results["sample_size"] = len(urls)
        else:
            # Random sample of 20 if more than 20
            urls_to_check = random.sample(urls, 20)
            results["sample_size"] = 20

        async def check_url(session, url):
            try:
                async with session.head(
                    url, timeout=5, allow_redirects=True
                ) as response:
                    if response.status < 400:
                        return url, "valid"
                    else:
                        return url, "invalid"
            except asyncio.TimeoutError:
                return url, "timeout"
            except Exception:
                return url, "invalid"

        async with aiohttp.ClientSession() as session:
            tasks = [check_url(session, url) for url in urls_to_check]
            url_results = await asyncio.gather(*tasks)

        for url, status in url_results:
            if status == "valid":
                results["valid_urls"] += 1
            elif status == "timeout":
                results["timeout_urls"] += 1
            else:
                results["invalid_urls"] += 1
                results["broken_links"].append(url)

        # Calculate score based on sampled URLs
        if results["sample_size"] > 0:
            valid_ratio = results["valid_urls"] / results["sample_size"]
            score = valid_ratio * 100
        else:
            score = 0

        # Update feedback to indicate sampling
        if len(urls) > 20:
            feedback = f"{results['valid_urls']}/{results['sample_size']} URLs valid (random sample from {len(urls)} total)"
        else:
            feedback = f"{results['valid_urls']}/{results['sample_size']} URLs valid"

        if results["broken_links"]:
            feedback += f", {len(results['broken_links'])} broken"

        return MetricResult(score=score, details=results, feedback=feedback)

    def evaluate_url_validity(self, report: str, topic: str = "") -> MetricResult:
        """Synchronous wrapper for URL validation"""
        try:
            return asyncio.run(self.evaluate_url_validity_async(report, topic))
        except Exception as e:
            # Fallback if async fails
            urls = re.findall(r"https?://[^\s\)]+", report)
            return MetricResult(
                score=50,
                details={"total_urls": len(urls), "check_failed": str(e)},
                feedback=f"Found {len(urls)} URLs (validation failed)",
                confidence=0.2,
            )

    def evaluate_log_example_quality(
        self, report: str, topic: str = ""
    ) -> MetricResult:
        """Evaluate the quality and usefulness of log examples"""
        # Find log examples (usually in code blocks or indented)
        code_blocks = re.findall(r"```[\s\S]*?```", report)

        prompt = f"""Evaluate the log example quality in this threat hunting report.

Number of code blocks found: {len(code_blocks)}

First few code blocks:
{" ".join(code_blocks[:3])}

Full report for context:
{report}

Score based on:
1. Are there actual log entry examples (not just descriptions)?
2. Are the important fields highlighted or explained?
3. Do examples show both malicious and benign for comparison?
4. Are the examples relevant to detecting the threat?

Respond with ONLY a JSON object in this exact format:
{{
    "score": 70,
    "has_log_examples": true,
    "explains_fields": true,
    "shows_comparison": false,
    "example_count": 3,
    "feedback": "Has log examples with field explanations but no comparisons",
    "confidence": 0.9
}}"""

        result = self.evaluate_with_llm_retry(
            prompt, "log_example_quality", "log_example_quality"
        )

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details=result,
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.9),
            )
        else:
            score = min(100, len(code_blocks) * 15)
            return MetricResult(
                score=score,
                feedback=f"Found {len(code_blocks)} code blocks",
                confidence=0.3,
            )

    def evaluate_instruction_clarity(
        self, report: str, topic: str = ""
    ) -> MetricResult:
        """Evaluate if instructions are clear enough to follow"""
        # Use LLM to extract Technique Details section with variations
        tech_content = self.extract_section_with_llm(
            report,
            "Technique Details",
            "detailed technical explanation of how this attack technique works",
            variations=[
                "Technical Details",
                "How It Works",
                "Technique Description",
                "Attack Methodology",
                "Technical Implementation",
                "Detailed Description",
                "How the Attack Works",
            ],
        )

        # If no content found, try fallback regex
        if not tech_content:
            tech_pattern = r"^##?\s+Technique Details\s*\n(.*?)(?=^##?\s+|\Z)"
            match = re.search(
                tech_pattern, report, re.MULTILINE | re.IGNORECASE | re.DOTALL
            )
            tech_content = match.group(1) if match else ""

        prompt = f"""Evaluate the clarity of instructions in this threat hunting report about {topic or "this technique"}.

Technique Details section:
{tech_content[:3000] if tech_content else "No technique details section found"}

Answer these questions:
1. Could a skilled threat hunter replicate this technique from the description?
2. Are the steps clearly numbered or sequenced?
3. Are prerequisites and requirements mentioned?
4. Is it clear WHY each step is performed?

Respond with ONLY a JSON object in this exact format:
{{
    "score": 75,
    "replicable": true,
    "has_clear_steps": true,
    "explains_why": false,
    "feedback": "Clear steps but lacks explanation of why",
    "confidence": 0.9
}}"""

        result = self.evaluate_with_llm_retry(
            prompt, "instruction_clarity", "instruction_clarity"
        )

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details=result,
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.9),
            )
        else:
            # Check for step indicators
            has_steps = bool(
                re.search(
                    r"(step \d|first|then|next|finally|\d\.)",
                    tech_content,
                    re.IGNORECASE,
                )
            )
            score = 60 if has_steps else 30
            return MetricResult(
                score=score, feedback="Instruction clarity evaluated", confidence=0.3
            )

    def evaluate_cross_section_consistency(
        self, report: str, topic: str = ""
    ) -> MetricResult:
        """Check if different sections are consistent with each other"""
        prompt = f"""Evaluate the internal consistency of this threat hunting report.

Full report:
{report}

Check for:
1. Do threat actors mentioned in Overview appear in Threat Actors section?
2. Do detection methods align with the technique described?
3. Are tools mentioned consistently across sections?
4. Do datasets mentioned support the detection strategies?

Respond with ONLY a JSON object in this exact format:
{{
    "score": 85,
    "is_consistent": true,
    "inconsistencies": [],
    "feedback": "Sections are internally consistent",
    "confidence": 0.85
}}"""

        result = self.evaluate_with_llm_retry(
            prompt, "cross_section_consistency", "cross_section_consistency"
        )

        if result:
            return MetricResult(
                score=result.get("score", 0),
                details=result,
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.85),
            )
        else:
            return MetricResult(
                score=70, feedback="Could not evaluate consistency", confidence=0.2
            )

    def evaluate_tool_documentation(self, report: str, topic: str = "") -> MetricResult:
        """Evaluate the documentation of tools used in the technique"""
        # Use LLM to extract Commonly-Used Tools section with variations
        tools_content = self.extract_section_with_llm(
            report,
            "Commonly-Used Tools",
            "tools, utilities, or software commonly used to perform this attack technique",
            variations=[
                "Common Tools",
                "Tools",
                "Attacker Tools",
                "Tools Used",
                "Attack Tools",
                "Malware and Tools",
                "Software Used",
            ],
        )

        # If no content found, try fallback regex
        if not tools_content:
            tools_pattern = r"^##?\s+Commonly-Used Tools\s*\n(.*?)(?=^##?\s+|\Z)"
            match = re.search(
                tools_pattern, report, re.MULTILINE | re.IGNORECASE | re.DOTALL
            )
            tools_content = match.group(1) if match else ""

        if not tools_content or tools_content.strip().lower() in ["n/a", "n/a."]:
            return MetricResult(score=0, feedback="No tools documented", confidence=1.0)

        # Count tools mentioned
        tool_lines = [
            line
            for line in tools_content.split("\n")
            if line.strip() and not line.strip().lower() == "n/a"
        ]

        score = min(100, len(tool_lines) * 20)

        # Check if tools have descriptions or just names
        if any(":" in line or "-" in line for line in tool_lines):
            score = min(100, score + 20)
            feedback = f"Found {len(tool_lines)} tools with descriptions"
        else:
            feedback = f"Found {len(tool_lines)} tools listed"

        return MetricResult(
            score=score, details={"tool_count": len(tool_lines)}, feedback=feedback
        )

    # ============== Main Evaluation Methods ==============

    def evaluate_report(self, report_data: Dict, pbar=None) -> ReportMetrics:
        """Evaluate a single report using all metrics
        
        Args:
            report_data: Dictionary with 'topic', 'backend', and 'report' keys
            pbar: Optional progress bar to update after each metric
        
        Returns:
            ReportMetrics with all evaluation results
        """
        topic = report_data["topic"]
        backend = report_data["backend"]
        report = report_data["report"]

        # Clear section cache for new report
        self.section_cache.clear()

        metrics = ReportMetrics(topic=topic, backend=backend)

        # Buffer verbose header for this report
        if self.verbose:
            self._verbose_buffer.append(f"\n## Evaluating {backend} report for '{topic}':")
            self._verbose_buffer.append(f"{'Metric':<30} {'Score':>8} {'Weight':>8} {'Feedback'}")
            self._verbose_buffer.append(f"{'-' * 30} {'-' * 8} {'-' * 8} {'-' * 40}")

        # Run each metric function
        for metric_name, (metric_func, judge_role, weight) in self.metric_functions.items():
            try:
                result = metric_func(report, topic)
                result.weight = weight
                metrics.metric_results[metric_name] = result

                # Buffer verbose output instead of printing
                if self.verbose:
                    score_str = f"{result.score:.1f}"
                    weight_str = f"x{weight:.1f}"
                    feedback_str = (
                        result.feedback[:40] + "..."
                        if len(result.feedback) > 40
                        else result.feedback
                    )
                    self._verbose_buffer.append(
                        f"{metric_name:<30} {score_str:>8} {weight_str:>8} {feedback_str}"
                    )
                
                # Update progress bar after each metric
                if pbar:
                    pbar.update(1)

            except Exception as e:
                error_result = MetricResult(
                    score=0,
                    weight=weight,
                    feedback=f"Evaluation failed: {str(e)}",
                    confidence=0,
                )
                metrics.metric_results[metric_name] = error_result

                # Buffer error message
                if self.verbose:
                    self._verbose_buffer.append(
                        f"{metric_name:<30} {'ERROR':>8} {f'x{weight:.1f}':>8} Failed: {str(e)[:35]}..."
                    )
                
                # Update progress bar even on error
                if pbar:
                    pbar.update(1)

        metrics.calculate_total_score()

        # Buffer total score
        if self.verbose:
            self._verbose_buffer.append(f"{'-' * 30} {'-' * 8} {'-' * 8} {'-' * 40}")
            self._verbose_buffer.append(f"{'TOTAL SCORE':<30} {metrics.total_score:>8.1f}")

        return metrics

    def compare_reports(
        self, old_metrics: ReportMetrics, new_metrics: ReportMetrics
    ) -> ComparisonResult:
        """Compare two reports and determine which is better"""
        key_differences = []

        # Calculate confidence based on how many metrics have high confidence
        confidences = []

        for metric_name in self.metric_functions.keys():
            old_result = old_metrics.metric_results.get(
                metric_name, MetricResult(score=0)
            )
            new_result = new_metrics.metric_results.get(
                metric_name, MetricResult(score=0)
            )

            confidences.append((old_result.confidence + new_result.confidence) / 2)

            diff = new_result.score - old_result.score
            if abs(diff) > 10:  # Significant difference
                if diff > 0:
                    key_differences.append(
                        f"{metric_name}: NEW better by {diff:.1f} points"
                    )
                else:
                    key_differences.append(
                        f"{metric_name}: OLD better by {abs(diff):.1f} points"
                    )

        score_diff = new_metrics.total_score - old_metrics.total_score

        if abs(score_diff) < 5:
            winner = "TIE"
        elif score_diff > 0:
            winner = "NEW"
        else:
            winner = "OLD"

        avg_confidence = statistics.mean(confidences) if confidences else 0.5

        return ComparisonResult(
            topic=old_metrics.topic,
            old_metrics=old_metrics,
            new_metrics=new_metrics,
            winner=winner,
            confidence=avg_confidence,
            key_differences=key_differences[:5],  # Top 5 differences
        )

    def _looks_like_base64(self, s: str) -> bool:
        """Check if a string looks like base64 encoding"""
        if not s:
            return False
        # Base64 has specific characteristics
        import re

        # Check if it matches base64 pattern and doesn't have markdown indicators
        base64_pattern = r"^[A-Za-z0-9+/]+=*$"
        if re.match(base64_pattern, s.replace("\n", "")) and "##" not in s:
            return True
        return False

    def process_reports(self, input_file: str, output_file: str):
        """Process all reports from input file - handles both single and comparison modes"""
        import base64

        # First, read all reports and detect what backends exist
        all_reports = []
        topics_backends = defaultdict(set)

        with open(input_file, "r") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line)

                    # Handle base64 encoded reports
                    if data.get("encoded") or self._looks_like_base64(
                        data.get("report", "")
                    ):
                        try:
                            report_bytes = base64.b64decode(data["report"])
                            data["report"] = report_bytes.decode("utf-8")
                        except Exception as e:
                            self.print_output(
                                f"Warning: Failed to decode report on line {line_num}: {e}"
                            )
                            continue

                    all_reports.append(data)
                    topics_backends[data["topic"]].add(data["backend"])
                except json.JSONDecodeError as e:
                    self.print_output(f"Warning: Invalid JSON on line {line_num}: {e}")
                    continue

        # Update metadata
        self.full_evaluation_data["metadata"]["total_reports"] = len(all_reports)

        # Determine mode based on backends per topic
        backends_per_topic = [len(backends) for backends in topics_backends.values()]

        if not backends_per_topic:
            self.print_output("Error: No valid reports found!")
            return

        if all(b == 1 for b in backends_per_topic):
            # Single evaluation mode - just evaluate individual reports
            self.print_output("Detected single evaluation mode")
            self.full_evaluation_data["metadata"]["evaluation_mode"] = "single"
            self._process_single_mode(all_reports, output_file)
        elif all(b >= 2 for b in backends_per_topic):
            # Comparison mode (2 or more backends)
            unique_backends = set()
            for backends in topics_backends.values():
                unique_backends.update(backends)
            self.print_output(
                f"Detected comparison mode: {len(unique_backends)} backends ({', '.join(sorted(unique_backends))})"
            )
            self.full_evaluation_data["metadata"]["evaluation_mode"] = "comparison"
            self.full_evaluation_data["metadata"]["backends"] = sorted(unique_backends)
            self._process_comparison_mode(all_reports, output_file)
        else:
            # Mixed - some topics have different numbers of backends
            self.print_output(
                "Warning: Mixed mode detected - some topics have different numbers of backends"
            )
            self.print_output("Processing as single evaluation mode...")
            self.full_evaluation_data["metadata"]["evaluation_mode"] = "mixed"
            self._process_single_mode(all_reports, output_file)

        # Save log file if specified
        self.save_log_file()

        # Save full JSON output if specified
        self.save_json_output()

    def _process_single_mode(self, all_reports: List[Dict], output_file: str):
        """Process reports in single evaluation mode (no comparison)"""
        # Group by backend for summary stats
        reports_by_backend = defaultdict(list)
        all_metrics = []

        # Setup progress bar
        total_metrics = len(all_reports) * len(self.metric_functions)
        pbar = None
        try:
            from tqdm.auto import tqdm as _tqdm  # type: ignore
            if not self.quiet:
                pbar = _tqdm(total=total_metrics, desc="Evaluating", unit="metric", dynamic_ncols=True)
        except Exception:
            if not self.quiet:
                self.print_output("(Tip: install tqdm for a progress bar: pip install tqdm)")

        # Evaluate all reports
        for report_data in all_reports:
            topic = report_data["topic"]
            backend = report_data["backend"]

            # Buffer verbose header
            if self.verbose:
                self._verbose_buffer.append(f"\n{'=' * 90}")
                self._verbose_buffer.append(f"Topic: {topic} | Backend: {backend}")
                self._verbose_buffer.append(f"{'=' * 90}")

            # Evaluate the report (updates progress bar internally)
            metrics = self.evaluate_report(report_data, pbar=pbar)
            all_metrics.append(metrics)
            reports_by_backend[backend].append(metrics.total_score)

            # Write detailed metrics to output file
            output_data = {
                "topic": topic,
                "backend": backend,
                "total_score": metrics.total_score,
                "metrics": {
                    k: {
                        "score": v.score,
                        "weight": v.weight,
                        "feedback": v.feedback,
                        "confidence": v.confidence,
                    }
                    for k, v in metrics.metric_results.items()
                },
                "metric_scores": {
                    k: v.score for k, v in metrics.metric_results.items()
                },
            }

            with open(output_file, "a") as f:
                f.write(json.dumps(output_data) + "\n")

        # Close progress bar
        if pbar:
            pbar.close()

        # Now print the complete report
        self._print_final_report_single(all_reports, all_metrics, reports_by_backend)

    def _print_final_report_single(self, all_reports: List[Dict], all_metrics: List[ReportMetrics], reports_by_backend: Dict):
        """Print the final evaluation report for single mode"""
        # Build markdown report
        md_lines = []
        
        md_lines.append("# Evaluation Complete")
        md_lines.append("")
        
        # Print verbose details if requested
        if self.verbose and self._verbose_buffer:
            md_lines.append("## Detailed Evaluation Results")
            md_lines.append("")
            md_lines.extend(self._verbose_buffer)
            md_lines.append("")
        
        # Summary statistics
        md_lines.append("## Evaluation Summary")
        md_lines.append("")
        md_lines.append(f"**Total reports evaluated:** {len(all_reports)}")
        md_lines.append("")
        
        for backend, scores in reports_by_backend.items():
            md_lines.append(f"### Backend: {backend}")
            md_lines.append(f"- Reports: {len(scores)}")
            md_lines.append(f"- Average score: {statistics.mean(scores):.1f}")
            md_lines.append(f"- Min score: {min(scores):.1f}")
            md_lines.append(f"- Max score: {max(scores):.1f}")
            if len(scores) > 1:
                md_lines.append(f"- Std deviation: {statistics.stdev(scores):.1f}")
            md_lines.append("")
        
        # Metric-level summary
        if all_metrics:
            md_lines.append("### Metric Performance Across All Reports")
            md_lines.append("")
            metric_scores = defaultdict(list)
            for m in all_metrics:
                for metric_name, result in m.metric_results.items():
                    metric_scores[metric_name].append(result.score)
            
            for metric_name, scores in sorted(metric_scores.items()):
                avg_score = statistics.mean(scores)
                md_lines.append(f"- **{metric_name}**: {avg_score:.1f}")
        
        # Print the complete markdown report
        self.print_markdown("\n".join(md_lines))

    def _process_comparison_mode(self, all_reports: List[Dict], output_file: str):
        """Process reports in comparison mode (2 or more backends)"""
        # Group reports by topic
        reports_by_topic = defaultdict(list)
        for report in all_reports:
            reports_by_topic[report["topic"]].append(report)

        # Track overall statistics
        backend_wins = defaultdict(int)
        backend_scores = defaultdict(list)
        backend_topic_scores = defaultdict(dict)  # backend -> {topic: score}
        backend_rankings = defaultdict(lambda: {"first": 0, "second": 0, "third": 0})
        metric_scores_by_backend = defaultdict(lambda: defaultdict(list))

        # Setup progress bar
        total_metrics = len(all_reports) * len(self.metric_functions)
        pbar = None
        try:
            from tqdm.auto import tqdm as _tqdm  # type: ignore
            if not self.quiet:
                pbar = _tqdm(total=total_metrics, desc="Evaluating", unit="metric", dynamic_ncols=True)
        except Exception:
            if not self.quiet:
                self.print_output("(Tip: install tqdm for a progress bar: pip install tqdm)")

        # Process each topic
        for topic, reports in reports_by_topic.items():
            # Buffer verbose header
            if self.verbose:
                self._verbose_buffer.append(f"\n{'=' * 90}")
                self._verbose_buffer.append(f"Topic: {topic}")
                self._verbose_buffer.append(f"{'=' * 90}")

            # Evaluate all reports for this topic
            topic_metrics = []
            for report in reports:
                metrics = self.evaluate_report(report, pbar=pbar)
                topic_metrics.append(metrics)
                backend_scores[metrics.backend].append(metrics.total_score)
                backend_topic_scores[metrics.backend][topic] = metrics.total_score

                # Track metric scores for overall summary
                for metric_name, result in metrics.metric_results.items():
                    metric_scores_by_backend[metrics.backend][metric_name].append(
                        result.score
                    )

            # Sort by score
            topic_metrics.sort(key=lambda x: x.total_score, reverse=True)

            # Track rankings
            winner = topic_metrics[0].backend
            backend_wins[winner] += 1
            for i, metrics in enumerate(topic_metrics):
                if i == 0:
                    backend_rankings[metrics.backend]["first"] += 1
                elif i == 1:
                    backend_rankings[metrics.backend]["second"] += 1
                elif i == 2:
                    backend_rankings[metrics.backend]["third"] += 1

            # Don't display results during evaluation - will show at end
            # self._display_topic_comparison(topic, topic_metrics)

            # Write to output file
            output_data = {
                "topic": topic,
                "rankings": [(m.backend, m.total_score) for m in topic_metrics],
                "winner": winner,
                "backends": {
                    m.backend: {
                        "total_score": m.total_score,
                        "metrics": {
                            k: {"score": v.score, "feedback": v.feedback}
                            for k, v in m.metric_results.items()
                        },
                    }
                    for m in topic_metrics
                },
            }

            with open(output_file, "a") as f:
                f.write(json.dumps(output_data) + "\n")

        # Close progress bar
        if pbar:
            pbar.close()

        # Display overall summary with enhanced statistics (this will be buffered too)
        self._display_overall_comparison_summary_enhanced(
            backend_wins,
            backend_scores,
            backend_rankings,
            metric_scores_by_backend,
            backend_topic_scores,
            len(reports_by_topic),
        )

    def _display_topic_comparison(self, topic: str, metrics_list: List[ReportMetrics]):
        """Display comparison results for a single topic"""
        # Rankings
        self.print_output("\nRankings:")
        for i, metrics in enumerate(metrics_list):
            trophy = " 🏆" if i == 0 else ""
            self.print_output(
                f"  {i + 1}. {metrics.backend} ({metrics.total_score:.1f}){trophy}"
            )

        # How others compare to winner
        if len(metrics_list) > 1:
            winner = metrics_list[0]
            self.print_output(f"\nHow others compare to {winner.backend} (winner):")

            for metrics in metrics_list[1:]:
                score_diff = metrics.total_score - winner.total_score
                self.print_output(f"  {metrics.backend} ({score_diff:+.1f} overall):")

                # Find significant differences
                better_metrics = []
                worse_metrics = []
                roughly_equal = []

                for metric_name in self.metric_functions.keys():
                    winner_score = winner.metric_results[metric_name].score
                    other_score = metrics.metric_results[metric_name].score
                    diff = other_score - winner_score

                    if abs(diff) < 3:
                        roughly_equal.append(metric_name)
                    elif diff > 0:
                        better_metrics.append((metric_name, diff))
                    else:
                        worse_metrics.append((metric_name, -diff))

                # Show top differences
                better_metrics.sort(key=lambda x: x[1], reverse=True)
                worse_metrics.sort(key=lambda x: x[1], reverse=True)

                for metric, diff in better_metrics[:2]:
                    self.print_output(
                        f"    • {metric}: {metrics.backend} better by {diff:.1f} points"
                    )
                for metric, diff in worse_metrics[:2]:
                    self.print_output(
                        f"    • {metric}: {winner.backend} better by {diff:.1f} points"
                    )
                if len(roughly_equal) > 0 and len(roughly_equal) <= 3:
                    self.print_output(
                        f"    • roughly equal: {', '.join(roughly_equal)}"
                    )
                elif len(roughly_equal) > 3:
                    self.print_output(
                        f"    • roughly equal: {', '.join(roughly_equal[:3])} and {len(roughly_equal) - 3} more"
                    )

        # Metric Leaders
        self.print_output("\nMetric Leaders:")
        metric_leaders = {}

        for metric_name in self.metric_functions.keys():
            # Find best score for this metric
            best_score = -1
            best_backend = None
            scores_by_backend = {}

            for metrics in metrics_list:
                score = metrics.metric_results[metric_name].score
                scores_by_backend[metrics.backend] = score
                if score > best_score:
                    best_score = score
                    best_backend = metrics.backend

            # Format the output
            others = []
            for metrics in metrics_list:
                if metrics.backend != best_backend:
                    diff = scores_by_backend[metrics.backend] - best_score
                    others.append(f"{metrics.backend} ({diff:+.1f})")

            self.print_output(
                f"  ⭐ {metric_name}: {best_backend} ({best_score:.1f}) → {', '.join(others)}"
            )
            metric_leaders[metric_name] = best_backend

        # Key Insights
        backend_metric_wins = defaultdict(int)
        for leader in metric_leaders.values():
            backend_metric_wins[leader] += 1

        self.print_output("\nKey Insights:")
        for backend, count in sorted(
            backend_metric_wins.items(), key=lambda x: x[1], reverse=True
        ):
            self.print_output(
                f"  • {backend} dominates {count}/{len(self.metric_functions)} metrics"
            )

        # Find biggest gaps
        biggest_gap = 0
        biggest_gap_metric = None
        for metric_name in self.metric_functions.keys():
            scores = [m.metric_results[metric_name].score for m in metrics_list]
            gap = max(scores) - min(scores)
            if gap > biggest_gap:
                biggest_gap = gap
                biggest_gap_metric = metric_name

        if biggest_gap_metric:
            self.print_output(
                f"  • Biggest gap: {biggest_gap_metric} ({biggest_gap:.1f} points)"
            )

        # Notable Differences (>15 points)
        self.print_output("\nNotable Differences (>15 point gaps):")
        notable_found = False

        for metric_name in self.metric_functions.keys():
            scores_with_backend = [
                (m.backend, m.metric_results[metric_name].score) for m in metrics_list
            ]
            scores_with_backend.sort(key=lambda x: x[1], reverse=True)

            for i in range(len(scores_with_backend)):
                for j in range(i + 1, len(scores_with_backend)):
                    diff = scores_with_backend[i][1] - scores_with_backend[j][1]
                    if diff > 15:
                        self.print_output(
                            f"  • {metric_name}: {scores_with_backend[i][0]} leads {scores_with_backend[j][0]} by {diff:.1f}"
                        )
                        notable_found = True

        if not notable_found:
            self.print_output("  • No differences greater than 15 points")

    def _display_overall_comparison_summary_enhanced(
        self,
        backend_wins,
        backend_scores,
        backend_rankings,
        metric_scores_by_backend,
        backend_topic_scores,
        total_topics,
    ):
        """Display overall summary with statistical robustness measures"""
        
        # Print verbose details first if requested
        if self.verbose and self._verbose_buffer:
            self.print_output("\n" + "=" * 60)
            self.print_output("DETAILED EVALUATION RESULTS")
            self.print_output("=" * 60)
            for line in self._verbose_buffer:
                self.print_output(line)
            self.print_output("")
        
        self.print_output("\n" + "=" * 60)
        self.print_output("OVERALL RANKINGS")
        self.print_output("=" * 60)
        self.print_output(f"Total topics evaluated: {total_topics}")

        # Calculate comprehensive statistics for each backend
        backend_stats = []

        for backend in backend_scores.keys():
            scores = backend_scores[backend]
            topic_score_map = backend_topic_scores[backend]

            stats = self.format_statistical_summary(scores, backend, topic_score_map)

            backend_stats.append(
                {
                    "backend": backend,
                    "wins": backend_wins[backend],
                    "seconds": backend_rankings[backend]["second"],
                    "mean": stats["mean"],
                    "median": stats["median"],
                    "trimmed_mean": stats["trimmed_mean"],
                    "consistency": stats["consistency"],
                    "confidence_interval": stats["confidence_interval"],
                    "outliers": stats["outliers"],
                    "has_outliers": stats["has_outliers"],
                }
            )

        # Sort by median (more robust than mean when outliers present)
        backend_stats.sort(key=lambda x: (x["wins"], x["median"]), reverse=True)

        # Check if we should use median due to outliers
        has_any_outliers = any(b["has_outliers"] for b in backend_stats)

        self.print_output("\nFinal Standings:")
        if has_any_outliers:
            self.print_output("  (Ranked by median due to detected outliers)")

        for i, stats in enumerate(backend_stats):
            trophy = " 🏆" if i == 0 else ""
            standing = f"{stats['wins']} wins"
            if stats["seconds"] > 0:
                standing += f", {stats['seconds']} second place"

            # Main line with key statistics
            consistency_marker = "" if stats["consistency"] > 80 else " ⚠️"
            outlier_marker = " ⚠️ outlier detected" if stats["has_outliers"] else ""

            self.print_output(
                f"  {i + 1}. {stats['backend']}: {standing} "
                f"(avg: {stats['mean']:.1f}, median: {stats['median']:.1f}, "
                f"consistency: {stats['consistency']:.0f}%{consistency_marker}){trophy}{outlier_marker}"
            )

            # Show outlier details if present
            if stats["outliers"]:
                for outlier in stats["outliers"]:
                    self.print_output(
                        f"     └─ Outlier: score of {outlier['score']:.1f} on '{outlier['topic']}' "
                        f"({abs(outlier['deviation']):.1f} points {'below' if outlier['deviation'] < 0 else 'above'} median)"
                    )

        # Statistical Summary Section
        self.print_output("\nStatistical Summary:")
        for stats in backend_stats:
            ci_low, ci_high = stats["confidence_interval"]
            self.print_output(f"  {stats['backend']}:")
            self.print_output(
                f"    Mean: {stats['mean']:.1f}, Median: {stats['median']:.1f}, "
                f"Trimmed Mean (10%): {stats['trimmed_mean']:.1f}"
            )
            self.print_output(
                f"    95% Confidence Interval: [{ci_low:.1f}, {ci_high:.1f}]"
            )
            self.print_output(f"    Consistency Score: {stats['consistency']:.0f}%")

        if has_any_outliers:
            self.print_output(
                "\n📊 Statistical Note: Rankings use median scores due to detected outliers."
            )
            self.print_output(
                "   Outliers may indicate LLM hallucinations or exceptional cases."
            )

        # Metric Champions Across All Topics
        self.print_output("\nMetric Champions Across All Topics:")

        for metric_name in self.metric_functions.keys():
            # Calculate average score for each backend for this metric
            metric_avgs = []
            for backend in backend_scores.keys():
                if metric_name in metric_scores_by_backend[backend]:
                    scores = metric_scores_by_backend[backend][metric_name]
                    # Use median for metric champions if outliers detected
                    if has_any_outliers:
                        avg = self.calculate_median(scores)
                    else:
                        avg = statistics.mean(scores)
                    metric_avgs.append((backend, avg))

            if metric_avgs:
                metric_avgs.sort(key=lambda x: x[1], reverse=True)
                champion = metric_avgs[0]
                measure = "median" if has_any_outliers else "avg"
                self.print_output(
                    f"  ⭐ {metric_name}: {champion[0]} ({measure} {champion[1]:.1f})"
                )

        # Most Consistent Differences
        if len(backend_scores) > 1:
            self.print_output("\nMost Consistent Differences:")

            # Find metrics where one backend consistently outperforms others
            for metric_name in self.metric_functions.keys():
                backend_avgs = {}
                for backend in backend_scores.keys():
                    if metric_name in metric_scores_by_backend[backend]:
                        # Use median for consistency checking if outliers present
                        if has_any_outliers:
                            backend_avgs[backend] = self.calculate_median(
                                metric_scores_by_backend[backend][metric_name]
                            )
                        else:
                            backend_avgs[backend] = statistics.mean(
                                metric_scores_by_backend[backend][metric_name]
                            )

                if len(backend_avgs) > 1:
                    sorted_backends = sorted(
                        backend_avgs.items(), key=lambda x: x[1], reverse=True
                    )
                    best_backend, best_score = sorted_backends[0]

                    # Calculate average gap
                    gaps = [best_score - score for _, score in sorted_backends[1:]]
                    avg_gap = statistics.mean(gaps)

                    if avg_gap > 10:  # Significant consistent difference
                        self.print_output(
                            f"  • {best_backend} consistently beats others on {metric_name} (avg +{avg_gap:.1f})"
                        )

        # Reliability Assessment
        self.print_output("\nReliability Assessment:")
        for stats in backend_stats:
            reliability = (
                "High"
                if stats["consistency"] > 85
                else "Medium"
                if stats["consistency"] > 70
                else "Low"
            )
            ci_width = stats["confidence_interval"][1] - stats["confidence_interval"][0]
            precision = (
                "High" if ci_width < 10 else "Medium" if ci_width < 20 else "Low"
            )

            self.print_output(
                f"  {stats['backend']}: Reliability: {reliability}, Precision: {precision}"
            )

            if stats["has_outliers"]:
                self.print_output(
                    "    ⚠️ Contains outliers - consider investigating anomalous reports"
                )


def main():
    # Load environment variables from .env file
    load_environment()
    
    parser = argparse.ArgumentParser(
        description="Evaluate and compare threat hunting reports"
    )
    parser.add_argument(
        "-i",
        "--input",
        default="input_reports.jsonl",
        help="JSON lines file with reports (default: input_reports.jsonl)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output_results.jsonl",
        help="Output JSON lines file with comparisons (default: output_results.jsonl)",
    )
    parser.add_argument(
        "-c",
        "--model-config",
        type=Path,
        required=True,
        help="Path to model_config.json",
    )
    parser.add_argument(
        "-l",
        "--log",
        default="evaluation_log.txt",
        help="Log file for console output (default: evaluation_log.txt)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output with document-by-document comparison",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode - only write to files, no console output",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Disable saving console output to log file",
    )
    parser.add_argument(
        "-j",
        "--json-output",
        default="evaluation_full.json",
        help="Full JSON output file with complete evaluation details (default: evaluation_full.json)",
    )
    parser.add_argument(
        "--no-json", action="store_true", help="Disable full JSON output file"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw Markdown instead of rendering with rich",
    )

    args = parser.parse_args()

    # Verify model config exists
    if not args.model_config.exists():
        print(f"Error: model_config.json not found at {args.model_config}", file=sys.stderr)
        sys.exit(1)

    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found!", file=sys.stderr)
        sys.exit(1)

    # Clear output file
    open(args.output, "w").close()

    # Determine log file setting
    log_file = None if args.no_log else args.log
    json_output_file = None if args.no_json else args.json_output

    try:
        # Create evaluator with quiet and log settings
        evaluator = ReportEvaluator(
            model_config_path=args.model_config,
            verbose=args.verbose,
            quiet=args.quiet,
            log_file=log_file,
            json_output_file=json_output_file,
            rich_mode=(not args.raw),
        )

        if not args.quiet:
            print(f"Reading reports from: {args.input}")
            print(f"Writing results to: {args.output}")
            if log_file:
                print(f"Logging output to: {log_file}")
            if json_output_file:
                print(f"JSON output to: {json_output_file}")
            if args.verbose:
                print("Verbose mode: ON (showing detailed comparisons)")
            print()

        evaluator.process_reports(args.input, args.output)

        if not args.quiet:
            print(f"\nResults written to: {args.output}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
