#!/usr/bin/env python3

import json
import os
import asyncio
import httpx
import atexit
import weakref
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from enum import Enum
import logging
from dotenv import load_dotenv

from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

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
    api_key: Optional[str] = None
    header_name: Optional[str] = "Authorization"
    requires_user_auth: bool = False         # True for authorization code flow

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
    
    def __init__(self, auth_config: AuthConfig, user_id: Optional[str] = None):
        self.auth_config = auth_config
        self.user_id = user_id  # For user-specific tokens
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        
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
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.auth_config.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            
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
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.auth_config.token_url,
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
            "redirect_uri": self.auth_config.redirect_uri,
            "client_id": self.auth_config.client_id,
            "client_secret": self.auth_config.client_secret,
        }
        
        # Add PKCE code verifier if provided
        if code_verifier:
            data["code_verifier"] = code_verifier
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.auth_config.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data.get("refresh_token")
            
            # Calculate expiry time
            import time
            expires_in = token_data.get("expires_in", 3600)
            self.token_expiry = time.time() + expires_in - 300
            
            return self.access_token
    
    def get_authorization_url(self, state: str, code_challenge: Optional[str] = None) -> str:
        """Generate OAuth2 authorization URL for authorization code flow"""
        if not self.auth_config.authorization_url:
            raise ValueError("Authorization URL not configured")
        
        params = {
            "response_type": "code",
            "client_id": self.auth_config.client_id,
            "redirect_uri": self.auth_config.redirect_uri,
            "state": state,
        }
        
        if self.auth_config.scope:
            params["scope"] = self.auth_config.scope
            
        # Add PKCE challenge if provided
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        from urllib.parse import urlencode
        return f"{self.auth_config.authorization_url}?{urlencode(params)}"

class UserSessionManager:
    """Manages user-specific OAuth tokens and sessions"""
    
    def __init__(self):
        # In-memory storage for user sessions (in production, use Redis/database)
        self.user_sessions: Dict[str, Dict[str, OAuth2TokenManager]] = {}
        self.user_states: Dict[str, Dict[str, str]] = {}  # For OAuth state tracking
    
    def get_or_create_token_manager(self, user_id: str, server_name: str, auth_config: AuthConfig) -> OAuth2TokenManager:
        """Get or create a token manager for a specific user and server"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        
        if server_name not in self.user_sessions[user_id]:
            self.user_sessions[user_id][server_name] = OAuth2TokenManager(auth_config, user_id)
        
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
    """Manages MCP server configurations and client connections"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._find_config_file()
        self.servers: Dict[str, MCPServerConfig] = {}
        self.server_groups: Dict[str, List[str]] = {}
        self.oauth_managers: Dict[str, OAuth2TokenManager] = {}  # For client credentials
        self.user_session_manager = UserSessionManager()
        self._load_config()
    
    def _find_config_file(self) -> str:
        """Find the MCP configuration file"""
        possible_paths = [
            "mcp_servers.json",
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
        if not os.path.exists(self.config_file):
            logger.warning(f"MCP config file not found: {self.config_file}")
            return
            
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
            
            # Load server configurations
            for name, server_config in config_data.get("mcpServers", {}).items():
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
                        api_key=auth_data.get("api_key"),
                        header_name=auth_data.get("header_name", "Authorization")
                    )
                
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
                    self.oauth_managers[name] = OAuth2TokenManager(auth_config)
                elif auth_config and auth_config.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
                    # User-specific token managers will be created on-demand
                    pass
            
            # Load server groups
            self.server_groups = config_data.get("serverGroups", {})
            
            logger.info(f"Loaded {len(self.servers)} MCP server configurations")
            
        except Exception as e:
            logger.error(f"Error loading MCP config: {e}")
            raise
    
    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """Get configuration for a specific server"""
        return self.servers.get(server_name)
    
    def get_server_group(self, group_name: str) -> List[str]:
        """Get list of server names in a group"""
        return self.server_groups.get(group_name, [])
    
    def list_servers(self) -> List[str]:
        """List all configured server names"""
        return list(self.servers.keys())
    
    def list_groups(self) -> List[str]:
        """List all configured server groups"""
        return list(self.server_groups.keys())

