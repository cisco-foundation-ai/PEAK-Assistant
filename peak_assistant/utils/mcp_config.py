#!/usr/bin/env python3

import json
import os
import asyncio
import httpx
import atexit
import weakref
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import logging
from urllib.parse import urljoin
from dotenv import load_dotenv

from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

logger = logging.getLogger(__name__)

class AuthType(Enum):
    NONE = "none"
    BEARER = "bearer"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"
    OAUTH2_AUTHORIZATION_CODE = "oauth2_authorization_code"
    API_KEY = "api_key"

class TransportType(Enum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"

@dataclass
class AuthConfig:
    type: AuthType
    token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scope: Optional[str] = None
    token_url: Optional[str] = None
    authorization_url: Optional[str] = None  # For authorization code flow
    redirect_uri: Optional[str] = None       # For authorization code flow
    client_registration_url: Optional[str] = None # For dynamic client registration
    api_key: Optional[str] = None
    header_name: Optional[str] = "Authorization"
    requires_user_auth: bool = False         # True for authorization code flow
    # OAuth discovery settings
    discovery_url: Optional[str] = None      # Base URL for OAuth discovery (will append /.well-known/oauth-authorization-server)
    enable_discovery: bool = True            # Whether to attempt OAuth discovery
    discovery_timeout: int = 10              # Timeout for discovery requests

@dataclass
class MCPServerConfig:
    name: str
    transport: TransportType = TransportType.STDIO
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    auth: Optional[AuthConfig] = None
    description: Optional[str] = None
    timeout: int = 30

class OAuth2TokenManager:
    """Manages OAuth2 token acquisition and refresh"""
    
    def __init__(self, auth_config: AuthConfig, user_id: Optional[str] = None, server_url: Optional[str] = None):
        self.auth_config = auth_config
        self.user_id = user_id  # For user-specific tokens
        self.server_url = server_url  # Server URL for auto-deriving discovery URL
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        self.token_user_id = None  # User ID from token response
        self._discovered_config = None  # Cache for discovered OAuth config
        
    def get_effective_discovery_url(self) -> Optional[str]:
        """Get the effective discovery URL, using explicit config or auto-deriving from server URL"""
        if self.auth_config.discovery_url:
            return self.auth_config.discovery_url
            
        if self.server_url:
            # Auto-derive discovery URL from server URL
            from urllib.parse import urlparse
            parsed = urlparse(self.server_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            logger.info(f"Auto-derived discovery URL from server URL: {base_url}")
            return base_url
            
        return None
        
    def get_effective_redirect_uri(self) -> str:
        """Get the effective redirect URI, using explicit config or auto-generating from Flask app"""
        if self.auth_config.redirect_uri:
            return self.auth_config.redirect_uri
            
        # Auto-generate redirect URI from Flask app configuration
        try:
            from flask import has_app_context, current_app, url_for
            if has_app_context():
                # Generate the full URL including domain and port
                redirect_uri = url_for('oauth.oauth_callback', _external=True)
                logger.info(f"Auto-generated redirect URI: {redirect_uri}")
                return redirect_uri
        except Exception as e:
            logger.warning(f"Failed to auto-generate redirect URI: {e}")
            
        # Fallback to default localhost pattern if Flask context not available
        default_redirect = "https://localhost:8000/oauth/callback"
        logger.warning(f"Using fallback redirect URI: {default_redirect}")
        return default_redirect
        
    async def discover_oauth_endpoints(self) -> Optional[Dict[str, Any]]:
        """Discover OAuth endpoints using RFC 8414 OAuth Authorization Server Metadata"""
        discovery_url = self.get_effective_discovery_url()
        if not self.auth_config.enable_discovery or not discovery_url:
            return None
            
        if self._discovered_config is not None:
            return self._discovered_config
            
        try:
            # Construct the well-known endpoint URL
            well_known_url = urljoin(discovery_url.rstrip('/'), '/.well-known/oauth-authorization-server')
            
            logger.info(f"Attempting OAuth discovery from: {well_known_url}")
            
            async with httpx.AsyncClient(timeout=self.auth_config.discovery_timeout) as client:
                response = await client.get(well_known_url)
                response.raise_for_status()
                
                discovery_data = response.json()
                
                # Validate required endpoints exist
                if 'token_endpoint' not in discovery_data:
                    logger.warning(f"OAuth discovery from {well_known_url} missing required token_endpoint")
                    return None
                    
                self._discovered_config = discovery_data
                logger.info(f"Successfully discovered OAuth endpoints from {well_known_url}")
                return discovery_data
                
        except Exception as e:
            logger.warning(f"OAuth discovery failed for {discovery_url}: {e}")
            return None
            
    async def get_effective_token_url(self) -> str:
        """Get the effective token URL, using discovery if available, fallback to manual config"""
        if self.auth_config.token_url:
            # Manual configuration takes precedence
            return self.auth_config.token_url
            
        discovered = await self.discover_oauth_endpoints()
        if discovered and 'token_endpoint' in discovered:
            return discovered['token_endpoint']
            
        raise ValueError("No token URL available from manual config or discovery")
        
    async def get_effective_authorization_url(self) -> str:
        """Get the effective authorization URL, using discovery if available, fallback to manual config"""
        if self.auth_config.authorization_url:
            # Manual configuration takes precedence
            return self.auth_config.authorization_url
            
        discovered = await self.discover_oauth_endpoints()
        if discovered and 'authorization_endpoint' in discovered:
            return discovered['authorization_endpoint']
            
        raise ValueError("No authorization URL available from manual config or discovery")
        
    async def get_token(self) -> str:
        """Get a valid access token, refreshing if necessary"""
        if self.access_token and not self._is_token_expired():
            return self.access_token
            
        return await self._refresh_token()
    
    def _is_token_expired(self) -> bool:
        """Check if the current token is expired"""
        if not self.token_expiry:
            return True
        import time
        return time.time() >= self.token_expiry
    
    async def _refresh_token(self) -> str:
        """Refresh the OAuth2 token based on flow type"""
        if self.auth_config.type == AuthType.OAUTH2_CLIENT_CREDENTIALS:
            return await self._refresh_client_credentials_token()
        elif self.auth_config.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
            if self.refresh_token:
                return await self._refresh_authorization_code_token()
            else:
                raise RuntimeError("No refresh token available for authorization code flow. User must re-authenticate.")
        else:
            raise ValueError(f"Unsupported OAuth2 flow: {self.auth_config.type}")
    
    async def _refresh_client_credentials_token(self) -> str:
        """Refresh token using client credentials flow"""
        data = {
            "grant_type": "client_credentials",
            "client_id": self.auth_config.client_id,
            "client_secret": self.auth_config.client_secret,
        }
        
        if self.auth_config.scope:
            data["scope"] = self.auth_config.scope
            
        token_url = await self.get_effective_token_url()
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            
            # Extract user ID from token response if present
            self.token_user_id = (
                token_data.get('user_id') or 
                token_data.get('userId') or
                token_data.get('sub') or
                token_data.get('id') or
                token_data.get('username')
            )
            
            # Calculate expiry time
            import time
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
            self.token_expiry = time.time() + expires_in - 300  # Refresh 5 minutes early
            
            return self.access_token
    
    async def _refresh_authorization_code_token(self) -> str:
        """Refresh token using authorization code flow refresh token"""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.auth_config.client_id,
            "client_secret": self.auth_config.client_secret,
        }
        
        token_url = await self.get_effective_token_url()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            
            # Update refresh token if provided
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            
            # Calculate expiry time
            import time
            expires_in = token_data.get("expires_in", 3600)
            self.token_expiry = time.time() + expires_in - 300
            
            return self.access_token
    
    async def exchange_authorization_code(self, authorization_code: str, code_verifier: Optional[str] = None) -> str:
        """Exchange authorization code for access token (authorization code flow)"""
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.get_effective_redirect_uri(),
            "client_id": self.auth_config.client_id,
            "client_secret": self.auth_config.client_secret,
        }
        
        # Add PKCE code verifier if provided
        if code_verifier:
            data["code_verifier"] = code_verifier
        
        token_url = await self.get_effective_token_url()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data.get("refresh_token")
            
            # Extract user ID from token response if present
            self.token_user_id = (
                token_data.get('user_id') or 
                token_data.get('userId') or
                token_data.get('sub') or
                token_data.get('id') or
                token_data.get('username')
            )
            
            # Calculate expiry time
            import time
            expires_in = token_data.get("expires_in", 3600)
            self.token_expiry = time.time() + expires_in - 300
            
            return self.access_token
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None) -> str:
        """Generate OAuth2 authorization URL for authorization code flow"""
        authorization_url = await self.get_effective_authorization_url()
        
        params = {
            "response_type": "code",
            "client_id": self.auth_config.client_id,
            "redirect_uri": self.get_effective_redirect_uri(),
            "state": state,
        }
        
        if self.auth_config.scope:
            params["scope"] = self.auth_config.scope
            
        # Add PKCE challenge if provided
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        from urllib.parse import urlencode
        return f"{authorization_url}?{urlencode(params)}"

