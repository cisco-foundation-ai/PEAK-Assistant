#!/usr/bin/env python3
"""
Test script for OAuth discovery functionality using /.well-known/oauth-authorization-server endpoint.

This script demonstrates:
1. OAuth discovery from a real OAuth provider (GitHub)
2. Fallback to manual configuration when discovery fails
3. Different discovery scenarios and error handling
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.mcp_config import AuthConfig, AuthType, OAuth2TokenManager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_github_oauth_discovery() -> None:
    """Test OAuth discovery using GitHub's well-known endpoint"""
    print("\n=== Testing GitHub OAuth Discovery ===")

    # GitHub supports OAuth discovery at https://github.com/.well-known/oauth_authorization_server
    auth_config = AuthConfig(
        type=AuthType.OAUTH2_AUTHORIZATION_CODE,
        client_id="test-client-id",
        client_secret="test-client-secret",
        scope="read:user",
        discovery_url="https://github.com",
        enable_discovery=True,
        discovery_timeout=10,
        redirect_uri="https://localhost:8000/oauth/callback",
    )

    token_manager = OAuth2TokenManager(auth_config)

    # Test discovery
    try:
        discovered_config = await token_manager.discover_oauth_endpoints()
        if discovered_config:
            print("✅ GitHub OAuth discovery successful!")
            print(f"   Token endpoint: {discovered_config.get('token_endpoint')}")
            print(
                f"   Authorization endpoint: {discovered_config.get('authorization_endpoint')}"
            )
            print(
                f"   Supported scopes: {discovered_config.get('scopes_supported', 'Not specified')}"
            )

            # Test getting effective URLs
            token_url = await token_manager.get_effective_token_url()
            auth_url = await token_manager.get_effective_authorization_url()
            print(f"   Effective token URL: {token_url}")
            print(f"   Effective auth URL: {auth_url}")

            # Test authorization URL generation
            full_auth_url = await token_manager.get_authorization_url("test_state_123")
            print(f"   Generated auth URL: {full_auth_url[:100]}...")

        else:
            print("❌ GitHub OAuth discovery failed")

    except Exception as e:
        print(f"❌ Error during GitHub discovery: {e}")


async def test_fallback_to_manual_config() -> None:
    """Test fallback to manual configuration when discovery fails"""
    print("\n=== Testing Fallback to Manual Configuration ===")

    # Configure with manual URLs and a non-existent discovery URL
    auth_config = AuthConfig(
        type=AuthType.OAUTH2_AUTHORIZATION_CODE,
        client_id="test-client-id",
        client_secret="test-client-secret",
        scope="read write",
        discovery_url="https://nonexistent-oauth-server.example.com",
        enable_discovery=True,
        discovery_timeout=5,
        # Manual fallback URLs
        token_url="https://manual.example.com/oauth/token",
        authorization_url="https://manual.example.com/oauth/authorize",
        redirect_uri="https://localhost:8000/oauth/callback",
    )

    token_manager = OAuth2TokenManager(auth_config)

    try:
        # Discovery should fail, but manual config should work
        discovered_config = await token_manager.discover_oauth_endpoints()
        if discovered_config is None:
            print("✅ Discovery correctly failed for non-existent server")

        # Should fall back to manual configuration
        token_url = await token_manager.get_effective_token_url()
        auth_url = await token_manager.get_effective_authorization_url()

        print("✅ Fallback successful!")
        print(f"   Token URL (manual): {token_url}")
        print(f"   Auth URL (manual): {auth_url}")

        # Test authorization URL generation with fallback
        full_auth_url = await token_manager.get_authorization_url("fallback_state")
        print(f"   Generated auth URL: {full_auth_url}")

    except Exception as e:
        print(f"❌ Error during fallback test: {e}")


