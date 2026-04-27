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

"""Tests for robust timeout handling in MCP stdio connections."""

from unittest.mock import MagicMock, patch

import pytest

from peak_assistant.utils.mcp_config import MCPClientManager, MCPServerConfig, TransportType


@pytest.fixture
def client_manager():
    """Create an MCPClientManager with a lightweight mocked config manager."""
    manager = MagicMock()
    manager.user_session_manager = MagicMock()
    return MCPClientManager(manager)


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_value", [None, "not-a-number"])
async def test_connect_stdio_server_uses_default_timeout_for_invalid_values(client_manager, timeout_value):
    """Invalid timeout config should not crash stdio server setup."""
    config = MCPServerConfig(
        name="test-server",
        transport=TransportType.STDIO,
        command="echo",
        args=["ok"],
        timeout=timeout_value,
    )

    captured = {}

    class _FakeWorkbench:
        async def __aenter__(self):
            return self

    def _capture_workbench(server_params):
        captured["read_timeout_seconds"] = server_params.read_timeout_seconds
        return _FakeWorkbench()

    with patch("peak_assistant.utils.mcp_config.McpWorkbench", side_effect=_capture_workbench):
        result = await client_manager._connect_stdio_server("test-server", config)

    assert result is True
    assert captured["read_timeout_seconds"] == 30.0
