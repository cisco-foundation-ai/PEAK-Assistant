#!/usr/bin/env python3
"""
OAuth authentication routes for PEAK Assistant
Handles user authentication flows for MCP servers requiring authorization code flow
"""

import os
import sys
import secrets
import hashlib
import base64
from urllib.parse import urlencode
import asyncio
import logging
from flask import Blueprint, request, redirect, url_for, session, jsonify, render_template, flash
from ..utils.decorators import async_action
from functools import wraps

# Add parent directory to path for importing utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from utils.mcp_config import get_config_manager, get_client_manager, AuthType

logger = logging.getLogger(__name__)

oauth_bp = Blueprint('oauth', __name__, url_prefix='/oauth')

def require_session(f):
    """Decorator to ensure user has a session and that it's saved."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            session['user_id'] = f"user_{secrets.token_hex(16)}"
            # Explicitly mark the session as modified to ensure it's saved.
            # This is crucial for the first request in a session.
            session.modified = True
            logger.info(f"Created new session with user_id: {session['user_id']}")
        return f(*args, **kwargs)
    return decorated_function

def generate_pkce_pair():
    """Generate PKCE code verifier and challenge"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge

@oauth_bp.route('/status')
@require_session
def oauth_status():
    """Get OAuth status for all MCP servers for current user"""
    try:
        user_id = session['user_id']
        config_manager = get_config_manager()
        client_manager = get_client_manager()
        
        servers_status = {}
        for server_name in config_manager.list_servers():
            config = config_manager.get_server_config(server_name)
            
            if config.auth:
                if config.auth.type == AuthType.OAUTH2_CLIENT_CREDENTIALS:
                    # System-level authentication
                    token_manager = config_manager.oauth_managers.get(server_name)
                    servers_status[server_name] = {
                        "auth_type": "system_oauth",
                        "status": "authenticated" if token_manager and token_manager.access_token else "needs_config",
                        "requires_user_auth": False,
                        "description": config.description
                    }
                elif config.auth.type == AuthType.OAUTH2_AUTHORIZATION_CODE:
                    # User-specific authentication
                    user_sessions = config_manager.user_session_manager.user_sessions.get(user_id, {})
                    token_manager = user_sessions.get(server_name)
                    
                    servers_status[server_name] = {
                        "auth_type": "user_oauth",
                        "status": "authenticated" if token_manager and token_manager.access_token else "needs_auth",
                        "requires_user_auth": True,
                        "description": config.description,
                        "token_expiry": token_manager.token_expiry if token_manager else None
                    }
                else:
                    servers_status[server_name] = {
                        "auth_type": config.auth.type.value,
                        "status": "configured",
                        "requires_user_auth": False,
                        "description": config.description
                    }
            else:
                servers_status[server_name] = {
                    "auth_type": "none",
                    "status": "available",
                    "requires_user_auth": False,
                    "description": config.description
                }
        
        return jsonify({
            "user_id": user_id,
            "servers": servers_status
        })
    except Exception as e:
        logger.error(f"Error getting OAuth status: {e}")
        return jsonify({"error": "Failed to get OAuth status"}), 500


@oauth_bp.route('/authenticate/<server_name>', methods=['GET'])
@require_session
@async_action  
async def initiate_oauth(server_name):
    """Initiate OAuth flow for a specific MCP server using standard OAuth 2.0 approach."""
    try:
        session_user_id = session['user_id']
        config_manager = get_config_manager()
        config = config_manager.get_server_config(server_name)

        if not config or not config.auth:
            flash(f'Authentication not configured for server: {server_name}', 'error')
            return redirect(url_for('pages.index'))
        
        # Debug: Log auth config values
        logger.info(f"[DEBUG] OAuth initiation for {server_name}:")
        logger.info(f"[DEBUG]   client_id: {config.auth.client_id}")
        logger.info(f"[DEBUG]   client_secret: {'***' if config.auth.client_secret else None}")
        logger.info(f"[DEBUG]   client_registration_url: {config.auth.client_registration_url}")
        logger.info(f"[DEBUG]   Dynamic registration condition: client_registration_url={bool(config.auth.client_registration_url)}, not client_id={not config.auth.client_id}")
        
        # Perform dynamic client registration if needed
        if config.auth.client_registration_url and not config.auth.client_id:
            logger.info(f"Client ID not found for {server_name}, attempting dynamic registration.")
            registered = await config_manager._register_dynamic_client(server_name)
            if not registered:
                flash(f'Failed to dynamically register client for {server_name}. Please check server logs.', 'error')
                return redirect(url_for('pages.index'))
            # Reload config to ensure we have the new client_id for the next steps
            config = config_manager.get_server_config(server_name)
        elif config.auth.client_registration_url and config.auth.client_id:
            # Check if redirect URI has changed and force re-registration if needed
            logger.info(f"Client ID exists for {server_name}, clearing credentials to force fresh registration with correct redirect URI.")
            config.auth.client_id = None
            config.auth.client_secret = None
            registered = await config_manager._register_dynamic_client(server_name)
            if not registered:
                flash(f'Failed to re-register client for {server_name}. Please check server logs.', 'error')
                return redirect(url_for('pages.index'))
            # Reload config to ensure we have the new client_id for the next steps
            config = config_manager.get_server_config(server_name)

        # PKCE for security
        code_verifier, code_challenge = generate_pkce_pair()

        # State for CSRF protection
        state = secrets.token_urlsafe(32)
        state_key = f'oauth_state_{state}'
        session[state_key] = {
            'server_name': server_name,
            'code_verifier': code_verifier
        }

        # Use session user ID for initial OAuth flow
        # Real user ID will be obtained from userinfo endpoint after authentication
        token_manager = config_manager.user_session_manager.get_or_create_token_manager(
            session_user_id, server_name, config.auth, config.url
        )
        
        auth_url = await token_manager.get_authorization_url(state, code_challenge)
        logger.info(f"Redirecting to OAuth authorization URL for server {server_name}")
        return redirect(auth_url)

    except Exception as e:
        logger.error(f"Error initiating OAuth for {server_name}: {e}", exc_info=True)
        flash(f'Failed to initiate authentication for {server_name}: {str(e)}', 'error')
        return redirect(url_for('pages.index'))

