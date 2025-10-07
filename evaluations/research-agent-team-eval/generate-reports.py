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
Generate threat hunting research reports for a set of topics using the
`research-assistant` CLI, and aggregate outputs into a JSONL file.

Features:
- Reads topics from an input file (-i), skipping blank lines and comments (#...)
- Runs `research-assistant -t "<topic>" -s` in the current working directory
- Retries failures up to --max-retries with exponential backoff
- Treats non-zero exit, traceback, or missing saved filename as failure
- On success, renames/moves the generated file to <output>/<sanitized_topic>.md
- Appends a JSON line per success to <output>/<basename(output)>.json
- Skips writing JSON lines for failures and for already-existing outputs (unless --force)
- Sequential execution with per-attempt timeout (default 15 minutes)
- Per-topic logs written to stdout and to <output>/logs/
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional


def sanitize_filename(name: str, max_len: int = 200) -> str:
    s = name.strip()
    # Replace path separators
    s = s.replace(os.sep, "_")
    if os.altsep:
        s = s.replace(os.altsep, "_")
    # Remove control characters; allow common safe set
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._()-")
    s = "".join(ch if (ch in allowed) else "_" for ch in s if ch.isprintable())
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        s = "report"
    # Truncate
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def short_slug(name: str, max_len: int = 40) -> str:
    s = sanitize_filename(name)
    s = s.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9._-]", "-", s)
    return s[:max_len]


def parse_saved_filename(output_text: str) -> Optional[str]:
    # Look for: Report saved as <filename>.md
    # Accept optional quotes
    if not output_text:
        return None
    lines = [ln.strip() for ln in output_text.splitlines() if ln.strip()]
    for ln in reversed(lines):
        m = re.search(r"Report saved as\s+[\"']?(.+?\.md)[\"']?$", ln)
        if m:
            return m.group(1)
    return None


def run_assistant(topic: str, assistant_cmd: str, timeout_seconds: int) -> Tuple[bool, Optional[str], str, str, Optional[str]]:
    cmd = [assistant_cmd, "-t", topic, "-s"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = stdout + ("\n[stderr]\n" + stderr if stderr else "")
        if proc.returncode != 0:
            return False, None, stdout, stderr, f"non-zero exit {proc.returncode}"
        if "Traceback (most recent call last)" in combined:
            return False, None, stdout, stderr, "traceback detected"
        if "Report:\nno report generated" in combined:
            return False, None, stdout, stderr, "no report generated"
        saved = parse_saved_filename(stdout) or parse_saved_filename(combined)
        if not saved:
            return False, None, stdout, stderr, "could not parse saved filename"
        return True, saved, stdout, stderr, None
    except subprocess.TimeoutExpired as e:
        # Capture partial outputs if available
        stdout = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode(errors="ignore") if e.stdout else "")
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode(errors="ignore") if e.stderr else "")
        return False, None, stdout, stderr, "timeout"


