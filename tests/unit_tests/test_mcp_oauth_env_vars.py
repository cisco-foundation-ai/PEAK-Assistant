"""Tests for OAuth environment variable authentication in mcp_config"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from peak_assistant.utils.mcp_config import (
    MCPClientManager,
    MCPConfigManager,
    MCPServerConfig,
    AuthConfig,
    AuthType,
    TransportType,
)


@pytest.fixture
def mock_config_manager():
    """Create a mock config manager"""
    manager = MagicMock(spec=MCPConfigManager)
    manager.get_server_config = MagicMock(return_value=None)
    manager.get_server_group = MagicMock(return_value=[])
    manager.user_session_manager = MagicMock()
    return manager


@pytest.fixture
def client_manager(mock_config_manager):
    """Create a client manager for testing"""
    return MCPClientManager(mock_config_manager)


@pytest.mark.asyncio
async def test_oauth_with_token_env_var(monkeypatch, client_manager):
    """Test OAuth authentication using environment variable"""
    monkeypatch.setenv("PEAK_MCP_TEST_SERVER_TOKEN", "test_token_123")
    
    config = MCPServerConfig(
        name="test-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=False
        )
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    assert headers["Authorization"] == "Bearer test_token_123"


@pytest.mark.asyncio
async def test_oauth_with_token_and_user_id_env_vars(monkeypatch, client_manager):
    """Test OAuth with both token and user ID from environment"""
    monkeypatch.setenv("PEAK_MCP_TEST_SERVER_TOKEN", "test_token_123")
    monkeypatch.setenv("PEAK_MCP_TEST_SERVER_USER_ID", "user@example.com")
    
    config = MCPServerConfig(
        name="test-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=True
        )
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    assert headers["Authorization"] == "Bearer test_token_123"
    assert headers["X-User-ID"] == "user@example.com"


@pytest.mark.asyncio
async def test_oauth_missing_required_user_id(monkeypatch, client_manager):
    """Test that missing user ID returns empty headers with warning"""
    monkeypatch.setenv("PEAK_MCP_TEST_SERVER_TOKEN", "test_token_123")
    # Don't set USER_ID
    
    config = MCPServerConfig(
        name="test-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=True
        )
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    # Should return empty when user ID required but missing
    assert headers == {}


@pytest.mark.asyncio
async def test_oauth_no_env_vars_no_streamlit(client_manager):
    """Test OAuth fails gracefully when no credentials available"""
    # No env vars set, Streamlit not running
    
    config = MCPServerConfig(
        name="test-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=False
        )
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    assert headers == {}


@pytest.mark.asyncio
async def test_oauth_env_var_name_formatting(monkeypatch, client_manager):
    """Test that server names with hyphens are converted correctly to env var names"""
    # Server name: "my-test-server" should become "PEAK_MCP_MY_TEST_SERVER_TOKEN"
    monkeypatch.setenv("PEAK_MCP_MY_TEST_SERVER_TOKEN", "test_token_456")
    
    config = MCPServerConfig(
        name="my-test-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=False
        )
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    assert headers["Authorization"] == "Bearer test_token_456"


@pytest.mark.asyncio
async def test_bearer_auth_still_works(client_manager):
    """Test that non-OAuth bearer auth still works as before"""
    config = MCPServerConfig(
        name="bearer-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.BEARER,
            token="static_bearer_token"
        )
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    assert headers["Authorization"] == "Bearer static_bearer_token"


@pytest.mark.asyncio
async def test_api_key_auth_still_works(client_manager):
    """Test that API key auth still works as before"""
    config = MCPServerConfig(
        name="api-key-server",
        transport=TransportType.HTTP,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.API_KEY,
            api_key="my_api_key",
            header_name="X-API-Key"
        )
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    assert headers["X-API-Key"] == "my_api_key"


@pytest.mark.asyncio
async def test_no_auth_returns_empty_headers(client_manager):
    """Test that servers without auth return empty headers"""
    config = MCPServerConfig(
        name="no-auth-server",
        transport=TransportType.STDIO,
        command="test"
    )
    
    headers = await client_manager._get_auth_headers(config)
    
    assert headers == {}
