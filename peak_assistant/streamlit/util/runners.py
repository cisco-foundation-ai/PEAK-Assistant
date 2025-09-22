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

import streamlit as st
import sys

from autogen_agentchat.messages import TextMessage

from peak_assistant.utils.agent_callbacks import (
    preprocess_messages_logging,
    postprocess_messages_logging,
)
from peak_assistant.research_assistant import researcher
from peak_assistant.hypothesis_assistant.hypothesis_assistant_cli import hypothesizer
from peak_assistant.hypothesis_assistant.hypothesis_refiner_cli import refiner
from peak_assistant.able_assistant import able_table
from peak_assistant.data_assistant import identify_data_sources
from peak_assistant.planning_assistant import plan_hunt

from .helpers import convert_chat_history_to_text_messages, convert_chat_history_to_user_messages
from .hypothesis_helpers import get_current_hypothesis


async def run_researcher(debug_agents: bool = True):

    debug_agents_opts = dict()
    if debug_agents:
        debug_agents_opts = {
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "researcher"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "researcher"},
        }


    previous_messages = convert_chat_history_to_text_messages(
        st.session_state["Research_messages"]
    )

    previous_messages.insert(-1, TextMessage(
        content=f"The current report draft is: {st.session_state['Research_document']}\n", source="user"
    ))

    result = await researcher(
        technique=st.session_state["Research_messages"][0]["content"],
        local_context=st.session_state["local_context"],
        previous_run=previous_messages,
        **debug_agents_opts
    )

    st.session_state["Research_previous_messages"] = result.messages

    # Find the final message from the "summarizer_agent" using next() and a generator expression
    report = next(
        (
            getattr(message, "content", None)
            for message in reversed(result.messages)
            if message.source == "summarizer_agent" and hasattr(message, "content")
        ),
        "no report generated",  # Default value if no "summarizer_agent" message is found
    )

    st.session_state["Research_document"] = report 

    return True

async def run_hypothesis_generator():

    hypotheses = await hypothesizer(
        user_input="",
        research_document=st.session_state["Research_document"],
        local_context=st.session_state["local_context"],
    )
    hypotheses = hypotheses.split("\n")
    hypotheses = [h for h in hypotheses if h.strip()]
    st.session_state["generated_hypotheses"] = hypotheses
    return True

async def run_hypothesis_refiner(debug_agents: bool = True):

    debug_agents_opts = dict()
    if debug_agents:
        debug_agents_opts = {
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "refiner"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "refiner"},
        }


    previous_messages = convert_chat_history_to_text_messages(
        st.session_state["Refinement_messages"]
    )

    # Use the current hypothesis if Refinement_document doesn't exist or is empty
    if "Refinement_document" in st.session_state and st.session_state["Refinement_document"].strip():
        current_hypothesis = st.session_state["Refinement_document"]
    else:
        current_hypothesis = st.session_state["Hypothesis"]

    previous_messages.insert(-1, TextMessage(
        content=f"The current hypothesis is: {current_hypothesis}\n", source="user"
    ))

    result = await refiner(
        hypothesis=current_hypothesis,
        local_context=st.session_state["local_context"],
        research_document=st.session_state["Research_document"],
        previous_run=previous_messages,
        **debug_agents_opts
    )

    st.session_state["Refinement_previous_messages"] = result.messages

    # Find the final message from the "critic" agent using next() and a generator expression
    refined_hypothesis_message = next(
        (
            getattr(message, "content", None)
            for message in reversed(result.messages)
            if message.source == "critic" and hasattr(message, "content")
        ),
        "Could not refine hypothesis. Something went wrong.",  # Default value if no "critic" message is found
    )
    
    # Remove the trailing "YYY-HYPOTHESIS-ACCEPTED-YYY" string if present
    refined_hypothesis = refined_hypothesis_message.replace("YYY-HYPOTHESIS-ACCEPTED-YYY", "").strip()

    st.session_state["Refinement_document"] = refined_hypothesis
    
    # Note: We don't update the main Hypothesis state during refinement iterations
    # to avoid triggering the reset logic in app.py
    
    return True

async def run_able_table(debug_agents: bool = False):

    previous_messages = convert_chat_history_to_user_messages(
        st.session_state["ABLE_messages"]
    )

    current_hypothesis = get_current_hypothesis()
    if not current_hypothesis:
        return False

    able = await able_table(
        hypothesis=get_current_hypothesis(),
        local_context=st.session_state["local_context"],
        research_document=st.session_state["Research_document"],
        previous_run=previous_messages,
    )

    st.session_state["ABLE_document"] = able
    
    return True

