import os
from dotenv import load_dotenv

import streamlit as st 

from peak_assistant.utils import find_dotenv_file
from peak_assistant.streamlit.util.ui import peak_assistant_chat, peak_assistant_hypothesis_list
from peak_assistant.streamlit.util.runners import run_researcher, run_hypothesis_generator, run_hypothesis_refiner
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

# Reduce the margin above the tabs
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
        }
    </style>
    """, unsafe_allow_html=True)

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
    if ("Research_document" not in st.session_state) or not st.session_state["Research_document"]:
        st.warning("Please run the Research tab first.")
    else:
        peak_assistant_hypothesis_list(
            agent_runner = run_hypothesis_generator
        )

with hypothesis_refinement_tab:
    if ("Hypothesis" not in st.session_state) or not st.session_state["Hypothesis"]:
        st.warning("Please run the Hypothesis Generation tab first.")
    else:
        # Reset refinement if hypothesis has changed
        if "Refinement_document" not in st.session_state:
            st.session_state["Refinement_document"] = st.session_state["Hypothesis"]
            st.session_state["last_hypothesis_for_refinement"] = st.session_state["Hypothesis"]
        elif st.session_state.get("last_hypothesis_for_refinement") != st.session_state["Hypothesis"]:
            # Hypothesis changed, reset the refinement
            st.session_state["Refinement_document"] = st.session_state["Hypothesis"]
            st.session_state["last_hypothesis_for_refinement"] = st.session_state["Hypothesis"]
            # Clear any previous refinement messages to start fresh
            if "Refinement_messages" in st.session_state:
                del st.session_state["Refinement_messages"]
        peak_assistant_chat(
            title="Hypothesis Refinement",
            page_description="The hypothesis refinement assistant will help you ensure your hypothesis is both specific and testable.",
            doc_title="Refinement",
            default_prompt="What would you like to refine?", 
            allow_upload=False,
            agent_runner=run_hypothesis_refiner
        )

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