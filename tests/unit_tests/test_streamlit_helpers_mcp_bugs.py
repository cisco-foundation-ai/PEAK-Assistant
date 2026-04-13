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
Tests for Streamlit helpers MCP configuration bugs.

Bug 1: load_mcp_server_configs() does not interpolate ${ENV_VAR} patterns.
Bug 2: test_mcp_connection() does not include system env vars in subprocess.
"""

import json
import os
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from peak_assistant.utils.mcp_config import MCPServerConfig, TransportType


class TestLoadMcpServerConfigsInterpolation:
    """Bug 1: load_mcp_server_configs() should interpolate ${ENV_VAR} patterns"""

    def test_interpolates_env_vars_in_server_env_dict(self, monkeypatch):
        """${VAR} in server env dict should be replaced with actual env value"""
        monkeypatch.setenv("TEST_TAVILY_KEY", "resolved_secret_value")

        config_data = {
            "mcpServers": {
                "tavily": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "tavily-mcp"],
                    "env": {
                        "TAVILY_API_KEY": "${TEST_TAVILY_KEY}"
                    }
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "mcp_servers.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(
                "peak_assistant.streamlit.util.helpers.st.session_state", {}
            )

            from peak_assistant.streamlit.util.helpers import load_mcp_server_configs
            result = load_mcp_server_configs()

        assert "tavily" in result
        assert result["tavily"].env["TAVILY_API_KEY"] == "resolved_secret_value"

    def test_interpolates_env_vars_in_auth_token(self, monkeypatch):
        """${VAR} in auth token field should be replaced with actual env value"""
        monkeypatch.setenv("TEST_AUTH_TOKEN", "resolved_token_value")

        config_data = {
            "mcpServers": {
                "http-server": {
                    "transport": "http",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "bearer",
                        "token": "${TEST_AUTH_TOKEN}"
                    }
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "mcp_servers.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(
                "peak_assistant.streamlit.util.helpers.st.session_state", {}
            )

            from peak_assistant.streamlit.util.helpers import load_mcp_server_configs
            result = load_mcp_server_configs()

        assert "http-server" in result
        assert result["http-server"].auth.token == "resolved_token_value"

    def test_missing_env_var_without_default_returns_empty(self, monkeypatch):
        """Missing env var without default should cause graceful failure (empty dict)"""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "http",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "bearer",
                        "token": "${NONEXISTENT_VAR_12345}"
                    }
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "mcp_servers.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(
                "peak_assistant.streamlit.util.helpers.st.session_state", {}
            )

            from peak_assistant.streamlit.util.helpers import load_mcp_server_configs
            result = load_mcp_server_configs()

        # After fix: ConfigInterpolationError is caught by the broad except,
        # returning {}. Before fix: the literal string passes through.
        assert result == {}


class TestMcpConnectionSubprocessEnv:
    """Bug 2: test_mcp_connection() should pass full system env to subprocess"""

    @pytest.mark.asyncio
    async def test_subprocess_env_includes_system_path(self, monkeypatch):
        """StdioServerParams.env should contain both custom and system env vars"""
        monkeypatch.setenv("PATH", "/usr/bin:/usr/local/bin")

        config = MCPServerConfig(
            name="test-server",
            transport=TransportType.STDIO,
            command="node",
            args=["server.js"],
            env={"CUSTOM_KEY": "custom_val"}
        )

        captured_params = {}

        mock_workbench_instance = MagicMock()
        mock_workbench_instance.list_tools = AsyncMock(return_value=[])
        mock_workbench_instance.stop = AsyncMock()

        def capture_workbench(server_params):
            captured_params["server_params"] = server_params
            return mock_workbench_instance

        with patch("shutil.which", return_value="/usr/bin/node"), \
             patch("autogen_ext.tools.mcp.McpWorkbench", side_effect=capture_workbench):
            from peak_assistant.streamlit.util.helpers import test_mcp_connection
            success, message = await test_mcp_connection("test-server", config)

        assert success is True
        params = captured_params["server_params"]
        assert "CUSTOM_KEY" in params.env
        assert params.env["CUSTOM_KEY"] == "custom_val"
        assert "PATH" in params.env
        assert params.env["PATH"] == "/usr/bin:/usr/local/bin"

    @pytest.mark.asyncio
    async def test_subprocess_env_with_no_config_env_gets_system_env(self, monkeypatch):
        """Even with env=None in config, subprocess should get system env"""
        monkeypatch.setenv("PATH", "/usr/bin:/usr/local/bin")

        config = MCPServerConfig(
            name="test-server",
            transport=TransportType.STDIO,
            command="node",
            args=[]
        )

        captured_params = {}

        mock_workbench_instance = MagicMock()
        mock_workbench_instance.list_tools = AsyncMock(return_value=[])
        mock_workbench_instance.stop = AsyncMock()

        def capture_workbench(server_params):
            captured_params["server_params"] = server_params
            return mock_workbench_instance

        with patch("shutil.which", return_value="/usr/bin/node"), \
             patch("autogen_ext.tools.mcp.McpWorkbench", side_effect=capture_workbench):
            from peak_assistant.streamlit.util.helpers import test_mcp_connection
            success, message = await test_mcp_connection("test-server", config)

        assert success is True
        params = captured_params["server_params"]
        assert "PATH" in params.env
