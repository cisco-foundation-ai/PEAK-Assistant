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
End-to-end MCP server workflow test script exercising all PEAK Assistant MCP tools.
Tests the complete threat hunting workflow: Internet Research → Local Data → 
Hypothesis → Refinement → ABLE → Data Discovery → Hunt Plan

This script tests the MCP server interface with real agents running.
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
from mcp import types
from peak_assistant.peak_mcp.__main__ import mcp
from peak_assistant.utils import find_dotenv_file


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


async def call_mcp_tool(tool_name, args, description, output_file=None, step_num=None, total_steps=None):
    """Execute MCP tool and optionally save output to file."""
    step_label = f"Step {step_num}/{total_steps}: " if step_num else ""
    
    print(f"\n{'='*60}")
    print(f"{step_label}{description}")
    print(f"Tool: {tool_name}")
    print(f"{'='*60}\n")
    
    result = None
    text_output = None
    
    try:
        with Timer(description):
            # Call tool directly on the mcp server object
            result = await mcp.call_tool(tool_name, args)
        
        # Validate we got a result
        if not result:
            print(f"❌ ERROR: {description} returned no content")
            return None
        
        # Result can be a tuple (content, metadata) or just a list
        # If it's a tuple, extract the first element (the content list)
        if isinstance(result, tuple):
            if len(result) == 0:
                print(f"❌ ERROR: Result tuple is empty")
                return None
            # Get the first element of the tuple (should be the content list)
            content_list = result[0]
        elif isinstance(result, list):
            content_list = result
        else:
            print(f"❌ ERROR: Expected list or tuple, got: {type(result)}")
            print(f"Result: {str(result)[:200]}")
            return None
        
        # Validate we have a list of content blocks
        if not isinstance(content_list, list):
            print(f"❌ ERROR: Expected content to be a list, got: {type(content_list)}")
            print(f"Content: {str(content_list)[:200]}")
            return None
        
        if len(content_list) == 0:
            print(f"❌ ERROR: Content list is empty")
            return None
        
        # Get the first content block (should be EmbeddedResource)
        content = content_list[0]
        
        # Validate it's an EmbeddedResource (artifact type)
        if not isinstance(content, types.EmbeddedResource):
            print(f"❌ ERROR: Expected EmbeddedResource, got: {type(content)}")
            print(f"Content: {str(content)[:200]}")
            return None
        
        # Validate it's a resource type
        if content.type != "resource":
            print(f"❌ ERROR: Expected type='resource', got: {content.type}")
            return None
        
        # Extract text from the resource
        if not hasattr(content, 'resource'):
            print(f"❌ ERROR: EmbeddedResource missing 'resource' attribute")
            print(f"Available attributes: {dir(content)}")
            return None
        
        if not hasattr(content.resource, 'text'):
            print(f"❌ ERROR: Resource missing 'text' attribute")
            print(f"Resource type: {type(content.resource)}")
            print(f"Available attributes: {dir(content.resource)}")
            return None
        
        text_output = content.resource.text
        
        # Validate output
        if not text_output or len(text_output) == 0:
            print(f"❌ ERROR: {description} returned empty output")
            return None
        
        # Success! Show what we got
        print(f"✅ Successfully extracted artifact (EmbeddedResource)")
        print(f"   MIME type: {content.resource.mimeType if hasattr(content.resource, 'mimeType') else 'unknown'}")
        print(f"   Text length: {len(text_output)} chars\n")
        
        # Show output preview (like the CLI test does)
        preview_len = min(500, len(text_output))
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
        
        # Show what we had before the exception
        if result is not None:
            result_str = str(result)
            preview_len = min(200, len(result_str))
            print(f"\nResult before error: {result_str[:preview_len]}")
            if len(result_str) > preview_len:
                print("...")
        
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
        default_context = """
# Local Computing Environment

This is a test environment for the PEAK Assistant MCP server.

## Environment Details
- Platform: Test Environment
- Purpose: Integration Testing
- Data Sources: Various test data sources may be available
"""
        print("📄 Using default local context\n")
        return default_context


def extract_first_hypothesis(hypotheses_text):
    """Extract the first hypothesis from the hypotheses list"""
    lines = [line.strip() for line in hypotheses_text.split('\n') if line.strip()]
    
    # Find first hypothesis (may start with number, bullet, or be in markdown)
    for line in lines:
        # Skip headers and empty lines
        if line.startswith('#') or not line:
            continue
        
        # Check if line looks like a hypothesis
        if any(line.startswith(prefix) for prefix in ['1.', '2.', '3.', '-', '*', '•']):
            # Strip leading markers and whitespace
            hypothesis = line.lstrip('0123456789.-*• \t')
            if hypothesis:
                return hypothesis
        
        # If it's substantial text without obvious formatting, use it
        if len(line.split()) > 5 and not line.startswith('##'):
            return line
    
    # Fallback: return first non-empty line that's not a header
    for line in lines:
        if line and not line.startswith('#'):
            return line
    
    return "Default hypothesis: Investigate suspicious behavior in the environment"


