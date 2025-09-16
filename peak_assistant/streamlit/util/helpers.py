from typing import List, Dict, Any
from autogen_agentchat.messages import TextMessage, UserMessage

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