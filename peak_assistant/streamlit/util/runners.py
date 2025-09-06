import streamlit as st
from autogen_agentchat.messages import TextMessage

from peak_assistant.utils.agent_callbacks import (
    preprocess_messages_logging,
    postprocess_messages_logging,
)
from peak_assistant.research_assistant import researcher
from .helpers import convert_chat_history_to_text_messages


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