async def run_workflow(args):
    """Execute full MCP workflow"""
    
    # Track overall timing
    workflow_start = time.time()
    
    # Create temporary directory
    if args.temp_dir:
        base_dir = Path(args.temp_dir)
        if not base_dir.exists():
            print(f"Error: Specified temp directory '{args.temp_dir}' does not exist")
            return 1
        if not base_dir.is_dir():
            print(f"Error: '{args.temp_dir}' is not a directory")
            return 1
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        temp_dir = base_dir / f"peak_mcp_workflow_{timestamp}_{os.getpid()}"
        temp_dir.mkdir(parents=True, exist_ok=False)
        temp_dir = str(temp_dir)
    else:
        temp_dir = tempfile.mkdtemp(prefix="peak_mcp_workflow_test_")
    
    print(f"🔧 Working directory: {temp_dir}\n")
    
    # Load local context
    local_context = load_local_context(args.local_context)
    
    cleanup_needed = True
    try:
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
        research_output = await call_mcp_tool(
            tool_name="peak-internet-researcher",
            args={
                "technique": args.hunt_topic,
                "local_context": local_context
            },
            description="Internet Research",
            output_file=research_file,
            step_num=1,
            total_steps=7
        )
        
        if not research_output:
            print("❌ Internet research failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Step 2: Local Data Search (optional, may fail if no MCP servers)
        local_data_output = await call_mcp_tool(
            tool_name="peak-local-data-researcher",
            args={
                "technique": args.hunt_topic,
                "local_context": local_context,
                "research_document": research_output
            },
            description="Local Data Search",
            output_file=local_data_file,
            step_num=2,
            total_steps=7
        )
        
        if not local_data_output:
            print("⚠️  Local data search failed, creating empty placeholder")
            local_data_output = "# Local Data Search Report\n\nNo local data available.\n"
            with open(local_data_file, 'w') as f:
                f.write(local_data_output)
        
        # Step 3: Generate Hypotheses
        hypotheses_output = await call_mcp_tool(
            tool_name="peak-hypothesizer",
            args={
                "research_document": research_output,
                "local_context": local_context,
                "local_data_search_results": local_data_output
            },
            description="Hypothesis Generation",
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
        with open(hypothesis_file, 'w') as f:
            f.write(first_hypothesis)
        print(f"📝 Selected first hypothesis:\n   {first_hypothesis}\n")
        
        # Step 4: Refine Hypothesis
        refined_output = await call_mcp_tool(
            tool_name="peak-hypothesis-refiner",
            args={
                "hypothesis": first_hypothesis,
                "research_document": research_output,
                "local_context": local_context,
                "local_data_search_results": local_data_output
            },
            description="Hypothesis Refinement",
            output_file=refined_hypothesis_file,
            step_num=4,
            total_steps=7
        )
        
        if not refined_output:
            print("⚠️  Hypothesis refinement failed, using original hypothesis")
            refined_hypothesis = first_hypothesis
            with open(refined_hypothesis_file, 'w') as f:
                f.write(refined_hypothesis)
        else:
            refined_hypothesis = refined_output.strip()
        
        # Step 5: Generate ABLE Table
        able_output = await call_mcp_tool(
            tool_name="peak-able-table",
            args={
                "hypothesis": refined_hypothesis,
                "research_document": research_output,
                "local_context": local_context,
                "local_data_search_results": local_data_output
            },
            description="ABLE Table Generation",
            output_file=able_file,
            step_num=5,
            total_steps=7
        )
        
        if not able_output:
            print("❌ ABLE generation failed, aborting workflow")
            cleanup_needed = False
            return 1
        
        # Step 6: Data Discovery (may fail, that's OK)
        data_discovery_output = await call_mcp_tool(
            tool_name="peak-data-discovery",
            args={
                "hypothesis": refined_hypothesis,
                "research_document": research_output,
                "able_info": able_output,
                "local_context": local_context,
                "local_data_search_results": local_data_output
            },
            description="Data Discovery",
            output_file=data_discovery_file,
            step_num=6,
            total_steps=7
        )
        
        if not data_discovery_output:
            print("⚠️  Data discovery failed, creating empty placeholder")
            data_discovery_output = "# Data Discovery Report\n\nData discovery unavailable.\n"
            with open(data_discovery_file, 'w') as f:
                f.write(data_discovery_output)
        
        # Step 7: Hunt Planning
        hunt_plan_output = await call_mcp_tool(
            tool_name="peak-hunt-planner",
            args={
                "hypothesis": refined_hypothesis,
                "research_document": research_output,
                "able_info": able_output,
                "data_discovery": data_discovery_output,
                "local_context": local_context,
                "local_data_search_results": local_data_output
            },
            description="Hunt Planning",
            output_file=hunt_plan_file,
            step_num=7,
            total_steps=7
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
        cleanup_needed = False
        return 1
    
    finally:
        if cleanup_needed:
            print(f"⚠️  Unexpected state - preserving files at: {temp_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Run end-to-end MCP workflow test for all PEAK Assistant MCP tools"
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
    print("PEAK Assistant MCP Server - Full Workflow Test")
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
        print("   Agents may fail if model configuration is not available\n")
    else:
        print(f"✅ Found model configuration: {model_config_path}\n")
    
    # Run workflow
    return asyncio.run(run_workflow(args))


if __name__ == "__main__":
    sys.exit(main())
