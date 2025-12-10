# Custom Authentication for LLM Providers

This guide explains how to implement custom authentication for Azure OpenAI providers that require non-standard authentication flows, such as OAuth2 gateways or enterprise proxies.

## Overview

By default, Azure OpenAI providers use a static API key for authentication. However, some enterprise deployments require:

- **OAuth2 authentication** - Token-based auth with automatic refresh
- **Custom headers** - Additional parameters like user identifiers or routing keys
- **Enterprise gateways** - Proxies that wrap Azure OpenAI with corporate auth

The `auth_module` feature allows you to implement custom authentication logic in a separate Python module that integrates seamlessly with the existing configuration system.

## When to Use Custom Authentication

Use `auth_module` when your Azure OpenAI deployment requires:

1. **OAuth2 Client Credentials Flow** - Your organization's identity provider issues short-lived tokens
2. **Token Refresh** - Credentials expire and must be refreshed automatically
3. **Additional Parameters** - The API requires extra fields like `user` for routing or auditing
4. **Private Implementation** - You need to keep authentication details separate from the public codebase

## Configuration

### Provider Configuration

Add `auth_module` to your Azure provider in `model_config.json`:

```json
{
  "providers": {
    "azure-enterprise": {
      "type": "azure",
      "auth_module": "my_auth.enterprise_oauth",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_version": "2025-04-01-preview",
        "client_id": "${OAUTH_CLIENT_ID}",
        "client_secret": "${OAUTH_CLIENT_SECRET}",
        "token_endpoint": "${OAUTH_TOKEN_ENDPOINT}"
      }
    }
  }
}
```

**Key points:**
- `auth_module` is a Python module path (e.g., `my_package.my_module`)
- `api_key` is **not required** when `auth_module` is specified
- All fields in `config` are passed to your auth module's `get_credentials()` function
- Use environment variable interpolation (`${VAR}`) for secrets

### Environment Variables

Store sensitive values in your `.env` file:

```bash
AZURE_OPENAI_ENDPOINT=https://your-gateway.example.com
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
OAUTH_TOKEN_ENDPOINT=https://identity.example.com/oauth2/token
```

## Implementing an Auth Module

### Required Interface

Your auth module must expose an async function named `get_credentials`:

```python
async def get_credentials(config: dict) -> dict:
    """
    Obtain authentication credentials for the Azure OpenAI client.
    
    Args:
        config: The provider's config dict from model_config.json
                (with environment variables already interpolated)
    
    Returns:
        A dict containing at minimum:
        - "api_key": The authentication token/key (required)
        
        Optionally:
        - "user": A string parameter passed to the API (for routing/auditing)
        - Any other parameters supported by AzureOpenAIChatCompletionClient
    
    Raises:
        Any exception will be wrapped in ModelConfigError with context
    """
    pass
```

### Complete Example

Here's a complete implementation with OAuth2 client credentials flow and token caching:

```python
# my_auth/enterprise_oauth.py
"""
Custom OAuth2 authentication for enterprise Azure OpenAI gateway.

This module implements the OAuth2 Client Credentials flow with:
- Automatic token caching
- Token refresh before expiration
- Custom user parameter for gateway routing
"""

import aiohttp
import base64
import time
from typing import Any


# Module-level token cache
_token_cache: dict[str, Any] = {
    "access_token": None,
    "expires_at": 0,
}


async def get_credentials(config: dict) -> dict[str, str]:
    """
    Get authentication credentials using OAuth2 Client Credentials flow.
    
    Required config fields:
        - client_id: OAuth client ID
        - client_secret: OAuth client secret
        - token_endpoint: OAuth token endpoint URL
    
    Optional config fields:
        - app_key: Application key for gateway routing (included in 'user' param)
    
    Returns:
        Dict with 'api_key' and optionally 'user'
    """
    # Validate required config
    required = ["client_id", "client_secret", "token_endpoint"]
    missing = [f for f in required if f not in config]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")
    
    # Get or refresh token
    access_token = await _get_access_token(config)
    
    result = {"api_key": access_token}
    
    # Add optional user parameter if app_key is configured
    if "app_key" in config:
        result["user"] = f'{{"appkey": "{config["app_key"]}"}}'
    
    return result


async def _get_access_token(config: dict) -> str:
    """Get a valid access token, refreshing if needed."""
    global _token_cache
    
    # Return cached token if still valid (with 60-second buffer)
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]
    
    # Refresh the token
    await _refresh_token(config)
    return _token_cache["access_token"]


async def _refresh_token(config: dict) -> None:
    """Fetch a new access token from the OAuth endpoint."""
    global _token_cache
    
    client_id = config["client_id"]
    client_secret = config["client_secret"]
    token_endpoint = config["token_endpoint"]
    
    # Prepare HTTP Basic authentication header
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    
    # OAuth2 client credentials grant
    payload = "grant_type=client_credentials"
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(token_endpoint, headers=headers, data=payload) as response:
                response.raise_for_status()
                token_data = await response.json()
        
        # Cache the token
        _token_cache["access_token"] = token_data["access_token"]
        
        # Set expiration (default 1 hour, refresh 60 seconds early)
        expires_in = token_data.get("expires_in", 3600)
        _token_cache["expires_at"] = time.time() + expires_in - 60
        
    except aiohttp.ClientError as e:
        _token_cache["access_token"] = None
        _token_cache["expires_at"] = 0
        raise RuntimeError(f"Failed to obtain access token: {e}") from e


# Optional: Function to clear the token cache (useful for testing)
def clear_token_cache() -> None:
    """Clear the cached token, forcing a refresh on next request."""
    global _token_cache
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = 0
```

