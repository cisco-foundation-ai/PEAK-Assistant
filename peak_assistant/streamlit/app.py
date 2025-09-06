import os
import asyncio 
import streamlit as st 
from dotenv import load_dotenv
from typing import List, Dict, Any, Callable
from datetime import datetime as dt
from autogen_agentchat.messages import BaseChatMessage, TextMessage

from peak_assistant.utils import find_dotenv_file
from peak_assistant.utils.agent_callbacks import (
    preprocess_messages_logging,
    postprocess_messages_logging,
)

from peak_assistant.research_assistant import researcher

def peak_assistant_chat(
    title: str = None,
    page_description: str = None,
    doc_title: str = None,
    default_prompt: str = "",
    allow_upload: bool = False,
    agent_runner: Callable = None,
):
    """
    Creates a two-column UI with a chat history and a document editor.
    User input is appended to both the chat history and the document,
    and the chat input is fixed at the bottom of the screen.
    """

    if not title:
        raise ValueError("peak_assistant_chat: Title is required for a unique session state.")
    if not doc_title:
        raise ValueError("peak_assistant_chat: Document title is required for a unique session state.")
    if not agent_runner:
        raise ValueError("peak_assistant_chat: Agent runner is required.")

    # Keys for the separate session state variables for chat and document.
    document_key = f"{doc_title}_document"
    chat_messages_key = f"{doc_title}_messages"

    # Initialize the document and chat history in session state.
    if document_key not in st.session_state:
        st.session_state[document_key] = ""
    if chat_messages_key not in st.session_state:
        st.session_state[chat_messages_key] = [
            dict(
                role="assistant", 
                content=default_prompt
            )
        ]

    st.title(title)
    if page_description:
        desc_col, button_col = st.columns([5, 1])
        with desc_col:
            st.markdown(page_description)
        with button_col:
            st.download_button(
                label="Download",
                data=st.session_state[document_key],
                file_name=f"{doc_title.replace(' ', '_').lower()}.md",
                mime="text/markdown",
                use_container_width=True
            )

    # Create two columns for the main content.
    chat_col, doc_col = st.columns([1,3])

    with chat_col:
        # Use a container with a fixed height to make the content scrollable.
        with st.container(height=500, border=True):
            for message in st.session_state[chat_messages_key]:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # Create a placeholder for the spinner
            spinner_placeholder = st.empty()

    with doc_col:
        # Use a container with a fixed height to make the content scrollable.
        with st.container(height=500, border=True):
            st.markdown(st.session_state[document_key])

    chat_extra_args = dict()
    if allow_upload:
        chat_extra_args = {
            "accept_file": True,
            "file_type": ["txt", "md"]
        }

    # The chat input is placed outside the columns to be full-width at the bottom.
    if prompt := st.chat_input("", key=doc_title, **chat_extra_args):
        # This needs to be async so we can call the agent
        async def do_agent(placeholder):
            if allow_upload:
                # The 'prompt' from st.chat_input with files is an object
                text_prompt = prompt.text
                if prompt.files:
                    st.session_state[document_key] += prompt.files[0].read().decode("utf-8")
            else:
                # The 'prompt' is just a string
                text_prompt = prompt

            # Append user message to chat history
            st.session_state[chat_messages_key].append({"role": "user", "content": text_prompt})

            # Record the start time
            start_time = dt.now()

            # Show the spinner in the placeholder
            with placeholder.container():
                with st.spinner("Please wait...", show_time=True):
                    await agent_runner()

            # Clear the spinner and update the UI
            placeholder.empty()

            # Record the end time
            end_time = dt.now()

            # Calculate the elapsed time
            elapsed_time = end_time - start_time

            response = f"Completed in {elapsed_time.seconds // 60 % 60}m {elapsed_time.seconds % 60}s."
            st.session_state[chat_messages_key].append({"role": "assistant", "content": response})

            # Rerun to display the updated content.
            st.rerun()

        # Run the async function.
        asyncio.run(do_agent(spinner_placeholder))

def convert_chat_history_to_text_messages(chat_history: List[Dict[str, Any]]) -> List[TextMessage]:
    """Converts a Streamlit chat history (list of dicts) to a list of TextMessage objects."""
    return [
        TextMessage(content=msg["content"], source=msg["role"])
        for msg in chat_history
    ]

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

#############################
## MAIN
#############################

# Load our environment variables
dotenv_path = find_dotenv_file()
if dotenv_path:
    load_dotenv(dotenv_path)
else:
    raise FileNotFoundError("No .env file found in current or parent directories")

# Find and load our local context file (used for the agents)
with open("context.txt", "r", encoding="utf-8") as file:
    local_context = file.read()

st.session_state["local_context"] = local_context

# Use the full page instead of a narrow central column
st.set_page_config(layout="wide")

st.sidebar.image("images/peak-logo-dark.png", width="stretch")

research_tab, hypothesis_generation_tab, hypothesis_refinement_tab, able_tab, data_discovery_tab, hunt_plan_tab, debug_tab = st.tabs(
    [
        "Research", 
        "Hypothesis Generation",
        "Hypothesis Refinement",
        "ABLE Table",
        "Data Discovery",
        "Hunt Plan",
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
    st.title("Hypothesis Generation")
    st.markdown("The hypothesis generation assistant will help you generate a hypothesis for your hunt topic.")
    

#with hypothesis_refinement_tab:
#    peak_assistant_chat(
#        title="Hypothesis Refinement",
#        page_description="This is a hypothesis refinement assistant. Given an existing hypothesis, it will help you make it more specific and testable.",
#        doc_title="Refined Hypothesis",
#        default_prompt="Feedback",
#    )

#with able_tab:
#    peak_assistant_chat(
#        title="ABLE Table",
#        page_description="The ABLE table assistant will help you create an ABLE table for your hunt topic.",
#        doc_title="ABLE Table",
#        default_prompt="What would you like to hunt for?", 
#        allow_upload=True
#    )

#with data_discovery_tab:
#    peak_assistant_chat(
#        title="Data Discovery",
#        page_description="The data discovery assistant will help you identify potential data sources for your hunt topic.",
#        doc_title="Data Sources",
#        default_prompt="What would you like to hunt for?", 
#        allow_upload=True
#    )   

#with hunt_plan_tab:
#    peak_assistant_chat(
#        title="Hunt Plan",
#        page_description="The hunt plan assistant will help you create a hunt plan for your hunt topic.",
#        doc_title="Hunt Plan",
#        default_prompt="What would you like to hunt for?", 
#        allow_upload=True
#    )

with debug_tab:
    with st.expander("Environment Variables"):
        st.write(os.environ)
    with st.expander("Session State"):
        st.write(st.session_state)
    with st.expander("Local Context"):
        st.markdown(local_context)