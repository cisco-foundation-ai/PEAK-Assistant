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
# SPDX-LICENSE-Identifier: MIT

"""
Integration tests for MCP configuration loading.

Tests verify that MCP server configurations can be loaded correctly
from JSON files and that the consolidated data classes work properly
across different modules.
"""

import json
import pytest
import tempfile
from pathlib import Path
from peak_assistant.utils.mcp_config import (
    MCPConfigManager,
    AuthType,
    TransportType,
    AuthConfig,
    MCPServerConfig
)
from peak_assistant.utils import ConfigInterpolationError


@pytest.fixture
def temp_config_file():
    """Create a temporary MCP configuration file"""
    config_data = {
        "mcpServers": {
            "test-stdio-server": {
                "transport": "stdio",
                "command": "node",
                "args": ["server.js"],
                "env": {
                    "NODE_ENV": "production"
                },
                "description": "Test stdio server",
                "timeout": 60
            },
            "test-http-bearer": {
                "transport": "http",
                "url": "https://api.example.com/mcp",
                "auth": {
                    "type": "bearer",
                    "token": "test_bearer_token"
                },
                "description": "Test HTTP server with bearer auth"
            },
            "test-http-api-key": {
                "transport": "http",
                "url": "https://api.example.com/mcp",
                "auth": {
                    "type": "api_key",
                    "api_key": "test_api_key",
                    "header_name": "X-API-Key"
                },
                "description": "Test HTTP server with API key"
            },
            "test-sse-oauth": {
                "transport": "sse",
                "url": "https://api.example.com/sse",
                "auth": {
                    "type": "oauth2_authorization_code",
                    "client_id": "test_client_id",
                    "discovery_url": "https://auth.example.com",
                    "requires_user_auth": True,
                    "enable_discovery": True
                },
                "description": "Test SSE server with OAuth",
                "timeout": 300
            }
        },
        "serverGroups": {
            "research-external": ["test-http-bearer"],
            "research-internal": ["test-stdio-server"],
            "data-discovery": ["test-sse-oauth"]
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f, indent=2)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


class TestMCPConfigLoading:
    """Test MCP configuration loading from JSON files"""
    
    def test_load_config_file(self, temp_config_file):
        """Test loading MCP configuration from file"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        
        # Verify servers were loaded
        assert len(config_manager.servers) == 4
        assert "test-stdio-server" in config_manager.servers
        assert "test-http-bearer" in config_manager.servers
        assert "test-http-api-key" in config_manager.servers
        assert "test-sse-oauth" in config_manager.servers
    
    def test_load_stdio_server_config(self, temp_config_file):
        """Test loading stdio server configuration"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        config = config_manager.get_server_config("test-stdio-server")
        
        assert config is not None
        assert config.name == "test-stdio-server"
        assert config.transport == TransportType.STDIO
        assert config.command == "node"
        assert config.args == ["server.js"]
        assert config.env == {"NODE_ENV": "production"}
        assert config.description == "Test stdio server"
        assert config.timeout == 60
    
    def test_load_http_bearer_config(self, temp_config_file):
        """Test loading HTTP server with bearer auth"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        config = config_manager.get_server_config("test-http-bearer")
        
        assert config is not None
        assert config.transport == TransportType.HTTP
        assert config.url == "https://api.example.com/mcp"
        assert config.auth is not None
        assert config.auth.type == AuthType.BEARER
        assert config.auth.token == "test_bearer_token"
    
    def test_load_http_api_key_config(self, temp_config_file):
        """Test loading HTTP server with API key auth"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        config = config_manager.get_server_config("test-http-api-key")
        
        assert config is not None
        assert config.auth is not None
        assert config.auth.type == AuthType.API_KEY
        assert config.auth.api_key == "test_api_key"
        assert config.auth.header_name == "X-API-Key"
    
    def test_load_sse_oauth_config(self, temp_config_file):
        """Test loading SSE server with OAuth"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        config = config_manager.get_server_config("test-sse-oauth")
        
        assert config is not None
        assert config.transport == TransportType.SSE
        assert config.url == "https://api.example.com/sse"
        assert config.auth is not None
        assert config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE
        assert config.auth.client_id == "test_client_id"
        assert config.auth.discovery_url == "https://auth.example.com"
        assert config.auth.requires_user_auth is True
        assert config.auth.enable_discovery is True
        assert config.timeout == 300
    
    def test_load_server_groups(self, temp_config_file):
        """Test loading server groups"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        
        # Test research-external group
        external_servers = config_manager.get_server_group("research-external")
        assert external_servers == ["test-http-bearer"]
        
        # Test research-internal group
        internal_servers = config_manager.get_server_group("research-internal")
        assert internal_servers == ["test-stdio-server"]
        
        # Test data-discovery group
        data_servers = config_manager.get_server_group("data-discovery")
        assert data_servers == ["test-sse-oauth"]
    
    def test_list_all_servers(self, temp_config_file):
        """Test listing all configured servers"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        servers = config_manager.list_servers()
        
        assert len(servers) == 4
        assert "test-stdio-server" in servers
        assert "test-http-bearer" in servers
        assert "test-http-api-key" in servers
        assert "test-sse-oauth" in servers
    
    def test_list_all_groups(self, temp_config_file):
        """Test listing all configured groups"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        groups = config_manager.list_groups()
        
        assert len(groups) == 3
        assert "research-external" in groups
        assert "research-internal" in groups
        assert "data-discovery" in groups
    
    def test_get_nonexistent_server(self, temp_config_file):
        """Test getting configuration for nonexistent server"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        config = config_manager.get_server_config("nonexistent-server")
        
        assert config is None
    
    def test_get_nonexistent_group(self, temp_config_file):
        """Test getting nonexistent server group"""
        config_manager = MCPConfigManager(config_file=temp_config_file)
        servers = config_manager.get_server_group("nonexistent-group")
        
        assert servers == []


class TestConfigValidation:
    """Test configuration validation and error handling"""
    
    def test_invalid_transport_type(self):
        """Test that invalid transport type raises error"""
        config_data = {
            "mcpServers": {
                "invalid-server": {
                    "transport": "invalid_transport",
                    "url": "https://example.com"
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError):
                MCPConfigManager(config_file=temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_invalid_auth_type(self):
        """Test that invalid auth type raises error"""
        config_data = {
            "mcpServers": {
                "invalid-auth-server": {
                    "transport": "http",
                    "url": "https://example.com",
                    "auth": {
                        "type": "invalid_auth_type"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError):
                MCPConfigManager(config_file=temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_missing_config_file(self):
        """Test handling of missing configuration file"""
        # MCPConfigManager doesn't raise an error for missing files,
        # it just logs an error and continues with empty configuration
        config_manager = MCPConfigManager(config_file="/nonexistent/path/mcp_servers.json")
        
        # Verify that no servers were loaded
        assert len(config_manager.servers) == 0
        assert config_manager.list_servers() == []
    
    def test_malformed_json(self):
        """Test handling of malformed JSON"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name
        
        try:
            with pytest.raises(json.JSONDecodeError):
                MCPConfigManager(config_file=temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestEnvironmentVariableInterpolation:
    """Test environment variable interpolation in config
    
    Environment variable interpolation (${ENV_VAR}) uses the shared
    interpolate_env_vars utility from peak_assistant.utils.
    """
    
    def test_env_var_in_token(self, monkeypatch):
        """Test ${ENV_VAR} interpolation in token field"""
        monkeypatch.setenv("TEST_TOKEN", "secret_token_value")
        
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "http",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "bearer",
                        "token": "${TEST_TOKEN}"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config_manager = MCPConfigManager(config_file=temp_path)
            config = config_manager.get_server_config("test-server")
            
            assert config.auth.token == "secret_token_value"
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_env_var_in_api_key(self, monkeypatch):
        """Test ${ENV_VAR} interpolation in api_key field"""
        monkeypatch.setenv("TEST_API_KEY", "secret_api_key")
        
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "http",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "api_key",
                        "api_key": "${TEST_API_KEY}",
                        "header_name": "X-API-Key"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config_manager = MCPConfigManager(config_file=temp_path)
            config = config_manager.get_server_config("test-server")
            
            assert config.auth.api_key == "secret_api_key"
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_env_var_in_client_secret(self, monkeypatch):
        """Test ${ENV_VAR} interpolation in client_secret field"""
        monkeypatch.setenv("OAUTH_CLIENT_SECRET", "secret_client_secret")
        
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "sse",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "oauth2_authorization_code",
                        "client_id": "test_client",
                        "client_secret": "${OAUTH_CLIENT_SECRET}",
                        "token_url": "https://auth.example.com/token"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config_manager = MCPConfigManager(config_file=temp_path)
            config = config_manager.get_server_config("test-server")
            
            assert config.auth.client_secret == "secret_client_secret"
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_env_var_in_env_dict(self, monkeypatch):
        """Test ${ENV_VAR} interpolation in stdio server env dictionary"""
        monkeypatch.setenv("TAVILY_API_KEY", "test_tavily_key")
        
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "tavily-mcp"],
                    "env": {
                        "TAVILY_API_KEY": "${TAVILY_API_KEY}"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config_manager = MCPConfigManager(config_file=temp_path)
            config = config_manager.get_server_config("test-server")
            
            assert config.env["TAVILY_API_KEY"] == "test_tavily_key"
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_env_var_with_default(self):
        """Test ${ENV_VAR|default} syntax"""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "http",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "bearer",
                        "token": "${MISSING_TOKEN|default_token_value}"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config_manager = MCPConfigManager(config_file=temp_path)
            config = config_manager.get_server_config("test-server")
            
            assert config.auth.token == "default_token_value"
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_env_var_null_default(self):
        """Test ${ENV_VAR|null} returns empty string"""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "http",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "bearer",
                        "token": "${MISSING_TOKEN|null}"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config_manager = MCPConfigManager(config_file=temp_path)
            config = config_manager.get_server_config("test-server")
            
            assert config.auth.token == ""
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_env_var_in_url(self, monkeypatch):
        """Test ${ENV_VAR} interpolation in URL field"""
        monkeypatch.setenv("API_KEY", "test_key_123")
        
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "http",
                    "url": "https://api.example.com/mcp?key=${API_KEY}",
                    "auth": {
                        "type": "none"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            config_manager = MCPConfigManager(config_file=temp_path)
            config = config_manager.get_server_config("test-server")
            
            assert config.url == "https://api.example.com/mcp?key=test_key_123"
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_missing_env_var_no_default(self):
        """Test that missing env var without default raises ConfigInterpolationError"""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "http",
                    "url": "https://api.example.com",
                    "auth": {
                        "type": "bearer",
                        "token": "${MISSING_TOKEN}"
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ConfigInterpolationError, match="MISSING_TOKEN"):
                MCPConfigManager(config_file=temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestCrossModuleCompatibility:
    """Test that configurations work across different modules"""
    
    def test_config_from_mcp_config_used_in_helpers(self, temp_config_file):
        """Test that config loaded in mcp_config can be used in helpers"""
        from peak_assistant.utils.mcp_config import MCPConfigManager
        from peak_assistant.streamlit.util.helpers import (
            AuthType as HelpersAuthType,
            TransportType as HelpersTransportType
        )
        
        config_manager = MCPConfigManager(config_file=temp_config_file)
        config = config_manager.get_server_config("test-http-bearer")
        
        # Verify config uses the same enum types as helpers
        assert isinstance(config.transport, HelpersTransportType)
        assert isinstance(config.auth.type, HelpersAuthType)
        assert config.transport == HelpersTransportType.HTTP
        assert config.auth.type == HelpersAuthType.BEARER
    
    def test_config_created_in_helpers_compatible_with_mcp_config(self):
        """Test that config created using helpers classes works with mcp_config"""
        from peak_assistant.streamlit.util.helpers import (
            AuthType,
            TransportType,
            AuthConfig,
            MCPServerConfig
        )
        from peak_assistant.utils.mcp_config import (
            AuthType as MCPAuthType,
            TransportType as MCPTransportType
        )
        
        # Create config using helpers imports
        auth = AuthConfig(type=AuthType.BEARER, token="test")
        config = MCPServerConfig(
            name="test",
            transport=TransportType.HTTP,
            url="https://example.com",
            auth=auth
        )
        
        # Verify it's compatible with mcp_config types
        assert isinstance(config.transport, MCPTransportType)
        assert isinstance(config.auth.type, MCPAuthType)