class UserSessionManager:
    """Manages user-specific OAuth tokens and sessions"""
    
    def __init__(self):
        # In-memory storage for user sessions (in production, use Redis/database)
        self.user_sessions: Dict[str, Dict[str, OAuth2TokenManager]] = {}
        self.user_states: Dict[str, Dict[str, str]] = {}  # For OAuth state tracking
    
    def get_or_create_token_manager(self, user_id: str, server_name: str, auth_config: AuthConfig, server_url: Optional[str] = None) -> OAuth2TokenManager:
        """Get or create a token manager for a specific user and server"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
            
        if server_name not in self.user_sessions[user_id]:
            logger.info(f"Creating new OAuth token manager for user {user_id} and server {server_name}")
            self.user_sessions[user_id][server_name] = OAuth2TokenManager(auth_config, user_id, server_url)
            
        return self.user_sessions[user_id][server_name]
    
    def store_oauth_state(self, user_id: str, state: str, server_name: str):
        """Store OAuth state for CSRF protection"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        self.user_states[user_id][state] = server_name
    
    def get_server_for_state(self, user_id: str, state: str) -> Optional[str]:
        """Retrieve server name for OAuth state"""
        return self.user_states.get(user_id, {}).get(state)
    
    def clear_oauth_state(self, user_id: str, state: str):
        """Clear OAuth state after use"""
        if user_id in self.user_states and state in self.user_states[user_id]:
            del self.user_states[user_id][state]
    
    def has_valid_tokens(self, user_id: str, server_name: str) -> bool:
        """Check if a user has valid tokens for a specific server"""
        user_session = self.user_sessions.get(user_id, {})
        
        if server_name not in user_session:
            return False
            
        token_manager = user_session[server_name]
        return token_manager.access_token is not None
    
    def clear_tokens(self, user_id: str, server_name: str):
        """Clear tokens for a specific user and server (disconnect)"""
        user_session = self.user_sessions.get(user_id, {})
        if server_name in user_session:
            # Clear the tokens but keep the token manager for potential re-authentication
            token_manager = user_session[server_name]
            token_manager.access_token = None
            token_manager.refresh_token = None
            token_manager.token_expiry = None
    
    def get_user_servers_needing_auth(self, user_id: str, servers: Dict[str, MCPServerConfig]) -> List[str]:
        """Get list of servers that need user authentication for this user"""
        needing_auth = []
        user_session = self.user_sessions.get(user_id, {})
        
        for server_name, config in servers.items():
            if (config.auth and 
                config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE and
                (server_name not in user_session or not user_session[server_name].access_token)):
                needing_auth.append(server_name)
        
        return needing_auth
    
    def clear_user_session(self, user_id: str):
        """Clear all tokens for a user (logout)"""
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        if user_id in self.user_states:
            del self.user_states[user_id]

