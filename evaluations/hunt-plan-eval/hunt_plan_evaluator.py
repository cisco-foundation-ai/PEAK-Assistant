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
Hunt Plan Evaluator (Markdown) – Evaluates 1..N hunt plan reports and compares them.
- Inputs: positional Markdown files
- Outputs (default: current directory):
  * console summary
  * JSON with the same data as console (single JSON object)
  * optional full JSON with all details
  * log file capturing console output
- Models: Configured via model_config.json (supports Azure, OpenAI, Anthropic, etc.)

Usage:
  hunt-plan-eval fileA.md [fileB.md ...] -c model_config.json
  [--output results.json] [--log eval.log] [--json-output full.json] [--no-json]
  [--raw] [-q]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path to import evaluation utilities
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import EvaluatorModelClient, load_environment

# Required sections for planner template conformance
REQUIRED_SECTIONS = [
    "Hypothesis",
    "Recommended Time Frame",
    "ABLE Table",
    "Data",
    "Hunt Procedure",
]


# ===================== Data Structures =====================
@dataclass
class MetricResult:
    score: float
    weight: float = 1.0
    details: Dict[str, Any] = field(default_factory=dict)
    feedback: str = ""
    confidence: float = 1.0


@dataclass
class PlanMetrics:
    filename: str
    metric_results: Dict[str, MetricResult] = field(default_factory=dict)
    total_score: float = 0.0

    def calculate_total_score(self) -> float:
        tw, tsum = 0.0, 0.0
        for res in self.metric_results.values():
            tsum += res.score * res.weight
            tw += res.weight
        self.total_score = (tsum / tw) if tw > 0 else 0.0
        return self.total_score


