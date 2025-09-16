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
            "msg_preprocess_kwargs": {"agent_id": "researcher"},
            "msg_postprocess_callback": postprocess_messages_logging,
            "msg_postprocess_kwargs": {"agent_id": "researcher"},
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