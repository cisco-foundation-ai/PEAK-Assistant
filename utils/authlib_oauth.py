#!/usr/bin/env python3
"""
Authlib-based OAuth2 manager for PEAK Assistant
Replaces custom OAuth2TokenManager with Authlib integration
"""

import logging
from typing import Dict, Optional, Any
from authlib.integrations.flask_client import OAuth, FlaskOAuth2App
from authlib.oauth2.rfc6749 import OAuth2Token
from flask import Flask, session
from .mcp_config import MCPConfigManager, AuthType, AuthConfig

logger = logging.getLogger(__name__)


class AuthlibOAuthManager:
    """Manages OAuth2 authentication using Authlib for Flask integration"""
    
    def __init__(self, app: Optional[Flask] = None, config_manager: Optional[MCPConfigManager] = None):
        self.oauth = OAuth()
        self.config_manager = config_manager
        self.clients: Dict[str, FlaskOAuth2App] = {}
        self.user_tokens: Dict[str, Dict[str, OAuth2Token]] = {}  # user_id -> server_name -> token
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize the OAuth manager with Flask app"""
        self.oauth.init_app(app)
        
        # Configure OAuth clients from MCP server configs
        if self.config_manager:
            self._configure_oauth_clients()
    
    def _configure_oauth_clients(self):
        """Configure OAuth clients from MCP server configurations"""
        servers = self.config_manager.get_all_servers()
        
        for server_name, config in servers.items():
            if config.auth and config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
                self._register_oauth_client(server_name, config.auth, config.url)
    
    def _register_oauth_client(self, server_name: str, auth_config: AuthConfig, server_url: Optional[str] = None):
        """Register an OAuth client with Authlib"""
        try:
            client_kwargs = {}
            
            # Add scope if specified
            if auth_config.scope:
                client_kwargs['scope'] = auth_config.scope
                
            # Enable PKCE for security
            client_kwargs['code_challenge_method'] = 'S256'
            
            # Add client metadata for proper identification
            client_kwargs.update({
                'client_name': 'PEAK Assistant',
                'client_uri': 'https://github.com/splunk/PEAK-Assistant',
                'logo_uri': None,  # Could add logo URL if available
                'tos_uri': None,   # Terms of service URL if available
                'policy_uri': None # Privacy policy URL if available
            })
            
            # Configure discovery or manual endpoints
            if auth_config.discovery_url or (auth_config.enable_discovery and server_url):
                # Use OAuth discovery
                discovery_url = auth_config.discovery_url or self._derive_discovery_url(server_url)
                if discovery_url:
                    metadata_url = f"{discovery_url}/.well-known/oauth-authorization-server"
                    
                    self.clients[server_name] = self.oauth.register(
                        override=True,
                        name=server_name,
                        client_id=auth_config.client_id,
                        client_secret=auth_config.client_secret,
                        server_metadata_url=metadata_url,
                        client_kwargs=client_kwargs
                    )
                    logger.info(f"Registered OAuth client for {server_name} with discovery: {metadata_url}")
                else:
                    logger.warning(f"Could not derive discovery URL for {server_name}")
                    self._register_manual_client(server_name, auth_config, client_kwargs)
            else:
                # Manual endpoint configuration
                self._register_manual_client(server_name, auth_config, client_kwargs)
                
        except Exception as e:
            logger.error(f"Failed to register OAuth client for {server_name}: {e}")
    
    def _register_manual_client(self, server_name: str, auth_config: AuthConfig, client_kwargs: Dict):
        """Register OAuth client with manual endpoint configuration"""
        if not auth_config.authorization_url or not auth_config.token_url:
            logger.error(f"Missing OAuth endpoints for {server_name}")
            return
            
        self.clients[server_name] = self.oauth.register(
                        override=True,
            name=server_name,
            client_id=auth_config.client_id,
            client_secret=auth_config.client_secret,
            authorize_url=auth_config.authorization_url,
            access_token_url=auth_config.token_url,
            client_kwargs=client_kwargs
        )
        logger.info(f"Registered OAuth client for {server_name} with manual endpoints")
    
    def _derive_discovery_url(self, server_url: str) -> Optional[str]:
        """Derive discovery URL from server URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(server_url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception as e:
            logger.error(f"Failed to derive discovery URL from {server_url}: {e}")
            return None
    
    def get_client(self, server_name: str) -> Optional[FlaskOAuth2App]:
        """Get OAuth client for a server"""
        return self.clients.get(server_name)

    def update_client(self, server_name: str):
        """Reload a client's configuration and re-register it."""
        if not self.config_manager:
            logger.error("Cannot update client without a config manager.")
            return

        config = self.config_manager.get_server_config(server_name)
        if config and config.auth and config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
            logger.info(f"Updating and re-registering client for {server_name}")
            self._register_oauth_client(server_name, config.auth, config.url)
        else:
            logger.warning(f"Could not find configuration to update for client {server_name}")

    def update_client(self, server_name: str):
        """Reload a client's configuration and re-register it."""
        if not self.config_manager:
            logger.error("Cannot update client without a config manager.")
            return

        config = self.config_manager.get_server_config(server_name)
        if config and config.auth and config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
            logger.info(f"Updating and re-registering client for {server_name}")
            self._register_oauth_client(server_name, config.auth, config.url)
        else:
            logger.warning(f"Could not find configuration to update for client {server_name}")
    
    def store_token(self, server_name: str, token: OAuth2Token, user_id: Optional[str] = None):
        """Store OAuth token for a user and server"""
        if not user_id:
            user_id = session.get('user_id', 'default')
            
        if user_id not in self.user_tokens:
            self.user_tokens[user_id] = {}
            
        self.user_tokens[user_id][server_name] = token
        logger.info(f"[TOKEN DEBUG] Stored OAuth token for user {user_id}, server {server_name}")
        logger.info(f"[TOKEN DEBUG] Token type: {type(token)}, Token keys: {list(token.keys()) if hasattr(token, 'keys') else 'N/A'}")
        logger.info(f"[TOKEN DEBUG] Current user tokens count: {len(self.user_tokens.get(user_id, {}))}") 
    
    def get_token(self, server_name: str, user_id: Optional[str] = None) -> Optional[OAuth2Token]:
        """Get OAuth token for a user and server"""
        if not user_id:
            user_id = session.get('user_id', 'default')
        
        token = self.user_tokens.get(user_id, {}).get(server_name)
        logger.info(f"[TOKEN DEBUG] Getting token for user {user_id}, server {server_name}: {'Found' if token else 'Not found'}")
        return token
    
    def has_valid_token(self, server_name: str, user_id: Optional[str] = None) -> bool:
        """Check if user has a valid token for a server"""
        token = self.get_token(server_name, user_id)
        if not token:
            logger.info(f"[TOKEN DEBUG] No token found for server {server_name}, user {user_id or session.get('user_id', 'default')}")
            return False
        
        try:
            # Check if token is expired (Authlib handles this automatically)
            is_expired = token.is_expired()
            logger.info(f"[TOKEN DEBUG] Token for {server_name} expired: {is_expired}")
            return not is_expired
        except Exception as e:
            logger.error(f"[TOKEN DEBUG] Error checking token expiration for {server_name}: {e}")
            logger.info(f"[TOKEN DEBUG] Token object type: {type(token)}, attributes: {dir(token)}")
            # Fallback: if we can't check expiration, assume token is valid
            return True
    
    def clear_token(self, server_name: str, user_id: Optional[str] = None):
        """Clear token for a user and server"""
        if not user_id:
            user_id = session.get('user_id', 'default')
            
        if user_id in self.user_tokens and server_name in self.user_tokens[user_id]:
            del self.user_tokens[user_id][server_name]
            logger.info(f"Cleared OAuth token for user {user_id}, server {server_name}")
    
    def clear_user_tokens(self, user_id: str):
        """Clear all tokens for a user"""
        if user_id in self.user_tokens:
            del self.user_tokens[user_id]
            logger.info(f"Cleared all OAuth tokens for user {user_id}")
    
    def get_servers_needing_auth(self, user_id: Optional[str] = None) -> list:
        """Get list of servers that need authentication for a user"""
        if not user_id:
            user_id = session.get('user_id', 'default')
            
        servers_needing_auth = []
        
        for server_name in self.clients.keys():
            if not self.has_valid_token(server_name, user_id):
                servers_needing_auth.append(server_name)
                
        return servers_needing_auth
    
    def get_auth_headers(self, server_name: str, user_id: Optional[str] = None) -> Dict[str, str]:
        """Get authentication headers for a server using stored token"""
        token = self.get_token(server_name, user_id)
        if not token:
            return {}
            
        return {
            'Authorization': f'Bearer {token["access_token"]}'
        }
    
    def refresh_token_if_needed(self, server_name: str, user_id: Optional[str] = None) -> bool:
        """Refresh token if needed and possible"""
        token = self.get_token(server_name, user_id)
        if not token:
            return False
            
        client = self.get_client(server_name)
        if not client:
            return False
            
        try:
            # Authlib automatically handles token refresh if refresh_token is available
            if token.is_expired() and 'refresh_token' in token:
                new_token = client.refresh_token(token['refresh_token'])
                self.store_token(server_name, new_token, user_id)
                logger.info(f"Refreshed OAuth token for user {user_id}, server {server_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to refresh token for {server_name}: {e}")
            
        return False


# Global OAuth manager instance
oauth_manager = None


def get_oauth_manager() -> AuthlibOAuthManager:
    """Get global OAuth manager instance"""
    global oauth_manager
    if oauth_manager is None:
        from .mcp_config import get_config_manager
        config_manager = get_config_manager()
        oauth_manager = AuthlibOAuthManager(config_manager=config_manager)
    return oauth_manager


def init_oauth_manager(app: Flask) -> AuthlibOAuthManager:
    """Initialize OAuth manager with Flask app"""
    global oauth_manager
    if oauth_manager is None:
        from .mcp_config import get_config_manager
        config_manager = get_config_manager()
        oauth_manager = AuthlibOAuthManager(app, config_manager)
    else:
        oauth_manager.init_app(app)
    return oauth_manager
