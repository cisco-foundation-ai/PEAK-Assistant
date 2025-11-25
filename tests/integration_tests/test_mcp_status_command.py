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

"""Integration tests for mcp-status command"""

import json
import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory for test configs"""
    return tmp_path


def test_mcp_status_basic_output(temp_config_dir):
    """Test basic mcp-status output with valid config"""
    config_file = temp_config_dir / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "test-server": {
                "transport": "stdio",
                "command": "test",
                "args": []
            }
        },
        "serverGroups": {
            "test-group": ["test-server"]
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "mcp-status", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "✓ test-server" in result.stdout
    assert "Status: Ready" in result.stdout
    assert "1 server" in result.stdout
    assert "ready" in result.stdout


def test_mcp_status_oauth_missing_credentials(temp_config_dir):
    """Test mcp-status shows missing OAuth credentials"""
    config_file = temp_config_dir / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "oauth-server": {
                "transport": "sse",
                "url": "https://example.com",
                "auth": {
                    "type": "oauth2_authorization_code",
                    "requires_user_auth": True
                }
            }
        },
        "serverGroups": {
            "test-group": ["oauth-server"]
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "mcp-status", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1  # Should exit with error
    assert "✗ oauth-server" in result.stdout
    assert "Missing credentials" in result.stdout
    assert "PEAK_MCP_OAUTH_SERVER_TOKEN" in result.stdout
    assert "PEAK_MCP_OAUTH_SERVER_USER_ID" in result.stdout
    assert "export PEAK_MCP_OAUTH_SERVER_TOKEN=" in result.stdout


def test_mcp_status_oauth_partial_credentials(temp_config_dir, monkeypatch):
    """Test mcp-status shows partial OAuth configuration"""
    config_file = temp_config_dir / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "oauth-server": {
                "transport": "sse",
                "url": "https://example.com",
                "auth": {
                    "type": "oauth2_authorization_code",
                    "requires_user_auth": True
                }
            }
        },
        "serverGroups": {
            "test-group": ["oauth-server"]
        }
    }))
    
    # Set token but not user ID
    env = {"PEAK_MCP_OAUTH_SERVER_TOKEN": "test_token"}
    
    result = subprocess.run(
        ["uv", "run", "mcp-status", "-c", str(config_file)],
        capture_output=True,
        text=True,
        env={**subprocess.os.environ, **env}
    )
    
    assert result.returncode == 1  # Should exit with error
    assert "⚠ oauth-server" in result.stdout
    assert "Partially configured" in result.stdout
    assert "✓ PEAK_MCP_OAUTH_SERVER_TOKEN" in result.stdout
    assert "✗ PEAK_MCP_OAUTH_SERVER_USER_ID" in result.stdout


def test_mcp_status_verbose_mode(temp_config_dir):
    """Test verbose mode shows additional details"""
    config_file = temp_config_dir / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "test-server": {
                "transport": "stdio",
                "command": "test-command",
                "args": ["arg1", "arg2"],
                "description": "Test server description"
            }
        },
        "serverGroups": {
            "test-group": ["test-server"]
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "mcp-status", "-v", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "Command: test-command" in result.stdout
    assert "Args: arg1 arg2" in result.stdout
    assert "Description: Test server description" in result.stdout
    assert "Configuration file:" in result.stdout


def test_mcp_status_verbose_long_form(temp_config_dir):
    """Test --verbose (long form) works same as -v"""
    config_file = temp_config_dir / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "test-server": {
                "transport": "stdio",
                "command": "test",
                "description": "Test"
            }
        },
        "serverGroups": {
            "test-group": ["test-server"]
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "mcp-status", "--verbose", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "Command: test" in result.stdout
    assert "Description: Test" in result.stdout


def test_mcp_status_no_config_file():
    """Test mcp-status handles missing config file gracefully"""
    result = subprocess.run(
        ["uv", "run", "mcp-status", "-c", "/nonexistent/config.json"],
        capture_output=True,
        text=True
    )
    
    # MCPConfigManager creates empty config if file doesn't exist
    # So we should see "No MCP servers configured" instead
    assert result.returncode == 0
    assert "No MCP servers configured" in result.stdout or "Configuration file: /nonexistent/config.json" in result.stdout


def test_mcp_status_multiple_groups(temp_config_dir):
    """Test mcp-status displays multiple server groups"""
    config_file = temp_config_dir / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "server1": {
                "transport": "stdio",
                "command": "test1"
            },
            "server2": {
                "transport": "stdio",
                "command": "test2"
            }
        },
        "serverGroups": {
            "group1": ["server1"],
            "group2": ["server2"]
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "mcp-status", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "Server Group: group1" in result.stdout
    assert "Server Group: group2" in result.stdout
    assert "✓ server1" in result.stdout
    assert "✓ server2" in result.stdout
    assert "2 servers ready" in result.stdout


def test_mcp_status_mixed_auth_types(temp_config_dir):
    """Test mcp-status with different authentication types"""
    config_file = temp_config_dir / "mcp_servers.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "no-auth": {
                "transport": "stdio",
                "command": "test"
            },
            "bearer-auth": {
                "transport": "sse",
                "url": "https://example.com",
                "auth": {
                    "type": "bearer",
                    "token": "my_token"
                }
            },
            "api-key": {
                "transport": "http",
                "url": "https://example.com",
                "auth": {
                    "type": "api_key",
                    "api_key": "my_key",
                    "header_name": "X-API-Key"
                }
            }
        },
        "serverGroups": {
            "test-group": ["no-auth", "bearer-auth", "api-key"]
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "mcp-status", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "✓ no-auth" in result.stdout
    assert "✓ bearer-auth" in result.stdout
    assert "✓ api-key" in result.stdout
    assert "3 servers ready" in result.stdout


def test_mcp_status_help():
    """Test mcp-status --help displays usage information"""
    result = subprocess.run(
        ["uv", "run", "mcp-status", "--help"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "Display configuration status" in result.stdout
    assert "-v, --verbose" in result.stdout
