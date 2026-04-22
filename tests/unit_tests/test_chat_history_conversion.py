"""Tests for convert_chat_history_to_user_messages and convert_chat_history_to_text_messages."""
import pytest
from autogen_agentchat.messages import TextMessage, UserMessage

from peak_assistant.streamlit.util.helpers import (
    convert_chat_history_to_user_messages,
    convert_chat_history_to_text_messages,
)


class TestConvertChatHistoryToUserMessages:
    def test_user_messages_are_included(self):
        history = [{"role": "user", "content": "hello"}]
        result = convert_chat_history_to_user_messages(history)
        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert result[0].content == "hello"

    def test_assistant_messages_are_filtered_out(self):
        history = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        result = convert_chat_history_to_user_messages(history)
        assert len(result) == 1
        assert result[0].content == "question"

    def test_system_messages_are_filtered_out(self):
        history = [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
        ]
        result = convert_chat_history_to_user_messages(history)
        assert len(result) == 1
        assert result[0].content == "hi"

    def test_messages_without_role_are_filtered_out(self):
        history = [
            {"content": "no role here"},
            {"role": "user", "content": "with role"},
        ]
        result = convert_chat_history_to_user_messages(history)
        assert len(result) == 1
        assert result[0].content == "with role"

    def test_empty_history_returns_empty_list(self):
        assert convert_chat_history_to_user_messages([]) == []

    def test_mixed_history_preserves_order(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
        result = convert_chat_history_to_user_messages(history)
        assert [m.content for m in result] == ["first", "second"]


class TestConvertChatHistoryToTextMessages:
    def test_all_messages_are_included(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        result = convert_chat_history_to_text_messages(history)
        assert len(result) == 2

    def test_source_preserves_role(self):
        history = [
            {"role": "user", "content": "msg"},
            {"role": "assistant", "content": "reply"},
        ]
        result = convert_chat_history_to_text_messages(history)
        assert result[0].source == "user"
        assert result[1].source == "assistant"

    def test_returns_text_message_instances(self):
        history = [{"role": "user", "content": "test"}]
        result = convert_chat_history_to_text_messages(history)
        assert all(isinstance(m, TextMessage) for m in result)

    def test_empty_history_returns_empty_list(self):
        assert convert_chat_history_to_text_messages([]) == []
