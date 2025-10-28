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
Unit tests for MCP configuration data classes.

Tests verify that AuthType, TransportType, AuthConfig, and MCPServerConfig
can be imported from both mcp_config.py and helpers.py, ensuring no
code duplication and consistent behavior across the codebase.
"""

import pytest
from peak_assistant.utils.mcp_config import (
    AuthType,
    TransportType,
    AuthConfig,
    MCPServerConfig
)


class TestAuthType:
    """Test AuthType enum values and behavior"""
    
    def test_auth_type_values(self):
        """Test that all expected AuthType values exist"""
        assert AuthType.NONE.value == "none"
        assert AuthType.BEARER.value == "bearer"
        assert AuthType.OAUTH2_CLIENT_CREDENTIALS.value == "oauth2_client_credentials"
        assert AuthType.OAUTH2_AUTHORIZATION_CODE.value == "oauth2_authorization_code"
        assert AuthType.API_KEY.value == "api_key"
    
    def test_auth_type_count(self):
        """Test that AuthType has exactly 5 values"""
        assert len(list(AuthType)) == 5
    
    def test_auth_type_from_string(self):
        """Test creating AuthType from string values"""
        assert AuthType("none") == AuthType.NONE
        assert AuthType("bearer") == AuthType.BEARER
        assert AuthType("oauth2_client_credentials") == AuthType.OAUTH2_CLIENT_CREDENTIALS
        assert AuthType("oauth2_authorization_code") == AuthType.OAUTH2_AUTHORIZATION_CODE
        assert AuthType("api_key") == AuthType.API_KEY
    
    def test_auth_type_invalid_value(self):
        """Test that invalid AuthType value raises ValueError"""
        with pytest.raises(ValueError):
            AuthType("invalid_auth_type")


class TestTransportType:
    """Test TransportType enum values and behavior"""
    
    def test_transport_type_values(self):
        """Test that all expected TransportType values exist"""
        assert TransportType.STDIO.value == "stdio"
        assert TransportType.HTTP.value == "http"
        assert TransportType.SSE.value == "sse"
    
    def test_transport_type_count(self):
        """Test that TransportType has exactly 3 values"""
        assert len(list(TransportType)) == 3
    
    def test_transport_type_from_string(self):
        """Test creating TransportType from string values"""
        assert TransportType("stdio") == TransportType.STDIO
        assert TransportType("http") == TransportType.HTTP
        assert TransportType("sse") == TransportType.SSE
    
    def test_transport_type_invalid_value(self):
        """Test that invalid TransportType value raises ValueError"""
        with pytest.raises(ValueError):
            TransportType("invalid_transport")


class TestAuthConfig:
    """Test AuthConfig dataclass"""
    
    def test_auth_config_minimal(self):
        """Test creating AuthConfig with minimal required fields"""
        config = AuthConfig(type=AuthType.NONE)
        assert config.type == AuthType.NONE
        assert config.token is None
        assert config.requires_user_auth is False
    
    def test_auth_config_bearer(self):
        """Test creating AuthConfig for bearer token authentication"""
        config = AuthConfig(
            type=AuthType.BEARER,
            token="test_token_123"
        )
        assert config.type == AuthType.BEARER
        assert config.token == "test_token_123"
    
    def test_auth_config_api_key(self):
        """Test creating AuthConfig for API key authentication"""
        config = AuthConfig(
            type=AuthType.API_KEY,
            api_key="test_api_key",
            header_name="X-API-Key"
        )
        assert config.type == AuthType.API_KEY
        assert config.api_key == "test_api_key"
        assert config.header_name == "X-API-Key"
    
    def test_auth_config_oauth2_client_credentials(self):
        """Test creating AuthConfig for OAuth2 client credentials flow"""
        config = AuthConfig(
            type=AuthType.OAUTH2_CLIENT_CREDENTIALS,
            client_id="test_client_id",
            client_secret="test_client_secret",
            token_url="https://auth.example.com/token",
            scope="read write"
        )
        assert config.type == AuthType.OAUTH2_CLIENT_CREDENTIALS
        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert config.token_url == "https://auth.example.com/token"
        assert config.scope == "read write"
    
    def test_auth_config_oauth2_authorization_code(self):
        """Test creating AuthConfig for OAuth2 authorization code flow"""
        config = AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            client_id="test_client_id",
            client_secret="test_client_secret",
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            redirect_uri="http://localhost:8501",
            scope="read write",
            requires_user_auth=True
        )
        assert config.type == AuthType.OAUTH2_AUTHORIZATION_CODE
        assert config.authorization_url == "https://auth.example.com/authorize"
        assert config.token_url == "https://auth.example.com/token"
        assert config.redirect_uri == "http://localhost:8501"
        assert config.requires_user_auth is True
    
    def test_auth_config_oauth2_with_discovery(self):
        """Test creating AuthConfig with OAuth discovery enabled"""
        config = AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            discovery_url="https://auth.example.com",
            enable_discovery=True,
            discovery_timeout=10
        )
        assert config.discovery_url == "https://auth.example.com"
        assert config.enable_discovery is True
        assert config.discovery_timeout == 10
    
    def test_auth_config_oauth2_with_dynamic_registration(self):
        """Test creating AuthConfig with dynamic client registration"""
        config = AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            client_registration_url="https://auth.example.com/register",
            redirect_uri="http://localhost:8501"
        )
        assert config.client_registration_url == "https://auth.example.com/register"
        assert config.redirect_uri == "http://localhost:8501"
    
    def test_auth_config_default_header_name(self):
        """Test that default header_name is 'Authorization'"""
        config = AuthConfig(type=AuthType.BEARER, token="test")
        assert config.header_name == "Authorization"
    
    def test_auth_config_default_discovery_settings(self):
        """Test default OAuth discovery settings"""
        config = AuthConfig(type=AuthType.OAUTH2_AUTHORIZATION_CODE)
        assert config.enable_discovery is True
        assert config.discovery_timeout == 10


class TestMCPServerConfig:
    """Test MCPServerConfig dataclass"""
    
    def test_mcp_server_config_minimal(self):
        """Test creating MCPServerConfig with minimal required fields"""
        config = MCPServerConfig(name="test-server")
        assert config.name == "test-server"
        assert config.transport == TransportType.STDIO
        assert config.timeout == 30
    
    def test_mcp_server_config_stdio(self):
        """Test creating MCPServerConfig for stdio transport"""
        config = MCPServerConfig(
            name="stdio-server",
            transport=TransportType.STDIO,
            command="node",
            args=["server.js"],
            env={"NODE_ENV": "production"},
            description="Test stdio server",
            timeout=60
        )
        assert config.name == "stdio-server"
        assert config.transport == TransportType.STDIO
        assert config.command == "node"
        assert config.args == ["server.js"]
        assert config.env == {"NODE_ENV": "production"}
        assert config.description == "Test stdio server"
        assert config.timeout == 60
    
    def test_mcp_server_config_http_with_bearer(self):
        """Test creating MCPServerConfig for HTTP transport with bearer auth"""
        auth = AuthConfig(type=AuthType.BEARER, token="test_token")
        config = MCPServerConfig(
            name="http-server",
            transport=TransportType.HTTP,
            url="https://api.example.com/mcp",
            auth=auth,
            description="Test HTTP server"
        )
        assert config.name == "http-server"
        assert config.transport == TransportType.HTTP
        assert config.url == "https://api.example.com/mcp"
        assert config.auth is not None
        assert config.auth.type == AuthType.BEARER
        assert config.auth.token == "test_token"
    
    def test_mcp_server_config_http_with_api_key(self):
        """Test creating MCPServerConfig for HTTP transport with API key auth"""
        auth = AuthConfig(
            type=AuthType.API_KEY,
            api_key="test_api_key",
            header_name="X-API-Key"
        )
        config = MCPServerConfig(
            name="api-server",
            transport=TransportType.HTTP,
            url="https://api.example.com/mcp",
            auth=auth
        )
        assert config.auth.type == AuthType.API_KEY
        assert config.auth.api_key == "test_api_key"
        assert config.auth.header_name == "X-API-Key"
    
    def test_mcp_server_config_sse_with_oauth(self):
        """Test creating MCPServerConfig for SSE transport with OAuth"""
        auth = AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            client_id="test_client",
            discovery_url="https://auth.example.com",
            requires_user_auth=True
        )
        config = MCPServerConfig(
            name="sse-server",
            transport=TransportType.SSE,
            url="https://api.example.com/sse",
            auth=auth,
            timeout=300
        )
        assert config.name == "sse-server"
        assert config.transport == TransportType.SSE
        assert config.url == "https://api.example.com/sse"
        assert config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE
        assert config.auth.requires_user_auth is True
        assert config.timeout == 300
    
    def test_mcp_server_config_no_auth(self):
        """Test creating MCPServerConfig without authentication"""
        config = MCPServerConfig(
            name="public-server",
            transport=TransportType.HTTP,
            url="https://api.example.com/mcp"
        )
        assert config.auth is None
    
    def test_mcp_server_config_default_timeout(self):
        """Test that default timeout is 30 seconds"""
        config = MCPServerConfig(name="test-server")
        assert config.timeout == 30


class TestImportConsistency:
    """Test that classes can be imported from both locations"""
    
    def test_import_from_mcp_config(self):
        """Test importing from peak_assistant.utils.mcp_config"""
        from peak_assistant.utils.mcp_config import (
            AuthType as AT1,
            TransportType as TT1,
            AuthConfig as AC1,
            MCPServerConfig as MSC1
        )
        assert AT1.BEARER.value == "bearer"
        assert TT1.HTTP.value == "http"
        assert AC1 is not None
        assert MSC1 is not None
    
    def test_import_from_helpers(self):
        """Test importing from peak_assistant.streamlit.util.helpers"""
        from peak_assistant.streamlit.util.helpers import (
            AuthType as AT2,
            TransportType as TT2,
            AuthConfig as AC2,
            MCPServerConfig as MSC2
        )
        assert AT2.BEARER.value == "bearer"
        assert TT2.HTTP.value == "http"
        assert AC2 is not None
        assert MSC2 is not None
    
    def test_same_class_from_both_imports(self):
        """Test that imports from both locations refer to the same class"""
        from peak_assistant.utils.mcp_config import (
            AuthType as AT1,
            TransportType as TT1,
            AuthConfig as AC1,
            MCPServerConfig as MSC1
        )
        from peak_assistant.streamlit.util.helpers import (
            AuthType as AT2,
            TransportType as TT2,
            AuthConfig as AC2,
            MCPServerConfig as MSC2
        )
        
        # Verify they are the exact same class objects
        assert AT1 is AT2
        assert TT1 is TT2
        assert AC1 is AC2
        assert MSC1 is MSC2
    
    def test_enum_values_consistent(self):
        """Test that enum values are consistent across imports"""
        from peak_assistant.utils.mcp_config import AuthType as AT1
        from peak_assistant.streamlit.util.helpers import AuthType as AT2
        
        assert list(AT1) == list(AT2)
        assert [e.value for e in AT1] == [e.value for e in AT2]
    
    def test_dataclass_instances_compatible(self):
        """Test that dataclass instances from different imports are compatible"""
        from peak_assistant.utils.mcp_config import AuthConfig as AC1, AuthType
        from peak_assistant.streamlit.util.helpers import AuthConfig as AC2
        
        # Create instance using class from mcp_config
        config1 = AC1(type=AuthType.BEARER, token="test")
        
        # Verify it's also an instance of the class from helpers
        assert isinstance(config1, AC2)
        
        # Create instance using class from helpers
        config2 = AC2(type=AuthType.API_KEY, api_key="key")
        
        # Verify it's also an instance of the class from mcp_config
        assert isinstance(config2, AC1)


class TestRealWorldScenarios:
    """Test real-world configuration scenarios"""
    
    def test_tavily_search_config(self):
        """Test configuration for Tavily search MCP server"""
        auth = AuthConfig(
            type=AuthType.API_KEY,
            api_key="tvly-test-key",
            header_name="X-API-Key"
        )
        config = MCPServerConfig(
            name="tavily-search",
            transport=TransportType.SSE,
            url="https://api.tavily.com/mcp",
            auth=auth,
            description="Tavily search MCP server"
        )
        assert config.name == "tavily-search"
        assert config.transport == TransportType.SSE
        assert config.auth.type == AuthType.API_KEY
    
    def test_atlassian_remote_mcp_config(self):
        """Test configuration for Atlassian remote MCP server with dynamic registration"""
        auth = AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            discovery_url="https://api.atlassian.com",
            client_registration_url="https://api.atlassian.com/oauth2/register",
            redirect_uri="http://localhost:8501",
            scope="read:jira-work read:confluence-content.all",
            requires_user_auth=True,
            enable_discovery=True
        )
        config = MCPServerConfig(
            name="atlassian-remote-mcp",
            transport=TransportType.SSE,
            url="https://api.atlassian.com/mcp",
            auth=auth,
            description="Atlassian remote MCP server",
            timeout=300
        )
        assert config.name == "atlassian-remote-mcp"
        assert config.auth.requires_user_auth is True
        assert config.auth.client_registration_url is not None
    
    def test_splunk_mcp_config(self):
        """Test configuration for Splunk MCP server (stdio)"""
        config = MCPServerConfig(
            name="splunk-mcp",
            transport=TransportType.STDIO,
            command="npx",
            args=["-y", "@splunk/mcp-server-splunk"],
            env={
                "SPLUNK_SERVER_URL": "https://splunk.example.com:8089",
                "SPLUNK_USERNAME": "admin",
                "SPLUNK_PASSWORD": "changeme"
            },
            description="Splunk MCP server for data discovery"
        )
        assert config.name == "splunk-mcp"
        assert config.transport == TransportType.STDIO
        assert config.command == "npx"
        assert "SPLUNK_SERVER_URL" in config.env
