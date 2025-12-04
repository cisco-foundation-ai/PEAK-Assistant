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

from typing import List, Dict, Any, Optional, Tuple
from autogen_agentchat.messages import TextMessage, UserMessage
import streamlit as st
import hashlib
import json
import os
import secrets
import tempfile
import time
import logging
from urllib.parse import urlparse, urljoin
from pathlib import Path

# Import MCP configuration classes from centralized location
from peak_assistant.utils.mcp_config import (
    AuthType,
    TransportType,
    AuthConfig,
    MCPServerConfig
)

logger = logging.getLogger(__name__)

def get_asset_path(relative_path: str) -> str:
    """Get absolute path to asset relative to streamlit app directory"""
    app_dir = Path(__file__).parent.parent  # Go up from util/ to streamlit/
    return str(app_dir / relative_path)

def get_streamlit_redirect_uri() -> str:
    """
    Get the current Streamlit app's base URL for OAuth redirects.
    Resolution order:
      1) Explicit override via env PEAK_REDIRECT_URI
      2) st.secrets['redirect_uri'] or st.secrets['peak']['redirect_uri']
      3) Streamlit config (browser.serverAddress/server.address, server.port, server.baseUrlPath, TLS)
      4) Streamlit runtime (detect active port, default host localhost)
      5) Default http://localhost:8501
    """
    # 1) Environment override
    try:
        env_uri = os.getenv("PEAK_REDIRECT_URI")
        if env_uri:
            logger.debug(f"Using PEAK_REDIRECT_URI from environment: {env_uri}")
            return env_uri
    except Exception:
        pass

    # 2) Secrets override
    try:
        secret_uri = None
        if hasattr(st, "secrets"):
            if "redirect_uri" in st.secrets:
                secret_uri = st.secrets["redirect_uri"]
            elif "peak" in st.secrets and isinstance(st.secrets["peak"], dict):
                secret_uri = st.secrets["peak"].get("redirect_uri")
        if secret_uri:
            logger.debug(f"Using redirect_uri from st.secrets: {secret_uri}")
            return str(secret_uri)
    except Exception:
        pass

    # 3) Streamlit config
    try:
        from streamlit import config as stconf  # type: ignore
        # Prefer browser.serverAddress (external) then server.address
        address = stconf.get_option("browser.serverAddress") or stconf.get_option("server.address") or "localhost"
        # Port from config if set
        cfg_port = stconf.get_option("server.port")
        # Base URL path (e.g., behind reverse proxy)
        base_path = stconf.get_option("server.baseUrlPath") or ""
        # Determine scheme from TLS config
        scheme = "https" if stconf.get_option("server.sslCertFile") else "http"
        # If port not set in config, try runtime below
        port = None
        try:
            from streamlit.runtime import get_instance
            runtime = get_instance()
            if cfg_port:
                port = cfg_port
            elif runtime and hasattr(runtime, '_main_server') and runtime._main_server:
                port = runtime._main_server._port
        except Exception:
            port = cfg_port or 8501
        port = port or 8501
        # Normalize base path
        if base_path and not str(base_path).startswith("/"):
            base_path = f"/{base_path}"
        base_url = f"{scheme}://{address}:{port}{base_path}"
        logger.debug(f"Detected Streamlit URL from config: {base_url}")
        return base_url
    except Exception as e:
        logger.debug(f"Failed to derive URL from Streamlit config: {e}")

    # 4) Runtime-only fallback (port)
    try:
        from streamlit.runtime import get_instance
        runtime = get_instance()
        if runtime and hasattr(runtime, '_main_server') and runtime._main_server:
            port = runtime._main_server._port
            base_url = f"http://localhost:{port}"
            logger.debug(f"Detected Streamlit URL from runtime: {base_url}")
            return base_url
    except Exception as e:
        logger.debug(f"Failed to detect Streamlit runtime URL: {e}")

    # 5) Final default
    logger.debug("Using default Streamlit URL: http://localhost:8501")
    return "http://localhost:8501"

def convert_chat_history_to_text_messages(chat_history: List[Dict[str, Any]]) -> List[TextMessage]:
    """Converts a Streamlit chat history (list of dicts) to a list of TextMessage objects."""
    return [
        TextMessage(content=msg["content"], source=msg["role"])
        for msg in chat_history
    ]

