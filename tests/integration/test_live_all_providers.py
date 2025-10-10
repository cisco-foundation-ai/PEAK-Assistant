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
Live integration test for all configured providers.

This test reads model_config.json and tests every provider/model combination
with a simple prompt to verify end-to-end functionality.

Prerequisites:
    - model_config.json must exist in the current working directory
    - .env file with secrets (searched in current and parent directories)
    - All providers in the config must have valid credentials (via env vars or direct config)
    - Mark with @pytest.mark.live to run: pytest -m live tests/integration/test_live_all_providers.py

The test will:
    1. Load .env file (same logic as the app)
    2. Load model_config.json
    3. Discover all unique provider+model combinations
    4. Test each with a simple prompt
    5. Report results for each provider/model
"""

import pytest
from pathlib import Path

from autogen_core.models import UserMessage, SystemMessage
from peak_assistant.utils.llm_factory import get_model_client
from peak_assistant.utils.model_config_loader import ModelConfigLoader, ModelConfigError
from peak_assistant.utils import load_env_defaults


@pytest.fixture(scope="session", autouse=True)
def load_env():
    """Load .env file before running any tests (same logic as the app)."""
    load_env_defaults()


def discover_provider_model_combinations(config_path: Path):
    """Discover all unique provider+model combinations from config.
    
    Returns:
        List of tuples: (agent_name_or_none, provider_name, model_name, description)
    """
    try:
        loader = ModelConfigLoader(config_path)
        loader.load()
    except ModelConfigError as e:
        pytest.skip(f"Could not load model_config.json: {e}")
        return []
    
    combinations = []
    
    # Get defaults
    try:
        defaults_config = loader.resolve_agent_config(None)
        provider_name = defaults_config["provider"]
        model = defaults_config.get("model", "unknown")
        provider_config = loader.get_provider_config(provider_name)
        provider_type = provider_config["type"]
        
        combinations.append((
            None,
            provider_name,
            model,
            f"defaults ({provider_type})"
        ))
    except Exception as e:
        print(f"Warning: Could not resolve defaults: {e}")
    
    # Get all agents
    config = loader._config
    if "agents" in config:
        for agent_name, agent_config in config["agents"].items():
            try:
                resolved = loader.resolve_agent_config(agent_name)
                provider_name = resolved["provider"]
                model = resolved.get("model", "unknown")
                provider_config = loader.get_provider_config(provider_name)
                provider_type = provider_config["type"]
                
                combinations.append((
                    agent_name,
                    provider_name,
                    model,
                    f"{agent_name} ({provider_type})"
                ))
            except Exception as e:
                print(f"Warning: Could not resolve agent {agent_name}: {e}")
    
    # Get all groups (test one agent per group)
    if "groups" in config:
        for group_name, group_config in config["groups"].items():
            if "match" not in group_config:
                continue
            
            # Use first pattern as test agent name
            patterns = group_config["match"]
            if not isinstance(patterns, list):
                patterns = [patterns]
            
            if patterns:
                # Create a test agent name from the pattern
                test_pattern = patterns[0]
                # If it's a wildcard, create a concrete name
                if "*" in test_pattern:
                    test_agent = test_pattern.replace("*", "test")
                else:
                    test_agent = test_pattern
                
                try:
                    resolved = loader.resolve_agent_config(test_agent)
                    provider_name = resolved["provider"]
                    model = resolved.get("model", "unknown")
                    provider_config = loader.get_provider_config(provider_name)
                    provider_type = provider_config["type"]
                    
                    combinations.append((
                        test_agent,
                        provider_name,
                        model,
                        f"group:{group_name} ({provider_type})"
                    ))
                except Exception as e:
                    print(f"Warning: Could not resolve group {group_name}: {e}")
    
    # Deduplicate by (provider_name, model)
    seen = set()
    unique_combinations = []
    for combo in combinations:
        key = (combo[1], combo[2])  # (provider_name, model)
        if key not in seen:
            seen.add(key)
            unique_combinations.append(combo)
    
    return unique_combinations


@pytest.fixture
def config_path():
    """Get path to model_config.json."""
    path = Path.cwd() / "model_config.json"
    if not path.exists():
        pytest.skip("model_config.json not found in current directory")
    return path


@pytest.mark.live
@pytest.mark.asyncio
async def test_all_providers_simple_prompt(config_path, capsys):
    """
    Test all providers and models in model_config.json with a simple prompt.
    
    This test discovers all unique provider+model combinations from the config
    and tests each one with a simple prompt to verify it works end-to-end.
    """
    combinations = discover_provider_model_combinations(config_path)
    
    if not combinations:
        pytest.skip("No provider/model combinations found in model_config.json")
    
    # Print header
    header = f"\n{'='*80}\nTesting {len(combinations)} provider/model combinations\n{'='*80}\n"
    print(header)
    
    # Flush to ensure it shows immediately
    with capsys.disabled():
        print(header, flush=True)
    
    results = []
    
    for agent_name, provider_name, model, description in combinations:
        status_msg = f"\nTesting: {description}\n  Provider: {provider_name}\n  Model: {model}\n  Agent: {agent_name or '(defaults)'}"
        print(status_msg)
        
        with capsys.disabled():
            print(status_msg, flush=True)
        
        try:
            # Create client for this agent
            client = await get_model_client(
                agent_name=agent_name,
                config_path=config_path
            )
            
            # Simple test prompt
            messages = [
                SystemMessage(content="You are a helpful assistant. Be concise."),
                UserMessage(content="Say 'Hello' and nothing else.", source="user"),
            ]
            
            # Make the call
            result = await client.create(messages)
            response_text = str(result.content).strip()
            
            # Validate response
            if response_text:
                success_msg = f"  ✓ Response: {response_text[:100]}..."
                print(success_msg)
                with capsys.disabled():
                    print(success_msg, flush=True)
                results.append((description, "PASS", response_text[:100]))
            else:
                fail_msg = "  ✗ Empty response"
                print(fail_msg)
                with capsys.disabled():
                    print(fail_msg, flush=True)
                results.append((description, "FAIL", "Empty response"))
            
        except Exception as e:
            error_msg = str(e)
            error_output = f"  ✗ Error: {error_msg[:200]}"
            print(error_output)
            with capsys.disabled():
                print(error_output, flush=True)
            results.append((description, "ERROR", error_msg[:200]))
    
    # Summary
    summary_header = f"\n{'='*80}\nSUMMARY\n{'='*80}\n"
    print(summary_header)
    with capsys.disabled():
        print(summary_header, flush=True)
    
    passed = sum(1 for _, status, _ in results if status == "PASS")
    failed = sum(1 for _, status, _ in results if status == "FAIL")
    errors = sum(1 for _, status, _ in results if status == "ERROR")
    
    for desc, status, detail in results:
        symbol = "✓" if status == "PASS" else "✗"
        result_line = f"{symbol} {desc:50s} {status:6s}"
        print(result_line)
        with capsys.disabled():
            print(result_line, flush=True)
        if status != "PASS":
            detail_line = f"    {detail}"
            print(detail_line)
            with capsys.disabled():
                print(detail_line, flush=True)
    
    summary_footer = f"\nTotal: {len(results)} | Passed: {passed} | Failed: {failed} | Errors: {errors}\n{'='*80}\n"
    print(summary_footer)
    with capsys.disabled():
        print(summary_footer, flush=True)
    
    # Assert that all providers passed (no failures or errors)
    if failed > 0 or errors > 0:
        error_details = []
        for desc, status, detail in results:
            if status != "PASS":
                error_details.append(f"  - {desc}: {detail}")
        
        failure_msg = (
            f"\n{failed + errors} provider(s) failed or had errors:\n" + 
            "\n".join(error_details)
        )
        pytest.fail(failure_msg)
    
    # All providers passed
    assert passed == len(results), f"Expected all {len(results)} providers to pass, but only {passed} passed"