def read_topics(path: Path) -> List[str]:
    topics: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            topics.append(raw)
    return topics


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def append_jsonl(jsonl_path: Path, record: dict) -> None:
    with jsonl_path.open("a", encoding="utf-8") as jf:
        jf.write(json.dumps(record, ensure_ascii=False) + "\n")
        jf.flush()
        os.fsync(jf.fileno())


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate research reports for topics and build a JSONL of results.")
    ap.add_argument("-i", "--input", required=True, help="Path to topics file (one topic per line)")
    ap.add_argument("-o", "--output", required=True, help="Output directory for reports and JSONL")
    ap.add_argument("--assistant-cmd", default="research-assistant", help="Command to invoke research assistant")
    ap.add_argument("--max-retries", type=int, default=5, help="Max retries on failure (in addition to the initial attempt)")
    ap.add_argument("--retry-wait", type=int, default=60, help="Base wait seconds before retry (exponential backoff)")
    ap.add_argument("--backoff-factor", type=float, default=2.0, help="Backoff multiplier between retries (exponential)")
    ap.add_argument("--timeout-seconds", type=int, default=900, help="Per-attempt timeout in seconds (default 15 minutes)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing report files if present")
    args = ap.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    ensure_dir(output_dir)
    logs_dir = output_dir / "logs"
    ensure_dir(logs_dir)

    backend = output_dir.name  # basename
    jsonl_path = output_dir / f"{backend}.json"

    topics = read_topics(input_path)
    total = len(topics)

    print(f"[INFO] Starting generation for {total} topics. Output: {output_dir}")
    print(f"[INFO] JSONL: {jsonl_path} (append-only)")
    print(f"[INFO] Retries: {args.max_retries}, base-wait: {args.retry_wait}s, backoff-factor: {args.backoff_factor}, per-attempt timeout: {args.timeout_seconds}s")
    print(f"[INFO] Backend: {backend}\n")
    sys.stdout.flush()

    successes: List[str] = []
    failures: List[Tuple[str, str]] = []  # (topic, reason)
    skipped_existing: List[str] = []

    for idx, topic in enumerate(topics, start=1):
        safe_name = sanitize_filename(topic)
        dest_path = output_dir / f"{safe_name}.md"
        topic_slug = short_slug(topic)
        log_path = logs_dir / f"{idx:04d}_{topic_slug}.log"

        # Skip if exists and not forcing
        if dest_path.exists() and not args.force:
            print(f"[{idx}/{total}] SKIP_EXISTS: {topic} -> {dest_path}")
            skipped_existing.append(topic)
            sys.stdout.flush()
            continue

        print(f"[{idx}/{total}] START: {topic}")
        sys.stdout.flush()

        attempts = args.max_retries + 1  # initial + retries
        success = False
        last_reason: Optional[str] = None
        saved_path: Optional[Path] = None

        # (Re)create/clear log file
        with log_path.open("w", encoding="utf-8") as lf:
            lf.write(f"Topic: {topic}\n")
            lf.write(f"Started: {datetime.now().isoformat()}\n")
            lf.write(f"Assistant: {args.assistant_cmd}\n")
            lf.write(f"Timeout: {args.timeout_seconds}s, Retries: {args.max_retries}, BaseWait: {args.retry_wait}s, Factor: {args.backoff_factor}\n\n")

        for attempt in range(1, attempts + 1):
            print(f"[{idx}/{total}] Attempt {attempt}/{attempts}: running assistant...")
            sys.stdout.flush()
            ok, saved, stdout_text, stderr_text, reason = run_assistant(
                topic=topic,
                assistant_cmd=args.assistant_cmd,
                timeout_seconds=args.timeout_seconds,
            )
            # Write per-attempt logs
            with log_path.open("a", encoding="utf-8") as lf:
                lf.write(f"==== Attempt {attempt} ====" + "\n")
                lf.write("-- STDOUT --\n")
                lf.write(stdout_text or "")
                lf.write("\n-- STDERR --\n")
                lf.write(stderr_text or "")
                lf.write("\n-- RESULT --\n")
                lf.write(("SUCCESS" if ok else f"FAIL: {reason}") + "\n\n")

            # Also print logs to stdout as requested
            print(f"[{idx}/{total}] Attempt {attempt} STDOUT:\n{stdout_text}")
            if stderr_text:
                print(f"[{idx}/{total}] Attempt {attempt} STDERR:\n{stderr_text}")
            sys.stdout.flush()

            if ok and saved is not None:
                # Resolve saved path
                p = Path(saved)
                if not p.is_absolute():
                    p = (Path.cwd() / p).resolve()
                if not p.exists():
                    last_reason = f"saved file not found: {p}"
                    ok = False
                else:
                    saved_path = p
                    success = True
                    break
            # Failure path
            last_reason = reason or "unknown failure"
            if attempt < attempts:
                # Exponential backoff
                backoff_mult = args.backoff_factor ** (attempt - 1)
                wait_seconds = int(args.retry_wait * backoff_mult)
                print(f"[{idx}/{total}] RETRY in {wait_seconds}s (reason: {last_reason})")
                sys.stdout.flush()
                time.sleep(max(0, wait_seconds))
            else:
                print(f"[{idx}/{total}] FAILED after {attempts} attempts (reason: {last_reason})")
                sys.stdout.flush()

        if not success:
            failures.append((topic, last_reason or "unknown"))
            continue

        # Move/rename to destination
        try:
            ensure_dir(dest_path.parent)
            if dest_path.exists() and args.force:
                dest_path.unlink()
            shutil.move(str(saved_path), str(dest_path))
        except Exception as e:
            failures.append((topic, f"move failed: {e}"))
            print(f"[{idx}/{total}] ERROR moving file to {dest_path}: {e}")
            sys.stdout.flush()
            continue

        # Read, encode, and append JSONL
        try:
            with dest_path.open("r", encoding="utf-8") as rf:
                content = rf.read()
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            record = {
                "topic": topic,
                "backend": backend,
                "report": encoded,
            }
            append_jsonl(jsonl_path, record)
        except Exception as e:
            failures.append((topic, f"jsonl write failed: {e}"))
            print(f"[{idx}/{total}] ERROR writing JSONL for {topic}: {e}")
            sys.stdout.flush()
            continue

        successes.append(topic)
        print(f"[{idx}/{total}] SUCCESS: {topic} -> {dest_path}")
        sys.stdout.flush()

    # Summary
    print("\n[SUMMARY]")
    print(f"Successes: {len(successes)}")
    for t in successes:
        print(f"  - {t}")
    print(f"Skipped (existing): {len(skipped_existing)}")
    for t in skipped_existing:
        print(f"  - {t}")
    print(f"Failures: {len(failures)}")
    for t, r in failures:
        print(f"  - {t}: {r}")
    sys.stdout.flush()

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
