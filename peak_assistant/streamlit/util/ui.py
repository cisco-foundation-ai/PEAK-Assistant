import asyncio
import streamlit as st
from typing import Callable
from datetime import datetime as dt

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