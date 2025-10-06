"""Tests for mcp-status auth checking functionality"""

import pytest
from peak_assistant.mcp_status.__main__ import check_auth_status
from peak_assistant.utils.mcp_config import (
    MCPServerConfig,
    AuthConfig,
    AuthType,
    TransportType,
)


def test_check_auth_status_no_auth():
    """Test server with no authentication"""
    config = MCPServerConfig(
        name="test",
        transport=TransportType.STDIO,
        command="test"
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "ready"
    assert configured == []
    assert missing == []


def test_check_auth_status_bearer_configured():
    """Test bearer auth with token configured"""
    config = MCPServerConfig(
        name="test",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.BEARER,
            token="my_token"
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "ready"
    assert configured == []
    assert missing == []


def test_check_auth_status_bearer_missing():
    """Test bearer auth without token configured"""
    config = MCPServerConfig(
        name="test",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.BEARER,
            token=None
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "missing"
    assert configured == []
    assert len(missing) == 1
    assert "Bearer token" in missing[0]


def test_check_auth_status_api_key_configured():
    """Test API key auth with key configured"""
    config = MCPServerConfig(
        name="test",
        transport=TransportType.HTTP,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.API_KEY,
            api_key="my_key",
            header_name="X-API-Key"
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "ready"
    assert configured == []
    assert missing == []


def test_check_auth_status_oauth_all_set(monkeypatch):
    """Test OAuth server with all credentials set"""
    monkeypatch.setenv("PEAK_MCP_TEST_TOKEN", "token")
    monkeypatch.setenv("PEAK_MCP_TEST_USER_ID", "user")
    
    config = MCPServerConfig(
        name="test",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=True
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "ready"
    assert "PEAK_MCP_TEST_TOKEN" in configured
    assert "PEAK_MCP_TEST_USER_ID" in configured
    assert missing == []


def test_check_auth_status_oauth_partial(monkeypatch):
    """Test OAuth server with only token set"""
    monkeypatch.setenv("PEAK_MCP_TEST_TOKEN", "token")
    
    config = MCPServerConfig(
        name="test",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=True
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "partial"
    assert "PEAK_MCP_TEST_TOKEN" in configured
    assert "PEAK_MCP_TEST_USER_ID" in missing


def test_check_auth_status_oauth_all_missing():
    """Test OAuth server with no credentials set"""
    config = MCPServerConfig(
        name="test-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=True
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "missing"
    assert configured == []
    assert "PEAK_MCP_TEST_SERVER_TOKEN" in missing
    assert "PEAK_MCP_TEST_SERVER_USER_ID" in missing


def test_check_auth_status_oauth_no_user_auth_required(monkeypatch):
    """Test OAuth server without user auth requirement"""
    monkeypatch.setenv("PEAK_MCP_SIMPLE_TOKEN", "token")
    
    config = MCPServerConfig(
        name="simple",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=False
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "ready"
    assert "PEAK_MCP_SIMPLE_TOKEN" in configured
    assert missing == []


def test_check_auth_status_oauth_hyphenated_name(monkeypatch):
    """Test OAuth server with hyphens in name"""
    monkeypatch.setenv("PEAK_MCP_MY_TEST_SERVER_TOKEN", "token")
    
    config = MCPServerConfig(
        name="my-test-server",
        transport=TransportType.SSE,
        url="https://example.com",
        auth=AuthConfig(
            type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            requires_user_auth=False
        )
    )
    
    status, configured, missing = check_auth_status(config)
    
    assert status == "ready"
    assert "PEAK_MCP_MY_TEST_SERVER_TOKEN" in configured
    assert missing == []
