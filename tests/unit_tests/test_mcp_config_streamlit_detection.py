# Copyright (c) 2025 Cisco Systems, Inc. and its affiliates
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# SPDX-License-Identifier: MIT

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
