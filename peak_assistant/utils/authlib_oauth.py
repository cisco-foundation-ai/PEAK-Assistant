#!/usr/bin/env python3
"""
Authlib-based OAuth2 manager for PEAK Assistant
Replaces custom OAuth2TokenManager with Authlib integration
"""

import logging
from typing import Optional, Dict
from flask import Flask, session
from authlib.integrations.flask_client import OAuth, FlaskOAuth2App
from authlib.oauth2.rfc6749 import OAuth2Token
from .mcp_config import MCPConfigManager, AuthType, AuthConfig

logger = logging.getLogger(__name__)


class AuthlibOAuthManager:
    """Manages OAuth2 authentication using Authlib for Flask integration"""

    def __init__(
        self,
        app: Optional[Flask] = None,
        config_manager: Optional[MCPConfigManager] = None,
    ):
        # Create OAuth with global update_token callback
        self.oauth = OAuth(update_token=self.update_token)
        self.config_manager = config_manager
        self.clients: Dict[str, FlaskOAuth2App] = {}

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

    def update_token(
        self, name: str, token: dict, refresh_token: str = "", access_token: str = ""
    ):
        """Global callback for automatic token updates from Authlib"""
        if refresh_token:
            token["refresh_token"] = refresh_token
        if access_token:
            token["access_token"] = access_token

        # Store the updated token
        oauth_token = OAuth2Token(token)
        logger.info(f"[SESSION DEBUG] Before storing updated token for {name}:")
        logger.info(
            f"[SESSION DEBUG] Session has oauth_tokens: {'oauth_tokens' in session}"
        )
        if "oauth_tokens" in session:
            logger.info(
                f"[SESSION DEBUG] Current session tokens: {list(session['oauth_tokens'].keys())}"
            )

        self.store_token(name, oauth_token)

        logger.info(f"[SESSION DEBUG] After storing updated token for {name}:")
        logger.info(
            f"[SESSION DEBUG] Session has oauth_tokens: {'oauth_tokens' in session}"
        )
        if "oauth_tokens" in session:
            logger.info(
                f"[SESSION DEBUG] Session tokens after store: {list(session['oauth_tokens'].keys())}"
            )
            if name in session["oauth_tokens"]:
                stored_token = OAuth2Token(session["oauth_tokens"][name])
                logger.info(
                    f"[SESSION DEBUG] Stored token expires_at: {stored_token.get('expires_at')} ({'expired' if stored_token.is_expired() else 'valid'})"
                )

        logger.info(f"Automatically updated token for {name}")

    def _register_oauth_client(
        self,
        server_name: str,
        auth_config: AuthConfig,
        server_url: Optional[str] = None,
    ):
        """Register an OAuth client with Authlib"""
        try:
            client_kwargs = {}

            # Add scope if specified
            if auth_config.scope:
                client_kwargs["scope"] = auth_config.scope

            # Enable PKCE for security
            client_kwargs["code_challenge_method"] = "S256"

            # Add client metadata for proper identification
            client_kwargs.update(
                {
                    "client_name": "PEAK Assistant",
                    "client_uri": "https://github.com/splunk/PEAK-Assistant",
                    "logo_uri": None,  # Could add logo URL if available
                    "tos_uri": None,  # Terms of service URL if available
                    "policy_uri": None,  # Privacy policy URL if available
                }
            )

            # Configure discovery or manual endpoints
            if auth_config.discovery_url or (
                auth_config.enable_discovery and server_url
            ):
                # Use OAuth discovery
                discovery_url = auth_config.discovery_url or self._derive_discovery_url(
                    server_url
                )
                if discovery_url:
                    metadata_url = (
                        f"{discovery_url}/.well-known/oauth-authorization-server"
                    )
                    logger.info(
                        f"Registering OAuth client for {server_name} with discovery: {metadata_url}"
                    )

                    self.clients[server_name] = self.oauth.register(
                        override=True,
                        name=server_name,
                        client_id=auth_config.client_id,
                        client_secret=auth_config.client_secret,
                        server_metadata_url=metadata_url,
                        client_kwargs=client_kwargs,
                    )
                else:
                    logger.warning(f"Could not derive discovery URL for {server_name}")
                    # Fall through to manual configuration

            # Manual endpoint configuration (also used as fallback)
            if (
                not discovery_url
                or not auth_config.discovery_url
                and not (auth_config.enable_discovery and server_url)
            ):
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
                    client_kwargs=client_kwargs,
                )
                logger.info(
                    f"Registered OAuth client for {server_name} with manual endpoints"
                )

        except Exception as e:
            logger.error(f"Failed to register OAuth client for {server_name}: {e}")

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

    def store_token(self, server_name: str, token: OAuth2Token):
        """Store OAuth token for a user and server in the Flask session."""
        if "oauth_tokens" not in session:
            session["oauth_tokens"] = {}
        # Store as dict for proper session serialization
        session["oauth_tokens"][server_name] = dict(token)
        session.modified = True
        logger.info(f"[TOKEN DEBUG] Stored token for server {server_name} in session.")
        logger.info(
            f"[TOKEN DEBUG] Token type: {type(token)}, Token keys: {list(token.keys()) if hasattr(token, 'keys') else 'N/A'}"
        )
        logger.info(
            f"[TOKEN DEBUG] Token expires_at: {token.get('expires_at')} ({'expired' if token.is_expired() else 'valid'})"
        )
        logger.info(
            f"[TOKEN DEBUG] Current user tokens count: {len(session['oauth_tokens'])}"
        )

    def get_token(self, server_name: str) -> Optional[OAuth2Token]:
        """Get OAuth token for a user and server from the Flask session."""
        if "oauth_tokens" in session and server_name in session["oauth_tokens"]:
            token_dict = session["oauth_tokens"][server_name]
            logger.info(
                f"[TOKEN DEBUG] Getting token for server {server_name} from session: Found"
            )
            return OAuth2Token(token_dict)
        logger.info(f"[TOKEN DEBUG] No token found in session for server {server_name}")
        return None

    def has_valid_token(self, server_name: str) -> bool:
        """Check if user has a valid token for a server"""
        token = self.get_token(server_name)
        if not token:
            logger.info(f"[TOKEN DEBUG] No token found for server {server_name}")
            return False

        # Check if token is expired (Authlib handles this automatically)
        is_expired = token.is_expired()
        logger.info(f"[TOKEN DEBUG] Token for {server_name} expired: {is_expired}")
        return not is_expired

    def clear_tokens(self, server_name: str):
        """Clear OAuth tokens for a specific server from the Flask session."""
        if "oauth_tokens" in session and server_name in session["oauth_tokens"]:
            del session["oauth_tokens"][server_name]
            session.modified = True
            logger.info(
                f"[TOKEN DEBUG] Cleared token for server {server_name} from session."
            )

    def clear_user_session(self, user_id: str):
        """Clear all OAuth tokens from the Flask session."""
        if "oauth_tokens" in session:
            del session["oauth_tokens"]
            session.modified = True
            logger.info(f"[TOKEN DEBUG] Cleared all OAuth tokens from session.")

    def get_servers_needing_auth(self, user_id: Optional[str] = None) -> list:
        """Get list of servers that need authentication for a user"""
        if not user_id:
            user_id = session.get("user_id", "default")

        servers_needing_auth = []

        for server_name in self.clients.keys():
            if not self.has_valid_token(server_name):
                servers_needing_auth.append(server_name)

        return servers_needing_auth

    def get_auth_headers(self, server_name: str) -> Dict[str, str]:
        """Get authentication headers for a server using stored token with automatic refresh"""
        token = self.get_token(server_name)
        if not token:
            return {}

        # Check if token is expired and refresh if needed
        if token.is_expired():
            logger.info(
                f"[TOKEN DEBUG] Token for {server_name} is expired, attempting refresh"
            )
            if self._refresh_token_manually(server_name, token):
                # Get the refreshed token
                token = self.get_token(server_name)
                if not token:
                    logger.error(
                        f"[TOKEN DEBUG] Failed to get refreshed token for {server_name}"
                    )
                    return {}
            else:
                logger.error(f"[TOKEN DEBUG] Failed to refresh token for {server_name}")
                return {}

        return {"Authorization": f"Bearer {token['access_token']}"}

    def _refresh_token_manually(self, server_name: str, token: OAuth2Token) -> bool:
        """Manually refresh an expired token using direct HTTP request"""
        try:
            client = self.get_client(server_name)
            if not client:
                logger.error(f"[TOKEN DEBUG] No OAuth client found for {server_name}")
                return False

            # Get client credentials (try dynamic credentials first, then static)
            client_id = token.get("_dynamic_client_id") or client.client_id
            client_secret = token.get("_dynamic_client_secret") or client.client_secret

            if not client_id or not client_secret:
                logger.warning(
                    f"[TOKEN DEBUG] No client credentials available for {server_name} - skipping refresh"
                )
                logger.warning(
                    f"[TOKEN DEBUG] Checked dynamic credentials: {bool(token.get('_dynamic_client_id'))}, static credentials: {bool(client.client_id)}"
                )
                return False

            logger.info(
                f"[TOKEN DEBUG] Using {'dynamic' if token.get('_dynamic_client_id') else 'static'} client credentials for {server_name}"
            )

            # Get token endpoint (try dynamic token URL first, then client metadata)
            token_endpoint = token.get("_dynamic_token_url")
            if not token_endpoint:
                if hasattr(client, "server_metadata") and client.server_metadata:
                    token_endpoint = client.server_metadata.get("token_endpoint")
                else:
                    logger.error(
                        f"[TOKEN DEBUG] No server metadata available for {server_name}"
                    )
                    return False

            if not token_endpoint:
                logger.error(f"[TOKEN DEBUG] No token endpoint found for {server_name}")
                return False

            logger.info(
                f"[TOKEN DEBUG] Using {'dynamic' if token.get('_dynamic_token_url') else 'metadata'} token endpoint: {token_endpoint}"
            )

            # Prepare refresh request
            import requests
            from requests.auth import HTTPBasicAuth

            refresh_token = token.get("refresh_token")
            if not refresh_token:
                logger.error(
                    f"[TOKEN DEBUG] No refresh token available for {server_name}"
                )
                return False

            # Try HTTP Basic auth first
            auth = HTTPBasicAuth(client_id, client_secret)
            data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

            logger.info(
                f"[TOKEN DEBUG] Attempting token refresh for {server_name} at {token_endpoint}"
            )

            response = requests.post(
                token_endpoint,
                auth=auth,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )

            if response.status_code == 200:
                new_token_data = response.json()
                logger.info(f"[TOKEN DEBUG] Token refresh successful for {server_name}")

                # Debug the token data
                logger.info(
                    f"[TOKEN DEBUG] Old token expires_at: {token.get('expires_at')}"
                )
                logger.info(
                    f"[TOKEN DEBUG] New token data keys: {list(new_token_data.keys())}"
                )
                logger.info(
                    f"[TOKEN DEBUG] New token expires_in: {new_token_data.get('expires_in')}"
                )
                logger.info(
                    f"[TOKEN DEBUG] New token expires_at: {new_token_data.get('expires_at')}"
                )

                # Update the token with new data
                updated_token = dict(token)
                updated_token.update(new_token_data)

                # Ensure expires_at is properly calculated if only expires_in is provided
                if (
                    "expires_in" in new_token_data
                    and "expires_at" not in new_token_data
                ):
                    import time

                    updated_token["expires_at"] = int(time.time()) + int(
                        new_token_data["expires_in"]
                    )
                    logger.info(
                        f"[TOKEN DEBUG] Calculated expires_at: {updated_token['expires_at']}"
                    )

                logger.info(
                    f"[TOKEN DEBUG] Final updated token expires_at: {updated_token.get('expires_at')}"
                )

                # Trigger update_token callback to store token and ensure Flask session is synchronized
                self.update_token(server_name, updated_token)

                return True
            else:
                logger.error(
                    f"[TOKEN DEBUG] Token refresh failed for {server_name}: HTTP {response.status_code}"
                )
                logger.error(f"[TOKEN DEBUG] Response: {response.text}")
                return False

        except Exception as e:
            logger.error(
                f"[TOKEN DEBUG] Exception during token refresh for {server_name}: {e}"
            )
            return False

    def _get_health_endpoint(self, server_name: str) -> Optional[str]:
        """Get a lightweight endpoint for token refresh testing"""
        try:
            client = self.get_client(server_name)
            if not client:
                return None

            # Get base URL from client metadata or configuration
            base_url = None
            if hasattr(client, "server_metadata") and client.server_metadata:
                # Try to get base URL from issuer or authorization endpoint
                issuer = client.server_metadata.get("issuer")
                if issuer:
                    base_url = issuer
                else:
                    auth_endpoint = client.server_metadata.get("authorization_endpoint")
                    if auth_endpoint:
                        from urllib.parse import urlparse

                        parsed = urlparse(auth_endpoint)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"

            if not base_url:
                # Fallback: try to derive from server config
                config = None
                if self.config_manager:
                    config = self.config_manager.get_server_config(server_name)
                    if config and config.url:
                        from urllib.parse import urlparse

                        parsed = urlparse(config.url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"

            if not base_url:
                logger.warning(
                    f"[TOKEN DEBUG] Could not determine base URL for {server_name}"
                )
                return None

            # Try common lightweight endpoints
            candidates = [
                f"{base_url}/health",
                f"{base_url}/api/health",
                f"{base_url}/status",
                f"{base_url}/info",
                f"{base_url}/user",
                f"{base_url}/.well-known/oauth-authorization-server",
            ]

            # Return first candidate (we'll test it when we use it)
            return candidates[0]

        except Exception as e:
            logger.warning(
                f"[TOKEN DEBUG] Error getting health endpoint for {server_name}: {e}"
            )
            return None

    def _get_authenticated_endpoint(self, server_name: str) -> Optional[str]:
        """Get an authenticated endpoint that will trigger 401 if token is expired"""
        try:
            client = self.get_client(server_name)
            if not client:
                return None

            # Get base URL from client metadata or configuration
            base_url = None
            if hasattr(client, "server_metadata") and client.server_metadata:
                # Try to get base URL from issuer or authorization endpoint
                issuer = client.server_metadata.get("issuer")
                if issuer:
                    base_url = issuer
                else:
                    auth_endpoint = client.server_metadata.get("authorization_endpoint")
                    if auth_endpoint:
                        from urllib.parse import urlparse

                        parsed = urlparse(auth_endpoint)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"

            if not base_url:
                # Fallback: try to derive from server config
                config = None
                if self.config_manager:
                    config = self.config_manager.get_server_config(server_name)
                    if config and config.url:
                        from urllib.parse import urlparse

                        parsed = urlparse(config.url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"

            if not base_url:
                logger.warning(
                    f"[TOKEN DEBUG] Could not determine base URL for {server_name}"
                )
                return None

            # Try authenticated endpoints that are likely to require auth and return 401 if token is expired
            candidates = [
                f"{base_url}/user",
                f"{base_url}/api/user",
                f"{base_url}/userinfo",
                f"{base_url}/api/userinfo",
                f"{base_url}/profile",
                f"{base_url}/api/profile",
                f"{base_url}/me",
                f"{base_url}/api/me",
            ]

            # Return first candidate (we'll test it when we use it)
            return candidates[0]

        except Exception as e:
            logger.warning(
                f"[TOKEN DEBUG] Error getting authenticated endpoint for {server_name}: {e}"
            )
            return None

    def _trigger_oauth_refresh(self, server_name: str) -> bool:
        """Use OAuth client to trigger automatic token refresh"""
        try:
            client = self.get_client(server_name)
            if not client:
                logger.debug(
                    f"[TOKEN DEBUG] No OAuth client available for {server_name}"
                )
                return False

            # Get current token and ensure client has access to it
            current_token = self.get_token(server_name)
            if not current_token:
                logger.debug(f"[TOKEN DEBUG] No token available for {server_name}")
                return False

            # Set the token on the client so Authlib can use it for refresh
            client.token = current_token

            # Get an authenticated endpoint that will trigger 401 if token is expired
            auth_endpoint = self._get_authenticated_endpoint(server_name)
            if not auth_endpoint:
                logger.debug(
                    f"[TOKEN DEBUG] No authenticated endpoint available for {server_name}"
                )
                return False

            logger.info(
                f"[TOKEN DEBUG] Triggering OAuth refresh for {server_name} via {auth_endpoint}"
            )

            # Store token before request to detect if refresh happened
            old_access_token = current_token.get("access_token")

            # This request will automatically refresh token if expired and server returns 401
            # Authlib will call our update_token callback if refresh happens
            response = client.get(auth_endpoint, timeout=10)

            # Check if token was actually refreshed by comparing access tokens
            new_token = self.get_token(server_name)
            new_access_token = new_token.get("access_token") if new_token else None

            token_refreshed = (
                old_access_token != new_access_token
            ) and new_access_token is not None

            if token_refreshed:
                logger.info(
                    f"[TOKEN DEBUG] OAuth client successfully refreshed token for {server_name}"
                )
                return True
            elif response.status_code < 400:
                logger.info(
                    f"[TOKEN DEBUG] OAuth request succeeded for {server_name} (HTTP {response.status_code}) - token still valid"
                )
                return True
            else:
                logger.warning(
                    f"[TOKEN DEBUG] OAuth client request failed for {server_name} (HTTP {response.status_code})"
                )
                return False

        except Exception as e:
            logger.info(
                f"[TOKEN DEBUG] OAuth client refresh trigger failed for {server_name}: {e}"
            )
            return False

    def _is_dynamic_client_registration(self, server_name: str) -> bool:
        """Check if this server uses dynamic client registration"""
        try:
            client = self.get_client(server_name)
            if not client:
                return False

            # Check if client has static credentials
            has_static_credentials = (
                hasattr(client, "client_id")
                and client.client_id
                and hasattr(client, "client_secret")
                and client.client_secret
            )

            if not has_static_credentials:
                logger.info(
                    f"[TOKEN DEBUG] {server_name} appears to use dynamic client registration (no static credentials)"
                )
                return True

            return False

        except Exception as e:
            logger.warning(
                f"[TOKEN DEBUG] Error checking client registration type for {server_name}: {e}"
            )
            return False

    def get_fresh_token(self, server_name: str) -> Optional[OAuth2Token]:
        """Get a guaranteed fresh token using OAuth client for refresh detection"""
        stored_token = self.get_token(server_name)

        # If no token exists, can't refresh
        if not stored_token:
            logger.info(f"[TOKEN DEBUG] No stored token found for {server_name}")
            return None

        # If token is still valid, return it
        if not stored_token.is_expired():
            logger.debug(f"[TOKEN DEBUG] Stored token for {server_name} is still valid")
            return stored_token

        logger.info(
            f"[TOKEN DEBUG] Token for {server_name} is expired, attempting refresh"
        )

        # Strategy 1: Use OAuth client auto-refresh (preferred)
        if self._trigger_oauth_refresh(server_name):
            refreshed_token = self.get_token(server_name)
            if refreshed_token and not refreshed_token.is_expired():
                logger.info(
                    f"[TOKEN DEBUG] Successfully refreshed token for {server_name} via OAuth client"
                )
                return refreshed_token
            else:
                logger.warning(
                    f"[TOKEN DEBUG] OAuth client refresh didn't produce valid token for {server_name}"
                )

        # Strategy 2: Manual refresh (fallback)
        logger.info(f"[TOKEN DEBUG] Falling back to manual refresh for {server_name}")
        if self._refresh_token_manually(server_name, stored_token):
            # Get the refreshed token from storage (update_token already called in _refresh_token_manually)
            refreshed_token = self.get_token(server_name)
            if refreshed_token:
                logger.info(
                    f"[TOKEN DEBUG] Successfully refreshed token for {server_name} via manual refresh"
                )
                return refreshed_token

        # Strategy 3: Return expired token (let caller handle auth failure)
        logger.warning(
            f"[TOKEN DEBUG] All refresh strategies failed for {server_name}, returning expired token"
        )
        return stored_token

    def get_fresh_auth_headers(self, server_name: str) -> Dict[str, str]:
        """Get authentication headers with guaranteed fresh token using hybrid approach"""
        token = self.get_fresh_token(server_name)
        if not token:
            # Check if this is a dynamic client registration server
            if self._is_dynamic_client_registration(server_name):
                logger.error(
                    f"[TOKEN DEBUG] {server_name} requires re-authentication (dynamic client registration)"
                )
                logger.error(
                    f"[TOKEN DEBUG] Please visit the OAuth flow to re-authenticate with {server_name}"
                )
            else:
                logger.warning(f"[TOKEN DEBUG] No token available for {server_name}")
            return {}

        return {"Authorization": f"Bearer {token['access_token']}"}


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
