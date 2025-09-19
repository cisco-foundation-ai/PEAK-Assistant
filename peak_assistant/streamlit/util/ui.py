import sys
import asyncio
from typing import Callable
from datetime import datetime as dt

import streamlit as st
from streamlit_option_menu import option_menu


def peak_assistant_chat(
    title: str = None,
    page_description: str = None,
    doc_title: str = None,
    default_prompt: str = "",
    allow_upload: bool = False,
    agent_runner: Callable = None,
    run_button_label: str = None,
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
    # TODO: Make page description mandatory
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
            
            # Create an empty container for immediate message display
            new_message_container = st.empty()

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

    # Conditional input: button or chat input based on document state and run_button_label
    document_exists = (
        document_key in st.session_state and 
        st.session_state[document_key] and 
        st.session_state[document_key].strip()
    )
    
    # Show button if run_button_label is provided and document doesn't exist/is empty
    if run_button_label and not document_exists:
        if st.button(run_button_label, key=f"{doc_title}_run_button"):
            # This needs to be async so we can call the agent
            async def do_agent_button():
                # Record the start time
                start_time = dt.now()

                # Show the spinner in the chat area
                with new_message_container.container():
                    with st.spinner("Please wait...", show_time=True):
                        await agent_runner(debug_agents=True)

                # Record the end time
                end_time = dt.now()

                # Calculate the elapsed time
                elapsed_time = end_time - start_time

                response = f"Completed in {elapsed_time.seconds // 60 % 60}m {elapsed_time.seconds % 60}s."
                st.session_state[chat_messages_key].append({"role": "assistant", "content": response})

            # Run the async function.
            asyncio.run(do_agent_button())
            
            # Clear the temporary container and rerun to display the updated content.
            new_message_container.empty()
            st.rerun()
    else:
        # Show chat input (normal behavior)
        if prompt := st.chat_input("", key=doc_title, **chat_extra_args):
            # Handle the prompt to determine text content
            if allow_upload:
                # The 'prompt' from st.chat_input with files is an object
                # TODO: we set the text_prompt here to None so we explicitly ignore whatever
                #       the user types when they upload a file. We should fix this to actually
                #       use the text they typed.
                text_prompt = None
                if prompt.files:
                    st.session_state[document_key] += prompt.files[0].read().decode("utf-8")
                    st.session_state[chat_messages_key].append({"role": "assistant", "content": "User uploaded a research report."})
                    # Rerun to show the upload message
                    st.rerun()
                else:
                    text_prompt = prompt.text
            else:
                # The 'prompt' is just a string
                text_prompt = prompt

            if text_prompt:
                # Show user message immediately in the empty container
                with new_message_container.container():
                    with st.chat_message("user"):
                        st.markdown(text_prompt)
                
                # Add to session state for permanent storage
                st.session_state[chat_messages_key].append({"role": "user", "content": text_prompt})

                # This needs to be async so we can call the agent
                async def do_agent():
                    # Record the start time
                    start_time = dt.now()

                    # Show the spinner in the chat area, right after the user message
                    with new_message_container.container():
                        with st.chat_message("user"):
                            st.markdown(text_prompt)
                        with st.spinner("Please wait...", show_time=True):
                            await agent_runner(debug_agents=True)

                    # Record the end time
                    end_time = dt.now()

                    # Calculate the elapsed time
                    elapsed_time = end_time - start_time

                    response = f"Completed in {elapsed_time.seconds // 60 % 60}m {elapsed_time.seconds % 60}s."
                    st.session_state[chat_messages_key].append({"role": "assistant", "content": response})

                # Run the async function.
                asyncio.run(do_agent())
                
                # Clear the temporary container and rerun to show in main chat history
                new_message_container.empty()
                st.rerun()

def peak_assistant_hypothesis_list(
    title: str = "Hypothesis Generation",
    page_description: str = "Create a hunting hypothesis, or let the assistant generate some for you to choose from.",
    agent_runner: Callable = None,
):

    st.title(title)
    st.markdown(page_description)

    # --- Callback function for the dropdown menu --- #
    def _set_hypothesis_from_menu(key):
        # This callback fires when the menu selection changes.
        # We check if the new menu value is different from the last known one.
        current_selection = st.session_state[key]
        if current_selection != st.session_state.hypothesis_list_last_menu_value:
            st.session_state["Hypothesis"] = current_selection
            # Update the last known value to the new selection.
            st.session_state.hypothesis_list_last_menu_value = current_selection

    # Initialize session state keys
    if "generated_hypotheses" not in st.session_state:
        st.session_state["generated_hypotheses"] = []
    if "Hypothesis" not in st.session_state:
        st.session_state["Hypothesis"] = ""
    if "hypothesis_list_last_menu_value" not in st.session_state:
        st.session_state.hypothesis_list_last_menu_value = None

    # Show current hypothesis status (always visible)
    if st.session_state["Hypothesis"]:
        st.success(f"Hypothesis: {st.session_state['Hypothesis'][:100]}{'...' if len(st.session_state['Hypothesis']) > 100 else ''}")
    else:
        st.info("Select a hypothesis from the list below or type your own at the bottom")

    with st.container(height=500, border=False):
        if not st.session_state["generated_hypotheses"]:
            if st.button("Generate Hypotheses"):
                async def do_generate():
                    with st.spinner("Generating hypotheses..."):
                        await agent_runner()
                    # After generating, clear current hypothesis and reset tracking
                    st.session_state["Hypothesis"] = ""
                    st.session_state.hypothesis_list_last_menu_value = None
                    st.rerun()
                asyncio.run(do_generate())
        else:
            try:
                default_index = st.session_state["generated_hypotheses"].index(st.session_state["Hypothesis"])
            except ValueError:
                default_index = 0
            
            option_menu(
                menu_title="Select a Hypothesis",
                options=st.session_state["generated_hypotheses"],
                default_index=default_index,
                key="hypothesis_list_menu",
                on_change=_set_hypothesis_from_menu
            )
        
    # Handle manual input directly
    manual_hypothesis = st.chat_input(placeholder="Or enter your hypothesis here.")
    if manual_hypothesis:
        st.session_state["Hypothesis"] = manual_hypothesis
        # A manual entry means the menu is now out of sync, so update last_menu_value
        # Only update if the menu exists (i.e., hypotheses have been generated)
        if "hypothesis_list_menu" in st.session_state:
            st.session_state.hypothesis_list_last_menu_value = st.session_state.hypothesis_list_menu
        # Trigger a rerun to update the status display
        st.rerun()