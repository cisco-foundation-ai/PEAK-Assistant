import streamlit as st 

def peak_assistant_chat(
    title: str = None,
    page_description: str = None,
    doc_title: str = None,
    input_default: str = "",
    allow_upload: bool = False
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

    # Keys for the separate session state variables for chat and document.
    document_key = f"{doc_title}_document"
    chat_messages_key = f"{doc_title}_messages"

    # Initialize the document and chat history in session state.
    if document_key not in st.session_state:
        st.session_state[document_key] = ("")
    if chat_messages_key not in st.session_state:
        st.session_state[chat_messages_key] = list()

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
    if prompt := st.chat_input(input_default, key=doc_title, **chat_extra_args):
        if allow_upload:
            if prompt.files:
                st.session_state[document_key] += prompt.files[0].read().decode("utf-8")
            prompt = prompt.text 

        # Append user message to chat history and document.
        st.session_state[chat_messages_key].append({"role": "user", "content": prompt})

        # TODO: Update the markdown document

        # TODO: Update this stub with output from the LLM.
        # Generate and append assistant response to chat history.
        response = f"Echo: {prompt}"
        st.session_state[chat_messages_key].append({"role": "assistant", "content": response})

        # Rerun to display the updated content.
        st.rerun()

def display_screen(title: str = "Untitled", input_default: str = "Untitled"):
    st.header(title)
    text_input = st.text_input(input_default)
    st.write("You entered:", text_input)


# Use the full page instead of a narrow central column
st.set_page_config(layout="wide")

st.sidebar.image("images/peak-logo-dark.png", width="stretch")

research_tab, hypothesis_generation_tab, hypothesis_refinement_tab, able_tab, data_discovery_tab, hunt_plan_tab = st.tabs(
    [
        "Research", 
        "Hypothesis Generation",
        "Hypothesis Refinement",
        "ABLE Table",
        "Data Discovery",
        "Hunt Plan"
    ]
)

with research_tab:
    peak_assistant_chat(
        title="Topic Research", 
        page_description="The topic research assistant will search internal and Internet sources and compile a research report for your hunt topic.",
        doc_title="Research",
        input_default="What would you like to hunt for?", 
        allow_upload=True
    )

# TODO: Implement something here.
with hypothesis_generation_tab:
    st.title("Hypothesis Generation")
    st.markdown("The hypothesis generation assistant will help you generate a hypothesis for your hunt topic.")
    

with hypothesis_refinement_tab:
    peak_assistant_chat(
        title="Hypothesis Refinement",
        page_description="This is a hypothesis refinement assistant. Given an existing hypothesis, it will help you make it more specific and testable.",
        doc_title="Refined Hypothesis",
        input_default="Feedback",
    )

with able_tab:
    peak_assistant_chat(
        title="ABLE Table",
        page_description="The ABLE table assistant will help you create an ABLE table for your hunt topic.",
        doc_title="ABLE Table",
        input_default="What would you like to hunt for?", 
        allow_upload=True
    )

with data_discovery_tab:
    peak_assistant_chat(
        title="Data Discovery",
        page_description="The data discovery assistant will help you identify potential data sources for your hunt topic.",
        doc_title="Data Sources",
        input_default="What would you like to hunt for?", 
        allow_upload=True
    )   

with hunt_plan_tab:
    peak_assistant_chat(
        title="Hunt Plan",
        page_description="The hunt plan assistant will help you create a hunt plan for your hunt topic.",
        doc_title="Hunt Plan",
        input_default="What would you like to hunt for?", 
        allow_upload=True
    )