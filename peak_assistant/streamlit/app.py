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

import os
import time
import logging
from dotenv import load_dotenv

import streamlit as st 
from streamlit_extras.stylable_container import stylable_container

from peak_assistant.utils import find_dotenv_file
from peak_assistant.streamlit.util.ui import peak_assistant_chat, peak_assistant_hypothesis_list
from peak_assistant.streamlit.util.runners import run_researcher, run_hypothesis_generator, run_hypothesis_refiner, run_able_table, run_data_discovery, run_hunt_plan
from peak_assistant.streamlit.util.hypothesis_helpers import get_current_hypothesis
from peak_assistant.streamlit.util.helpers import (
    reset_session, 
    switch_tabs, 
    load_mcp_server_configs, 
    get_user_session_id, 
    get_mcp_auth_status, 
    test_mcp_connection, 
    initiate_oauth_flow,
    restore_session_from_oauth,
    exchange_oauth_code_for_token,
    get_asset_path,
    get_agent_config_data
)
#############################
## LOGGING SETUP
#############################

# Use Streamlit's built-in logging configuration
# Control via: streamlit run app.py --logger.level debug
logger = logging.getLogger(__name__)

#############################
## MAIN
#############################

# Load our environment variables
dotenv_path = find_dotenv_file()
if dotenv_path:
    load_dotenv(dotenv_path)
    logger.info(f"Loaded environment variables from {dotenv_path}")
else:
    logger.error("No .env file found in current or parent directories")
    raise FileNotFoundError("No .env file found in current or parent directories")

# Handle OAuth callback with session recovery
query_params = st.query_params
if "code" in query_params and "state" in query_params:
    # This is an OAuth callback
    auth_code = query_params["code"]
    state = query_params["state"]
    
    # Try to restore session state using the OAuth state parameter
    session_restored = restore_session_from_oauth(state)
    if session_restored:
        logger.debug("Session state restored from OAuth redirect")
    
    # Find which server this callback is for
    server_name = None
    
    # First try the direct state-to-server mapping (if session was restored)
    state_key = f"oauth_server_for_state_{state}"
    if state_key in st.session_state:
        server_name = st.session_state[state_key]
    else:
        # Fallback: scan for OAuth state
        for key in st.session_state.keys():
            if key.startswith("oauth_state_") and st.session_state[key] == state:
                server_name = key.replace("oauth_state_", "")
                break
    
    if server_name:
        # Try to exchange authorization code for access token
        logger.debug(f"Exchanging authorization code for access token for {server_name}")
        token_exchange_success = exchange_oauth_code_for_token(server_name, auth_code)
        
        if not token_exchange_success:
            # Fallback: store authorization code if token exchange fails
            logger.warning("Token exchange failed, storing authorization code as fallback")
            auth_key = f"MCP.{server_name}"
            user_session_id = get_user_session_id()
            st.session_state[auth_key] = {
                "authorization_code": auth_code,
                "auth_type": "oauth2_authorization_code",
                "authenticated_at": time.time(),
                "user_id": user_session_id,
                "server_name": server_name
            }
        
        # Clean up OAuth state
        if f"oauth_state_{server_name}" in st.session_state:
            del st.session_state[f"oauth_state_{server_name}"]
        if f"oauth_server_for_state_{state}" in st.session_state:
            del st.session_state[f"oauth_server_for_state_{state}"]
        
        # Log authentication details
        logger.info(f"OAuth authentication successful for {server_name}")
        logger.debug(f"Session restored: {session_restored}")
        logger.debug(f"Token exchange successful: {token_exchange_success}")
        
        # Log current auth data
        auth_key = f"MCP.{server_name}"
        if auth_key in st.session_state:
            auth_data = st.session_state[auth_key]
            logger.debug(f"Stored auth data keys: {list(auth_data.keys())}")
            logger.debug(f"User ID: {auth_data.get('user_id', 'Not set')}")
            logger.debug(f"Auth type: {auth_data.get('auth_type', 'Not set')}")
            if auth_data.get("access_token"):
                logger.debug(f"Access token present: {auth_data['access_token'][:20]}...")
            else:
                logger.debug("No access token - only authorization code stored")
            
            # Log OAuth client info if available
            client_key = f"oauth_client_{server_name}"
            if client_key in st.session_state:
                client_info = st.session_state[client_key]
                logger.debug(f"OAuth client info available: {list(client_info.keys())}")
            else:
                logger.debug("No OAuth client info found for token exchange")
        else:
            logger.warning("No auth data found in session state")
        
        # Clear query parameters and redirect to status tab
        st.query_params.clear()
        switch_tabs(6)  # Status tab is index 6
        st.rerun()
    else:
        st.error("OAuth callback failed: Could not identify server from state parameter")
        import logging
        logger = logging.getLogger(__name__)
        logger.error("OAuth callback failed: Could not identify server from state parameter")
        logger.debug(f"Session restored: {session_restored}")
        logger.debug(f"Received state: {state}")
        logger.debug(f"Available OAuth states: {[k for k in st.session_state.keys() if k.startswith('oauth_state_')]}")