async def test_manual_config_precedence() -> None:
    """Test that manual configuration takes precedence over discovery"""
    print("\n=== Testing Manual Config Precedence ===")

    # Configure with both discovery and manual URLs - manual should win
    auth_config = AuthConfig(
        type=AuthType.OAUTH2_AUTHORIZATION_CODE,
        client_id="test-client-id",
        client_secret="test-client-secret",
        scope="read",
        discovery_url="https://github.com",
        enable_discovery=True,
        # Manual URLs should take precedence
        token_url="https://manual-override.example.com/oauth/token",
        authorization_url="https://manual-override.example.com/oauth/authorize",
        redirect_uri="https://localhost:8000/oauth/callback",
    )

    token_manager = OAuth2TokenManager(auth_config)

    try:
        # Get effective URLs - should use manual config despite discovery being enabled
        token_url = await token_manager.get_effective_token_url()
        auth_url = await token_manager.get_effective_authorization_url()

        if (
            "manual-override.example.com" in token_url
            and "manual-override.example.com" in auth_url
        ):
            print("✅ Manual configuration correctly takes precedence over discovery")
            print(f"   Token URL: {token_url}")
            print(f"   Auth URL: {auth_url}")
        else:
            print("❌ Manual configuration precedence failed")

    except Exception as e:
        print(f"❌ Error during precedence test: {e}")


async def test_discovery_disabled() -> None:
    """Test behavior when discovery is disabled"""
    print("\n=== Testing Discovery Disabled ===")

    auth_config = AuthConfig(
        type=AuthType.OAUTH2_AUTHORIZATION_CODE,
        client_id="test-client-id",
        client_secret="test-client-secret",
        discovery_url="https://github.com",
        enable_discovery=False,  # Discovery disabled
        token_url="https://manual.example.com/oauth/token",
        authorization_url="https://manual.example.com/oauth/authorize",
        redirect_uri="https://localhost:8000/oauth/callback",
    )

    token_manager = OAuth2TokenManager(auth_config)

    try:
        # Discovery should be skipped
        discovered_config = await token_manager.discover_oauth_endpoints()
        if discovered_config is None:
            print("✅ Discovery correctly skipped when disabled")

        # Should use manual configuration only
        token_url = await token_manager.get_effective_token_url()
        auth_url = await token_manager.get_effective_authorization_url()

        if "manual.example.com" in token_url and "manual.example.com" in auth_url:
            print("✅ Manual configuration used when discovery disabled")
        else:
            print("❌ Failed to use manual configuration when discovery disabled")

    except Exception as e:
        print(f"❌ Error during discovery disabled test: {e}")


async def test_client_credentials_discovery() -> None:
    """Test OAuth discovery with client credentials flow"""
    print("\n=== Testing Client Credentials Discovery ===")

    auth_config = AuthConfig(
        type=AuthType.OAUTH2_CLIENT_CREDENTIALS,
        client_id="test-client-id",
        client_secret="test-client-secret",
        scope="api:read",
        discovery_url="https://github.com",
        enable_discovery=True,
        discovery_timeout=10,
    )

    token_manager = OAuth2TokenManager(auth_config)

    try:
        # Test discovery for client credentials flow
        discovered_config = await token_manager.discover_oauth_endpoints()
        if discovered_config:
            print("✅ Discovery successful for client credentials flow")

            # Only token URL is needed for client credentials
            token_url = await token_manager.get_effective_token_url()
            print(f"   Token URL: {token_url}")

            # Authorization URL should fail for client credentials
            try:
                auth_url = await token_manager.get_effective_authorization_url()
                print(f"⚠️  Authorization URL available but not needed: {auth_url}")
            except ValueError:
                print(
                    "✅ Authorization URL correctly not needed for client credentials"
                )

        else:
            print("❌ Discovery failed for client credentials flow")

    except Exception as e:
        print(f"❌ Error during client credentials discovery test: {e}")


async def main():
    """Run all OAuth discovery tests"""
    print("OAuth Discovery Test Suite")
    print("=" * 50)

    tests = [
        test_github_oauth_discovery,
        test_fallback_to_manual_config,
        test_manual_config_precedence,
        test_discovery_disabled,
        test_client_credentials_discovery,
    ]

    for test_func in tests:
        try:
            await test_func()
        except Exception as e:
            print(f"❌ Test {test_func.__name__} failed with error: {e}")

        print()  # Add spacing between tests

    print("=" * 50)
    print("OAuth Discovery Test Suite Complete")


if __name__ == "__main__":
    asyncio.run(main())
