"""Tests for Streamlit runtime detection in mcp_config"""

import sys
from unittest.mock import MagicMock
import pytest

from peak_assistant.utils.mcp_config import _is_streamlit_running


def test_streamlit_not_running():
    """Test that _is_streamlit_running returns False when Streamlit isn't loaded"""
    # Ensure streamlit.runtime.scriptrunner is not in sys.modules
    if 'streamlit.runtime.scriptrunner' in sys.modules:
        del sys.modules['streamlit.runtime.scriptrunner']
    
    assert not _is_streamlit_running()


def test_streamlit_running(monkeypatch):
    """Test that _is_streamlit_running returns True when Streamlit is loaded"""
    # Mock sys.modules to include streamlit.runtime.scriptrunner
    mock_module = MagicMock()
    monkeypatch.setitem(sys.modules, 'streamlit.runtime.scriptrunner', mock_module)
    
    assert _is_streamlit_running()


def test_streamlit_detection_does_not_import_streamlit():
    """Test that checking for Streamlit doesn't actually import it"""
    # Remove streamlit from sys.modules if present
    streamlit_modules = [key for key in sys.modules.keys() if key.startswith('streamlit')]
    for module in streamlit_modules:
        del sys.modules[module]
    
    # Call the detection function
    result = _is_streamlit_running()
    
    # Verify streamlit was not imported
    assert not result
    assert 'streamlit' not in sys.modules
    assert 'streamlit.runtime.scriptrunner' not in sys.modules