async def run_data_discovery(debug_agents: bool = False):

    debug_agents_opts = dict()
    if debug_agents:
        debug_agents_opts = {
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "discovery"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "discovery"},
        }

    previous_messages = convert_chat_history_to_text_messages(
        st.session_state["Discovery_messages"]
    )

    current_hypothesis = get_current_hypothesis()
    if not current_hypothesis:
        return False

    try:
        data_sources_result = await identify_data_sources(
            hypothesis=current_hypothesis,
            local_context=st.session_state["local_context"],
            research_document=st.session_state["Research_document"],
            able_info=st.session_state["ABLE_document"],
            previous_run=previous_messages,
            **debug_agents_opts
        )

        # Extract the actual content from the TaskResult object
        data_sources_message = next(
            (
                getattr(message, "content", None)
                for message in reversed(data_sources_result.messages)
                if hasattr(message, "content")
                and message.source == "Data_Discovery_Agent"
            ),
            None,  # Default value if no message is found
        )

        # If no message found from Data_Discovery_Agent, try to get any message with content
        if data_sources_message is None:
            data_sources_message = next(
                (
                    getattr(message, "content", None)
                    for message in reversed(data_sources_result.messages)
                    if hasattr(message, "content") and getattr(message, "content", None) is not None
                ),
                None,
            )

        # Final fallback if still None
        if data_sources_message is None:
            data_sources_message = "Error: Unable to identify data sources due to system configuration issues. Please check MCP server configuration."

    except Exception as e:
        # Handle MCP or other errors gracefully
        data_sources_message = f"Error: Unable to identify data sources due to system error: {str(e)}\n\nPlease check your MCP server configuration and ensure all required services are running."

    st.session_state["Discovery_document"] = data_sources_message
    
    return True

async def run_hunt_plan(debug_agents: bool = False):

    debug_agents_opts = dict()
    if debug_agents:
        debug_agents_opts = {
            "msg_preprocess_callback": preprocess_messages_logging,
            "msg_preprocess_kwargs": {"agent_id": "hunt-planner"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "hunt-planner"},
        }

    previous_messages = convert_chat_history_to_text_messages(
        st.session_state["Hunt Plan_messages"]
    )

    current_hypothesis = get_current_hypothesis()
    if not current_hypothesis:
        return False

    # Check if required dependencies exist
    if "ABLE_document" not in st.session_state or not st.session_state["ABLE_document"]:
        st.session_state["Hunt Plan_document"] = "Error: ABLE table is required before creating a hunt plan. Please generate an ABLE table first."
        return True
    
    if "Discovery_document" not in st.session_state or not st.session_state["Discovery_document"]:
        st.session_state["Hunt Plan_document"] = "Error: Data discovery information is required before creating a hunt plan. Please run data discovery first."
        return True

    try:
        hunt_plan_result = await plan_hunt(
            hypothesis=current_hypothesis,
            research_document=st.session_state["Research_document"],
            able_info=st.session_state["ABLE_document"],
            data_discovery=st.session_state["Discovery_document"],
            local_context=st.session_state["local_context"],
            previous_run=previous_messages,
            **debug_agents_opts
        )

        # Extract the actual content from the TaskResult object
        hunt_plan_message = next(
            (
                getattr(message, "content", None)
                for message in reversed(hunt_plan_result.messages)
                if hasattr(message, "content")
                and message.source == "hunt_planner"
            ),
            None,  # Default value if no message is found
        )

        # If no message found from hunt_planner, try to get any message with content
        if hunt_plan_message is None:
            hunt_plan_message = next(
                (
                    getattr(message, "content", None)
                    for message in reversed(hunt_plan_result.messages)
                    if hasattr(message, "content") and getattr(message, "content", None) is not None
                ),
                None,
            )

        # Final fallback if still None
        if hunt_plan_message is None:
            hunt_plan_message = "Error: Unable to create hunt plan due to system configuration issues. Please check system configuration."

    except Exception as e:
        # Handle errors gracefully
        hunt_plan_message = f"Error: Unable to create hunt plan due to system error: {str(e)}\n\nPlease check your system configuration and ensure all required services are running."

    st.session_state["Hunt Plan_document"] = hunt_plan_message
    
    return True