async def _exchange_token_async(token_manager, code, code_verifier):
    """Asynchronous helper to exchange the authorization code for a token."""
    await token_manager.exchange_authorization_code(code, code_verifier)



@oauth_bp.route('/callback')
@require_session
def oauth_callback():
    """Handle OAuth callback from authorization server."""
    try:
        user_id = session['user_id']
        state = request.args.get('state')
        code = request.args.get('code')
        error = request.args.get('error')

        if error:
            flash(f'OAuth authorization failed: {error}', 'error')
            return redirect(url_for('pages.index'))

        if not code or not state:
            flash('Invalid OAuth callback parameters', 'error')
            return redirect(url_for('pages.index'))

        state_key = f'oauth_state_{state}'
        if state_key not in session:
            logger.warning(f"OAuth state not found in session for user {user_id}. Possible CSRF or session issue.")
            flash('Invalid OAuth state - possible CSRF attack', 'error')
            return redirect(url_for('pages.index'))

        state_info = session.pop(state_key) # Pop the state to prevent reuse
        server_name = state_info['server_name']
        code_verifier = state_info.get('code_verifier')

        config_manager = get_config_manager()
        config = config_manager.get_server_config(server_name)

        if not config or not config.auth:
            flash('Server configuration not found', 'error')
            return redirect(url_for('pages.index'))

        # Start with session user ID for token exchange
        token_manager = config_manager.user_session_manager.get_or_create_token_manager(
            user_id, server_name, config.auth, config.url
        )

        # Run the async token exchange in a dedicated event loop
        try:
            asyncio.run(_exchange_token_async(token_manager, code, code_verifier))
            logger.info(f"OAuth token exchange successful for server {server_name}")
            
            # Get user ID from token response if available
            if token_manager.token_user_id:
                logger.info(f"Retrieved user ID from token response: {token_manager.token_user_id} for server {server_name}")
                
                # Create a new token manager with the token-discovered user ID
                real_token_manager = config_manager.user_session_manager.get_or_create_token_manager(
                    token_manager.token_user_id, server_name, config.auth, config.url
                )
                # Copy the tokens to the new token manager
                real_token_manager.access_token = token_manager.access_token
                real_token_manager.refresh_token = token_manager.refresh_token
                real_token_manager.token_expiry = token_manager.token_expiry
                real_token_manager.token_user_id = token_manager.token_user_id
                
                logger.info(f"OAuth authentication complete with token user ID: {token_manager.token_user_id}")
            else:
                logger.info(f"No user ID in token response for {server_name}, using session user ID as fallback")
            
            flash(f'Successfully authenticated with {server_name}', 'success')
        except Exception as e:
            logger.error(f"OAuth token exchange failed for server {server_name}: {e}", exc_info=True)
            flash(f'Authentication failed for {server_name}: {str(e)}', 'error')
            return redirect(url_for('pages.index'))
        
        return redirect(url_for('pages.index', auth_status='success'))

    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}", exc_info=True)
        flash(f'OAuth authentication failed: {str(e)}', 'error')
        return redirect(url_for('pages.index'))

@oauth_bp.route('/disconnect/<server_name>')
@require_session
def disconnect_oauth(server_name):
    """Disconnect user from a specific MCP server"""
    try:
        user_id = session['user_id']
        config_manager = get_config_manager()
        
        # Clear user token for this server
        user_sessions = config_manager.user_session_manager.user_sessions.get(user_id, {})
        if server_name in user_sessions:
            del user_sessions[server_name]
            flash(f'Disconnected from {server_name}', 'success')
        else:
            flash(f'Not connected to {server_name}', 'info')
        
        return redirect(url_for('pages.index'))
        
    except Exception as e:
        logger.error(f"Error disconnecting from {server_name}: {e}")
        flash(f'Failed to disconnect from {server_name}: {str(e)}', 'error')
        return redirect(url_for('pages.index'))