### Module Structure

Organize your auth module as a Python package:

```
my_auth/
├── __init__.py
└── enterprise_oauth.py
```

The `__init__.py` can be empty or re-export `get_credentials`:

```python
# my_auth/__init__.py
from .enterprise_oauth import get_credentials

__all__ = ["get_credentials"]
```

Then reference it as `my_auth` or `my_auth.enterprise_oauth` in your config.

## Return Value Reference

The dict returned by `get_credentials()` can include:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `api_key` | `str` | Yes | Authentication token passed to the Azure client |
| `user` | `str` | No | User identifier string (often JSON) for routing or auditing |

These values are merged into the client parameters, so `api_key` becomes the bearer token and `user` is passed as-is to the API.

## Error Handling

### In Your Auth Module

Raise exceptions with clear error messages:

```python
async def get_credentials(config: dict) -> dict:
    # Validate config
    if "client_id" not in config:
        raise ValueError("Missing required 'client_id' in provider config")
    
    try:
        token = await fetch_token(config)
    except aiohttp.ClientError as e:
        raise RuntimeError(f"OAuth token request failed: {e}") from e
    
    return {"api_key": token}
```

### Error Messages You May See

| Error | Cause | Solution |
|-------|-------|----------|
| `Failed to import auth_module 'X'` | Module not found or import error | Check module path and that it's installed/importable |
| `Auth module 'X' must expose an async 'get_credentials(config)' function` | Missing function | Add `async def get_credentials(config)` to your module |
| `Auth module 'X' get_credentials() must return a dict` | Wrong return type | Return a dict, not a string or other type |
| `Auth module 'X' get_credentials() must return a dict with 'api_key'` | Missing api_key | Include `"api_key"` in the returned dict |
| `Auth module 'X' get_credentials() failed: ...` | Exception in your code | Check your implementation and the error message |

## Testing Your Auth Module

### Unit Testing

```python
# tests/test_my_auth.py
import pytest
from my_auth.enterprise_oauth import get_credentials, clear_token_cache


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear token cache before each test."""
    clear_token_cache()
    yield
    clear_token_cache()


@pytest.mark.asyncio
async def test_get_credentials_missing_config():
    """Test that missing config raises ValueError."""
    with pytest.raises(ValueError, match="Missing required"):
        await get_credentials({})


@pytest.mark.asyncio
async def test_get_credentials_success(mocker):
    """Test successful token fetch."""
    # Mock the aiohttp request
    mock_response = mocker.AsyncMock()
    mock_response.json.return_value = {
        "access_token": "test-token-123",
        "expires_in": 3600
    }
    mock_response.raise_for_status = mocker.Mock()
    
    mock_session = mocker.AsyncMock()
    mock_session.post.return_value.__aenter__.return_value = mock_response
    
    mocker.patch("aiohttp.ClientSession", return_value=mock_session)
    
    config = {
        "client_id": "test-client",
        "client_secret": "test-secret",
        "token_endpoint": "https://auth.example.com/token",
        "app_key": "my-app"
    }
    
    result = await get_credentials(config)
    
    assert result["api_key"] == "test-token-123"
    assert '"appkey": "my-app"' in result["user"]
```

### Integration Testing

Test with the actual configuration validation:

```bash
# Validate your config works
uv run python scripts/validate_model_config.py

# The output should show your provider with "Auth: my_auth.enterprise_oauth (custom module)"
```

## Security Best Practices

1. **Never commit secrets** - Use environment variables for client IDs, secrets, and endpoints
2. **Keep auth modules private** - Add your auth module directory to `.gitignore` if it contains proprietary logic
3. **Use HTTPS** - Always use HTTPS for token endpoints
4. **Minimize token lifetime** - Refresh tokens early (the example refreshes 60 seconds before expiration)
5. **Handle errors gracefully** - Clear cached tokens on auth failures to force re-authentication
6. **Log carefully** - Never log tokens or secrets; log only non-sensitive metadata

### Keeping Auth Modules Private

If your auth implementation is proprietary, add it to `.gitignore`:

```gitignore
# Private auth modules
private_auth/
my_auth/
```

## Troubleshooting

### Token Not Refreshing

If you're getting 401 errors after a while:
- Check that `expires_at` is being set correctly
- Ensure you're refreshing before expiration (e.g., 60 seconds early)
- Verify the token endpoint returns `expires_in`

### Module Import Errors

