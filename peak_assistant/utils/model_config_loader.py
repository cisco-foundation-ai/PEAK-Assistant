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
Model configuration loader for per-agent LLM provider configuration.

Loads model_config.json from the current working directory and resolves
provider and model settings for each agent using precedence:
    agents > groups (wildcard matching) > defaults

Supports:
- Multiple named provider instances (azure, openai types)
- Environment variable interpolation with ${ENV_VAR} syntax
- Wildcard matching for agent groups
- Provider-level model_info for OpenAI-compatible servers
"""

from __future__ import annotations

import json
import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Optional

from peak_assistant.utils import interpolate_env_vars, ConfigInterpolationError


class ModelConfigError(Exception):
    """Raised when model configuration is invalid or missing."""
    pass


class ModelConfigLoader:
    """Loads and resolves model configuration from model_config.json."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the loader.
        
        Args:
            config_path: Path to model_config.json. If None, looks in CWD.
        """
        if config_path is None:
            config_path = Path.cwd() / "model_config.json"
        
        self.config_path = config_path
        self._config: Optional[Dict[str, Any]] = None
        self._providers: Optional[Dict[str, Any]] = None
    
    def load(self) -> None:
        """Load and parse the configuration file.
        
        Raises:
            ModelConfigError: If file is missing or invalid JSON.
        """
        if not self.config_path.exists():
            raise ModelConfigError(
                f"model_config.json not found at {self.config_path}. "
                "This file is required for LLM configuration."
            )
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        except json.JSONDecodeError as e:
            raise ModelConfigError(
                f"Invalid JSON in {self.config_path}: {e}"
            )
        
        # Validate top-level structure
        if not isinstance(self._config, dict):
            raise ModelConfigError("model_config.json must be a JSON object")
        
        if "version" not in self._config:
            raise ModelConfigError("model_config.json must have a 'version' field")
        
        if "providers" not in self._config:
            raise ModelConfigError("model_config.json must have a 'providers' section")
        
        if "defaults" not in self._config:
            raise ModelConfigError("model_config.json must have a 'defaults' section")
        
        self._providers = self._config["providers"]
        
        # Interpolate environment variables in providers
        self._providers = self._interpolate_env(self._providers)
    
    def _interpolate_env(self, obj: Any) -> Any:
        """Recursively interpolate ${ENV_VAR} in strings.
        
        Delegates to shared interpolate_env_vars utility.
        
        Raises:
            ModelConfigError: If environment variable not found and no default provided
        """
        try:
            return interpolate_env_vars(obj)
        except ConfigInterpolationError as e:
            # Wrap in ModelConfigError for backward compatibility
            raise ModelConfigError(str(e))
    
    def resolve_agent_config(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """Resolve configuration for a specific agent.
        
        Resolution order:
        1. agents.<agent_name> (exact match)
        2. First matching group in groups.* (wildcard match)
        3. defaults
        
        Args:
            agent_name: Name of the agent. If None, uses defaults.
        
        Returns:
            Dict with keys:
                - provider_name: str (name of provider in providers section)
                - model: str (model identifier)
                - deployment: str (for Azure only)
                - ... (any other agent-level fields)
        
        Raises:
            ModelConfigError: If configuration is invalid.
        """
        if self._config is None:
            self.load()
        
        agent_config = None
        
        # 1. Check for exact agent match
        if agent_name and "agents" in self._config:
            agents = self._config["agents"]
            if agent_name in agents:
                agent_config = agents[agent_name].copy()
        
        # 2. Check for group match (first match wins)
        if agent_config is None and agent_name and "groups" in self._config:
            groups = self._config["groups"]
            for group_name, group_config in groups.items():
                if "match" not in group_config:
                    continue
                match_patterns = group_config["match"]
                if not isinstance(match_patterns, list):
                    match_patterns = [match_patterns]
                
                for pattern in match_patterns:
                    if fnmatch(agent_name, pattern):
                        # Found a match - use this group config (excluding 'match' key)
                        agent_config = {k: v for k, v in group_config.items() if k != "match"}
                        break
                
                if agent_config:
                    break
        
        # 3. Fall back to defaults
        if agent_config is None:
            agent_config = self._config["defaults"].copy()
        
        # Validate that we have a provider reference
        if "provider" not in agent_config:
            raise ModelConfigError(
                f"No 'provider' field found for agent '{agent_name or 'defaults'}'"
            )
        
        return agent_config
    
    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """Get provider configuration by name.
        
        Args:
            provider_name: Name of provider in providers section.
        
        Returns:
            Dict with keys:
                - type: str ("azure", "openai", or "anthropic")
                - config: dict (provider-specific connection config)
                - models: dict (optional, model_info for OpenAI-compatible)
        
        Raises:
            ModelConfigError: If provider not found or invalid.
        """
        if self._providers is None:
            self.load()
        
        if provider_name not in self._providers:
            raise ModelConfigError(
                f"Provider '{provider_name}' not found in providers section"
            )
        
        provider_config = self._providers[provider_name]
        
        if "type" not in provider_config:
            raise ModelConfigError(
                f"Provider '{provider_name}' missing required 'type' field"
            )
        
        provider_type = provider_config["type"]
        
        if provider_type not in ["azure", "openai", "anthropic"]:
            raise ModelConfigError(
                f"Provider '{provider_name}': Invalid type '{provider_type}'. "
                f"Must be 'azure', 'openai', or 'anthropic'."
            )
        
        if "config" not in provider_config:
            raise ModelConfigError(
                f"Provider '{provider_name}' missing required 'config' field"
            )
        
        config = provider_config["config"]
        
        # Validate provider-specific required fields
        if provider_type == "azure":
            required = ["endpoint", "api_key", "api_version"]
            missing = [f for f in required if f not in config]
            if missing:
                raise ModelConfigError(
                    f"Provider '{provider_name}' (azure): Missing required fields: {', '.join(missing)}"
                )
        elif provider_type == "openai":
            if "api_key" not in config:
                raise ModelConfigError(
                    f"Provider '{provider_name}' (openai): Missing required field 'api_key'"
                )
        elif provider_type == "anthropic":
            if "api_key" not in config:
                raise ModelConfigError(
                    f"Provider '{provider_name}' (anthropic): Missing required field 'api_key'"
                )
        
        return provider_config
        
    
    def get_model_info(
        self, 
        provider_name: str, 
        model: str
    ) -> Optional[Dict[str, Any]]:
        """Get model_info for a specific model from a provider.
        
        Args:
            provider_name: Name of provider in providers section.
            model: Model identifier.
        
        Returns:
            model_info dict if found, None otherwise.
        """
        provider_config = self.get_provider_config(provider_name)
        
        if "models" not in provider_config:
            return None
        
        models = provider_config["models"]
        if model not in models:
            return None
        
        model_config = models[model]
        return model_config.get("model_info")


# Global singleton instance
_loader: Optional[ModelConfigLoader] = None


def get_loader(config_path: Optional[Path] = None) -> ModelConfigLoader:
    """Get or create the global ModelConfigLoader instance.
    
    Args:
        config_path: Path to model_config.json. If None, uses CWD.
    
    Returns:
        ModelConfigLoader instance.
    """
    global _loader
    if _loader is None or config_path is not None:
        _loader = ModelConfigLoader(config_path)
        _loader.load()
    return _loader


def reset_loader() -> None:
    """Reset the global loader instance. Useful for testing."""
    global _loader
    _loader = None
