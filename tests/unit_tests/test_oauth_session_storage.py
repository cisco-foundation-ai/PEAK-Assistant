"""Tests for store_session_for_oauth allowlist and file-permission hardening."""
import json
import os
import stat
import tempfile
from unittest.mock import MagicMock, patch

import pytest


def _make_session(entries: dict):
    """Return a mock st.session_state that iterates over the given entries."""
    mock = MagicMock()
    mock.items.return_value = entries.items()
    mock.__contains__ = lambda self, key: key in entries
    mock.__getitem__ = lambda self, key: entries[key]
    return mock


@pytest.fixture()
def helpers_module():
    """Import helpers with st.session_state mocked at module level."""
    import importlib
    import peak_assistant.streamlit.util.helpers as mod
    return mod


class TestOAuthSessionAllowlist:
    def _call_store(self, session_entries: dict, server="test_server", state="abc123"):
        """Call store_session_for_oauth with a synthetic session state."""
        mock_session = _make_session(session_entries)
        with patch("peak_assistant.streamlit.util.helpers.st") as mock_st, \
             patch("peak_assistant.streamlit.util.helpers.get_user_session_id", return_value="uid_test"):
            mock_st.session_state = mock_session
            from peak_assistant.streamlit.util.helpers import store_session_for_oauth
            result = store_session_for_oauth(server, state)
        return result

    def _read_temp_file(self, state="abc123"):
        path = os.path.join(tempfile.gettempdir(), f"peak_oauth_session_{state}.json")
        with open(path) as f:
            return json.load(f), path

    def test_allowlisted_keys_are_preserved(self):
        entries = {
            "user_session_id": "uid1",
            "oauth_client_myserver": {"client_id": "cid"},
            "oauth_state_myserver": "state1",
            "oauth_server_for_state_state1": "myserver",
            "oauth_endpoints_myserver": {"token_endpoint": "https://example.com/token"},
            "oauth_discovery_myserver": {"issuer": "https://example.com"},
            "MCP.myserver": {"access_token": "tok"},
        }
        self._call_store(entries, state="keep1")
        data, _ = self._read_temp_file("keep1")
        stored = data["session_state"]
        assert set(stored.keys()) == set(entries.keys())

    def test_non_allowlisted_keys_are_stripped(self):
        entries = {
            "user_session_id": "uid1",
            "oauth_client_srv": {"client_id": "cid"},
            "Research_messages": [{"role": "user", "content": "sensitive"}],
            "AZURE_OPENAI_API_KEY": "sk-secret",
            "some_widget_state": True,
        }
        self._call_store(entries, state="strip1")
        data, _ = self._read_temp_file("strip1")
        stored = data["session_state"]
        assert "Research_messages" not in stored
        assert "AZURE_OPENAI_API_KEY" not in stored
        assert "some_widget_state" not in stored
        assert "user_session_id" in stored
        assert "oauth_client_srv" in stored

    def test_oauth_endpoints_preserved_for_token_exchange(self):
        entries = {
            "oauth_endpoints_srv": {"token_endpoint": "https://idp.example.com/token"},
        }
        self._call_store(entries, state="endpts1")
        data, _ = self._read_temp_file("endpts1")
        assert "oauth_endpoints_srv" in data["session_state"]
        assert data["session_state"]["oauth_endpoints_srv"]["token_endpoint"] == "https://idp.example.com/token"

    def test_mcp_tokens_preserved(self):
        entries = {
            "MCP.server_a": {"access_token": "tok_a"},
        }
        self._call_store(entries, state="mcp1")
        data, _ = self._read_temp_file("mcp1")
        assert "MCP.server_a" in data["session_state"]

    def test_empty_session_succeeds(self):
        result = self._call_store({}, state="empty1")
        assert result == "empty1"


class TestOAuthSessionFilePermissions:
    def test_temp_file_is_owner_readable_only(self):
        entries = {"user_session_id": "uid1"}
        mock_session = _make_session(entries)
        state = "perm_test_123"
        with patch("peak_assistant.streamlit.util.helpers.st") as mock_st, \
             patch("peak_assistant.streamlit.util.helpers.get_user_session_id", return_value="uid1"):
            mock_st.session_state = mock_session
            from peak_assistant.streamlit.util.helpers import store_session_for_oauth
            store_session_for_oauth("srv", state)

        path = os.path.join(tempfile.gettempdir(), f"peak_oauth_session_{state}.json")
        file_stat = os.stat(path)
        # Mask off file type bits; only owner read+write should be set (0o600)
        permissions = stat.S_IMODE(file_stat.st_mode)
        assert permissions == 0o600, f"Expected 0o600, got {oct(permissions)}"