def convert_chat_history_to_user_messages(chat_history: List[Dict[str, Any]]) -> List[TextMessage]:
    """Converts a Streamlit chat history (list of dicts) to a list of TextMessage objects."""
    return [
        UserMessage(content=msg["content"], source=msg["role"])
        for msg in chat_history
    ]

def switch_tabs(tab_index: int = 0):
    st.html(f"""
    <script>
        var tabGroup = window.parent.document.getElementsByClassName("stTabs")[0];
        var tabButtons = tabGroup.getElementsByTagName("button");
        tabButtons[{tab_index}].click();
    </script>
    """)

# MCP Server Configuration and Status Management
# Data classes now imported from peak_assistant.utils.mcp_config
# This eliminates code duplication and ensures consistency across the codebase

def load_mcp_server_configs() -> Dict[str, MCPServerConfig]:
    """Load MCP server configurations from mcp_servers.json file"""
    if "mcp_server_configs" in st.session_state:
        cached_configs = st.session_state["mcp_server_configs"]
        logger.info(f"Returning cached MCP configs: {len(cached_configs)} servers")
        # Debug: Check if cached configs are valid
        invalid_configs = []
        for name, config in cached_configs.items():
            if not hasattr(config, 'transport'):
                logger.error(f"Invalid cached config for {name}: {type(config)}")
                invalid_configs.append(name)
        
        if invalid_configs:
            logger.info(f"Clearing invalid cached configs: {invalid_configs}")
            # Clear invalid cache and reload
            del st.session_state["mcp_server_configs"]
            return load_mcp_server_configs()
        return cached_configs
    
    # Find the configuration file
    possible_paths = [
        "mcp_servers.json",  # Current directory
        "../mcp_servers.json",  # Parent directory
        ".mcp_servers.json",
        os.path.expanduser("~/.config/peak-assistant/mcp_servers.json"),
        "/etc/peak-assistant/mcp_servers.json"
    ]
    
    config_file = None
    for path in possible_paths:
        if os.path.exists(path):
            config_file = path
            break
    
    if not config_file:
        logger.warning("No MCP server configuration file found")
        st.session_state["mcp_server_configs"] = {}
        return {}
    
    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Load server groups
        server_groups = config_data.get("serverGroups", {})
        st.session_state["mcp_server_groups"] = server_groups
        logger.info(f"Loaded {len(server_groups)} server groups")
        
        servers = {}
        servers_to_load = []
        
        # Handle "mcpServers" object format (existing format)
        if "mcpServers" in config_data:
            for name, server_config in config_data["mcpServers"].items():
                server_config["name"] = name
                servers_to_load.append(server_config)
        
        # Handle "servers" array format (new format)
        if "servers" in config_data:
            servers_to_load.extend(config_data["servers"])
        
        for server_config in servers_to_load:
            name = server_config.get("name")
            if not name:
                logger.warning(f"Server config missing name: {server_config}")
                continue
            
            logger.debug(f"Processing server config for {name}: {type(server_config)}")
                
            transport_str = server_config.get("transport", "stdio")
            transport = TransportType(transport_str)
            
            auth_config = None
            if "auth" in server_config:
                auth_data = server_config["auth"]
                auth_config = AuthConfig(
                    type=AuthType(auth_data["type"]),
                    token=auth_data.get("token"),
                    client_id=auth_data.get("client_id"),
                    client_secret=auth_data.get("client_secret"),
                    scope=auth_data.get("scope"),
                    token_url=auth_data.get("token_url"),
                    authorization_url=auth_data.get("authorization_url"),
                    redirect_uri=auth_data.get("redirect_uri"),
                    client_registration_url=auth_data.get("client_registration_url"),
                    requires_user_auth=auth_data.get("requires_user_auth", False),
                    api_key=auth_data.get("api_key"),
                    header_name=auth_data.get("header_name", "Authorization"),
                    discovery_url=auth_data.get("discovery_url"),
                    enable_discovery=auth_data.get("enable_discovery", True),
                    discovery_timeout=auth_data.get("discovery_timeout", 10)
                )
            
            try:
                config_obj = MCPServerConfig(
                    name=name,
                    transport=transport,
                    command=server_config.get("command"),
                    args=server_config.get("args", []),
                    env=server_config.get("env", {}),
                    url=server_config.get("url"),
                    auth=auth_config,
                    description=server_config.get("description"),
                    timeout=server_config.get("timeout", 30)
                )
                servers[name] = config_obj
                logger.debug(f"Successfully created MCPServerConfig for {name}: {type(config_obj)}")
            except Exception as e:
                logger.error(f"Failed to create MCPServerConfig for {name}: {e}")
                # Store the raw config as fallback for debugging
                servers[name] = f"ERROR_CREATING_CONFIG: {server_config}"
        
        # Debug: Check what we're actually storing
        for name, config in servers.items():
            logger.debug(f"Storing config for {name}: {type(config)} - {config}")
        
        st.session_state["mcp_server_configs"] = servers
        logger.info(f"Loaded {len(servers)} MCP server configurations")
        return servers
        
    except Exception as e:
        logger.error(f"Error loading MCP server configurations: {e}", exc_info=True)
        st.session_state["mcp_server_configs"] = {}
        return {}