If you see "Failed to import auth_module":
- Verify the module path is correct (use dots, not slashes)
- Ensure the module is in your Python path
- Check for syntax errors in your module
- Verify all dependencies (like `aiohttp`) are installed

### Config Not Passed Correctly

If your auth module isn't receiving expected config values:
- Remember that environment variables are interpolated before being passed
- Check that your `.env` file is being loaded
- Use the validation script to see the resolved config

## Example Configurations

### OAuth2 with User Routing

```json
{
  "providers": {
    "azure-gateway": {
      "type": "azure",
      "auth_module": "my_auth.oauth_gateway",
      "config": {
        "endpoint": "${GATEWAY_ENDPOINT}",
        "api_version": "2025-04-01-preview",
        "client_id": "${OAUTH_CLIENT_ID}",
        "client_secret": "${OAUTH_CLIENT_SECRET}",
        "token_endpoint": "${OAUTH_TOKEN_ENDPOINT}",
        "app_key": "${GATEWAY_APP_KEY}"
      }
    }
  }
}
```

### Multiple Providers (Standard + Custom)

```json
{
  "providers": {
    "azure-direct": {
      "type": "azure",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_key": "${AZURE_OPENAI_API_KEY}",
        "api_version": "2025-04-01-preview"
      }
    },
    "azure-enterprise": {
      "type": "azure",
      "auth_module": "my_auth.enterprise",
      "config": {
        "endpoint": "${ENTERPRISE_ENDPOINT}",
        "api_version": "2025-04-01-preview",
        "client_id": "${ENTERPRISE_CLIENT_ID}",
        "client_secret": "${ENTERPRISE_CLIENT_SECRET}",
        "token_endpoint": "${ENTERPRISE_TOKEN_ENDPOINT}"
      }
    }
  },
  "defaults": {
    "provider": "azure-direct",
    "model": "gpt-4o",
    "deployment": "gpt-4o"
  },
  "agents": {
    "hunt_planner": {
      "provider": "azure-enterprise",
      "model": "gpt-4o",
      "deployment": "gpt-4o-enterprise"
    }
  }
}
```

## Using Custom Auth with Docker

The standard PEAK Assistant Docker image supports custom auth modules via volume mounts - no custom image required.

### Mount Your Auth Module

Mount your auth module directory and config file to the container's working directory (`/home/peakassistant`):

```bash
docker run \
  -v ./my_auth:/home/peakassistant/my_auth \
  -v ./model_config.json:/home/peakassistant/model_config.json \
  -v ./mcp_servers.json:/home/peakassistant/mcp_servers.json \
  -e OAUTH_CLIENT_ID=your-client-id \
  -e OAUTH_CLIENT_SECRET=your-client-secret \
  -e OAUTH_TOKEN_ENDPOINT=https://identity.example.com/token \
  -p 8501:8501 \
  peak-assistant
```

### Directory Structure

Your local directory should look like:

```
./
├── my_auth/
│   ├── __init__.py
│   └── enterprise_oauth.py
├── model_config.json
└── mcp_servers.json
```

### Config Reference

Your `model_config.json` references the module as mounted:

```json
{
  "providers": {
    "azure-enterprise": {
      "type": "azure",
      "auth_module": "my_auth.enterprise_oauth",
      "config": {
        "endpoint": "${AZURE_OPENAI_ENDPOINT}",
        "api_version": "2025-04-01-preview",
        "client_id": "${OAUTH_CLIENT_ID}",
        "client_secret": "${OAUTH_CLIENT_SECRET}",
        "token_endpoint": "${OAUTH_TOKEN_ENDPOINT}"
      }
    }
  }
}
```

### Docker Compose Example

```yaml
version: '3.8'
services:
  peak-assistant:
    image: peak-assistant:latest
    ports:
      - "8501:8501"
    volumes:
      - ./my_auth:/home/peakassistant/my_auth:ro
      - ./model_config.json:/home/peakassistant/model_config.json:ro
      - ./mcp_servers.json:/home/peakassistant/mcp_servers.json:ro
    environment:
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
      - OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID}
      - OAUTH_CLIENT_SECRET=${OAUTH_CLIENT_SECRET}
      - OAUTH_TOKEN_ENDPOINT=${OAUTH_TOKEN_ENDPOINT}
```

**Note:** The `:ro` suffix mounts volumes as read-only for security.

### Alternative: Custom Mount Location

If you prefer to mount your auth module elsewhere, set `PYTHONPATH` to the parent directory:

```bash
docker run \
  -v ./my_auth:/opt/custom/my_auth \
  -v ./model_config.json:/home/peakassistant/model_config.json \
  -e PYTHONPATH=/opt/custom \
  -p 8501:8501 \
  peak-assistant
```

The `PYTHONPATH` must point to the **parent** of your module directory (e.g., `/opt/custom` if your module is at `/opt/custom/my_auth`).

## See Also

- [MODEL_CONFIGURATION.md](MODEL_CONFIGURATION.md) - Main configuration reference
- [README.md](README.md) - Getting started guide