# Reset the app if requested. _reset_requested flag is set in utils.helpers.reset_session()
if st.session_state.get("_reset_requested", False):
    del st.session_state["_reset_requested"]
    switch_tabs(0)

# Read the local context file if it's not already in the session state.
if "local_context" not in st.session_state:
    # Find and load our local context file (used for the agents)
    with open("context.txt", "r", encoding="utf-8") as file:
        local_context = file.read()

    st.session_state["local_context"] = local_context

# Use the full page instead of a narrow central column
st.set_page_config(layout="wide")
st.set_page_config(page_title="PEAK Assistant")


# Reduce the margin above the tabs
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
        }
    </style>
    """, unsafe_allow_html=True)


with st.sidebar:

    st.image(get_asset_path("images/peak-logo-dark.png"), width="stretch")

    with stylable_container(
        key="reset_button_container",
        css_styles="""
        button {
            background-color: #990F02;
            }
            """
    ):
        reset_button = st.button(
            "Reset Session",
            icon=":material/warning:",
            on_click=reset_session
        )


research_tab, \
hypothesis_generation_tab, \
hypothesis_refinement_tab, \
able_tab, \
data_discovery_tab, \
hunt_plan_tab, \
status_tab, \
agent_config_tab, \
debug_tab = st.tabs(
    [
        "Research", 
        "Hypothesis Generation",
        "Hypothesis Refinement",
        "ABLE Table",
        "Data Discovery",
        "Hunt Plan",
        "Status",
        "Agent Config",
        "Debug"
    ]
)



with research_tab:
    peak_assistant_chat(
        title="Topic Research", 
        page_description="The topic research assistant will search internal and Internet sources and compile a research report for your hunt topic.",
        doc_title="Research",
        default_prompt="What would you like to hunt for?", 
        allow_upload=True,
        agent_runner=run_researcher
    )

# TODO: Implement something here.
with hypothesis_generation_tab:
    if ("Research_document" not in st.session_state) or not st.session_state["Research_document"]:
        st.warning("Please run the Research tab first.")
    else:
        peak_assistant_hypothesis_list(
            agent_runner = run_hypothesis_generator
        )

with hypothesis_refinement_tab:
    current_hypothesis = get_current_hypothesis()
    if not current_hypothesis:
        st.warning("Please run the Hypothesis Generation tab first.")
    else:
        # Reset refinement if original hypothesis has changed
        if "last_hypothesis_for_refinement" not in st.session_state:
            st.session_state["last_hypothesis_for_refinement"] = st.session_state.get("Hypothesis")
        elif st.session_state.get("last_hypothesis_for_refinement") != st.session_state.get("Hypothesis"):
            # Original hypothesis changed, reset the refinement
            st.session_state["Refinement_document"] = ""  # Clear document to show button
            st.session_state["last_hypothesis_for_refinement"] = st.session_state.get("Hypothesis")
            # Clear any previous refinement messages to start fresh
            if "Refinement_messages" in st.session_state:
                del st.session_state["Refinement_messages"]
        peak_assistant_chat(
            title="Hypothesis Refinement",
            page_description="The hypothesis refinement assistant will help you ensure your hypothesis is both specific and testable.",
            doc_title="Refinement",
            default_prompt=f"Your original hypothesis was: :green[{current_hypothesis}]", 
            allow_upload=False,
            agent_runner=run_hypothesis_refiner,
            run_button_label="Refine Hypothesis"
        )

with able_tab:
    current_hypothesis = get_current_hypothesis()
    if not current_hypothesis:
        st.warning("Please run the Hypothesis Generation or Hypothesis Refinement tab first.")
    else:
        # Reset if effective hypothesis has changed
        if "last_hypothesis_for_able" not in st.session_state:
            st.session_state["last_hypothesis_for_able"] = current_hypothesis
        elif st.session_state.get("last_hypothesis_for_able") != current_hypothesis:
            # Effective hypothesis changed, reset the ABLE table
            st.session_state["ABLE_document"] = ""  # Clear document to show button
            st.session_state["last_hypothesis_for_able"] = current_hypothesis
            # Clear any previous ABLE messages to start fresh
            if "ABLE_messages" in st.session_state:
                del st.session_state["ABLE_messages"]
        peak_assistant_chat(
            title="ABLE Table",
            page_description="The ABLE table assistant will help you create an Actor/Behavior/Location/Evidence (ABLE table to scope your hunt.",
            doc_title="ABLE",
            default_prompt=f"The hunting hypothesis is :green[{get_current_hypothesis()}]",
            allow_upload=False,
            agent_runner=run_able_table,
            run_button_label="Create ABLE Table"
        )

with data_discovery_tab:
    current_hypothesis = get_current_hypothesis()
    
    if "ABLE_document" not in st.session_state or not st.session_state["ABLE_document"]:
        st.warning("Please generate an ABLE table first.")
    else:
        # Track hypothesis changes for this tab
        if "last_hypothesis_for_data_discovery" not in st.session_state:
            st.session_state["last_hypothesis_for_data_discovery"] = None
        
        # Reset if hypothesis changed
        if st.session_state["last_hypothesis_for_data_discovery"] != current_hypothesis:
            st.session_state["last_hypothesis_for_data_discovery"] = current_hypothesis
            # Clear the data sources document to show run button
            if "Data Sources_document" in st.session_state:
                del st.session_state["Data Sources_document"]
            if "Data Sources_messages" in st.session_state:
                del st.session_state["Data Sources_messages"]
        
        peak_assistant_chat(
            title="Data Discovery",
            page_description="The data discovery assistant will help you identify potential data sources for your hunt topic.",
            doc_title="Discovery",
            default_prompt=f"Identify data sources for: :green[{current_hypothesis}]",
            allow_upload=True,
            agent_runner=run_data_discovery,
            run_button_label="Identify Data Sources"
        )   

with hunt_plan_tab:
    current_hypothesis = get_current_hypothesis()
    
    if "ABLE_document" not in st.session_state or not st.session_state["ABLE_document"]:
        st.warning("Please generate an ABLE table first.")
    elif "Discovery_document" not in st.session_state or not st.session_state["Discovery_document"]:
        st.warning("Please run data discovery first.")
    else:
        # Track hypothesis changes for this tab
        if "last_hypothesis_for_hunt_plan" not in st.session_state:
            st.session_state["last_hypothesis_for_hunt_plan"] = None
        
        # Reset if hypothesis changed
        if st.session_state["last_hypothesis_for_hunt_plan"] != current_hypothesis:
            st.session_state["last_hypothesis_for_hunt_plan"] = current_hypothesis
            # Clear the hunt plan document to show run button
            if "Hunt Plan_document" in st.session_state:
                del st.session_state["Hunt Plan_document"]
            if "Hunt Plan_messages" in st.session_state:
                del st.session_state["Hunt Plan_messages"]
        
        peak_assistant_chat(
            title="Hunt Plan",
            page_description="The hunt plan assistant will help you create a comprehensive hunt plan for your hunt topic.",
            doc_title="Hunt Plan",
            default_prompt=f"Create hunt plan for: :green[{current_hypothesis}]",
            allow_upload=True,
            agent_runner=run_hunt_plan,
            run_button_label="Create Hunt Plan"
        )

with status_tab:
    st.header("MCP Server Status")
    st.write("Monitor the status and authentication state of configured MCP servers.")
    
    # Load MCP server configurations
    server_configs = load_mcp_server_configs()
    
    if not server_configs:
        st.warning("No MCP servers configured. Please add server configurations to `mcp_servers.json`.")
        st.info("Expected location: `mcp_servers.json` in the Streamlit app directory.")
    else:
        # Display server status table
        st.subheader(f"Configured Servers ({len(server_configs)})")
        
        # Create columns for the table header (added Actions column)
        col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 3])
        with col1:
            st.write("**Server Name**")
        with col2:
            st.write("**Transport**")
        with col3:
            st.write("**Description**")
        with col4:
            st.write("**Status**")
        with col5:
            st.write("**Actions**")
        
        st.divider()
        
        # Display each server
        for server_name, config in server_configs.items():
            # Debug: Check if config is the right type
            if not hasattr(config, 'transport'):
                st.error(f"Invalid configuration for {server_name}: {type(config)} - {config}")
                continue
            
            # Clear any potentially conflicting keys from session state
            keys_to_remove = []
            for key in st.session_state.keys():
                if (
                    key.startswith(f"auth_button_{server_name}")
                    or key.startswith(f"status_btn_{server_name}")
                    or key.startswith(f"btn_{server_name}")
                    or key.startswith(f"test_conn_{server_name}")  # clear restored test button keys
                ):
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del st.session_state[key]
                
            # Include Actions column on the same row
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 3])
            
            with col1:
                st.write(f"**{server_name}**")
            
            with col2:
                st.write(config.transport.value.upper())
            
            with col3:
                st.write(config.description or "No description")
            
            with col4:
                # Get authentication status
                status_color, status_message = get_mcp_auth_status(server_name, config)
                
                # Log status for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Status for {server_name}: {status_color} - {status_message}")
                
                # Create status button with appropriate color
                if status_color == "green":
                    button_type = "primary"
                    button_disabled = True
                    button_label = "✅ Connected"
                elif status_color == "yellow":
                    button_type = "secondary"
                    button_disabled = False
                    button_label = "🔐 Authenticate"
                else:  # red
                    button_type = "secondary"
                    button_disabled = False
                    button_label = "❌ Error"
                
                # Create the status button (no key to avoid conflicts)
                if st.button(
                    f"{button_label} ({server_name})",  # Make label unique since no key
                    disabled=button_disabled,
                    type=button_type,
                    help=status_message
                ):
                    # Handle authentication button click
                    import logging
                    logger = logging.getLogger(__name__)
                    
                    logger.debug(f"Button clicked for {server_name}")
                    logger.debug(f"Explicit OAuth config: {config.auth and config.auth.type.value == 'oauth2_authorization_code'}")
                    logger.debug(f"OAuth discovered: {status_message == 'OAuth2 authentication detected'}")
                    logger.debug(f"Status message: '{status_message}'")
                    
                    if (config.auth and config.auth.type.value == "oauth2_authorization_code") or \
                       (status_message == "OAuth2 authentication detected"):
                        # OAuth2 flow (either explicit config or discovered)
                        logger.info(f"Initiating OAuth flow for {server_name}")
                        auth_url = initiate_oauth_flow(server_name, config)
                        if auth_url:
                            logger.debug(f"Redirecting to authenticate with {server_name}")
                            logger.debug(f"Generated auth URL: {auth_url[:100]}...")
                            
                            # Log dynamic registration info if available
                            if f"oauth_client_{server_name}" in st.session_state:
                                client_info = st.session_state[f"oauth_client_{server_name}"]
                                logger.debug(f"Using dynamically registered client: {client_info['client_id']}")
                            
                            # Use meta refresh to redirect in the same tab
                            st.markdown(f"""
                            <meta http-equiv="refresh" content="0; url={auth_url}">
                            <p>If you are not redirected automatically, <a href="{auth_url}" target="_self">click here</a>.</p>
                            """, unsafe_allow_html=True)
                            
                            # Also try JavaScript as backup
                            st.markdown(f"""
                            <script>
                                setTimeout(function() {{
                                    window.location.href = "{auth_url}";
                                }}, 1000);
                            </script>
                            """, unsafe_allow_html=True)
                        else:
                            st.error(f"Failed to initiate OAuth2 flow for {server_name}")
                    
                    elif config.auth and config.auth.type.value == "api_key":
                        # API Key input
                        st.session_state[f"show_api_key_input_{server_name}"] = True
                        st.rerun()
                    
                    elif config.auth and config.auth.type.value == "bearer":
                        # Bearer token input
                        st.session_state[f"show_bearer_input_{server_name}"] = True
                        st.rerun()
                    
                    else:
                        # Test connection for other types
                        with st.spinner(f"Testing connection to {server_name}..."):
                            import asyncio
                            try:
                                success, message = asyncio.run(test_mcp_connection(server_name, config))
                                if success:
                                    st.success(f"{server_name}: {message}")
                                else:
                                    st.error(f"{server_name}: {message}")
                            except Exception as e:
                                st.error(f"{server_name}: Connection test failed - {str(e)}")
                
            with col5:
                # Dedicated Test Connection button (always available) on same row
                # Avoid an explicit key to prevent conflicts with restored session state
                if st.button(f"🧪 Test Connection ({server_name})", type="secondary"):
                    with st.spinner(f"Testing connection to {server_name}..."):
                        import asyncio
                        try:
                            success, message = asyncio.run(test_mcp_connection(server_name, config))
                            if success:
                                st.success(f"{server_name}: {message}")
                            else:
                                st.error(f"{server_name}: {message}")
                        except Exception as e:
                            st.error(f"{server_name}: Connection test failed - {str(e)}")
            
            # Show API key input if requested
            if st.session_state.get(f"show_api_key_input_{server_name}", False):
                with st.expander(f"Enter API Key for {server_name}", expanded=True):
                    api_key = st.text_input(
                        "API Key",
                        type="password",
                        key=f"api_key_input_{server_name}",
                        help="Enter your API key for this server"
                    )
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("Save", key=f"save_api_key_{server_name}"):
                            if api_key:
                                # Store API key in session state
                                auth_key = f"MCP.{server_name}"
                                st.session_state[auth_key] = {
                                    "api_key": api_key,
                                    "auth_type": "api_key"
                                }
                                st.success(f"API key saved for {server_name}")
                                st.session_state[f"show_api_key_input_{server_name}"] = False
                                st.rerun()
                            else:
                                st.error("Please enter an API key")
                    with col_cancel:
                        if st.button("Cancel", key=f"cancel_api_key_{server_name}"):
                            st.session_state[f"show_api_key_input_{server_name}"] = False
                            st.rerun()
            
            # Show bearer token input if requested
            if st.session_state.get(f"show_bearer_input_{server_name}", False):
                with st.expander(f"Enter Bearer Token for {server_name}", expanded=True):
                    bearer_token = st.text_input(
                        "Bearer Token",
                        type="password",
                        key=f"bearer_input_{server_name}",
                        help="Enter your bearer token for this server"
                    )
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("Save", key=f"save_bearer_{server_name}"):
                            if bearer_token:
                                # Store bearer token in session state
                                auth_key = f"MCP.{server_name}"
                                st.session_state[auth_key] = {
                                    "access_token": bearer_token,
                                    "auth_type": "bearer"
                                }
                                st.success(f"Bearer token saved for {server_name}")
                                st.session_state[f"show_bearer_input_{server_name}"] = False
                                st.rerun()
                            else:
                                st.error("Please enter a bearer token")
                    with col_cancel:
                        if st.button("Cancel", key=f"cancel_bearer_{server_name}"):
                            st.session_state[f"show_bearer_input_{server_name}"] = False
                            st.rerun()
            
            st.divider()
        
        # Add refresh button
        if st.button("🔄 Refresh Status", type="secondary"):
            # Clear cached configurations to force reload
            if "mcp_server_configs" in st.session_state:
                del st.session_state["mcp_server_configs"]
            
            # Clear OAuth2 discovery cache
            discovery_keys = [key for key in st.session_state.keys() if key.startswith("oauth_discovery_")]
            for key in discovery_keys:
                del st.session_state[key]
            
            st.rerun()
        
        # Show session info
        with st.expander("Session Information"):
            user_session_id = get_user_session_id()
            st.write(f"**Session ID:** `{user_session_id}`")
            
            # Show stored authentication data
            auth_keys = [key for key in st.session_state.keys() if key.startswith("MCP.")]
            if auth_keys:
                st.write("**Stored Authentication:**")
                for auth_key in auth_keys:
                    server_name = auth_key.replace("MCP.", "")
                    auth_data = st.session_state[auth_key]
                    auth_type = auth_data.get("auth_type", "unknown")
                    st.write(f"- {server_name}: {auth_type}")
            else:
                st.write("No authentication data stored in session.")
            
            # Show OAuth2 discovery results
            discovery_keys = [key for key in st.session_state.keys() if key.startswith("oauth_discovery_")]
            if discovery_keys:
                st.write("**OAuth2 Discovery Results:**")
                for discovery_key in discovery_keys:
                    server_name = discovery_key.replace("oauth_discovery_", "")
                    discovery_data = st.session_state[discovery_key]
                    supports_oauth2 = discovery_data.get("supports_oauth2", False)
                    checked_at = discovery_data.get("checked_at", 0)
                    status = "✅ OAuth2 Detected" if supports_oauth2 else "❌ No OAuth2"
                    import datetime
                    check_time = datetime.datetime.fromtimestamp(checked_at).strftime("%H:%M:%S")
                    st.write(f"- {server_name}: {status} (checked at {check_time})")
            else:
                st.write("No OAuth2 discovery performed yet.")

with agent_config_tab:
    st.header("Agent Model Configuration")
    st.write("View the model and provider configuration for all agents in the system.")
    
    # Get agent configuration data
    agent_data = get_agent_config_data()
    
    if not agent_data:
        st.error("Unable to load agent configuration. Please ensure `model_config.json` exists and is valid.")
        st.info("Run `python scripts/validate_model_config.py` to validate your configuration.")
    else:
        # Display summary statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Agents", len(agent_data))
        with col2:
            unique_providers = len(set(item["provider"] for item in agent_data if item["provider"] != "ERROR"))
            st.metric("Providers", unique_providers)
        with col3:
            unique_models = len(set(item["model"] for item in agent_data if item["model"] != "N/A"))
            st.metric("Models", unique_models)
        
        st.divider()
        
        # Create a nice table using Streamlit's dataframe
        import pandas as pd
        
        # Prepare data for display
        display_data = []
        for item in agent_data:
            row = {
                "Agent": item["agent"],
                "Provider": item["provider"],
                "Type": item["provider_type"].title(),
                "Model": item["model"],
                "Source": item["source"]
            }
            
            # Add deployment column only for Azure providers
            if item["provider_type"] == "azure" and item["deployment"]:
                row["Deployment"] = item["deployment"]
            else:
                row["Deployment"] = ""
            
            display_data.append(row)
        
        df = pd.DataFrame(display_data)
        
        # Display the dataframe with nice formatting
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Agent": st.column_config.TextColumn("Agent", width="medium"),
                "Provider": st.column_config.TextColumn("Provider", width="medium"),
                "Type": st.column_config.TextColumn("Type", width="small"),
                "Model": st.column_config.TextColumn("Model", width="medium"),
                "Deployment": st.column_config.TextColumn("Deployment", width="medium"),
                "Source": st.column_config.TextColumn("Source", width="medium")
            }
        )
        
        # Add legend for source column
        with st.expander("ℹ️ About the Source Column"):
            st.markdown("""
            The **Source** column indicates where each agent's configuration comes from:
            - **agent**: Explicitly configured in the `agents` section
            - **group:[name]**: Matched by a wildcard pattern in the `groups` section
            - **defaults**: Using the default configuration
            """)
        
        # Add helpful links
        st.divider()
        st.markdown("""
        **Configuration Management:**
        - Edit your configuration in `model_config.json`
        - Run `python scripts/validate_model_config.py` to validate changes
        - See `MODEL_CONFIGURATION.md` for documentation
        """)

with debug_tab:
    with st.expander("Environment Variables"):
        st.write(os.environ)
    with st.expander("Session State"):
        st.write(st.session_state)
