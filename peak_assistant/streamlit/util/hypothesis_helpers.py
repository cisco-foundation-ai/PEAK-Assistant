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