# ===================== Evaluator =====================
class HuntPlanEvaluator:
    def __init__(
        self,
        model_config_path: Path,
        quiet: bool = False,
        log_file: Optional[str] = None,
        json_output_file: Optional[str] = None,
        rich_mode: bool = False,
    ):
        self.model_client = EvaluatorModelClient(model_config_path)
        self.quiet = quiet
        self.log_file = log_file
        self.log_buffer = StringIO() if log_file else None
        self.json_output_file = json_output_file
        self.rich_mode = rich_mode
        self.console = None
        self._Markdown = None
        if self.rich_mode:
            try:
                # Import lazily so users without rich can still run without --rich
                from rich.console import Console  # type: ignore
                from rich.markdown import Markdown  # type: ignore
                self.console = Console()
                self._Markdown = Markdown
            except Exception:
                # Fallback to plain output if rich is unavailable
                self.rich_mode = False
                if not self.quiet:
                    print("Warning: rich is not installed. Falling back to plain console output.", file=sys.stderr)

        # Cache for extracted sections
        self.section_cache: Dict[str, str] = {}

        # Metric registry with weights and judge roles
        # Tier 1: 2.5 | Tier 2: 2.0 | Tier 3: 1.5 | Tier 4: 1.2
        self.metric_functions: Dict[str, Tuple[Any, str, float]] = {
            "technical_accuracy": (self.evaluate_technical_accuracy, "technical_accuracy", 2.5),                          # Tier 1
            "query_efficiency": (self.evaluate_query_efficiency, "query_efficiency", 2.5),                              # Tier 1
            "organization_progression": (self.evaluate_organization_progression, "organization_progression", 2.5),             # Tier 1
            "template_conformance": (self.evaluate_template_conformance, "template_conformance", 2.5),                     # Tier 1
            "hypothesis_alignment": (self.evaluate_hypothesis_alignment, "hypothesis_alignment", 2.0),                     # Tier 2
            "actionability_clarity": (self.evaluate_actionability_clarity, "actionability_clarity", 2.0),                   # Tier 2
            "environmental_integration": (self.evaluate_environmental_integration, "environmental_integration", 2.0),           # Tier 2
            "operational_practicality": (self.evaluate_operational_practicality, "operational_practicality", 1.5),             # Tier 3
            "comprehensiveness": (self.evaluate_comprehensiveness, "comprehensiveness", 1.2),                           # Tier 4
            "threat_intel_integration": (self.evaluate_threat_intel_integration, "threat_intel_integration", 1.2),             # Tier 4
        }

        # Collect model info for metadata
        model_info = {}
        for metric_name, (_, judge_role, _) in self.metric_functions.items():
            model_name = self.model_client.get_model_name(judge_role)
            provider = self.model_client.get_provider_type(judge_role)
            model_info[metric_name] = f"{provider}:{model_name}"

        # Full JSON object we can optionally save
        self.full_data: Dict[str, Any] = {
            "metadata": {
                "evaluation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model_config": str(model_config_path),
                "models_used": model_info,
                "files": [],
            },
            "evaluations": [],
            "comparison": {},
        }

    # --------------- Utilities ---------------
    def print_output(self, message: str = "", end: str = "\n") -> None:
        if self.log_buffer is not None:
            self.log_buffer.write(message + end)
        if not self.quiet:
            if self.rich_mode and self.console and self._Markdown:
                if message == "" and end == "\n":
                    # Blank line
                    self.console.print()
                else:
                    # Render message as Markdown
                    self.console.print(self._Markdown(message))
            else:
                print(message, end=end)

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
        judge_role: str,
        max_retries: int = 2,
        max_tokens: int = 700,
    ) -> Optional[Dict[str, Any]]:
        json_instructions = (
            "\n\nCRITICAL: Respond with ONLY a valid JSON object.\n"
            "Do NOT include any text outside the JSON.\n"
            "Start with { and end with }.\n"
            "Your JSON response:"
        )
        full_prompt = prompt + json_instructions

        for attempt in range(max_retries + 1):
            try:
                text = self.model_client.call_llm(
                    judge_role=judge_role,
                    prompt=full_prompt,
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
                return json.loads(text)
            except json.JSONDecodeError:
                if attempt < max_retries:
                    # Log retry but do not print to console
                    if self.log_buffer is not None:
                        self.log_buffer.write(
                            f"Retrying {metric_name} (attempt {attempt + 2}/{max_retries + 1})...\n"
                        )
                    full_prompt = (
                        prompt
                        + "\n\nRETRY: Previous response was not valid JSON. Return ONLY a JSON object like {\"score\": 50, \"feedback\": \"...\"}"
                        + json_instructions
                    )
            except Exception as e:
                if attempt == max_retries and self.log_buffer is not None:
                    self.log_buffer.write(
                        f"LLM API error for {metric_name}: {str(e)[:200]}\n"
                    )
        return None

    def extract_section_with_llm(
        self,
        report: str,
        section_name: str,
        section_description: str,
        variations: Optional[List[str]] = None,
    ) -> str:
        key = f"{hash(report)}::{section_name}"
        if key in self.section_cache:
            return self.section_cache[key]

        var_str = (
            ", ".join([f'"{v}"' for v in (variations or [])]) if variations else f'variations of "{section_name}"'
        )
        prompt = f"""
Extract the content of a specific section from this hunt plan (Markdown).

You are looking for the section that contains:
{section_description}

This section might be titled "{section_name}" or similar variations like:
{var_str}

Important:
- Look for headers # or ## followed by the name
- The section ends at the next header or end of document
- Return ONLY the section content (NOT the header)
- If not found, return exactly: SECTION_NOT_FOUND

Plan:
{report}

Return the extracted section content:
"""
        try:
            content = self.model_client.call_llm(
                judge_role="section_extractor",
                prompt=prompt,
                max_tokens=3000,
                temperature=0.0,
            )
            if content == "SECTION_NOT_FOUND":
                content = ""
            self.section_cache[key] = content
            return content
        except Exception:
            self.section_cache[key] = ""
            return ""

    # --------------- Metrics ---------------
    def evaluate_template_conformance(self, report: str) -> MetricResult:
        details = {"sections_found": [], "missing_sections": [], "tables_ok": {}, "formatting_ok": True}
        for sec in REQUIRED_SECTIONS:
            pattern = rf"^##?\s+{re.escape(sec)}\s*$"
            if re.search(pattern, report, re.MULTILINE | re.IGNORECASE):
                details["sections_found"].append(sec)
            else:
                details["missing_sections"].append(sec)

        # Basic table formatting check for ABLE/Data (look for pipe usage within section)
        def section_body(name: str) -> str:
            m = re.search(rf"^##?\s+{re.escape(name)}\s*\n(.*?)(?=^##?\s+|\Z)", report, re.MULTILINE | re.IGNORECASE | re.DOTALL)
            return (m.group(1) if m else "").strip()

        for tabsec in ["ABLE Table", "Data"]:
            body = section_body(tabsec)
            details["tables_ok"][tabsec] = bool(body and ("|" in body))

        missing_penalty = len(details["missing_sections"]) * 20
        table_penalty = 0
        for tabsec in ["ABLE Table", "Data"]:
            if not details["tables_ok"][tabsec]:
                table_penalty += 10
        score = max(0, 100 - missing_penalty - table_penalty)

        feedback = f"Found {len(details['sections_found'])}/{len(REQUIRED_SECTIONS)} required sections."
        if details["missing_sections"]:
            feedback += f" Missing: {', '.join(details['missing_sections'])}."
        if table_penalty:
            feedback += " Table formatting issues detected."
        return MetricResult(score=score, details=details, feedback=feedback, confidence=1.0)

    def evaluate_organization_progression(self, report: str) -> MetricResult:
        # Prefer analyzing Hunt Procedure
        hunt_proc = self.extract_section_with_llm(
            report,
            "Hunt Procedure",
            "numbered, ordered steps of the investigation with dependencies and branching",
            variations=["Procedure", "Investigation Steps"],
        ) or report

        prompt = f"""
Evaluate the organization and logical progression of this hunt procedure.

Focus on:
- progressive refinement (validation → detection → investigation)
- explicit dependencies
- logical flow
- building complexity

Hunt Procedure:
{hunt_proc[:4000]}

Respond with ONLY JSON:
{{
  "score": 80,
  "progressive_refinement": true,
  "explicit_dependencies": true,
  "logical_flow": true,
  "building_complexity": true,
  "issues": ["example"],
  "feedback": "...",
  "confidence": 0.9
}}"""
        result = self.evaluate_with_llm_retry(prompt, "organization_progression", "organization_progression")
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.85),
            )
        # Fallback heuristic
        step_markers = len(re.findall(r"^(?:\d+\.|- )", hunt_proc, re.MULTILINE))
        has_validation = bool(re.search(r"validation|baseline", hunt_proc, re.IGNORECASE))
        has_detection = bool(re.search(r"detect|detection", hunt_proc, re.IGNORECASE))
        has_investigation = bool(re.search(r"investigat|pivot|enrich", hunt_proc, re.IGNORECASE))
        score = min(100, 30 + step_markers * 5 + (20 if has_validation else 0) + (25 if has_detection else 0) + (25 if has_investigation else 0))
        return MetricResult(score=score, feedback="Fallback progression heuristic", confidence=0.3)

    def evaluate_technical_accuracy(self, report: str) -> MetricResult:
        data_section = self.extract_section_with_llm(
            report,
            "Data",
            "relevant Splunk indices, sourcetypes, key fields and their relevance",
            variations=["Data Sources", "Relevant Data"],
        )
        hunt_proc = self.extract_section_with_llm(
            report,
            "Hunt Procedure",
            "detailed steps including specific SPL queries and filters",
            variations=["Procedure", "Investigation Steps"],
        ) or report

        prompt = f"""
Evaluate technical ACCURACY of SPL queries and data usage.

Focus ONLY on:
- syntax correctness
- absence of hallucinated SPL commands
- correctness of field names for given sourcetypes (if you know them)
- alignment of index/sourcetype to the described data (if you know them)

If you have no information about indices, sourcetypes, or field names,
assume they are correct.

Data section (for reference):
{data_section[:2000] if data_section else "(none)"}

Hunt Procedure (queries to assess):
{hunt_proc[:4000]}

Respond with ONLY JSON:
{{
  "score": 85,
  "syntax_errors": 0,
  "hallucinated_cmds": 0,
  "field_name_mismatches": 0,
  "index_sourcetype_alignment": true,
  "specific_errors": ["example"],
  "feedback": "...",
  "confidence": 0.9
}}"""
        result = self.evaluate_with_llm_retry(prompt, "technical_accuracy", "technical_accuracy", max_tokens=900)
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.85),
            )
        # Fallback heuristic
        code_blocks = re.findall(r"```[\s\S]*?```", hunt_proc)
        index_mentions = len(re.findall(r"index=", hunt_proc, re.IGNORECASE))
        sourcetype_mentions = len(re.findall(r"sourcetype=", hunt_proc, re.IGNORECASE))
        score = min(100, 30 + len(code_blocks) * 8 + (5 if index_mentions > 0 else 0) + (5 if sourcetype_mentions > 0 else 0))
        return MetricResult(score=score, feedback="Fallback technical accuracy heuristic", confidence=0.3)

    def evaluate_query_efficiency(self, report: str) -> MetricResult:
        hunt_proc = self.extract_section_with_llm(
            report,
            "Hunt Procedure",
            "detailed steps including specific SPL queries and filters",
            variations=["Procedure", "Investigation Steps"],
        ) or report

        prompt = f"""
Evaluate QUERY EFFICIENCY for large Splunk datasets.

Focus on:
- appropriate use of tstats
- practical filtering for billion-row datasets
  (time scoping, index/sourcetype scoping, selective fields)
- avoidance of heavy/expensive patterns
  (unbounded join/transaction/subsearch)
- general performance-aware patterns

Hunt Procedure (queries to assess):
{hunt_proc[:4000]}

Respond with ONLY JSON:
{{
  "score": 85,
  "tstats_usage": "appropriate|overused|underused|not_applicable",
  "large_data_filtering": true,
  "inefficient_patterns": ["example"],
  "heavy_commands": ["join", "transaction"],
  "index_scoping": true,
  "sourcetype_scoping": true,
  "time_scoping": true,
  "feedback": "...",
  "confidence": 0.9
}}"""
        result = self.evaluate_with_llm_retry(prompt, "query_efficiency", "query_efficiency", max_tokens=900)
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.85),
            )
        # Fallback heuristic
        tstats_mentions = len(re.findall(r"\btstats\b", hunt_proc, re.IGNORECASE))
        index_mentions = len(re.findall(r"index=", hunt_proc, re.IGNORECASE))
        sourcetype_mentions = len(re.findall(r"sourcetype=", hunt_proc, re.IGNORECASE))
        time_scoping = len(re.findall(r"earliest=|latest=", hunt_proc, re.IGNORECASE))
        score = min(100, 25 + (15 if tstats_mentions > 0 else 0) + (15 if index_mentions > 0 else 0) + (15 if sourcetype_mentions > 0 else 0) + (15 if time_scoping > 0 else 0))
        return MetricResult(score=score, feedback="Fallback query efficiency heuristic", confidence=0.3)

    def evaluate_hypothesis_alignment(self, report: str) -> MetricResult:
        hypothesis = self.extract_section_with_llm(
            report,
            "Hypothesis",
            "the restated hunting hypothesis to be tested",
            variations=["Hunting Hypothesis", "Restated Hypothesis"],
        )
        hunt_proc = self.extract_section_with_llm(
            report,
            "Hunt Procedure",
            "detailed steps of validation, detection, and investigation",
            variations=["Procedure", "Investigation Steps"],
        ) or report

        prompt = f"""
Evaluate alignment to the hypothesis.

Check:
- complete coverage of the hypothesis
- relevance of each step to testing it
- absence of critical gaps

Hypothesis section:
{hypothesis[:1500] if hypothesis else "(none)"}

Hunt Procedure:
{hunt_proc[:3000]}

Respond with ONLY JSON:
{{
  "score": 80,
  "complete_coverage": true,
  "step_relevance": true,
  "critical_gap_detected": false,
  "cited_alignment_evidence": ["example"],
  "feedback": "...",
  "confidence": 0.85
}}"""
        result = self.evaluate_with_llm_retry(prompt, "hypothesis_alignment", "hypothesis_alignment")
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.85),
            )
        # Fallback heuristic
        has_hypo = bool(hypothesis)
        refers = bool(re.search(r"hypoth|this hunt|we test", hunt_proc, re.IGNORECASE))
        score = 70 if has_hypo and refers else (40 if has_hypo else 20)
        return MetricResult(score=score, feedback="Fallback hypothesis heuristic", confidence=0.3)

    def evaluate_actionability_clarity(self, report: str) -> MetricResult:
        hunt_proc = self.extract_section_with_llm(
            report,
            "Hunt Procedure",
            "detailed numbered steps with executable queries and interpretation guidance",
            variations=["Procedure", "Investigation Steps"],
        ) or report

        prompt = f"""
Evaluate actionability and clarity.

Check:
- queries runnable as-is
- unambiguous interpretation guidance
- specific thresholds
- clear decision points/branches

Hunt Procedure:
{hunt_proc[:4000]}

Respond with ONLY JSON:
{{
  "score": 80,
  "executable_queries": true,
  "clear_interpretation": true,
  "thresholds_present": true,
  "decision_points_present": true,
  "feedback": "...",
  "confidence": 0.85
}}"""
        result = self.evaluate_with_llm_retry(prompt, "actionability_clarity", "actionability_clarity")
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.85),
            )
        # Fallback heuristic
        code_blocks = re.findall(r"```[\s\S]*?```", hunt_proc)
        has_threshold = bool(re.search(r">\s*\d+|\b(\d+\s*(?:minutes|hours|days))\b", hunt_proc, re.IGNORECASE))
        has_if = bool(re.search(r"\bif\b|\bthen\b|\belse\b", hunt_proc, re.IGNORECASE))
        score = min(100, 30 + len(code_blocks) * 10 + (15 if has_threshold else 0) + (15 if has_if else 0))
        return MetricResult(score=score, feedback="Fallback actionability heuristic", confidence=0.3)

    def evaluate_environmental_integration(self, report: str) -> MetricResult:
        # We only have plan text; look for concrete use of local context, allowlists, baselines, links
        prompt = f"""
Evaluate environmental integration.

Check:
- use of provided local context
- known-good exclusions/allowlisting
- references to documentation/baselines/ticketing
- asset prioritization when specified

Full plan:
{report[:5000]}

Respond with ONLY JSON:
{{
  "score": 75,
  "local_context_used": true,
  "known_good_exclusions": true,
  "resource_references_present": true,
  "asset_prioritization": true,
  "feedback": "...",
  "confidence": 0.8
}}"""
        result = self.evaluate_with_llm_retry(prompt, "environmental_integration", "environmental_integration")
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.8),
            )
        # Fallback heuristic
        hints = [
            bool(re.search(r"allowlist|known-good|baseline", report, re.IGNORECASE)),
            bool(re.search(r"ticket|jira|servicenow|runbook|playbook|kb|doc", report, re.IGNORECASE)),
            bool(re.search(r"critical system|high value|crown jewel|domain controller", report, re.IGNORECASE)),
        ]
        score = 40 + 20 * sum(1 for h in hints if h)
        return MetricResult(score=score, feedback="Fallback env integration heuristic", confidence=0.3)

    def evaluate_operational_practicality(self, report: str) -> MetricResult:
        timeframe = self.extract_section_with_llm(
            report,
            "Recommended Time Frame",
            "the time window recommended for the hunt",
            variations=["Timeframe", "Time Window"],
        )
        prompt = f"""
Evaluate operational practicality.

Check:
- appropriate time window for the threat
- data volume awareness and scoping
- incremental tuning guidance
- documentation path for findings

Recommended Time Frame:
{timeframe[:1500] if timeframe else "(none)"}

Full plan (for context):
{report[:4000]}

Respond with ONLY JSON:
{{
  "score": 75,
  "timeframe_fit": true,
  "data_volume_awareness": true,
  "incremental_tuning": true,
  "documentation_path": true,
  "feedback": "...",
  "confidence": 0.8
}}"""
        result = self.evaluate_with_llm_retry(prompt, "operational_practicality", "operational_practicality")
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.8),
            )
        # Fallback heuristic
        has_time_words = bool(re.search(r"\b(\d+\s*(minutes|hours|days|weeks|months))\b|previous \d+", report, re.IGNORECASE))
        has_scoping = bool(re.search(r"earliest=|latest=|index=|sourcetype=|tstats", report, re.IGNORECASE))
        score = 60 + (15 if has_time_words else 0) + (15 if has_scoping else 0)
        return MetricResult(score=score, feedback="Fallback operational heuristic", confidence=0.3)

    def evaluate_comprehensiveness(self, report: str) -> MetricResult:
        prompt = f"""
Evaluate overall comprehensiveness.

Check:
- ABLE utilization
- appropriate use of available data sources
- depth of investigation (enrichment/context)
- actionable remediation guidance

Full plan:
{report[:5000]}

Respond with ONLY JSON:
{{
  "score": 80,
  "able_utilization": true,
  "data_source_usage_quality": "strong|adequate|weak",
  "investigation_depth": "deep|moderate|shallow",
  "remediation_guidance": true,
  "feedback": "...",
  "confidence": 0.8
}}"""
        result = self.evaluate_with_llm_retry(prompt, "comprehensiveness", "comprehensiveness")
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.8),
            )
        # Fallback heuristic
        has_able = bool(re.search(r"##\s*ABLE Table", report, re.IGNORECASE))
        has_data = bool(re.search(r"##\s*Data", report, re.IGNORECASE))
        has_proc = bool(re.search(r"##\s*Hunt Procedure", report, re.IGNORECASE))
        score = 50 + (10 if has_able else 0) + (10 if has_data else 0) + (10 if has_proc else 0)
        return MetricResult(score=score, feedback="Fallback comprehensiveness heuristic", confidence=0.3)

    def evaluate_threat_intel_integration(self, report: str) -> MetricResult:
        prompt = f"""
Evaluate threat intelligence integration.

Check:
- actor TTPs when actor specified
- technique variations
- modern patterns/methodologies
- mapping of expected evidence to data sources

Full plan:
{report[:5000]}

Respond with ONLY JSON:
{{
  "score": 70,
  "actor_ttps_used": true,
  "technique_variations": true,
  "modern_patterns": true,
  "evidence_mapping_quality": "strong|adequate|weak",
  "feedback": "...",
  "confidence": 0.8
}}"""
        result = self.evaluate_with_llm_retry(prompt, "threat_intel_integration", "threat_intel_integration")
        if result:
            return MetricResult(
                score=result.get("score", 0),
                details={k: v for k, v in result.items() if k not in ("score", "feedback", "confidence")},
                feedback=result.get("feedback", ""),
                confidence=result.get("confidence", 0.8),
            )
        # Fallback heuristic
        hints = [
            bool(re.search(r"T\d{4}(?:\.\d{3})?", report)),
            bool(re.search(r"MITRE|ATT&CK|APT|actor|campaign", report, re.IGNORECASE)),
            bool(re.search(r"variant|variation|modern|trend", report, re.IGNORECASE)),
        ]
        score = 40 + 20 * sum(1 for h in hints if h)
        return MetricResult(score=score, feedback="Fallback threat intel heuristic", confidence=0.3)

    # --------------- Orchestration ---------------
    def evaluate_plan(self, report_text: str, filename: str) -> Tuple[PlanMetrics, str]:
        # Clear section cache per plan
        self.section_cache.clear()
        metrics = PlanMetrics(filename=filename)

        # Build Markdown table for this file
        md_lines: List[str] = [f"## Evaluating: {filename}", "", "| Metric | Score | Weight | Feedback |", "| :-- | --: | --: | :-- |"]

        for name, (func, judge_role, weight) in self.metric_functions.items():
            try:
                res: MetricResult = func(report_text)
                res.weight = weight
                metrics.metric_results[name] = res
                metric_cell = (name or "").replace("|", "\\|")
                weight_cell = f"x{weight}"
                fb_cell = (res.feedback or "").replace("|", "\\|")
                fb_cell = " ".join(fb_cell.splitlines()).strip()
                md_lines.append(f"| {metric_cell} | {res.score:.1f} | {weight_cell} | {fb_cell} |")
            except Exception as e:
                res = MetricResult(score=0, weight=weight, feedback=f"Evaluation failed: {e}", confidence=0)
                metrics.metric_results[name] = res
                metric_cell = (name or "").replace("|", "\\|")
                err_cell = (str(e) or "").replace("|", "\\|")
                err_cell = " ".join(err_cell.splitlines()).strip()
                md_lines.append(f"| {metric_cell} | ERROR | x{weight} | {err_cell} |")

        metrics.calculate_total_score()
        md_lines += ["", f"**TOTAL SCORE:** {metrics.total_score:.1f}"]
        return metrics, "\n".join(md_lines)

    def process_files(self, files: List[str], output_file: str) -> None:
        # Populate metadata
        self.full_data["metadata"]["files"] = [{"path": os.path.abspath(p), "name": os.path.basename(p)} for p in files]

        # Prepare progress bar (tqdm optional)
        tqdm = None
        try:
            from tqdm.auto import tqdm as _tqdm  # type: ignore
            tqdm = _tqdm
        except Exception:
            if not self.quiet:
                self.print_output("(Tip: install tqdm for a progress bar: pip install tqdm)")

        # Evaluate all, accumulate Markdown sections
        metrics_list: List[PlanMetrics] = []
        sections: List[str] = []
        pbar = None
        if tqdm and not self.quiet:
            pbar = tqdm(total=len(files), desc="Evaluating plans", dynamic_ncols=True)

        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                self.print_output(f"Error reading {path}: {e}")
                if pbar:
                    pbar.update(1)
                continue

            m, md_section = self.evaluate_plan(content, os.path.basename(path))

            # Append detailed metrics to full JSON
            self.full_data["evaluations"].append({
                "file": m.filename,
                "total_score": m.total_score,
                "metrics": {
                    k: {
                        "score": v.score,
                        "weight": v.weight,
                        "feedback": v.feedback,
                        "confidence": v.confidence,
                        "details": v.details,
                    } for k, v in m.metric_results.items()
                },
                "metric_scores": {k: v.score for k, v in m.metric_results.items()},
            })
            metrics_list.append(m)
            sections.append(md_section)

            if pbar:
                pbar.update(1)

        if pbar:
            pbar.close()

        # Comparison logic
        comparison_json: Dict[str, Any] = {}
        comparison_md_lines: List[str] = []
        if len(metrics_list) >= 2:
            # Rank by score desc
            rankings = sorted([(m.filename, m.total_score) for m in metrics_list], key=lambda x: x[1], reverse=True)
            winner = rankings[0][0]
            comparison_json["winner"] = winner
            comparison_json["rankings"] = [{"file": f, "total_score": s} for f, s in rankings]

            # Score diff vs runner-up
            if len(rankings) > 1:
                comparison_json["score_diff"] = round(rankings[0][1] - rankings[1][1], 2)
            else:
                comparison_json["score_diff"] = None

            # Average confidence (winner's metrics)
            winner_metrics = next(m for m in metrics_list if m.filename == winner)
            winner_confidences = [res.confidence for res in winner_metrics.metric_results.values()]
            comparison_json["confidence"] = round(sum(winner_confidences) / len(winner_confidences), 3) if winner_confidences else 0.0

            # Differences vs winner per competitor
            diffs: Dict[str, Any] = {}
            all_diff_msgs: List[Tuple[float, str]] = []
            for other in metrics_list:
                if other.filename == winner:
                    continue
                diff_entry = {"score_diff": round(other.total_score - winner_metrics.total_score, 2), "better_metrics": [], "worse_metrics": [], "roughly_equal": []}
                for metric_name in self.metric_functions.keys():
                    w_score = winner_metrics.metric_results[metric_name].score
                    o_score = other.metric_results[metric_name].score
                    d = o_score - w_score
                    if abs(d) < 3:
                        diff_entry["roughly_equal"].append(metric_name)
                    elif d > 0:
                        diff_entry["better_metrics"].append({"metric": metric_name, "diff": round(d, 1)})
                        all_diff_msgs.append((abs(d), f"{metric_name}: {other.filename} better by {abs(d):.1f}"))
                    else:
                        diff_entry["worse_metrics"].append({"metric": metric_name, "diff": round(-d, 1)})
                        all_diff_msgs.append((abs(d), f"{metric_name}: {winner} better than {other.filename} by {abs(d):.1f}"))
                diffs[other.filename] = diff_entry
            comparison_json["differences_vs_winner"] = diffs

            # Key differences (top 5 by absolute gap across competitors)
            all_diff_msgs.sort(key=lambda x: x[0], reverse=True)
            comparison_json["key_differences"] = [msg for _, msg in all_diff_msgs[:5]]

            # Build comparison Markdown
            comparison_md_lines.append("## Comparison")
            comparison_md_lines.append("")
            comparison_md_lines.append(f"**Winner:** {winner}")
            comparison_md_lines.append("")
            comparison_md_lines.append("### Rankings")
            comparison_md_lines.append("| File | Total Score |")
            comparison_md_lines.append("| :-- | --: |")
            for f, s in rankings:
                comparison_md_lines.append(f"| {f.replace('|','\\|')} | {s:.1f} |")
            if comparison_json.get("key_differences"):
                comparison_md_lines.append("")
                comparison_md_lines.append("### Key differences")
                for msg in comparison_json["key_differences"]:
                    comparison_md_lines.append(f"- {msg}")
        else:
            # Single-file mode – leave comparison blank fields to keep schema stable
            comparison_json["winner"] = None
            comparison_json["rankings"] = (
                [{"file": metrics_list[0].filename, "total_score": metrics_list[0].total_score}] if metrics_list else []
            )
            comparison_json["score_diff"] = None
            comparison_json["confidence"] = (
                round(sum(res.confidence for res in metrics_list[0].metric_results.values()) / len(metrics_list[0].metric_results), 3)
                if metrics_list else 0.0
            )
            comparison_json["differences_vs_winner"] = {}
            comparison_json["key_differences"] = []

        # Render Markdown once at the end (rich if enabled)
        if sections:
            final_md_lines: List[str] = ["# Hunt Plan Evaluation", ""]
            final_md_lines.extend(sections)
            if comparison_md_lines:
                final_md_lines.append("")
                final_md_lines.extend(comparison_md_lines)
            final_md = "\n".join(final_md_lines)
            self.print_output(final_md)

        # Save combined result JSON (single object)
        self.full_data["comparison"] = comparison_json
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.full_data, f, indent=2)
        self.print_output(f"\nResults written to: {output_file}")

        # Save optional artifacts
        self.save_log_file()
        self.save_json_output()


