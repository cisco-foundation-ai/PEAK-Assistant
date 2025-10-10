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
Evaluation model client utilities.

Provides synchronous wrappers around the async model factory for use in
evaluation scripts that need to make many sequential LLM calls.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path to import peak_assistant modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from peak_assistant.utils.model_config_loader import ModelConfigLoader, ModelConfigError


class EvaluatorModelClient:
    """Synchronous wrapper for model clients used in evaluation scripts.
    
    This class provides a simple interface for evaluation scripts to make
    LLM calls using the flexible model configuration system.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the evaluator model client.
        
        Args:
            config_path: Path to model_config.json. If None, looks in CWD.
        """
        self.config_path = config_path
        self.loader = ModelConfigLoader(config_path)
        self.loader.load()
        
        # Cache for model clients by judge role
        self._clients: Dict[str, Any] = {}
        
        # Track which provider types we're using
        self._provider_types: Dict[str, str] = {}
    
    def _create_sync_client(self, judge_role: str) -> Any:
        """Create a synchronous client for the given judge role.
        
        Args:
            judge_role: Name of the judge role
        
        Returns:
            Synchronous client instance
        """
        agent_config = self.loader.resolve_agent_config(judge_role)
        provider_config = self.loader.get_provider_config(agent_config["provider"])
        provider_type = provider_config["type"]
        config = provider_config["config"]
        
        # Store provider type
        self._provider_types[judge_role] = provider_type
        
        # Create appropriate sync client
        if provider_type == "anthropic":
            from anthropic import Anthropic
            return Anthropic(api_key=config["api_key"])
        elif provider_type == "azure":
            from openai import AzureOpenAI
            return AzureOpenAI(
                api_key=config["api_key"],
                api_version=config["api_version"],
                azure_endpoint=config["endpoint"],
            )
        elif provider_type == "openai":
            from openai import OpenAI
            return OpenAI(
                api_key=config["api_key"],
                base_url=config.get("base_url"),
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")
    
    def get_client(self, judge_role: str) -> Any:
        """Get or create a model client for a specific judge role.
        
        Args:
            judge_role: Name of the judge role (e.g., "assertion_quality", "critical_judge")
        
        Returns:
            Model client instance (Anthropic, OpenAI, or Azure client)
        """
        if judge_role not in self._clients:
            self._clients[judge_role] = self._create_sync_client(judge_role)
        
        return self._clients[judge_role]
    
    def call_llm(
        self,
        judge_role: str,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.0,
    ) -> str:
        """Make a synchronous LLM call.
        
        Args:
            judge_role: Name of the judge role
            prompt: The prompt to send
            max_tokens: Maximum tokens in response
            temperature: Temperature for sampling
        
        Returns:
            Response text from the LLM
        """
        client = self.get_client(judge_role)
        provider_type = self._provider_types[judge_role]
        agent_config = self.loader.resolve_agent_config(judge_role)
        
        if provider_type == "anthropic":
            model = agent_config["model"]
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        elif provider_type == "azure":
            model = agent_config["deployment"]
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        elif provider_type == "openai":
            model = agent_config["model"]
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")
    
    def get_model_name(self, judge_role: str) -> str:
        """Get the model name for a specific judge role.
        
        Args:
            judge_role: Name of the judge role
        
        Returns:
            Model name/identifier
        """
        agent_config = self.loader.resolve_agent_config(judge_role)
        return agent_config.get("model", "unknown")
    
    def get_provider_type(self, judge_role: str) -> str:
        """Get the provider type for a specific judge role.
        
        Args:
            judge_role: Name of the judge role
        
        Returns:
            Provider type (e.g., "anthropic", "openai", "azure")
        """
        if judge_role not in self._provider_types:
            agent_config = self.loader.resolve_agent_config(judge_role)
            provider_config = self.loader.get_provider_config(agent_config["provider"])
            self._provider_types[judge_role] = provider_config["type"]
        
        return self._provider_types[judge_role]
