#!/usr/bin/env python3
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

"""
MCP Status Command - Display configuration status of all MCP servers
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from ..utils.mcp_config import MCPConfigManager, AuthType


def check_auth_status(server_config) -> Tuple[str, List[str], List[str]]:
    """
    Check authentication status for a server.
    
    Returns:
        Tuple of (status, configured_vars, missing_vars)
        status: "ready", "partial", or "missing"
    """
    if not server_config.auth or server_config.auth.type == AuthType.NONE:
        return ("ready", [], [])
    
    if server_config.auth.type == AuthType.BEARER:
        if server_config.auth.token:
            return ("ready", [], [])
        else:
            return ("missing", [], ["Bearer token not configured in config file"])
    
    if server_config.auth.type == AuthType.API_KEY:
        if server_config.auth.api_key:
            return ("ready", [], [])
        else:
            return ("missing", [], ["API key not configured in config file"])
    
    # OAuth2 - check environment variables
    if server_config.auth.type in [AuthType.OAUTH2_CLIENT_CREDENTIALS, AuthType.OAUTH2_AUTHORIZATION_CODE]:
        env_var_name = f"PEAK_MCP_{server_config.name.upper().replace('-', '_')}_TOKEN"
        user_id_var = f"PEAK_MCP_{server_config.name.upper().replace('-', '_')}_USER_ID"
        
        configured = []
        missing = []
        
        # Check token
        if os.getenv(env_var_name):
            configured.append(env_var_name)
        else:
            missing.append(env_var_name)
        
        # Check user ID if required
        if server_config.auth.requires_user_auth:
            if os.getenv(user_id_var):
                configured.append(user_id_var)
            else:
                missing.append(user_id_var)
        
        if not missing:
            return ("ready", configured, [])
        elif configured:
            return ("partial", configured, missing)
        else:
            return ("missing", [], missing)
    
    return ("ready", [], [])


def print_server_status(server_name: str, server_config, verbose: bool = False):
    """Print status information for a single server"""
    status, configured_vars, missing_vars = check_auth_status(server_config)
    
    # Status symbol
    if status == "ready":
        symbol = "✓"
    elif status == "partial":
        symbol = "⚠"
    else:
        symbol = "✗"
    
    print(f"{symbol} {server_name}")
    print(f"  Transport: {server_config.transport.value}")
    
    # Auth type
    if server_config.auth:
        auth_desc = server_config.auth.type.value
        if server_config.auth.requires_user_auth:
            auth_desc += " (requires user authentication)"
        print(f"  Auth: {auth_desc}")
    else:
        print(f"  Auth: none")
    
    # Verbose details
    if verbose:
        if server_config.transport.value == "stdio":
            print(f"  Command: {server_config.command}")
            if server_config.args:
                print(f"  Args: {' '.join(server_config.args)}")
            else:
                print(f"  Args: None")
        elif server_config.transport.value in ["http", "sse"]:
            print(f"  URL: {server_config.url}")
            if server_config.auth and hasattr(server_config.auth, 'discovery_url') and server_config.auth.discovery_url:
                print(f"  Discovery URL: {server_config.auth.discovery_url}")
            if server_config.auth and hasattr(server_config.auth, 'client_registration_url') and server_config.auth.client_registration_url:
                print(f"  Client Registration: {server_config.auth.client_registration_url}")
        
        if server_config.description:
            print(f"  Description: {server_config.description}")
    
    # Status message
    if status == "ready":
        if server_config.auth and server_config.auth.type == AuthType.BEARER:
            print(f"  Status: Ready (token configured)")
        elif server_config.auth and server_config.auth.type == AuthType.API_KEY:
            print(f"  Status: Ready (API key configured)")
        elif configured_vars:
            print(f"  Status: Ready (credentials configured)")
        else:
            print(f"  Status: Ready")
    elif status == "partial":
        print(f"  Status: Partially configured")
    else:
        print(f"  Status: Missing credentials")
    
    # Show configured variables
    if configured_vars:
        print(f"  ")
        print(f"  Configured environment variable(s):")
        for var in configured_vars:
            print(f"    ✓ {var}")
    
    # Show missing variables with export commands
    if missing_vars:
        print(f"  ")
        print(f"  Missing environment variable(s):")
        for var in missing_vars:
            if var.startswith("PEAK_MCP_"):
                print(f"    ✗ {var}")
            else:
                print(f"    ✗ {var}")
        
        print(f"  ")
        print(f"  To enable, set:")
        for var in missing_vars:
            if var.startswith("PEAK_MCP_"):
                if "USER_ID" in var:
                    print(f"    export {var}=\"your_user_id\"")
                else:
                    print(f"    export {var}=\"your_token_here\"")
        
        if verbose:
            print(f"  ")
            print(f"  Alternatively, authenticate via Streamlit web interface at:")
            print(f"    http://localhost:8501")


def main():
    parser = argparse.ArgumentParser(
        description="Display configuration status of all MCP servers"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed configuration information"
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to MCP configuration file (default: auto-detect)"
    )
    
    args = parser.parse_args()
    
    # Print header
    print()
    print("PEAK Assistant - MCP Server Status")
    print("═" * 79)
    print()
    
    # Load configuration
    try:
        if args.config:
            config_manager = MCPConfigManager(args.config)
            config_file = args.config
        else:
            config_manager = MCPConfigManager()
            config_file = config_manager.config_file
    except FileNotFoundError as e:
        print("✗ Error: No MCP configuration file found")
        print()
        print("  Searched locations:")
        print("    • ./mcp_servers.json")
        print("    • ./peak_assistant/streamlit/mcp_servers.json")
        print("    • ~/.config/peak-assistant/mcp_servers.json")
        print()
        print("  Create an mcp_servers.json file to configure MCP servers.")
        print("  See documentation for configuration format.")
        print()
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error loading configuration: {e}")
        print()
        sys.exit(1)
    
    # Get all servers organized by group
    all_groups = config_manager.get_all_groups()
    
    if not all_groups:
        print("✗ No MCP servers configured")
        print()
        print(f"  Configuration file: {config_file}")
        print("  Add server configurations to enable MCP functionality.")
        print()
        sys.exit(0)
    
    # Track statistics
    ready_count = 0
    partial_count = 0
    missing_count = 0
    
    # Display servers by group
    for group_name in sorted(all_groups.keys()):
        server_names = all_groups[group_name]
        
        print(f"Server Group: {group_name}")
        print("─" * 79)
        
        for server_name in server_names:
            server_config = config_manager.get_server_config(server_name)
            if server_config:
                status, _, _ = check_auth_status(server_config)
                
                if status == "ready":
                    ready_count += 1
                elif status == "partial":
                    partial_count += 1
                else:
                    missing_count += 1
                
                print_server_status(server_name, server_config, args.verbose)
                print()
        
        print()
    
    # Print summary
    print("═" * 79)
    print("Summary:")
    if ready_count > 0:
        print(f"  {ready_count} server{'s' if ready_count != 1 else ''} ready")
    if partial_count > 0:
        print(f"  {partial_count} server{'s' if partial_count != 1 else ''} partially configured")
    if missing_count > 0:
        print(f"  {missing_count} server{'s' if missing_count != 1 else ''} missing credentials")
    
    print()
    
    if missing_count == 0 and partial_count == 0:
        print("  All MCP servers are properly configured! ✓")
        print()
    
    if args.verbose:
        print(f"Configuration file: {config_file}")
        print()
    
    # Exit with appropriate code
    if missing_count > 0 or partial_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
