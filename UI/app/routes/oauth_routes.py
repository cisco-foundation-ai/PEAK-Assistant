#!/usr/bin/env python3
"""
Authlib-based OAuth authentication routes for PEAK Assistant
Handles user authentication flows for MCP servers using Authlib
"""

import os
import sys
import secrets
import logging
import asyncio
from flask import Blueprint, request, redirect, url_for, session, jsonify, render_template, flash
from functools import wraps
from authlib.integrations.requests_client import OAuth2Session

# Add parent directory to path for importing utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from utils.mcp_config import get_config_manager, get_client_manager, AuthType
from utils.authlib_oauth import get_oauth_manager

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
def initiate_oauth(server_name):
    """Initiate OAuth flow for a specific MCP server using Authlib."""
    try:
        config_manager = get_config_manager()
        config = config_manager.get_server_config(server_name)

        if not config or not config.auth:
            flash(f'Authentication not configured for server: {server_name}', 'error')
            return redirect(url_for('pages.index'))

        # Perform dynamic client registration if needed
        if config.auth.client_registration_url and not config.auth.client_id:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:  # 'RuntimeError: There is no current event loop...'
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            registered = loop.run_until_complete(config_manager._register_dynamic_client(server_name))
            if not registered:
                flash(f'Failed to dynamically register client for {server_name}. Please check server logs.', 'error')
                return redirect(url_for('pages.index'))
            # Reload config to ensure we have the new client_id for the next steps
            config = config_manager.get_server_config(server_name)
            # Store dynamic credentials and token endpoint in session to survive the redirect
            session['dynamic_oauth_credentials'] = {
                'client_id': config.auth.client_id,
                'client_secret': config.auth.client_secret,
                'token_url': config.auth.token_url
            }

        oauth_manager = get_oauth_manager()
        # Store server name in session for callback
        session['oauth_server_name'] = server_name
        session.modified = True

        dynamic_creds = session.get('dynamic_oauth_credentials')
        if dynamic_creds:
            # For dynamic clients, create a temporary session to generate the auth URL
            with OAuth2Session(
                client_id=dynamic_creds['client_id'],
                client_secret=dynamic_creds['client_secret'],
                redirect_uri=url_for('oauth.oauth_callback', _external=True),
                scope=config.auth.scope
            ) as temp_client:
                authorization_url, state = temp_client.create_authorization_url(config.auth.authorization_url)
                session['oauth_state'] = state
                return redirect(authorization_url)
        else:
            # Standard flow for pre-configured clients
            client = oauth_manager.get_client(server_name)
            if not client:
                flash(f'OAuth not configured for server: {server_name}', 'error')
                return redirect(url_for('pages.index'))
            redirect_uri = url_for('oauth.oauth_callback', _external=True)
            return client.authorize_redirect(redirect_uri)
        
    except Exception as e:
        logger.error(f"Error initiating OAuth for {server_name}: {e}", exc_info=True)
        flash(f'Failed to initiate authentication for {server_name}: {str(e)}', 'error')
        return redirect(url_for('pages.index'))

@oauth_bp.route('/callback', methods=['GET'])
@require_session
def oauth_callback():
    """Handle OAuth callback from authorization server using Authlib."""
    try:
        user_id = session['user_id']
        server_name = session.get('oauth_server_name')
        error = request.args.get('error')

        if error:
            flash(f'OAuth authorization failed: {error}', 'error')
            return redirect(url_for('pages.index'))

        if not server_name:
            flash('OAuth session expired or invalid', 'error')
            return redirect(url_for('pages.index'))

        oauth_manager = get_oauth_manager()
        client = oauth_manager.get_client(server_name)
        if not client:
            flash(f'OAuth client not found for server: {server_name}', 'error')
            return redirect(url_for('pages.index'))

        try:
            client = oauth_manager.get_client(server_name)
            if not client:
                flash(f'OAuth client not found for server: {server_name}', 'error')
                return redirect(url_for('pages.index'))

            dynamic_creds = session.pop('dynamic_oauth_credentials', None)
            if dynamic_creds:
                # For dynamic clients, create a temporary session to fetch the token
                with OAuth2Session(
                    client_id=dynamic_creds['client_id'],
                    client_secret=dynamic_creds['client_secret'],
                    redirect_uri=url_for('oauth.oauth_callback', _external=True),
                    scope=client.client_kwargs.get('scope')
                ) as temp_client:
                    token = temp_client.fetch_token(
                        url=dynamic_creds['token_url'],
                        authorization_response=request.url
                    )
                
                # Store dynamic client credentials in the token for refresh operations
                token['_dynamic_client_id'] = dynamic_creds['client_id']
                token['_dynamic_client_secret'] = dynamic_creds['client_secret']
                token['_dynamic_token_url'] = dynamic_creds['token_url']
                logger.info(f"[TOKEN DEBUG] Stored dynamic client credentials for {server_name}")
            else:
                # Standard flow for pre-configured clients
                token = client.authorize_access_token()
            
            # Store the token for the user
            oauth_manager.store_token(server_name, token)
            
            # Clean up session
            session.pop('oauth_server_name', None)
            session.modified = True
            
            logger.info(f"OAuth authentication successful for user {user_id}, server {server_name}")
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

@oauth_bp.route('/disconnect/<server_name>', methods=['POST'])
@require_session
def disconnect_oauth(server_name):
    """Disconnect user from a specific MCP server"""
    try:
        user_id = session['user_id']
        oauth_manager = get_oauth_manager()
        
        # Clear OAuth token for this server
        oauth_manager.clear_tokens(server_name)
        flash(f'Disconnected from {server_name}', 'success')
        return jsonify({'success': True})
        
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
        oauth_manager = get_oauth_manager()
        
        # Clear all OAuth tokens for this user
        oauth_manager.clear_user_tokens(user_id)
        
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
        oauth_manager = get_oauth_manager()
        
        needing_auth = oauth_manager.get_servers_needing_auth(user_id)
        
        # Get detailed info about servers needing auth
        server_details = []
        for server_name in needing_auth:
            config = config_manager.get_server_config(server_name)
            server_details.append({
                "name": server_name,
                "description": config.description if config else server_name,
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
        oauth_manager = get_oauth_manager()
        
        # Get all configured servers
        all_servers = []
        # Sort servers alphabetically by name
        for server_name, config in sorted(config_manager.servers.items(), key=lambda x: x[0].lower()):
            # Check if server requires authentication
            requires_auth = hasattr(config, 'auth') and config.auth is not None
            
            # Check current authentication status using authlib manager
            is_authenticated = False
            if requires_auth:
                # Proactively refresh expired tokens for accurate status display
                fresh_headers = oauth_manager.get_fresh_auth_headers(server_name)
                is_authenticated = bool(fresh_headers.get('Authorization'))
                
                # Log status check result
                if is_authenticated:
                    logger.info(f"[Server Status] {server_name}: Authenticated (token fresh)")
                else:
                    logger.info(f"[Server Status] {server_name}: Not authenticated (no valid token)")
            
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
        oauth_manager = get_oauth_manager()
        
        # Check if server exists
        if server_name not in config_manager.servers:
            return jsonify({"error": f"Server '{server_name}' not found"}), 404
        
        # Remove stored OAuth tokens for this user and server
        oauth_manager.clear_token(server_name, user_id)
        
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
