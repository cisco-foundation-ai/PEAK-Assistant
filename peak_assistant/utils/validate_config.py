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
Configuration validation tool for model_config.json.

Validates syntax, structure, and semantics of the configuration file,
and provides a human-readable summary of provider and agent assignments.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from collections import defaultdict

from .model_config_loader import ModelConfigLoader, ModelConfigError
from . import load_env_defaults


# Known agent names from the codebase
KNOWN_AGENTS = [
    "external_search_agent",
    "summarizer_agent",
    "summary_critic",
    "research_team_lead",
    "local_data_search_agent",
    "local_data_summarizer_agent",
    "hypothesis-refiner",
    "hypothesis-refiner-critic",
    "Data_Discovery_Agent",
    "Discovery_Critic_Agent",
    "hunt_planner",
    "hunt_plan_critic",
    "able_table",
    "hypothesizer_agent",
]


class ConfigValidator:
    """Validates and reports on model_config.json."""
    
    def __init__(self, config_path: Path):
        """Initialize validator.
        
        Args:
            config_path: Path to model_config.json
        """
        self.config_path = config_path
        self.loader: Optional[ModelConfigLoader] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate(self) -> bool:
        """Run validation and return True if valid.
        
        Returns:
            True if configuration is valid, False otherwise.
        """
        # Try to load the configuration
        try:
            self.loader = ModelConfigLoader(self.config_path)
            self.loader.load()
        except ModelConfigError as e:
            self.errors.append(f"Configuration error: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Unexpected error loading config: {e}")
            return False
        
        # Run validation checks
        self._validate_providers()
        self._validate_agent_assignments()
        self._check_unused_providers()
        
        return len(self.errors) == 0
    
    def _validate_providers(self):
        """Validate provider configurations.
        
        Delegates to ModelConfigLoader.get_provider_config() for core validation,
        then adds additional warnings for best practices.
        """
        if not self.loader or not self.loader._providers:
            return
        
        for provider_name, provider_config in self.loader._providers.items():
            # Delegate core validation to the loader
            try:
                self.loader.get_provider_config(provider_name)
            except ModelConfigError as e:
                self.errors.append(str(e))
                continue
            
            # Additional warnings (not errors) for best practices
            provider_type = provider_config.get("type")
            config = provider_config.get("config", {})
            
            # Check if base_url is set for OpenAI-compatible without model_info
            if provider_type == "openai" and "base_url" in config:
                models = provider_config.get("models", {})
                if not models:
                    self.warnings.append(
                        f"Provider '{provider_name}': Uses base_url (OpenAI-compatible) but has no "
                        f"'models' section. Consider adding model_info for non-standard models."
                    )
    
    def _validate_agent_assignments(self):
        """Validate that agent assignments reference valid providers and have required fields."""
        if not self.loader:
            return
        
        # Check defaults
        try:
            defaults = self.loader.resolve_agent_config(None)
            self._validate_agent_config("defaults", defaults)
        except Exception as e:
            self.errors.append(f"Error resolving defaults: {e}")
        
        # Check all known agents
        for agent_name in KNOWN_AGENTS:
            try:
                agent_config = self.loader.resolve_agent_config(agent_name)
                self._validate_agent_config(agent_name, agent_config)
            except Exception as e:
                self.errors.append(f"Error resolving agent '{agent_name}': {e}")
    
    def _validate_agent_config(self, agent_name: str, config: Dict[str, Any]):
        """Validate a single agent configuration."""
        if not self.loader:
            return
        
        provider_name = config.get("provider")
        if not provider_name:
            self.errors.append(f"Agent '{agent_name}': No provider specified")
            return
        
        # Check provider exists
        try:
            provider_config = self.loader.get_provider_config(provider_name)
        except ModelConfigError as e:
            self.errors.append(f"Agent '{agent_name}': {e}")
            return
        
        provider_type = provider_config["type"]
        
        # Validate Azure agent config
        if provider_type == "azure":
            if "model" not in config:
                self.errors.append(f"Agent '{agent_name}': Missing required field 'model' for Azure provider")
            if "deployment" not in config:
                self.errors.append(f"Agent '{agent_name}': Missing required field 'deployment' for Azure provider")
        
        # Validate OpenAI agent config
        elif provider_type == "openai":
            if "model" not in config:
                self.errors.append(f"Agent '{agent_name}': Missing required field 'model' for OpenAI provider")
        
        # Validate Anthropic agent config
        elif provider_type == "anthropic":
            if "model" not in config:
                self.errors.append(f"Agent '{agent_name}': Missing required field 'model' for Anthropic provider")
            
            # Check if model_info is needed
            model = config.get("model")
            if model and "base_url" in provider_config["config"]:
                # OpenAI-compatible - check if model_info exists
                model_info = self.loader.get_model_info(provider_name, model)
                if not model_info:
                    # Check if it's a standard OpenAI model (starts with gpt-)
                    if not model.startswith("gpt-") and not model.startswith("o1-"):
                        self.warnings.append(
                            f"Agent '{agent_name}': Uses non-standard model '{model}' from OpenAI-compatible "
                            f"provider '{provider_name}' without model_info. This may cause errors."
                        )
    
    def _check_unused_providers(self):
        """Check for providers that are defined but not used."""
        if not self.loader:
            return
        
        # Collect all provider references
        used_providers = set()
        
        # Check defaults
        try:
            defaults = self.loader.resolve_agent_config(None)
            used_providers.add(defaults.get("provider"))
        except:
            pass
        
        # Check all known agents
        for agent_name in KNOWN_AGENTS:
            try:
                agent_config = self.loader.resolve_agent_config(agent_name)
                used_providers.add(agent_config.get("provider"))
            except:
                pass
        
        # Find unused providers
        all_providers = set(self.loader._providers.keys())
        unused = all_providers - used_providers
        
        for provider_name in unused:
            self.warnings.append(f"Provider '{provider_name}' is defined but not used by any agent")
    
    def print_report(self):
        """Print validation report to stdout."""
        print("\n" + "="*80)
        print("Model Configuration Validation Report")
        print("="*80 + "\n")
        
        # Validation status
        if self.errors:
            print(f"✗ Configuration is INVALID ({len(self.errors)} error(s))\n")
            for error in self.errors:
                print(f"  ✗ {error}")
            print()
        else:
            print("✓ Configuration is valid\n")
        
        if self.warnings:
            print(f"⚠ {len(self.warnings)} warning(s):\n")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")
            print()
        
        # If there are errors, don't print the rest
        if self.errors:
            self._print_final_summary()
            return
        
        # Print provider tree
        self._print_provider_tree()
        
        # Print agent assignments table
        self._print_agent_table()
        
        # Print provider summary
        self._print_provider_summary()
        
        # Print final summary
        self._print_final_summary()
    
    def _print_provider_tree(self):
        """Print provider configuration as a tree."""
        if not self.loader or not self.loader._providers:
            return
        
        print(f"Providers ({len(self.loader._providers)} defined)")
        print("-" * 80)
        
        provider_items = list(self.loader._providers.items())
        for idx, (provider_name, provider_config) in enumerate(provider_items):
            is_last = idx == len(provider_items) - 1
            prefix = "└─" if is_last else "├─"
            continuation = "  " if is_last else "│ "
            
            provider_type = provider_config.get("type", "unknown")
            print(f"{prefix} {provider_name} ({provider_type})")
            
            config = provider_config.get("config", {})
            
            # Show relevant config fields
            if provider_type == "azure":
                endpoint = config.get("endpoint", "")
                # Truncate long endpoints
                if len(endpoint) > 50:
                    endpoint = endpoint[:47] + "..."
                print(f"{continuation}  ├─ Endpoint: {endpoint}")
                print(f"{continuation}  ├─ API Version: {config.get('api_version', 'N/A')}")
                
                # Check authentication method
                auth_module = provider_config.get("auth_module")
                if auth_module:
                    print(f"{continuation}  └─ Auth: {auth_module} (custom module)")
                else:
                    api_key = config.get("api_key", "")
                    if api_key.startswith("$"):
                        print(f"{continuation}  └─ Credentials: (from env var)")
                    else:
                        print(f"{continuation}  └─ Credentials: ✓")
            
            elif provider_type == "openai":
                api_key = config.get("api_key", "")
                if api_key.startswith("$"):
                    print(f"{continuation}  ├─ Credentials: (from env var)")
                else:
                    print(f"{continuation}  ├─ Credentials: ✓")
                
                if "base_url" in config:
                    base_url = config["base_url"]
                    if len(base_url) > 50:
                        base_url = base_url[:47] + "..."
                    print(f"{continuation}  ├─ Base URL: {base_url}")
                
                if "organization" in config:
                    print(f"{continuation}  ├─ Organization: {config['organization']}")
                
                if "project" in config:
                    print(f"{continuation}  ├─ Project: {config['project']}")
                
                # Show models with model_info
                models = provider_config.get("models", {})
                if models:
                    model_list = ", ".join(models.keys())
                    if len(model_list) > 50:
                        model_list = model_list[:47] + "..."
                    print(f"{continuation}  └─ Models defined: {model_list}")
                else:
                    print(f"{continuation}  └─ No models defined")
            
            elif provider_type == "anthropic":
                api_key = config.get("api_key", "")
                if api_key.startswith("$"):
                    print(f"{continuation}  ├─ Credentials: (from env var)")
                else:
                    print(f"{continuation}  ├─ Credentials: ✓")
                
                # Show optional config
                if "max_tokens" in config:
                    print(f"{continuation}  ├─ Max Tokens: {config['max_tokens']}")
                if "temperature" in config:
                    print(f"{continuation}  ├─ Temperature: {config['temperature']}")
                if "base_url" in config:
                    base_url = config["base_url"]
                    if len(base_url) > 50:
                        base_url = base_url[:47] + "..."
                    print(f"{continuation}  ├─ Base URL: {base_url}")
                
                print(f"{continuation}  └─ Model: (configured per agent)")
            
            if not is_last:
                print(f"{continuation}")
        
        print()
    
    def _print_agent_table(self):
        """Print agent assignments as a table."""
        if not self.loader:
            return
        
        print(f"Agent Model Assignments ({len(KNOWN_AGENTS)} agents)")
        print("="*80)
        
        # Collect agent assignments
        assignments = []
        for agent_name in KNOWN_AGENTS:
            try:
                agent_config = self.loader.resolve_agent_config(agent_name)
                provider_name = agent_config.get("provider", "N/A")
                model = agent_config.get("model", "N/A")
                
                # Determine source
                config = self.loader._config
                if "agents" in config and agent_name in config["agents"]:
                    source = "agent"
                elif "groups" in config:
                    # Check if any group matches
                    matched_group = None
                    for group_name, group_config in config["groups"].items():
                        if "match" not in group_config:
                            continue
                        patterns = group_config["match"]
                        if not isinstance(patterns, list):
                            patterns = [patterns]
                        
                        from fnmatch import fnmatch
                        for pattern in patterns:
                            if fnmatch(agent_name, pattern):
                                matched_group = group_name
                                break
                        if matched_group:
                            break
                    
                    if matched_group:
                        source = f"group:{matched_group}"
                    else:
                        source = "defaults"
                else:
                    source = "defaults"
                
                # Get provider type for display
                try:
                    provider_config = self.loader.get_provider_config(provider_name)
                    provider_type = provider_config["type"]
                    
                    # Add deployment for Azure
                    if provider_type == "azure":
                        deployment = agent_config.get("deployment", "")
                        if deployment:
                            model = f"{model} ({deployment})"
                except:
                    pass
                
                assignments.append((agent_name, provider_name, model, source))
            except Exception as e:
                assignments.append((agent_name, "ERROR", str(e)[:20], "error"))
        
        # Print table header
        print(f"┌─{'─'*27}┬─{'─'*16}┬─{'─'*20}┬─{'─'*18}┐")
        print(f"│ {'Agent':<27}│ {'Provider':<16}│ {'Model':<20}│ {'Source':<18}│")
        print(f"├─{'─'*27}┼─{'─'*16}┼─{'─'*20}┼─{'─'*18}┤")
        
        # Print rows
        for agent_name, provider_name, model, source in assignments:
            # Truncate long values
            agent_display = agent_name[:27]
            provider_display = provider_name[:16]
            model_display = model[:20]
            source_display = source[:18]
            
            print(f"│ {agent_display:<27}│ {provider_display:<16}│ {model_display:<20}│ {source_display:<18}│")
        
        print(f"└─{'─'*27}┴─{'─'*16}┴─{'─'*20}┴─{'─'*18}┘")
        print()
    
    def _print_provider_summary(self):
        """Print summary of which providers are used by how many agents."""
        if not self.loader:
            return
        
        print("Provider Usage Summary")
        print("="*80)
        
        # Count usage by provider and model
        provider_usage = defaultdict(lambda: defaultdict(list))
        
        for agent_name in KNOWN_AGENTS:
            try:
                agent_config = self.loader.resolve_agent_config(agent_name)
                provider_name = agent_config.get("provider")
                model = agent_config.get("model")
                
                if provider_name and model:
                    provider_usage[provider_name][model].append(agent_name)
            except:
                pass
        
        # Print summary
        for provider_name in sorted(provider_usage.keys()):
            try:
                provider_config = self.loader.get_provider_config(provider_name)
                provider_type = provider_config["type"]
            except:
                provider_type = "unknown"
            
            models = provider_usage[provider_name]
            total_agents = sum(len(agents) for agents in models.values())
            
            print(f"\nProvider: {provider_name} (type: {provider_type})")
            print(f"  Total agents: {total_agents}")
            
            for model, agents in sorted(models.items()):
                print(f"  • {model}: {len(agents)} agent(s)")
                if len(agents) <= 5:
                    print(f"    {', '.join(agents)}")
                else:
                    print(f"    {', '.join(agents[:5])}, ... (+{len(agents)-5} more)")
        
        print()
    
    def _print_final_summary(self):
        """Print final summary line with error and warning counts."""
        print("="*80)
        
        error_count = len(self.errors)
        warning_count = len(self.warnings)
        
        if error_count == 0 and warning_count == 0:
            print("✓ Validation complete: No errors or warnings found")
        elif error_count > 0 and warning_count > 0:
            print(f"✗ Validation complete: {error_count} error(s), {warning_count} warning(s) found")
        elif error_count > 0:
            print(f"✗ Validation complete: {error_count} error(s) found")
        else:
            print(f"⚠ Validation complete: {warning_count} warning(s) found")
        
        print("="*80 + "\n")


def main():
    """Main entry point for the validation tool."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate model_config.json and show configuration summary"
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path.cwd() / "model_config.json",
        help="Path to model_config.json (default: ./model_config.json)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Only show errors and warnings, not full report"
    )
    
    args = parser.parse_args()
    
    # Load .env file (same logic as the app)
    load_env_defaults()
    
    if not args.config.exists():
        print(f"✗ Error: Configuration file not found: {args.config}")
        sys.exit(1)
    
    validator = ConfigValidator(args.config)
    is_valid = validator.validate()
    
    if args.quiet:
        # Only print errors and warnings
        if validator.errors:
            print(f"✗ {len(validator.errors)} error(s):")
            for error in validator.errors:
                print(f"  ✗ {error}")
        if validator.warnings:
            print(f"⚠ {len(validator.warnings)} warning(s):")
            for warning in validator.warnings:
                print(f"  ⚠ {warning}")
    else:
        # Print full report
        validator.print_report()
    
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