class MCPClientManager:
    """Manages MCP client connections and tool execution"""
    
    def __init__(self, config_manager: MCPConfigManager):
        self.config_manager = config_manager
        self.active_clients: Dict[str, Any] = {}
        self.workbenches: Dict[str, McpWorkbench] = {}
        self.user_workbenches: Dict[str, Dict[str, McpWorkbench]] = {}  # user_id -> {server_name -> workbench}
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
        headers = {}
        if config.auth:
            if config.auth.type == AuthType.BEARER:
                headers["Authorization"] = f"Bearer {config.auth.token}"
            elif config.auth.type == AuthType.API_KEY:
                headers[config.auth.header_name] = config.auth.api_key
            elif config.auth.type == AuthType.OAUTH2_CLIENT_CREDENTIALS:
                # System-level authentication
                token_manager = self.config_manager.oauth_managers.get(server_name)
                if token_manager:
                    try:
                        token = await token_manager.get_token()
                        headers["Authorization"] = f"Bearer {token}"
                    except Exception as e:
                        logger.error(f"Failed to get OAuth token for {server_name}: {e}")
                        return False
            elif config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
                # User-specific authentication
                if not user_id:
                    logger.error(f"User ID required for authorization code flow server: {server_name}")
                    return False
                
                token_manager = self.config_manager.user_session_manager.get_or_create_token_manager(
                    user_id, server_name, config.auth
                )
                
                if not token_manager.access_token:
                    logger.warning(f"No access token available for user {user_id} on server {server_name}. User must authenticate.")
                    return False
                
                try:
                    token = await token_manager.get_token()
                    headers["Authorization"] = f"Bearer {token}"
                except Exception as e:
                    logger.error(f"Failed to get user OAuth token for {server_name}: {e}")
                    return False
        
        # Store the connection (user-specific or system-level)
        connection_key = f"{server_name}_{user_id}" if user_id else server_name
        self.active_clients[connection_key] = {
            "type": "http",
            "url": config.url,
            "headers": headers,
            "config": config,
            "user_id": user_id
        }
        
        logger.info(f"Connected to HTTP server: {server_name}" + (f" for user {user_id}" if user_id else ""))
        return True
    
    async def _connect_sse_server(self, server_name: str, config: MCPServerConfig) -> bool:
        """Connect to an SSE-based MCP server"""
        if not config.url:
            logger.error(f"No URL specified for SSE server: {server_name}")
            return False
        
        # SSE connection logic would go here
        # For now, store the config
        self.active_clients[server_name] = {
            "type": "sse",
            "url": config.url,
            "config": config
        }
        
        logger.info(f"Connected to SSE server: {server_name}")
        return True
    
    async def connect_servers(self, server_names: List[str]) -> List[str]:
        """Connect to multiple servers, return list of successfully connected servers"""
        connected = []
        for server_name in server_names:
            if await self.connect_server(server_name):
                connected.append(server_name)
        return connected
    
    async def connect_server_group(self, group_name: str) -> List[str]:
        """Connect to all servers in a group"""
        server_names = self.config_manager.get_server_group(group_name)
        if not server_names:
            logger.warning(f"No servers found in group: {group_name}")
            return []
        
        return await self.connect_servers(server_names)
    
    def get_workbench(self, server_name: str) -> Optional[McpWorkbench]:
        """Get the workbench for a stdio server"""
        return self.workbenches.get(server_name)
    
    def get_all_workbenches(self) -> List[McpWorkbench]:
        """Get all active workbenches"""
        return list(self.workbenches.values())
    
    async def disconnect_server(self, server_name: str):
        """Disconnect from a server with proper error handling"""
        if server_name in self.workbenches:
            workbench = self.workbenches[server_name]
            try:
                # Try graceful shutdown first
                if hasattr(workbench, 'stop'):
                    await workbench.stop()
                else:
                    await workbench.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error during graceful shutdown of {server_name}: {e}")
                # Force cleanup even if graceful shutdown fails
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

async def setup_mcp_servers(server_group: str = "all") -> List[str]:
    """Set up MCP servers for a specific group"""
    client_manager = get_client_manager()
    return await client_manager.connect_server_group(server_group)

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
