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
End-to-end Streamlit UI workflow test script exercising all PEAK Assistant UI functions.
Tests the complete threat hunting workflow: Internet Research → Local Data → 
Hypothesis → Refinement → ABLE → Data Discovery → Hunt Plan

This script tests the Streamlit UI via the runner functions with real agents running.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

# Configure logging BEFORE importing anything that might use it
# Default to ERROR level, will be reconfigured based on args later
logging.basicConfig(
    level=logging.ERROR,
    format='%(levelname)s: %(message)s',
    force=True
)

from dotenv import load_dotenv
from peak_assistant.utils import find_dotenv_file

# Import streamlit runner functions
from peak_assistant.streamlit.util.runners import (
    run_researcher,
    run_local_data,
    run_hypothesis_generator,
    run_hypothesis_refiner,
    run_able_table,
    run_data_discovery,
    run_hunt_plan
)


def configure_logging(verbosity: int):
    """Configure logging based on verbosity level.
    
    Args:
        verbosity: 0 = ERROR+, 1 = WARNING+, 2 = INFO+, 3+ = DEBUG+
    """
    if verbosity == 0:
        level = logging.ERROR
    elif verbosity == 1:
        level = logging.WARNING
    elif verbosity == 2:
        level = logging.INFO
    else:  # 3 or higher
        level = logging.DEBUG
    
    # Configure root logger - this needs to be done first
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s',
        force=True  # Override any existing configuration
    )
    
    # Set the root logger's level
    logging.root.setLevel(level)
    
    # Update all handlers on the root logger
    for handler in logging.root.handlers:
        handler.setLevel(level)
    
    # Get all existing loggers and configure them
    # This catches loggers that were already created before our config
    for name in list(logging.root.manager.loggerDict.keys()):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        # Also update all handlers on each logger
        for handler in logger.handlers:
            handler.setLevel(level)


class Timer:
    """Context manager for timing operations"""
    def __init__(self, description):
        self.description = description
        self.start_time = None
        self.elapsed = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args):
        self.elapsed = time.time() - self.start_time
        print(f"⏱️  Time: {self.elapsed:.2f} seconds\n")