class MCPConfigManager:
    """Manages MCP server configurations and OAuth settings"""
    
    async def _discover_oauth_config(self, server_url: str, server_name: str) -> Optional[AuthConfig]:
        """Attempt to discover OAuth configuration from server URL"""
        try:
            # Extract base URL from server URL
            from urllib.parse import urlparse
            parsed = urlparse(server_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Construct well-known OAuth discovery URL
            discovery_url = urljoin(base_url.rstrip('/'), '/.well-known/oauth-authorization-server')
            
            logger.info(f"Attempting automatic OAuth discovery for {server_name} from: {discovery_url}")
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(discovery_url)
                response.raise_for_status()
                
                oauth_metadata = response.json()
                
                # Validate required OAuth endpoints exist
                if 'token_endpoint' not in oauth_metadata or 'authorization_endpoint' not in oauth_metadata:
                    logger.warning(f"OAuth discovery from {discovery_url} missing required endpoints")
                    return None
                
                logger.info(f"OAuth discovery successful for {server_name}:")
                logger.info(f"  Token endpoint: {oauth_metadata.get('token_endpoint')}")
                logger.info(f"  Authorization endpoint: {oauth_metadata.get('authorization_endpoint')}")
                logger.info(f"  Registration endpoint: {oauth_metadata.get('registration_endpoint', 'None')}")
                
                # Create AuthConfig from discovered metadata
                # Use authorization_code flow as default for discovered OAuth
                auth_config = AuthConfig(
                    type=AuthType.OAUTH2_AUTHORIZATION_CODE,
                    requires_user_auth=True,  # Discovered OAuth typically requires user auth
                    token_url=oauth_metadata['token_endpoint'],
                    authorization_url=oauth_metadata['authorization_endpoint'],
                    client_registration_url=oauth_metadata.get('registration_endpoint'),
                    discovery_url=base_url,
                    enable_discovery=True,
                    discovery_timeout=10,
                    # Client credentials will need to be provided via dynamic registration or manual config
                    client_id=None,  # Will be set via dynamic registration
                    client_secret=None,  # Will be set via dynamic registration
                    scope=None,  # Default scope, can be overridden
                    redirect_uri=None  # Will be auto-generated
                )
                
                return auth_config
                
        except Exception as e:
            logger.info(f"OAuth discovery failed for {server_name} at {server_url}: {e}")
            return None
    
    async def _perform_oauth_discovery(self):
        """Perform OAuth discovery for servers that need it"""
        for server_name, server_url in self._servers_needing_oauth_discovery.items():
            try:
                logger.info(f"Performing OAuth discovery for {server_name}")
                auth_config = await self._discover_oauth_config(server_url, server_name)
                
                if auth_config:
                    # Update the server configuration with discovered OAuth
                    server = self.servers[server_name]
                    server.auth = auth_config
                    logger.info(f"Updated {server_name} with discovered OAuth configuration")
                    
                    # Create OAuth manager if needed
                    if auth_config.type == AuthType.OAUTH2_CLIENT_CREDENTIALS:
                        self.oauth_managers[server_name] = OAuth2TokenManager(auth_config, server_url=server_url)
                else:
                    logger.info(f"No OAuth discovered for {server_name}, server will be accessible without authentication")
                    
            except Exception as e:
                logger.warning(f"OAuth discovery failed for {server_name}: {e}")
        
        # Clear the discovery queue
        self._servers_needing_oauth_discovery.clear()
    
    def get_all_servers(self) -> Dict[str, MCPServerConfig]:
        """Get all loaded server configurations"""
        return self.servers.copy()
    
    def __init__(self, config_file: Optional[str] = None):
        logger.info(f"[INIT DEBUG] MCPConfigManager.__init__ called with config_file: {config_file}")
        self.config_file = config_file or self._find_config_file()
        logger.info(f"[INIT DEBUG] Using config file path: {self.config_file}")
        logger.info(f"[INIT DEBUG] Config file exists: {os.path.exists(self.config_file)}")
        
        self.servers: Dict[str, MCPServerConfig] = {}
        self.server_groups: Dict[str, List[str]] = {}
        self.oauth_managers: Dict[str, OAuth2TokenManager] = {}  # For client credentials
        self.user_session_manager = UserSessionManager()
        self._servers_needing_oauth_discovery: Dict[str, str] = {}  # server_name -> server_url
        
        logger.info(f"[INIT DEBUG] About to call _load_config()")
        self._load_config()
        logger.info(f"[INIT DEBUG] _load_config() completed. Loaded {len(self.servers)} servers and {len(self.server_groups)} server groups")
        
        # Perform OAuth discovery for servers that need it
        if self._servers_needing_oauth_discovery:
            logger.info(f"[INIT DEBUG] Performing OAuth discovery for {len(self._servers_needing_oauth_discovery)} servers")
            
            # Check if we can use asyncio.run or need alternative approach
            try:
                # Test if we can create a new event loop (this will fail if one is already running)
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an existing event loop, use separate thread approach
                    import concurrent.futures
                    import threading
                    
                    def run_discovery():
                        # Create a new event loop in a separate thread
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(self._perform_oauth_discovery())
                        finally:
                            new_loop.close()
                    
                    # Run discovery in a separate thread with its own event loop
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_discovery)
                        future.result(timeout=30)  # Wait up to 30 seconds
                    
                    logger.info(f"[INIT DEBUG] OAuth discovery completed using separate thread for {len(self._servers_needing_oauth_discovery)} servers")
                else:
                    # Event loop exists but not running, can use run_until_complete
                    loop.run_until_complete(self._perform_oauth_discovery())
                    logger.info(f"[INIT DEBUG] OAuth discovery completed using run_until_complete for {len(self._servers_needing_oauth_discovery)} servers")
            except RuntimeError as e:
                if "no running event loop" in str(e) or "no current event loop" in str(e):
                    # No event loop exists, we can use asyncio.run
                    try:
                        asyncio.run(self._perform_oauth_discovery())
                        logger.info(f"[INIT DEBUG] OAuth discovery completed using asyncio.run for {len(self._servers_needing_oauth_discovery)} servers")
                    except Exception as ex:
                        logger.warning(f"[INIT DEBUG] Failed to run OAuth discovery with asyncio.run: {ex}. Discovery will happen on first access.")
                else:
                    logger.warning(f"[INIT DEBUG] Failed to run OAuth discovery synchronously: {e}. Discovery will happen on first access.")
            except Exception as ex:
                logger.warning(f"[INIT DEBUG] Failed to run OAuth discovery synchronously: {ex}. Discovery will happen on first access.")


    
    def _find_config_file(self) -> str:
        """Find the MCP configuration file"""
        possible_paths = [
            "mcp_servers.json",  # Current directory
            "../mcp_servers.json",  # Parent directory (when Flask runs from UI subdirectory)
            ".mcp_servers.json",
            os.path.expanduser("~/.config/peak-assistant/mcp_servers.json"),
            "/etc/peak-assistant/mcp_servers.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        # If no config file found, create a default one
        default_path = "mcp_servers.json"
        if os.path.exists("mcp_servers.json.example"):
            import shutil
            shutil.copy("mcp_servers.json.example", default_path)
        
        return default_path
    
    def _load_config(self):
        """Load MCP server configurations from file"""
        logger.info(f"[LOAD CONFIG DEBUG] Starting _load_config for file: {self.config_file}")
        
        if not os.path.exists(self.config_file):
            logger.error(f"[LOAD CONFIG DEBUG] MCP config file not found: {self.config_file}")
            logger.error(f"[LOAD CONFIG DEBUG] Current working directory: {os.getcwd()}")
            logger.error(f"[LOAD CONFIG DEBUG] File existence check failed - configuration loading aborted")
            return
        
        logger.info(f"[LOAD CONFIG DEBUG] Config file exists, attempting to read and parse JSON")
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
            logger.info(f"[LOAD CONFIG DEBUG] JSON parsing successful, config_data type: {type(config_data)}")
            logger.info(f"[LOAD CONFIG DEBUG] Top-level keys in config: {list(config_data.keys()) if isinstance(config_data, dict) else 'Not a dict'}")
            
            # Load server configurations - support both formats
            servers_to_load = []
            
            # Handle "mcpServers" object format (existing format)
            if "mcpServers" in config_data:
                for name, server_config in config_data["mcpServers"].items():
                    server_config["name"] = name  # Ensure name is set
                    servers_to_load.append(server_config)
            
            # Handle "servers" array format (new format)
            if "servers" in config_data:
                servers_to_load.extend(config_data["servers"])
            
            for server_config in servers_to_load:
                name = server_config.get("name")
                if not name:
                    logger.warning("Skipping server configuration without name")
                    continue
                transport_str = server_config.get("transport", "stdio")
                transport = TransportType(transport_str)
                
                auth_config = None
                server_url = server_config.get("url")
                
                if "auth" in server_config:
                    # Explicit auth configuration provided
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
                        # OAuth discovery settings
                        discovery_url=auth_data.get("discovery_url"),
                        enable_discovery=auth_data.get("enable_discovery", True),
                        discovery_timeout=auth_data.get("discovery_timeout", 10)
                    )
                elif server_url and transport in [TransportType.HTTP, TransportType.SSE]:
                    # No explicit auth config - attempt automatic OAuth discovery
                    logger.info(f"No auth config for {name}, attempting automatic OAuth discovery from {server_url}")
                    try:
                        # Schedule OAuth discovery to run after config loading
                        self._servers_needing_oauth_discovery[name] = server_url
                        auth_config = None  # Will be set later via discovery
                        logger.info(f"Scheduled automatic OAuth discovery for {name}")
                    except Exception as e:
                        logger.warning(f"Failed to schedule OAuth discovery for {name}: {e}")
                        auth_config = None
                
                self.servers[name] = MCPServerConfig(
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
                
                # Initialize OAuth2 manager for client credentials flow
                if auth_config and auth_config.type == AuthType.OAUTH2_CLIENT_CREDENTIALS:
                    self.oauth_managers[name] = OAuth2TokenManager(auth_config, server_url=server_config.get("url"))
                elif auth_config and auth_config.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
                    # User-specific token managers will be created on-demand
                    pass
            
            # Load server groups
            logger.info(f"[CONFIG DEBUG] Loading server groups from config...")
            self.server_groups = config_data.get("serverGroups", {})
            logger.info(f"[CONFIG DEBUG] Loaded server groups: {list(self.server_groups.keys())}")
            logger.info(f"[CONFIG DEBUG] Research group contents: {self.server_groups.get('research', 'NOT FOUND')}")
            
            logger.info(f"Loaded {len(self.servers)} MCP server configurations")
            logger.info(f"[CONFIG DEBUG] Loaded servers: {list(self.servers.keys())}")
            
        except Exception as e:
            logger.error(f"Error loading MCP config: {e}")
            raise
    
    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """Get configuration for a specific server"""
        return self.servers.get(server_name)
    
    def get_server_group(self, group_name: str) -> List[str]:
        """Get list of server names in a group"""
        logger.info(f"[RUNTIME DEBUG] get_server_group called for '{group_name}'")
        logger.info(f"[RUNTIME DEBUG] Available server groups: {list(self.server_groups.keys())}")
        logger.info(f"[RUNTIME DEBUG] All server groups content: {self.server_groups}")
        result = self.server_groups.get(group_name, [])
        logger.info(f"[RUNTIME DEBUG] Returning for '{group_name}': {result}")
        return result
    
    def list_servers(self) -> List[str]:
        """List all configured server names"""
        return list(self.servers.keys())
    
    def list_groups(self) -> List[str]:
        """List all configured server groups"""
        return list(self.server_groups.keys())

    def _save_config(self):
        """Save the current server configurations back to the file."""
        config_data = {
            "mcpServers": {},
            "serverGroups": self.server_groups
        }

        for name, server_config in self.servers.items():
            config_dict = {
                "transport": server_config.transport.value,
                "description": server_config.description,
                "timeout": server_config.timeout
            }
            if server_config.command:
                config_dict["command"] = server_config.command
            if server_config.args:
                config_dict["args"] = server_config.args
            if server_config.env:
                config_dict["env"] = server_config.env
            if server_config.url:
                config_dict["url"] = server_config.url
            
            if server_config.auth:
                auth_dict = {
                    "type": server_config.auth.type.value,
                    "requires_user_auth": server_config.auth.requires_user_auth
                }
                for field in ["token", "client_id", "client_secret", "scope", "token_url", "authorization_url", "redirect_uri", "client_registration_url", "api_key", "header_name"]:
                    if hasattr(server_config.auth, field) and getattr(server_config.auth, field) is not None:
                        auth_dict[field] = getattr(server_config.auth, field)
                config_dict["auth"] = auth_dict

            config_data["mcpServers"][name] = config_dict

        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            logger.info(f"Successfully saved updated configuration to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration file: {e}")

    async def _register_dynamic_client(self, server_name: str) -> bool:
        """Dynamically register the client with the OAuth server."""
        config = self.get_server_config(server_name)
        if not config or not config.auth or not config.auth.client_registration_url:
            logger.error(f"Dynamic registration not configured for {server_name}")
            return False

        # Auto-generate redirect_uri if not set
        redirect_uri = config.auth.redirect_uri
        if not redirect_uri:
            try:
                from flask import url_for
                redirect_uri = url_for('oauth.oauth_callback', _external=True)
                logger.info(f"Auto-generated redirect URI for {server_name}: {redirect_uri}")
            except Exception:
                # Fallback if Flask context not available
                redirect_uri = f"http://localhost:5000/oauth/callback"
                logger.info(f"Using fallback redirect URI for {server_name}: {redirect_uri}")
        
        # Build registration payload with proper handling of None values
        registration_payload = {
            "client_name": "PEAK Assistant",
            "redirect_uris": [redirect_uri],  # Ensure we have a valid string
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_post"
        }
        
        # Only include scope if it's not None
        if config.auth.scope:
            registration_payload["scope"] = config.auth.scope

        logger.info(f"Attempting dynamic registration for {server_name} at {config.auth.client_registration_url}")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(config.auth.client_registration_url, json=registration_payload)
                response.raise_for_status()
                registration_data = response.json()

                # Update the in-memory config with the new credentials
                config.auth.client_id = registration_data['client_id']
                config.auth.client_secret = registration_data['client_secret']

                
                logger.info(f"Successfully registered client for {server_name}. Client ID: {config.auth.client_id}")
                logger.info(f"Dynamic credentials stored in memory only - configuration file remains unchanged")
                
                # NOTE: We deliberately do NOT save to config file to keep it read-only
                # Dynamic credentials are stored in memory only for this session
                
                return True
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to dynamically register client for {server_name}: {e.response.status_code} - {e.response.text}")
                return False
            except Exception as e:
                logger.error(f"An unexpected error occurred during dynamic registration for {server_name}: {e}")
                return False

class MCPClientManager:
    """Manages connections to multiple MCP servers"""
    def __init__(self, config_manager: 'MCPConfigManager'):
        self.config_manager = config_manager
        # Share the same UserSessionManager instance to ensure token persistence
        self.user_session_manager = config_manager.user_session_manager
        self.workbenches: Dict[str, McpWorkbench] = {}  # System-level workbenches
        self.user_workbenches: Dict[str, Dict[str, McpWorkbench]] = {}  # User-specific workbenches
        self.active_clients: Dict[str, Any] = {}
        self._cleanup_registered = False
        self._register_cleanup()
    
    def _register_cleanup(self):
        """Register cleanup handlers to prevent runtime warnings"""
        if not self._cleanup_registered:
            # Ensure global cleanup handler is registered
            _register_global_cleanup()
            # Register this instance for cleanup
            _cleanup_managers.add(self)
            self._cleanup_registered = True
    
    def _safe_cleanup(self):
        """Synchronous cleanup that can be called from atexit"""
        try:
            # Force aggressive cleanup of workbenches to prevent destructor warnings
            for workbench in list(self.workbenches.values()):
                try:
                    # Multiple approaches to prevent async destructor issues
                    if hasattr(workbench, '_actor') and workbench._actor:
                        # Mark actor as closed
                        if hasattr(workbench._actor, '_closed'):
                            workbench._actor._closed = True
                        # Clear the shutdown future to prevent awaiting
                        if hasattr(workbench._actor, '_shutdown_future'):
                            workbench._actor._shutdown_future = None
                    
                    # Remove the destructor to prevent it from running
                    if hasattr(workbench, '__del__'):
                        delattr(workbench.__class__, '__del__')
                        
                except Exception:
                    pass  # Ignore cleanup errors during shutdown
            
            # Also clean user workbenches
            for user_workbenches in self.user_workbenches.values():
                for workbench in user_workbenches.values():
                    try:
                        if hasattr(workbench, '_actor') and workbench._actor:
                            if hasattr(workbench._actor, '_closed'):
                                workbench._actor._closed = True
                            if hasattr(workbench._actor, '_shutdown_future'):
                                workbench._actor._shutdown_future = None
                        if hasattr(workbench, '__del__'):
                            delattr(workbench.__class__, '__del__')
                    except Exception:
                        pass
            
            # Clear collections
            self.workbenches.clear()
            self.user_workbenches.clear()
            self.active_clients.clear()
                
        except Exception:
            # Don't let cleanup errors propagate during shutdown
            pass
    
    async def connect_server(self, server_name: str, user_id: Optional[str] = None) -> bool:
        """Connect to an MCP server (system-level or user-specific)"""
        config = self.config_manager.get_server_config(server_name)
        if not config:
            logger.error(f"No configuration found for server: {server_name}")
            return False
        
        try:
            if config.transport == TransportType.STDIO:
                return await self._connect_stdio_server(server_name, config, user_id)
            elif config.transport == TransportType.HTTP:
                return await self._connect_http_server(server_name, config, user_id)
            elif config.transport == TransportType.SSE:
                return await self._connect_sse_server(server_name, config, user_id)
            else:
                logger.error(f"Unsupported transport type: {config.transport}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to server {server_name}: {e}")
            return False
    
    async def _connect_stdio_server(self, server_name: str, config: MCPServerConfig, user_id: Optional[str] = None) -> bool:
        """Connect to a stdio-based MCP server (typically system-level)"""
        if not config.command:
            logger.error(f"No command specified for stdio server: {server_name}")
            return False
        
        # Set up environment variables
        env = os.environ.copy()
        if config.env:
            env.update(config.env)
            logger.info(f"Setting environment variables for {server_name}: {list(config.env.keys())}")
            for key, value in config.env.items():
                logger.debug(f"  {key}={'*' * len(value) if 'PASS' in key.upper() else value}")
        
        # Create stdio server parameters
        # Fix: Ensure args is properly formatted for StdioServerParams
        args_list = config.args or []
        server_params = StdioServerParams(
            command=config.command,
            args=args_list,
            env=env
        )
        logger.debug(f"Created StdioServerParams with command: {config.command}, args: {args_list}, env keys: {list(env.keys()) if env else 'None'}")
        
        # Create workbench
        # Fix: Pass server_params directly, not as a list
        workbench = McpWorkbench(server_params)
        await workbench.__aenter__()
        
        # Store workbench (user-specific or system-level)
        if user_id:
            if user_id not in self.user_workbenches:
                self.user_workbenches[user_id] = {}
            self.user_workbenches[user_id][server_name] = workbench
        else:
            self.workbenches[server_name] = workbench
            
        logger.info(f"Connected to stdio server: {server_name}" + (f" for user {user_id}" if user_id else ""))
        return True
    
    async def _connect_http_server(self, server_name: str, config: MCPServerConfig, user_id: Optional[str] = None) -> bool:
        """Connect to an HTTP-based MCP server with mixed authentication support"""
        if not config.url:
            logger.error(f"No URL specified for HTTP server: {server_name}")
            return False
        
        # Create HTTP client with authentication
        headers = await self._get_auth_headers(config, user_id)
        if headers is False:
            return False
        
        # Store the connection (user-specific or system-level)
        self.active_clients[server_name] = {
            "type": "http",
            "url": config.url,
            "headers": headers,
            "config": config,
            "user_id": user_id
        }
        
        logger.info(f"Connected to HTTP server: {server_name}" + (f" for user {user_id}" if user_id else ""))
        return True

    async def _get_auth_headers(self, config: MCPServerConfig, user_id: Optional[str] = None) -> Dict[str, str]:
        """Get authentication headers for a server"""
        headers = {}
        if config.auth:
            if config.auth.type == AuthType.BEARER:
                if not config.auth.token:
                    logger.error(f"No token specified for bearer auth on {config.name}")
                    return False
                headers["Authorization"] = f"Bearer {config.auth.token}"
            elif config.auth.type == AuthType.API_KEY:
                if not config.auth.api_key or not config.auth.header_name:
                    logger.error(f"API key or header name not specified for {config.name}")
                    return False
                headers[config.auth.header_name] = config.auth.api_key
            elif config.auth.type in [AuthType.OAUTH2_CLIENT_CREDENTIALS, AuthType.OAUTH2_AUTHORIZATION_CODE]:
                if not user_id and config.auth.requires_user_auth:
                    logger.error(f"User ID is required for user-based OAuth on {config.name}")
                    return False
                
                # Use authlib OAuth manager for OAuth token handling
                try:
                    from .authlib_oauth import get_oauth_manager
                    oauth_manager = get_oauth_manager()
                    
                    # Get authentication headers from OAuth manager using hybrid approach (OAuth client + manual fallback)
                    oauth_headers = oauth_manager.get_fresh_auth_headers(config.name)
                    if oauth_headers:
                        headers.update(oauth_headers)
                    else:
                        logger.error(f"No valid OAuth token available for {config.name}")
                        return False
                        
                except Exception as e:
                    logger.error(f"Failed to get OAuth headers for {config.name}: {e}")
                    return False
        
        return headers
    
    async def _connect_sse_server(self, server_name: str, config: MCPServerConfig, user_id: Optional[str] = None) -> bool:
        """Connect to an SSE-based MCP server"""
        logger.info(f"[SSE DEBUG] Starting connection to {server_name} for user_id: {user_id}")
        
        if not config.url:
            logger.error(f"[SSE DEBUG] No URL specified for SSE server: {server_name}")
            return False

        logger.info(f"[SSE DEBUG] Getting auth headers for {server_name}")
        headers = await self._get_auth_headers(config, user_id)
        if headers is False:
            logger.error(f"[SSE DEBUG] Failed to get auth headers for {server_name}")
            return False
        
        logger.info(f"[SSE DEBUG] Auth headers obtained for {server_name}: {list(headers.keys()) if headers else 'None'}")

        try:
            # Use SseServerParams approach for proper AutoGen compatibility
            from autogen_ext.tools.mcp import SseServerParams
            
            logger.info(f"[SSE DEBUG] Creating SseServerParams for {server_name}")
            # Create proper SseServerParams object with extended timeouts for stability
            server_params = SseServerParams(
                url=config.url,
                headers=headers,
                timeout=config.timeout or 60.0,
                sse_read_timeout=300.0  # 5 minutes read timeout
            )
            logger.info(f"[SSE DEBUG] SseServerParams created successfully for {server_name}")
            
            # Create workbench with SseServerParams - let McpWorkbench handle connection lifecycle
            logger.info(f"[SSE DEBUG] Creating McpWorkbench for {server_name}")
            workbench = McpWorkbench(server_params)
            logger.info(f"[SSE DEBUG] Entering workbench context for {server_name}")
            await workbench.__aenter__()
            logger.info(f"[SSE DEBUG] Workbench context entered successfully for {server_name}")
            
            # Test connection health by listing tools
            try:
                logger.info(f"[SSE DEBUG] Testing connection by listing tools for {server_name}")
                tools = await workbench.list_tools()
                logger.info(f"[SSE DEBUG] SSE workbench for {server_name} connected successfully with {len(tools)} tools available")
            except Exception as e:
                logger.warning(f"[SSE DEBUG] SSE workbench for {server_name} connection test failed: {e}")
                # Try to continue anyway
            
            # Store workbench (user-specific or system-level)
            logger.info(f"[SSE DEBUG] Storing workbench for {server_name}, user_id: {user_id}")
            if user_id:
                if user_id not in self.user_workbenches:
                    self.user_workbenches[user_id] = {}
                    logger.info(f"[SSE DEBUG] Created new user_workbenches entry for user {user_id}")
                self.user_workbenches[user_id][server_name] = workbench
                logger.info(f"[SSE DEBUG] Stored user-specific workbench for {server_name} under user {user_id}")
                logger.info(f"[SSE DEBUG] Current user_workbenches keys: {list(self.user_workbenches.keys())}")
                logger.info(f"[SSE DEBUG] Workbenches for user {user_id}: {list(self.user_workbenches[user_id].keys())}")
            else:
                self.workbenches[server_name] = workbench
                logger.info(f"[SSE DEBUG] Stored system-level workbench for {server_name}")
                logger.info(f"[SSE DEBUG] Current system workbenches: {list(self.workbenches.keys())}")

            # Store connection info for proper cleanup (simplified for SseServerParams)
            self.active_clients[server_name] = {
                "type": "sse",
                "url": config.url,
                "config": config,
                "headers": headers,
                "workbench": workbench,
                "user_id": user_id
            }
            logger.info(f"[SSE DEBUG] Active client info stored for {server_name}")
            logger.info(f"Connected to SSE server and created workbench: {server_name}")
        except Exception as e:
            logger.error(f"Failed to connect to SSE server {server_name}: {e}")
            return False
        return True
    
    async def connect_servers(self, server_names: List[str], user_id: Optional[str] = None) -> List[str]:
        """Connect to multiple servers with optional user context, return list of successfully connected servers"""
        connected = []
        for server_name in server_names:
            if await self.connect_server(server_name, user_id=user_id):
                connected.append(server_name)
        return connected
    
    async def connect_server_group(self, group_name: str, user_id: Optional[str] = None) -> List[str]:
        """Connect to all servers in a group with optional user context for OAuth authentication"""
        server_names = self.config_manager.get_server_group(group_name)
        if not server_names:
            logger.warning(f"No servers found in group: {group_name}")
            return []
        
        return await self.connect_servers(server_names, user_id=user_id)
    
    def get_workbench(self, server_name: str, user_id: Optional[str] = None) -> Optional[McpWorkbench]:
        """Get the workbench for a server, checking both user-specific and system-level storage"""
        # First check user-specific workbenches if user_id is provided
        if user_id and user_id in self.user_workbenches:
            workbench = self.user_workbenches[user_id].get(server_name)
            if workbench:
                return workbench
        
        # Fall back to system-level workbenches
        return self.workbenches.get(server_name)
    
    def get_all_workbenches(self) -> List[McpWorkbench]:
        """Get all active workbenches"""
        return list(self.workbenches.values())
    
    async def disconnect_server(self, server_name: str):
        """Disconnect from a server with proper error handling"""
        # Handle connection-specific shutdown first (e.g., for SSE)
        if server_name in self.active_clients:
            client_info = self.active_clients.get(server_name, {})
            if client_info.get("type") == "sse":
                context_manager = client_info.get("context_manager")
                if context_manager and hasattr(context_manager, "__aexit__"):
                    try:
                        await context_manager.__aexit__(None, None, None)
                        logger.info(f"Closed SSE context manager for {server_name}")
                    except Exception as e:
                        logger.warning(f"Error closing SSE context manager for {server_name}: {e}")

        # Handle workbench shutdown (for stdio)
        if server_name in self.workbenches:
            workbench = self.workbenches[server_name]
            try:
                if hasattr(workbench, 'stop'):
                    await workbench.stop()
            except Exception as e:
                logger.warning(f"Error during graceful shutdown of {server_name}: {e}")
            finally:
                del self.workbenches[server_name]
        
        if server_name in self.active_clients:
            del self.active_clients[server_name]
        
        logger.info(f"Disconnected from server: {server_name}")
    
    async def disconnect_all(self):
        """Disconnect from all servers with error isolation"""
        server_names = list(self.workbenches.keys())
        
        for server_name in server_names:
            try:
                await self.disconnect_server(server_name)
            except Exception as e:
                logger.error(f"Failed to disconnect server {server_name}: {e}")
                # Continue with other servers even if one fails
                if server_name in self.workbenches:
                    del self.workbenches[server_name]

# Global instances for easy access
_config_manager = None
_client_manager = None

# Global cleanup management
_cleanup_managers = weakref.WeakSet()
_cleanup_registered = False

def _cleanup_all_managers():
    """Clean up all MCP client managers during shutdown"""
    for manager in list(_cleanup_managers):
        try:
            manager._safe_cleanup()
        except Exception:
            pass  # Ignore cleanup errors during shutdown

def _register_global_cleanup():
    """Register global cleanup handler once"""
    global _cleanup_registered
    if not _cleanup_registered:
        atexit.register(_cleanup_all_managers)
        _cleanup_registered = True

def get_config_manager(config_file: Optional[str] = None) -> MCPConfigManager:
    """Get global MCP configuration manager"""
    global _config_manager
    if _config_manager is None:
        _config_manager = MCPConfigManager(config_file)
    return _config_manager

def get_client_manager(config_file: Optional[str] = None) -> MCPClientManager:
    """Get global MCP client manager"""
    global _client_manager
    if _client_manager is None:
        config_manager = get_config_manager(config_file)
        _client_manager = MCPClientManager(config_manager)
    return _client_manager

async def setup_mcp_servers(server_group: str = "all", user_id: Optional[str] = None) -> List[str]:
    """Set up MCP servers for a specific group with optional user context for OAuth authentication"""
    client_manager = get_client_manager()
    return await client_manager.connect_server_group(server_group, user_id=user_id)

def find_dotenv_file():
    """Search for a .env file in current directory and parent directories"""
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:  # Stop at root directory
        env_path = current_dir / '.env'
        if env_path.exists():
            return str(env_path)
        current_dir = current_dir.parent
    return None  # No .env file found

# Initialize environment variables
dotenv_path = find_dotenv_file()
if dotenv_path:
    load_dotenv(dotenv_path)