# ===================== CLI =====================

def main() -> int:
    # Load environment variables from .env file
    load_environment()
    
    ap = argparse.ArgumentParser(description="Evaluate and compare hunt plan Markdown files")
    ap.add_argument("files", nargs="+", help="One or more Markdown files to evaluate")
    ap.add_argument("-c", "--model-config", type=Path, required=True, help="Path to model_config.json")
    ap.add_argument("--output", default="hunt-plan-compare.json", help="Output JSON file (single object)")
    ap.add_argument("--log", default="hunt-plan-compare.log", help="Log file capturing console output")
    ap.add_argument("-j", "--json-output", default="hunt-plan-compare.full.json", help="Full JSON with complete evaluation details")
    ap.add_argument("--no-json", action="store_true", help="Disable saving the full JSON details file")
    ap.add_argument("--raw", action="store_true", help="Print raw Markdown instead of rendering it")
    ap.add_argument("-q", "--quiet", action="store_true", help="Quiet mode (no console output)")
    args = ap.parse_args()

    if not args.files:
        print("Error: at least one Markdown file is required", file=sys.stderr)
        return 1

    # Verify files exist
    missing = [p for p in args.files if not os.path.exists(p)]
    if missing:
        print(f"Error: missing files: {', '.join(missing)}", file=sys.stderr)
        return 1

    # Verify model config exists
    if not args.model_config.exists():
        print(f"Error: model_config.json not found at {args.model_config}", file=sys.stderr)
        return 1

    # Determine full JSON setting
    json_output_file = None if args.no_json else args.json_output

    try:
        evaluator = HuntPlanEvaluator(
            model_config_path=args.model_config,
            quiet=args.quiet,
            log_file=args.log,
            json_output_file=json_output_file,
            rich_mode=(not args.raw),
        )

        # Route print_output through evaluator so logs are captured
        evaluator.process_files(args.files, args.output)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
