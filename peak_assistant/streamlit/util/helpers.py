from typing import List, Dict, Any
from autogen_agentchat.messages import TextMessage, UserMessage
import streamlit as st

def convert_chat_history_to_text_messages(chat_history: List[Dict[str, Any]]) -> List[TextMessage]:
    """Converts a Streamlit chat history (list of dicts) to a list of TextMessage objects."""
    return [
        TextMessage(content=msg["content"], source=msg["role"])
        for msg in chat_history
    ]

def convert_chat_history_to_user_messages(chat_history: List[Dict[str, Any]]) -> List[TextMessage]:
    """Converts a Streamlit chat history (list of dicts) to a list of TextMessage objects."""
    return [
        UserMessage(content=msg["content"], source=msg["role"])
        for msg in chat_history
    ]

def switch_tabs(tab_index: int = 0):
    st.html(f"""
    <script>
        var tabGroup = window.parent.document.getElementsByClassName("stTabs")[0];
        var tabButtons = tabGroup.getElementsByTagName("button");
        tabButtons[{tab_index}].click();
    </script>
    """)

@st.dialog("Reset Session", dismissible=True, on_dismiss="ignore")
def reset_session():
    st.warning("Are you sure you want to reset the session? This will erase all progress and start over.")
    if st.button("Reset Session"):
        for key in st.session_state.keys():
            del st.session_state[key]
        
        st.session_state["_reset_requested"] = True

        st.rerun()
