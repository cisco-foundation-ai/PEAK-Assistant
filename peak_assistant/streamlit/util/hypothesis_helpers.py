import streamlit as st


def get_current_hypothesis():
    """
    Returns the most current/effective hypothesis for use by downstream tabs.
    
    Returns:
        str: The current hypothesis (refined if available, otherwise original)
        None: If no hypothesis has been generated yet
    """
    # Check if refinement exists and has meaningful content
    if ("Refinement_document" in st.session_state and 
        st.session_state["Refinement_document"] and 
        st.session_state["Refinement_document"].strip()):
        return st.session_state["Refinement_document"]
    
    # Check if original hypothesis exists and has content
    if ("Hypothesis" in st.session_state and 
        st.session_state["Hypothesis"] and 
        st.session_state["Hypothesis"].strip()):
        return st.session_state["Hypothesis"]
    
    # No hypothesis available
    return None