@oauth_bp.route('/logout')
@require_session
def logout_all():
    """Logout user from all MCP servers"""
    try:
        user_id = session['user_id']
        config_manager = get_config_manager()
        
        # Clear all user sessions
        config_manager.user_session_manager.clear_user_session(user_id)
        
        # Clear Flask session
        session.clear()
        
        flash('Logged out from all services', 'success')
        return redirect(url_for('pages.index'))
        
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        flash(f'Logout failed: {str(e)}', 'error')
        return redirect(url_for('pages.index'))

@oauth_bp.route('/servers/needing-auth')
@require_session
def servers_needing_auth():
    """Get list of servers that need user authentication"""
    logger.info(f"[Auth Status Check] Checking auth status for user_id: {session.get('user_id')}")
    try:
        user_id = session['user_id']
        config_manager = get_config_manager()
        
        needing_auth = config_manager.user_session_manager.get_user_servers_needing_auth(
            user_id, config_manager.servers
        )
        
        # Get detailed info about servers needing auth
        server_details = []
        for server_name in needing_auth:
            config = config_manager.get_server_config(server_name)
            server_details.append({
                "name": server_name,
                "description": config.description,
                "auth_url": url_for('oauth.initiate_oauth', server_name=server_name)
            })
        
        return jsonify({
            "servers_needing_auth": server_details,
            "count": len(server_details)
        })
        
    except Exception as e:
        logger.error(f"Error getting servers needing auth: {e}")
        return jsonify({"error": "Failed to get authentication status"}), 500


@oauth_bp.route('/servers/status')
@require_session
def servers_status():
    """Get comprehensive status of all MCP servers with authentication information"""
    logger.info(f"[Server Status Check] Getting status for all servers for user_id: {session.get('user_id')}")
    try:
        user_id = session['user_id']
        config_manager = get_config_manager()
        
        # Get all configured servers
        all_servers = []
        # Sort servers alphabetically by name
        for server_name, config in sorted(config_manager.servers.items(), key=lambda x: x[0].lower()):
            # Check if server requires authentication
            requires_auth = hasattr(config, 'auth') and config.auth is not None
            
            # Check current authentication status
            is_authenticated = False
            if requires_auth:
                is_authenticated = config_manager.user_session_manager.has_valid_tokens(
                    user_id, server_name
                )
            
            server_info = {
                "name": server_name,
                "description": config.description or "No description available",
                "requires_auth": requires_auth,
                "is_authenticated": is_authenticated,
                "auth_url": url_for('oauth.initiate_oauth', server_name=server_name) if requires_auth else None,
                "disconnect_url": url_for('oauth.disconnect_server', server_name=server_name) if requires_auth else None,
                "transport": getattr(config, 'transport', 'unknown').value if hasattr(getattr(config, 'transport', 'unknown'), 'value') else str(getattr(config, 'transport', 'unknown'))
            }
            all_servers.append(server_info)
        
        return jsonify({
            "servers": all_servers,
            "total_count": len(all_servers),
            "authenticated_count": sum(1 for s in all_servers if s['is_authenticated']),
            "needing_auth_count": sum(1 for s in all_servers if s['requires_auth'] and not s['is_authenticated'])
        })
        
    except Exception as e:
        logger.error(f"Error getting server status: {e}")
        return jsonify({"error": "Failed to get server status"}), 500


@oauth_bp.route('/disconnect/<server_name>', methods=['POST'])
@require_session
def disconnect_server(server_name):
    """Disconnect from an MCP server and remove stored authentication credentials"""
    logger.info(f"[Disconnect Server] Disconnecting server {server_name} for user_id: {session.get('user_id')}")
    try:
        user_id = session['user_id']
        config_manager = get_config_manager()
        
        # Check if server exists
        if server_name not in config_manager.servers:
            return jsonify({"error": f"Server '{server_name}' not found"}), 404
        
        # Remove stored tokens for this user and server
        config_manager.user_session_manager.clear_tokens(user_id, server_name)
        
        logger.info(f"Successfully disconnected server {server_name} for user {user_id}")
        return jsonify({
            "success": True,
            "message": f"Successfully disconnected from {server_name}",
            "server_name": server_name
        })
        
    except Exception as e:
        logger.error(f"Error disconnecting server {server_name}: {e}")
        return jsonify({"error": f"Failed to disconnect from {server_name}"}), 500


@oauth_bp.route('/test-connection/<server_name>')
@require_session
async def test_mcp_connection(server_name):
    """Test connection to an MCP server"""
    try:
        user_id = session['user_id']
        client_manager = get_client_manager()
        
        # Attempt to connect to the server
        connected = await client_manager.connect_server(server_name, user_id)
        
        if connected:
            return jsonify({
                "status": "success",
                "message": f"Successfully connected to {server_name}"
            })
        else:
            return jsonify({
                "status": "error", 
                "message": f"Failed to connect to {server_name}"
            }), 400
            
    except Exception as e:
        logger.error(f"Error testing connection to {server_name}: {e}")
        return jsonify({
            "status": "error",
            "message": f"Connection test failed: {str(e)}"
        }), 500