class MockSessionState(dict):
    """Mock Streamlit session state for testing"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize required session state fields
        self["Research_messages"] = []
        self["Research_document"] = ""
        self["Research_previous_messages"] = []
        
        self["Local_Data_messages"] = []
        self["Local_Data_document"] = ""
        self["Local_Data_previous_messages"] = []
        
        self["generated_hypotheses"] = []
        self["Hypothesis"] = ""
        
        self["Refinement_messages"] = []
        self["Refinement_document"] = ""
        self["Refinement_previous_messages"] = []
        
        self["ABLE_messages"] = []
        self["ABLE_document"] = ""
        
        self["Discovery_messages"] = []
        self["Discovery_document"] = ""
        
        self["Hunt Plan_messages"] = []
        self["Hunt Plan_document"] = ""
        
        self["local_context"] = ""
        self["user_id"] = "test_user"


async def run_workflow_step(step_func, description, session_state, output_key, output_file=None, step_num=None, total_steps=None, debug_agents=False):
    """Execute a workflow step and validate output.
    
    Args:
        step_func: The runner function to call
        description: Human-readable description for display
        session_state: Mock session state object
        output_key: The exact session state key to check for output
        output_file: Optional file path to save output
        step_num: Current step number
        total_steps: Total number of steps
        debug_agents: Whether to enable agent debugging
    """
    step_label = f"Step {step_num}/{total_steps}: " if step_num else ""
    
    print(f"\n{'='*60}")
    print(f"{step_label}{description}")
    print(f"{'='*60}\n")
    
    try:
        with Timer(description):
            # Run the step
            if 'debug_agents' in step_func.__code__.co_varnames:
                success = await step_func(debug_agents=debug_agents)
            else:
                success = await step_func()
        
        if not success:
            print(f"❌ ERROR: {description} returned False")
            return None
        
        # Special handling for hypotheses list
        if output_key == "generated_hypotheses":
            output = session_state.get(output_key, [])
            if not output or len(output) == 0:
                print(f"❌ ERROR: {description} returned empty list")
                return None
            # Convert list to string for display/saving
            text_output = "\n".join(output)
        else:
            text_output = session_state.get(output_key, "")
            if not text_output or len(text_output) == 0:
                print(f"❌ ERROR: {description} returned empty output")
                return None
        
        # Show output preview
        preview_len = min(500, len(text_output))
        print(f"✅ Successfully completed")
        print(f"   Output length: {len(text_output)} chars\n")
        print(f"Output preview:\n{text_output[:preview_len]}")
        if len(text_output) > preview_len:
            print("...")
        print()
        
        # Save to file
        if output_file:
            with open(output_file, 'w') as f:
                f.write(text_output)
            print(f"✅ Saved to: {output_file}\n")
        
        return text_output
        
    except Exception as e:
        print(f"❌ ERROR: {description} failed with exception")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {e}")
        
        # Show traceback
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        
        return None


def load_local_context(context_file):
    """Load local context file or return default"""
    if context_file and os.path.exists(context_file):
        with open(context_file, 'r') as f:
            context = f.read()
        print(f"📄 Loaded local context from: {context_file}\n")
        return context
    else:
        # Use default context file
        default_path = Path("context.txt")
        if default_path.exists():
            with open(default_path, 'r') as f:
                context = f.read()
            print(f"📄 Loaded local context from: {default_path}\n")
            return context
        else:
            print("⚠️  No context file found, using empty context\n")
            return ""


def extract_first_hypothesis(hypotheses_text):
    """Extract first hypothesis from generated list"""
    lines = hypotheses_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            # Remove numbering if present
            if line[0].isdigit() and '.' in line[:3]:
                line = line.split('.', 1)[1].strip()
            return line
    return lines[0] if lines else ""


async def main():
    parser = argparse.ArgumentParser(
        description="Run end-to-end Streamlit UI workflow test for all PEAK Assistant functions"
    )
    parser.add_argument(
        "hunt_topic",
        help="The hunt topic/technique to research (e.g., 'PowerShell Empire', 'T1055 Process Injection')"
    )
    parser.add_argument(
        "-c", "--local-context",
        help="Path to local context file (optional, will use default if not provided)",
        default=None
    )
    parser.add_argument(
        "-e", "--environment",
        help="Path to .env file (optional, will search for .env automatically if not provided)",
        default=None
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity: -v for WARNING, -vv for INFO, -vvv for DEBUG (default: ERROR only)"
    )
    parser.add_argument(
        "--debug-agents",
        action="store_true",
        help="Enable debug logging for agent callbacks (creates msgs.txt and results.txt)"
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
    
    # Configure logging based on verbosity
    configure_logging(args.verbose)
    
    print("="*60)
    print("PEAK Assistant Streamlit UI - Full Workflow Test")
    print("="*60)
    print(f"\n🎯 Hunt Topic: {args.hunt_topic}\n")
    
    # Load environment variables
    if args.environment:
        env_path = Path(args.environment)
        if not env_path.exists():
            print(f"❌ Error: Environment file '{args.environment}' not found")
            return 1
        load_dotenv(env_path)
        print(f"✅ Loaded environment from: {args.environment}\n")
    else:
        dotenv_path = find_dotenv_file()
        if dotenv_path:
            load_dotenv(dotenv_path)
            print(f"✅ Loaded environment from: {dotenv_path}\n")
        else:
            print("⚠️  No .env file found, using system environment variables\n")
    
    # Verify model_config.json exists
    model_config_path = Path("model_config.json")
    if not model_config_path.exists():
        print("⚠️  Warning: model_config.json not found in current directory")
        print("    The workflow may fail if model configuration is required\n")
    else:
        print(f"✅ Found model_config.json\n")
    
    # Load local context
    local_context = load_local_context(args.local_context)
    
    # Create temp directory
    if args.temp_dir:
        temp_dir = args.temp_dir
        os.makedirs(temp_dir, exist_ok=True)
    else:
        temp_dir = tempfile.mkdtemp(prefix="peak_streamlit_workflow_")
    
    print(f"📁 Temp directory: {temp_dir}\n")
    
    cleanup_needed = True
    workflow_start = time.time()
    
    try:
        # Initialize mock session state
        session_state = MockSessionState()
        session_state["local_context"] = local_context
        
        # Inject session state into streamlit module for runners to use
        import streamlit as st
        st.session_state = session_state
        
        # File paths
        research_file = os.path.join(temp_dir, "01_research_report.md")
        local_data_file = os.path.join(temp_dir, "02_local_data_report.md")
        hypotheses_file = os.path.join(temp_dir, "03_hypotheses.txt")
        hypothesis_file = os.path.join(temp_dir, "04_selected_hypothesis.txt")
        refined_hypothesis_file = os.path.join(temp_dir, "05_refined_hypothesis.txt")
        able_file = os.path.join(temp_dir, "06_able_table.txt")
        data_discovery_file = os.path.join(temp_dir, "07_data_discovery.txt")
        hunt_plan_file = os.path.join(temp_dir, "08_hunt_plan.md")
        
        # Step 1: Internet Research
        session_state["Research_messages"] = [{"role": "user", "content": args.hunt_topic}]
        research_output = await run_workflow_step(
            step_func=run_researcher,
            description="Internet Research",
            session_state=session_state,
            output_key="Research_document",
            output_file=research_file,
            step_num=1,
            total_steps=7,
            debug_agents=args.debug_agents
        )
        
        if not research_output:
            print("❌ Internet research failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Step 2: Local Data Search (optional, may fail if no MCP servers)
        session_state["Local_Data_messages"] = [{"role": "user", "content": args.hunt_topic}]
        local_data_output = await run_workflow_step(
            step_func=run_local_data,
            description="Local Data Search",
            session_state=session_state,
            output_key="Local_Data_document",
            output_file=local_data_file,
            step_num=2,
            total_steps=7,
            debug_agents=args.debug_agents
        )
        
        if not local_data_output:
            print("⚠️  Local data search failed, creating empty placeholder")
            local_data_output = "# Local Data Search Report\n\nNo local data available.\n"
            session_state["Local_Data_document"] = local_data_output
            with open(local_data_file, 'w') as f:
                f.write(local_data_output)
        
        # Step 3: Generate Hypotheses
        hypotheses_output = await run_workflow_step(
            step_func=run_hypothesis_generator,
            description="Hypothesis Generation",
            session_state=session_state,
            output_key="generated_hypotheses",
            output_file=hypotheses_file,
            step_num=3,
            total_steps=7
        )
        
        if not hypotheses_output:
            print("❌ Hypothesis generation failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Select first hypothesis
        first_hypothesis = extract_first_hypothesis(hypotheses_output)
        session_state["Hypothesis"] = first_hypothesis
        with open(hypothesis_file, 'w') as f:
            f.write(first_hypothesis)
        print(f"📝 Selected first hypothesis:\n   {first_hypothesis}\n")
        
        # Step 4: Refine Hypothesis
        session_state["Refinement_messages"] = [{"role": "user", "content": "Refine this hypothesis"}]
        refined_output = await run_workflow_step(
            step_func=run_hypothesis_refiner,
            description="Hypothesis Refinement",
            session_state=session_state,
            output_key="Hypothesis",
            output_file=refined_hypothesis_file,
            step_num=4,
            total_steps=7,
            debug_agents=args.debug_agents
        )
        
        if not refined_output:
            print("⚠️  Hypothesis refinement failed, using original hypothesis")
            refined_hypothesis = first_hypothesis
            session_state["Hypothesis"] = refined_hypothesis
            with open(refined_hypothesis_file, 'w') as f:
                f.write(refined_hypothesis)
        else:
            refined_hypothesis = refined_output.strip()
        
        # Step 5: Generate ABLE Table
        session_state["ABLE_messages"] = []
        able_output = await run_workflow_step(
            step_func=run_able_table,
            description="ABLE Table Generation",
            session_state=session_state,
            output_key="ABLE_document",
            output_file=able_file,
            step_num=5,
            total_steps=7,
            debug_agents=args.debug_agents
        )
        
        if not able_output:
            print("❌ ABLE generation failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Step 6: Data Discovery (may fail, that's OK)
        session_state["Discovery_messages"] = []
        data_discovery_output = await run_workflow_step(
            step_func=run_data_discovery,
            description="Data Discovery",
            session_state=session_state,
            output_key="Discovery_document",
            output_file=data_discovery_file,
            step_num=6,
            total_steps=7,
            debug_agents=args.debug_agents
        )
        
        if not data_discovery_output:
            print("⚠️  Data discovery failed, creating empty placeholder")
            data_discovery_output = "# Data Discovery Report\n\nData discovery unavailable.\n"
            session_state["Discovery_document"] = data_discovery_output
            with open(data_discovery_file, 'w') as f:
                f.write(data_discovery_output)
        
        # Step 7: Hunt Planning
        session_state["Hunt Plan_messages"] = []
        hunt_plan_output = await run_workflow_step(
            step_func=run_hunt_plan,
            description="Hunt Planning",
            session_state=session_state,
            output_key="Hunt Plan_document",
            output_file=hunt_plan_file,
            step_num=7,
            total_steps=7,
            debug_agents=args.debug_agents
        )
        
        if not hunt_plan_output:
            print("❌ Hunt planning failed")
            cleanup_needed = False
            return 1
        
        # Calculate total time
        total_time = time.time() - workflow_start
        
        # Success!
        print("\n" + "="*60)
        print("✅ WORKFLOW COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"\n⏱️  Total workflow time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)")
        print(f"\n📁 All outputs saved to: {temp_dir}")
        print("\n📄 Generated files (in workflow order):")
        
        # List files with sizes
        files_with_info = []
        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            size = os.path.getsize(filepath)
            files_with_info.append((filename, size))
        
        for filename, size in sorted(files_with_info):
            print(f"  - {filename:<35} ({size:>8,} bytes)")
        
        # Cleanup decision
        if args.keep_files:
            print(f"\n� Files preserved at: {temp_dir}")
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
        cleanup_needed = False
        return 1
    
    finally:
        if cleanup_needed:
            print(f"⚠️  Unexpected state - preserving files at: {temp_dir}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
