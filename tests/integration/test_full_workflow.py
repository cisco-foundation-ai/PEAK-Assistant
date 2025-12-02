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
End-to-end workflow test script exercising all PEAK Assistant agents.
Tests the complete threat hunting workflow: Research → Local Data → 
Hypothesis → Refinement → ABLE → Data Discovery → Hunt Plan
"""

import argparse
import subprocess
import tempfile
import shutil
import os
import sys
import time
import shlex
from pathlib import Path


def run_command(cmd, description, output_file=None):
    """Execute command and optionally save output to file."""
    print(f"\n{'='*60}")
    print(f"Step: {description}")
    print(f"Command: {' '.join(shlex.quote(arg) for arg in cmd)}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ ERROR: {description} failed")
        print(f"STDERR: {result.stderr}")
        if result.stdout:
            print(f"STDOUT: {result.stdout}")
        return None
    
    output = result.stdout
    
    # Show preview of output
    if output:
        preview_len = min(500, len(output))
        print(f"Output preview ({preview_len} chars):\n{output[:preview_len]}")
        if len(output) > preview_len:
            print("...")
        print()
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(output)
        print(f"✅ Saved to: {output_file}\n")
    
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Run end-to-end workflow test for all PEAK Assistant agents"
    )
    parser.add_argument(
        "hunt_topic",
        help="The hunt topic/technique to research (e.g., 'PowerShell Empire')"
    )
    parser.add_argument(
        "-c", "--local-context",
        help="Path to local context file",
        default=None
    )
    parser.add_argument(
        "-e", "--environment",
        help="Path to .env file",
        default=None
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output for all agents"
    )
    parser.add_argument(
        "--temp-dir",
        help="Directory where temporary files will be created (default: system temp)",
        default=None
    )
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Keep temporary files after test completion (default: cleanup on success)"
    )
    args = parser.parse_args()
    
    # Create temporary directory
    if args.temp_dir:
        # User-specified location
        base_dir = Path(args.temp_dir)
        if not base_dir.exists():
            print(f"Error: Specified temp directory '{args.temp_dir}' does not exist")
            return 1
        if not base_dir.is_dir():
            print(f"Error: '{args.temp_dir}' is not a directory")
            return 1
        
        # Create subdirectory with unique name
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        temp_dir = base_dir / f"peak_workflow_{timestamp}_{os.getpid()}"
        temp_dir.mkdir(parents=True, exist_ok=False)
        temp_dir = str(temp_dir)
    else:
        # Use system temp directory
        temp_dir = tempfile.mkdtemp(prefix="peak_workflow_test_")
    
    print(f"🔧 Working directory: {temp_dir}\n")
    
    cleanup_needed = True
    try:
        # File paths
        research_file = os.path.join(temp_dir, "research_report.md")
        local_data_file = os.path.join(temp_dir, "local_data_report.md")
        hypotheses_file = os.path.join(temp_dir, "hypotheses.txt")
        hypothesis_file = os.path.join(temp_dir, "selected_hypothesis.txt")
        refined_hypothesis_file = os.path.join(temp_dir, "refined_hypothesis.txt")
        able_file = os.path.join(temp_dir, "able_table.txt")
        data_discovery_file = os.path.join(temp_dir, "data_discovery.txt")
        hunt_plan_file = os.path.join(temp_dir, "hunt_plan.md")
        
        # Common arguments
        env_arg = ["-e", args.environment] if args.environment else []
        context_arg = ["-c", args.local_context] if args.local_context else []
        verbose_arg = ["-v"] if args.verbose else []
        
        # Step 1: Research (Internet)
        cmd = [
            "uv", "run", "-m", "peak_assistant.research_assistant",
            "-t", args.hunt_topic,
            "--no-feedback",
            "--format", "markdown"
        ] + env_arg + context_arg + verbose_arg
        
        research_output = run_command(cmd, "1. Research Assistant (Internet)", research_file)
        if not research_output:
            print("❌ Research failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Step 2: Local Data Search (optional, may fail if no MCP servers)
        cmd = [
            "uv", "run", "-m", 
            "peak_assistant.research_assistant.local_data_search_cli",
            "-t", args.hunt_topic,
            "-r", research_file,
            "--no-feedback"
        ] + env_arg + context_arg + verbose_arg
        
        local_data_output = run_command(cmd, "2. Local Data Search", local_data_file)
        if not local_data_output:
            print("⚠️  Local data search failed, creating empty placeholder")
            with open(local_data_file, 'w') as f:
                f.write("# Local Data Search Report\n\nNo local data available.\n")
        
        # Step 3: Generate Hypotheses
        cmd = [
            "uv", "run", "-m", "peak_assistant.hypothesis_assistant.hypothesis_assistant_cli",
            "-r", research_file,
            "-u", args.hunt_topic,
            "-l", local_data_file
        ] + env_arg + context_arg
        
        hypotheses_output = run_command(cmd, "3. Hypothesis Generation", hypotheses_file)
        if not hypotheses_output:
            print("❌ Hypothesis generation failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Select first hypothesis
        first_hypothesis = hypotheses_output.strip().split('\n')[0]
        with open(hypothesis_file, 'w') as f:
            f.write(first_hypothesis)
        print(f"📝 Selected first hypothesis: {first_hypothesis}\n")
        
        # Step 4: Refine Hypothesis
        cmd = [
            "uv", "run", "-m", "peak_assistant.hypothesis_assistant.hypothesis_refiner_cli",
            "-y", first_hypothesis,
            "-r", research_file,
            "-l", local_data_file,
            "--no-feedback"
        ] + env_arg + context_arg + verbose_arg
        
        refined_output = run_command(cmd, "4. Hypothesis Refinement", refined_hypothesis_file)
        if not refined_output:
            print("⚠️  Hypothesis refinement failed, using original hypothesis")
            refined_hypothesis = first_hypothesis
            with open(refined_hypothesis_file, 'w') as f:
                f.write(refined_hypothesis)
        else:
            refined_hypothesis = refined_output.strip()
        
        # Step 5: Generate ABLE Table
        cmd = [
            "uv", "run", "-m", "peak_assistant.able_assistant",
            "-r", research_file,
            "-y", refined_hypothesis,
            "-l", local_data_file,
            "--no-feedback"
        ] + env_arg + context_arg
        
        able_output = run_command(cmd, "5. ABLE Table Generation", able_file)
        if not able_output:
            print("❌ ABLE generation failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Step 6: Data Discovery (may fail, that's OK)
        cmd = [
            "uv", "run", "-m", "peak_assistant.data_assistant",
            "-r", research_file,
            "-y", refined_hypothesis,
            "-a", able_file,
            "-l", local_data_file,
            "--no-feedback"
        ] + env_arg + context_arg + verbose_arg
        
        data_discovery_output = run_command(cmd, "6. Data Discovery", data_discovery_file)
        if not data_discovery_output:
            print("⚠️  Data discovery failed, creating empty placeholder")
            with open(data_discovery_file, 'w') as f:
                f.write("# Data Discovery Report\n\nData discovery unavailable.\n")
        
        # Step 7: Hunt Planning
        cmd = [
            "uv", "run", "-m", "peak_assistant.planning_assistant",
            "-r", research_file,
            "-y", refined_hypothesis,
            "-a", able_file,
            "-d", data_discovery_file,
            "-l", local_data_file,
            "--no-feedback"
        ] + env_arg + context_arg + verbose_arg
        
        hunt_plan_output = run_command(cmd, "7. Hunt Planning", hunt_plan_file)
        if not hunt_plan_output:
            print("❌ Hunt planning failed")
            cleanup_needed = False
            return 1
        
        # Success!
        print("\n" + "="*60)
        print("✅ WORKFLOW COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"\n📁 All outputs saved to: {temp_dir}")
        print("\n📄 Generated files (in workflow order):")
        
        # Sort files by creation time to show workflow order
        files_with_time = []
        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            ctime = os.path.getctime(filepath)
            size = os.path.getsize(filepath)
            files_with_time.append((ctime, filename, size))
        
        for _, filename, size in sorted(files_with_time):
            print(f"  - {filename:<30} ({size:>8} bytes)")
        
        # Cleanup decision
        if args.keep_files:
            print(f"\n📁 Files preserved at: {temp_dir}")
            print("   (--keep-files specified)")
            cleanup_needed = False
        else:
            print(f"\n🧹 Cleaning up temporary files...")
            shutil.rmtree(temp_dir)
            print(f"   ✅ Removed: {temp_dir}")
            cleanup_needed = False
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Workflow failed with exception: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n📁 Temporary files preserved for inspection at: {temp_dir}")
        cleanup_needed = False  # Don't cleanup on failure
        return 1
    
    finally:
        # Safety check - should never happen but prevents accidental cleanup
        if cleanup_needed:
            print(f"⚠️  Unexpected state - preserving files at: {temp_dir}")


if __name__ == "__main__":
    sys.exit(main())