def organize_servers_by_group(
    server_configs: Dict[str, MCPServerConfig],
    server_groups: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """
    Organize server names by their group.
    
    Args:
        server_configs: Dictionary of server configurations
        server_groups: Dictionary mapping group names to lists of server names
    
    Returns:
        Dictionary with group names as keys and lists of server names as values.
        Servers not in any group are placed in an "Others" group.
    """
    # Track which servers are in groups
    grouped_servers = set()
    for servers in server_groups.values():
        grouped_servers.update(servers)
    
    # Find ungrouped servers
    all_servers = set(server_configs.keys())
    ungrouped = all_servers - grouped_servers
    
    # Build result - copy existing groups
    result = dict(server_groups)
    
    # Add "Others" group if there are ungrouped servers
    if ungrouped:
        result["Others"] = sorted(list(ungrouped))
    
    return result

def get_user_session_id() -> str:
    """Get or create a unique session ID for the current user"""
    if "user_session_id" not in st.session_state:
        st.session_state["user_session_id"] = f"streamlit_user_{secrets.token_hex(16)}"
    return st.session_state["user_session_id"]

def store_session_for_oauth(server_name: str, state: str) -> str:
    """
    Store current session state in a temporary file for OAuth redirect recovery.
    Uses the OAuth state parameter as the key for recovery.
    """
    try:
        # Create session data - exclude non-serializable objects
        filtered_session_state = {}
        for key, value in st.session_state.items():
            # Skip MCP server configs (they'll be reloaded from JSON)
            if key == "mcp_server_configs":
                continue
            # Skip UI widget keys that can conflict with Streamlit policies on restore
            if (
                key.startswith("test_conn_")
                or key.startswith("status_btn_")
                or key.startswith("auth_button_")
                or key.startswith("btn_")
            ):
                continue
            # Preserve OAuth client info (needed for token exchange)
            if key.startswith("oauth_client_"):
                # OAuth client info should be serializable (it's from JSON responses)
                try:
                    json.dumps(value)
                    filtered_session_state[key] = value
                    continue
                except (TypeError, ValueError):
                    logger.warning(f"OAuth client info not serializable for key: {key}")
                    continue
            # Only store simple serializable data
            try:
                json.dumps(value)  # Test if it's serializable
                filtered_session_state[key] = value
            except (TypeError, ValueError):
                logger.debug(f"Skipping non-serializable session key: {key}")
                continue
        
        session_data = {
            "timestamp": time.time(),
            "server_name": server_name,
            "user_session_id": get_user_session_id(),
            "oauth_state": state,
            # Store only serializable session state
            "session_state": filtered_session_state
        }
        
        # Use OAuth state as the key (it's already unique and secure)
        temp_file = os.path.join(tempfile.gettempdir(), f"peak_oauth_session_{state}.json")
        with open(temp_file, 'w') as f:
            json.dump(session_data, f, default=str)  # default=str handles non-serializable objects
        
        logger.info(f"Stored OAuth session state for {server_name} with state: {state}")
        logger.debug(f"Session data keys stored: {list(filtered_session_state.keys())}")
        
        # Check if OAuth client info was included
        oauth_client_keys = [k for k in filtered_session_state.keys() if k.startswith("oauth_client_")]
        if oauth_client_keys:
            logger.debug(f"OAuth client info included in session storage: {oauth_client_keys}")
        else:
            logger.debug(f"No OAuth client info found in session state during storage")
        
        return state
        
    except Exception as e:
        logger.error(f"Failed to store OAuth session state: {e}")
        return None

def restore_session_from_oauth(state: str) -> bool:
    """
    Restore session state from temporary file using the OAuth state parameter.
    Returns True if successful, False otherwise.
    """
    try:
        temp_file = os.path.join(tempfile.gettempdir(), f"peak_oauth_session_{state}.json")
        
        if not os.path.exists(temp_file):
            logger.warning(f"OAuth session file not found for state: {state}")
            return False
        
        with open(temp_file, 'r') as f:
            session_data = json.load(f)
        
        # Check if session is not too old (max 1 hour)
        if time.time() - session_data.get("timestamp", 0) > 3600:
            logger.warning(f"OAuth session expired for state: {state}")
            os.remove(temp_file)
            return False
        
        # Restore session state (merge with current state to preserve any new data)
        # Note: MCP server configs are excluded from storage and will be reloaded from JSON
        stored_state = session_data.get("session_state", {})
        for key, value in stored_state.items():
            # Skip UI widget keys to avoid Streamlit assignment errors
            if (
                key.startswith("test_conn_")
                or key.startswith("status_btn_")
                or key.startswith("auth_button_")
                or key.startswith("btn_")
                or key.endswith("_run_button")
            ):
                continue
            if key not in st.session_state:  # Don't overwrite existing state
                st.session_state[key] = value
        
        # Clean up temp file
        os.remove(temp_file)
        
        logger.info(f"Restored OAuth session state for state: {state}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to restore OAuth session state: {e}")
        return False

def store_oauth_state_persistent(state: str, server_name: str):
    """Store OAuth state persistently to survive session resets"""
    try:
        state_file = os.path.join(tempfile.gettempdir(), f"peak_oauth_state_{state}.json")
        state_data = {
            "server_name": server_name,
            "timestamp": time.time(),
            "user_session_id": get_user_session_id()
        }
        with open(state_file, 'w') as f:
            json.dump(state_data, f)
        logger.info(f"Stored OAuth state persistently: {state} -> {server_name}")
    except Exception as e:
        logger.error(f"Failed to store OAuth state persistently: {e}")

def retrieve_oauth_state_persistent(state: str) -> Optional[str]:
    """Retrieve OAuth state from persistent storage"""
    try:
        state_file = os.path.join(tempfile.gettempdir(), f"peak_oauth_state_{state}.json")
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state_data = json.load(f)
            
            # Check if the state is not too old (max 1 hour)
            if time.time() - state_data.get("timestamp", 0) < 3600:
                server_name = state_data.get("server_name")
                logger.info(f"Retrieved OAuth state persistently: {state} -> {server_name}")
                
                # Clean up the state file
                os.remove(state_file)
                return server_name
            else:
                # Clean up expired state file
                os.remove(state_file)
                logger.info(f"Removed expired OAuth state file: {state}")
        
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve OAuth state persistently: {e}")
        return None

def check_oauth2_discovery(server_url: str) -> bool:
    """
    Check if a server supports OAuth2 by attempting discovery
    Returns: True if OAuth2 is supported, False otherwise
    """
    try:
        import httpx
        from urllib.parse import urlparse, urljoin
        
        # Parse the server URL to get the base
        parsed = urlparse(server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Common OAuth2 discovery endpoints to check
        discovery_paths = [
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid_configuration",
            "/oauth2/.well-known/oauth-authorization-server",
            "/auth/.well-known/oauth-authorization-server"
        ]
        
        with httpx.Client(timeout=5.0) as client:
            for path in discovery_paths:
                try:
                    discovery_url = urljoin(base_url, path)
                    logger.info(f"Checking OAuth2 discovery at: {discovery_url}")
                    
                    response = client.get(discovery_url)
                    if response.status_code == 200:
                        try:
                            discovery_data = response.json()
                            # Check if it looks like OAuth2 discovery data
                            if any(key in discovery_data for key in [
                                "authorization_endpoint", 
                                "token_endpoint", 
                                "issuer",
                                "response_types_supported"
                            ]):
                                logger.info(f"OAuth2 discovery successful for {server_url}")
                                return True
                        except json.JSONDecodeError:
                            continue
                            
                except httpx.RequestError:
                    continue
        
        # Also check if the server responds with 401 Unauthorized to a basic request
        # This often indicates authentication is required
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(server_url)
                if response.status_code == 401:
                    # Check if the WWW-Authenticate header suggests OAuth2
                    auth_header = response.headers.get("WWW-Authenticate", "").lower()
                    if "bearer" in auth_header or "oauth" in auth_header:
                        logger.info(f"OAuth2 authentication detected via 401 response for {server_url}")
                        return True
        except httpx.RequestError:
            pass
        
        logger.info(f"No OAuth2 discovery found for {server_url}")
        return False
        
    except Exception as e:
        logger.warning(f"OAuth2 discovery check failed for {server_url}: {e}")
        return False

def get_mcp_auth_status(server_name: str, server_config: MCPServerConfig) -> Tuple[str, str]:
    """
    Get authentication status for an MCP server
    Returns: (status, message) where status is 'green', 'yellow', or 'red'
    """
    # Check if we have stored authentication for this server first
    auth_key = f"MCP.{server_name}"
    logger.info(f"[AUTH STATUS] Checking auth status for {server_name}, key: {auth_key}")
    
    if auth_key in st.session_state:
        auth_data = st.session_state[auth_key]
        logger.info(f"[AUTH STATUS] Found auth data for {server_name}: {auth_data}")
        
        # Check for OAuth2 access token
        if auth_data.get("access_token"):
            # Check token expiry if available
            expires_at = auth_data.get("expires_at")
            if expires_at:
                if time.time() > expires_at:
                    return "yellow", "Access token expired - re-authentication required"
            return "green", "Authenticated with access token"
        
        # Check for OAuth2 authorization code (awaiting token exchange)
        elif auth_data.get("authorization_code"):
            return "green", "Authenticated with authorization code"
        
        # Check for API key
        elif auth_data.get("api_key"):
            return "green", "Authenticated with API key"
        
        # Check for other auth types
        elif auth_data.get("auth_type"):
            return "green", f"Authenticated ({auth_data['auth_type']})"
    
    # If explicit auth config is provided, use it
    if server_config.auth and server_config.auth.type != AuthType.NONE:
        if server_config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
            return "yellow", "OAuth2 authorization required"
        elif server_config.auth.type == AuthType.OAUTH2_CLIENT_CREDENTIALS:
            return "yellow", "OAuth2 client credentials required"
        elif server_config.auth.type == AuthType.API_KEY:
            return "yellow", "API key required"
        elif server_config.auth.type == AuthType.BEARER:
            return "yellow", "Bearer token required"
        else:
            return "red", f"Unknown authentication type: {server_config.auth.type.value}"
    
    # For HTTP/SSE servers without explicit auth config, check for OAuth2 discovery
    if server_config.transport in [TransportType.HTTP, TransportType.SSE] and server_config.url:
        # Check if we've already discovered OAuth2 for this server
        discovery_key = f"oauth_discovery_{server_name}"
        if discovery_key in st.session_state:
            discovery_result = st.session_state[discovery_key]
            if discovery_result.get("supports_oauth2"):
                return "yellow", "OAuth2 authentication detected"
            else:
                return "green", "No authentication required"
        
        # Perform OAuth2 discovery check
        oauth_discovered = check_oauth2_discovery(server_config.url)
        
        # Cache the discovery result
        st.session_state[discovery_key] = {
            "supports_oauth2": oauth_discovered,
            "checked_at": time.time()
        }
        
        if oauth_discovered:
            return "yellow", "OAuth2 authentication detected"
        else:
            return "green", "No authentication required"
    
    # STDIO servers typically don't require authentication
    elif server_config.transport == TransportType.STDIO:
        return "green", "No authentication required"
    
    # Default case
    return "green", "No authentication required"

async def test_mcp_connection(server_name: str, server_config: MCPServerConfig) -> Tuple[bool, str]:
    """
    Test connection to an MCP server and try to list tools
    Returns: (success, message)
    """
    try:
        if server_config.transport == TransportType.STDIO:
            if not server_config.command:
                return False, "No command specified for stdio transport"
            
            # Test if the command exists and is executable
            import shutil
            command_path = shutil.which(server_config.command)
            if not command_path:
                return False, f"Command '{server_config.command}' not found in PATH"
            
            # Try to create a basic McpWorkbench connection
            try:
                from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
                
                server_params = StdioServerParams(
                    command=server_config.command,
                    args=server_config.args or [],
                    env=server_config.env or {}
                )
                
                # Create a temporary workbench to test the connection
                workbench = McpWorkbench(server_params)
                
                # Try to list tools (this will test the connection)
                tools = await workbench.list_tools()
                tool_count = len(tools)
                
                # Clean up
                if hasattr(workbench, 'stop'):
                    await workbench.stop()
                
                return True, f"STDIO connection successful, {tool_count} tools available"
                
            except Exception as e:
                return False, f"STDIO connection failed: {str(e)}"
        
        elif server_config.transport in [TransportType.HTTP, TransportType.SSE]:
            if not server_config.url:
                return False, "No URL specified for HTTP/SSE transport"
            
            # Test HTTP/SSE connection with authentication
            import httpx
            
            # Prepare headers
            headers = {"Content-Type": "application/json"}
            
            # Add authentication if available
            auth_key = f"MCP.{server_name}"
            if auth_key in st.session_state:
                auth_data = st.session_state[auth_key]
                if auth_data.get("access_token"):
                    headers["Authorization"] = f"Bearer {auth_data['access_token']}"
                elif auth_data.get("api_key"):
                    # Use the configured header name or default to Authorization
                    header_name = server_config.auth.header_name if server_config.auth else "Authorization"
                    headers[header_name] = auth_data["api_key"]
            
            # Test basic connectivity
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    # Try to make a basic request to the server
                    response = await client.get(server_config.url, headers=headers)
                    
                    if response.status_code == 200:
                        return True, f"{server_config.transport.value.upper()} server responding (HTTP {response.status_code})"
                    elif response.status_code == 401:
                        return False, "Authentication required or invalid credentials"
                    elif response.status_code == 403:
                        return False, "Access forbidden - check permissions"
                    else:
                        return False, f"Server responded with HTTP {response.status_code}"
                        
                except httpx.ConnectError:
                    return False, f"Cannot connect to {server_config.url}"
                except httpx.TimeoutException:
                    return False, f"Connection timeout to {server_config.url}"
                except Exception as e:
                    return False, f"HTTP connection failed: {str(e)}"
        
        else:
            return False, f"Unsupported transport type: {server_config.transport.value}"
            
    except Exception as e:
        return False, f"Connection test failed: {str(e)}"

def initiate_oauth_flow(server_name: str, server_config: MCPServerConfig) -> Optional[str]:
    """
    Initiate OAuth flow for a server
    Returns: authorization URL to redirect to, or None if not applicable
    """
    # Check if explicit OAuth2 config is provided
    if server_config.auth and server_config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        st.session_state[f"oauth_state_{server_name}"] = state
        
        # Also store the server name in the state itself for recovery
        st.session_state[f"oauth_server_for_state_{state}"] = server_name
        
        # Build authorization URL
        auth_url = server_config.auth.authorization_url
        if not auth_url:
            return None
        
        # Store session state for recovery after OAuth redirect (using state as key)
        store_session_for_oauth(server_name, state)
        
        # Add required parameters
        params = {
            "response_type": "code",
            "client_id": server_config.auth.client_id,
            "state": state,
            "scope": server_config.auth.scope or "read",
            # Use clean redirect URI (no query parameters)
            "redirect_uri": server_config.auth.redirect_uri or get_streamlit_redirect_uri()
        }
        
        # Build the full URL
        from urllib.parse import urlencode
        full_url = f"{auth_url}?{urlencode(params)}"
        return full_url
    
    # Check if OAuth2 was discovered for this server
    elif server_config.transport in [TransportType.HTTP, TransportType.SSE] and server_config.url:
        discovery_key = f"oauth_discovery_{server_name}"
        if discovery_key in st.session_state and st.session_state[discovery_key].get("supports_oauth2"):
            # Try to get OAuth2 endpoints via discovery
            oauth_endpoints = discover_oauth2_endpoints(server_config.url)
            if oauth_endpoints and oauth_endpoints.get("authorization_endpoint"):
                # Generate state parameter for security
                state = secrets.token_urlsafe(32)
                st.session_state[f"oauth_state_{server_name}"] = state
                
                # Also store the server name in the state itself for recovery
                st.session_state[f"oauth_server_for_state_{state}"] = server_name
                
                # Store discovered endpoints for callback handling
                st.session_state[f"oauth_endpoints_{server_name}"] = oauth_endpoints
                
                # First, try dynamic client registration if needed
                client_id = "PEAK Assistant"  # Default
                
                # Try dynamic client registration for all OAuth servers
                # Many servers support dynamic registration even if they don't advertise the endpoint
                logger.info(f"Attempting dynamic client registration for {server_name}")
                registered_client = perform_dynamic_client_registration(server_config.url)
                if registered_client:
                    client_id = registered_client["client_id"]
                    # Store the registered client info for token exchange
                    st.session_state[f"oauth_client_{server_name}"] = registered_client
                    logger.info(f"Stored OAuth client info for {server_name}: {list(registered_client.keys())}")
                else:
                    logger.debug(f"Dynamic client registration failed for {server_name}, using default client ID")
                
                # Store session state for recovery after OAuth redirect (AFTER client registration)
                store_session_for_oauth(server_name, state)
                
                # Build authorization URL with discovered endpoint
                params = {
                    "response_type": "code",
                    "client_id": client_id,
                    "state": state,
                    "scope": "read",  # Default scope
                    # Use clean redirect URI (no query parameters)
                    "redirect_uri": get_streamlit_redirect_uri()
                }
                
                from urllib.parse import urlencode
                full_url = f"{oauth_endpoints['authorization_endpoint']}?{urlencode(params)}"
                return full_url
    
    return None

def discover_oauth2_endpoints(server_url: str) -> Optional[Dict[str, str]]:
    """
    Discover OAuth2 endpoints for a server
    Returns: Dictionary with endpoint URLs, or None if discovery fails
    """
    try:
        import httpx
        from urllib.parse import urlparse, urljoin
        
        # Parse the server URL to get the base
        parsed = urlparse(server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Common OAuth2 discovery endpoints to check
        discovery_paths = [
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid_configuration",
            "/oauth2/.well-known/oauth-authorization-server",
            "/auth/.well-known/oauth-authorization-server"
        ]
        
        with httpx.Client(timeout=5.0) as client:
            for path in discovery_paths:
                try:
                    discovery_url = urljoin(base_url, path)
                    response = client.get(discovery_url)
                    
                    if response.status_code == 200:
                        try:
                            discovery_data = response.json()
                            
                            # Extract relevant endpoints
                            endpoints = {}
                            if "authorization_endpoint" in discovery_data:
                                endpoints["authorization_endpoint"] = discovery_data["authorization_endpoint"]
                            if "token_endpoint" in discovery_data:
                                endpoints["token_endpoint"] = discovery_data["token_endpoint"]
                            if "issuer" in discovery_data:
                                endpoints["issuer"] = discovery_data["issuer"]
                            
                            if endpoints:
                                logger.info(f"OAuth2 endpoints discovered for {server_url}: {endpoints}")
                                return endpoints
                                
                        except json.JSONDecodeError:
                            continue
                            
                except httpx.RequestError:
                    continue
        
        return None
        
    except Exception as e:
        logger.warning(f"OAuth2 endpoint discovery failed for {server_url}: {e}")
        return None

def perform_dynamic_client_registration(server_url: str) -> Optional[Dict[str, str]]:
    """
    Perform dynamic client registration for OAuth2 servers that support it
    Returns: Dictionary with client credentials, or None if registration fails
    """
    try:
        import httpx
        from urllib.parse import urlparse, urljoin
        
        # Parse the server URL to get the base
        parsed = urlparse(server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Common dynamic registration endpoints
        registration_paths = [
            "/v1/register",
            "/oauth2/register", 
            "/auth/register",
            "/.well-known/oauth-authorization-server/register"
        ]
        
        # Client registration payload
        registration_data = {
            "client_name": "PEAK Assistant",
            "client_uri": "https://github.com/cisco-foundation-ai/PEAK-Assistant",
            "redirect_uris": [get_streamlit_redirect_uri()],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "scope": "read write",
            "token_endpoint_auth_method": "client_secret_basic"
        }
        
        with httpx.Client(timeout=10.0) as client:
            for path in registration_paths:
                try:
                    registration_url = urljoin(base_url, path)
                    logger.info(f"Attempting dynamic client registration at: {registration_url}")
                    
                    response = client.post(
                        registration_url,
                        json=registration_data,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code in [200, 201]:
                        try:
                            client_info = response.json()
                            
                            # Extract client credentials
                            if "client_id" in client_info:
                                result = {
                                    "client_id": client_info["client_id"],
                                    "client_secret": client_info.get("client_secret"),
                                    "registration_url": registration_url
                                }
                                
                                logger.info(f"Dynamic client registration successful: {result['client_id']}")
                                return result
                                
                        except json.JSONDecodeError:
                            continue
                            
                except httpx.RequestError as e:
                    logger.debug(f"Registration attempt failed at {registration_url}: {e}")
                    continue
        
        logger.warning(f"Dynamic client registration failed for {server_url}")
        return None
        
    except Exception as e:
        logger.warning(f"Dynamic client registration error for {server_url}: {e}")
        return None

def exchange_oauth_code_for_token(server_name: str, auth_code: str) -> bool:
    """
    Exchange OAuth authorization code for access token
    """
    try:
        import requests
        
        # Get stored OAuth client info
        client_key = f"oauth_client_{server_name}"
        if client_key not in st.session_state:
            logger.warning(f"No OAuth client info found for {server_name} - skipping token exchange")
            return False
        
        client_info = st.session_state[client_key]
        client_id = client_info.get("client_id")
        client_secret = client_info.get("client_secret")
        token_url = client_info.get("token_endpoint")
        
        # If no token endpoint in client info, try to get it from discovered endpoints
        if not token_url:
            endpoints_key = f"oauth_endpoints_{server_name}"
            if endpoints_key in st.session_state:
                oauth_endpoints = st.session_state[endpoints_key]
                token_url = oauth_endpoints.get("token_endpoint")
                logger.debug(f"Using discovered token endpoint for {server_name}: {token_url}")
        
        if not all([client_id, client_secret, token_url]):
            logger.warning(f"Missing OAuth client credentials for {server_name} - skipping token exchange")
            logger.debug(f"Available client info: {list(client_info.keys())}")
            logger.debug(f"client_id: {bool(client_id)}, client_secret: {bool(client_secret)}, token_url: {bool(token_url)}")
            return False
        
        # Prepare token exchange request
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": get_streamlit_redirect_uri(),
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        logger.info(f"Exchanging authorization code for access token: {server_name}")
        response = requests.post(token_url, data=token_data, timeout=30)
        
        if response.status_code == 200:
            token_data = response.json()
            
            # Store the access token
            auth_key = f"MCP.{server_name}"
            user_session_id = get_user_session_id()
            
            st.session_state[auth_key] = {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_type": token_data.get("token_type", "Bearer"),
                "expires_in": token_data.get("expires_in"),
                "expires_at": time.time() + token_data.get("expires_in", 3600),
                "scope": token_data.get("scope"),
                "auth_type": "oauth2_authorization_code",
                "authenticated_at": time.time(),
                "user_id": user_session_id,
                "server_name": server_name
            }
            
            logger.info(f"Successfully exchanged authorization code for access token: {server_name}")
            return True
        else:
            logger.error(f"Token exchange failed for {server_name}: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error exchanging OAuth code for token: {e}")
        return False


def get_agent_config_data() -> List[Dict[str, str]]:
    """
    Get agent configuration data for all known agents.
    
    Returns:
        List of dicts with keys: agent, provider, provider_type, model, deployment, source
    """
    from peak_assistant.utils.model_config_loader import get_loader, ModelConfigError
    from peak_assistant.utils.validate_config import KNOWN_AGENTS
    from fnmatch import fnmatch
    
    try:
        loader = get_loader()
        agent_data = []
        
        for agent_name in KNOWN_AGENTS:
            try:
                agent_config = loader.resolve_agent_config(agent_name)
                provider_name = agent_config.get("provider", "N/A")
                model = agent_config.get("model", "N/A")
                deployment = agent_config.get("deployment", "")
                
                # Determine source
                config = loader._config
                if "agents" in config and agent_name in config["agents"]:
                    source = "agent"
                elif "groups" in config:
                    # Check if any group matches
                    matched_group = None
                    for group_name, group_config in config["groups"].items():
                        if "match" not in group_config:
                            continue
                        patterns = group_config["match"]
                        if not isinstance(patterns, list):
                            patterns = [patterns]
                        
                        for pattern in patterns:
                            if fnmatch(agent_name, pattern):
                                matched_group = group_name
                                break
                        if matched_group:
                            break
                    
                    if matched_group:
                        source = f"group:{matched_group}"
                    else:
                        source = "defaults"
                else:
                    source = "defaults"
                
                # Get provider type
                try:
                    provider_config = loader.get_provider_config(provider_name)
                    provider_type = provider_config["type"]
                except:
                    provider_type = "unknown"
                
                agent_data.append({
                    "agent": agent_name,
                    "provider": provider_name,
                    "provider_type": provider_type,
                    "model": model,
                    "deployment": deployment,
                    "source": source
                })
            except Exception as e:
                agent_data.append({
                    "agent": agent_name,
                    "provider": "ERROR",
                    "provider_type": "error",
                    "model": str(e)[:30],
                    "deployment": "",
                    "source": "error"
                })
        
        return agent_data
    except ModelConfigError as e:
        logger.error(f"Model config error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading agent config data: {e}")
        return []
