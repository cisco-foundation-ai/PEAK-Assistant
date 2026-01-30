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

"""Tests for OAuth URL validation to prevent XSS/injection attacks"""

import pytest
from peak_assistant.streamlit.util.helpers import validate_and_escape_oauth_url


class TestValidOAuthUrls:
    """Test cases for URLs that SHOULD be accepted"""
    
    def test_https_url_accepted(self):
        """Standard HTTPS OAuth URL should be accepted"""
        url = "https://oauth.provider.com/authorize?client_id=123&state=abc"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
        assert "oauth.provider.com" in result
    
    def test_https_with_port_accepted(self):
        """HTTPS URL with explicit port should be accepted"""
        url = "https://oauth.provider.com:8443/authorize"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
    
    def test_http_localhost_accepted(self):
        """HTTP localhost should be accepted for dev"""
        url = "http://localhost:8501/callback"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
    
    def test_http_127_0_0_1_accepted(self):
        """HTTP 127.0.0.1 should be accepted for dev"""
        url = "http://127.0.0.1:8000/callback"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
    
    def test_http_localhost_no_port_accepted(self):
        """HTTP localhost without port should be accepted"""
        url = "http://localhost/callback"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
    
    def test_complex_oauth_url_accepted(self):
        """Complex OAuth URL with many parameters should be accepted"""
        url = "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?client_id=abc&response_type=code&redirect_uri=https%3A%2F%2Fexample.com&scope=openid%20profile"
        result = validate_and_escape_oauth_url(url)
        assert result is not None


class TestMaliciousUrls:
    """Test cases for URLs that MUST be rejected"""
    
    def test_javascript_scheme_rejected(self):
        """javascript: URLs must be rejected"""
        url = "javascript:alert('XSS')"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_javascript_scheme_uppercase_rejected(self):
        """JAVASCRIPT: scheme should also be rejected"""
        url = "JAVASCRIPT:alert('XSS')"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_javascript_scheme_mixed_case_rejected(self):
        """Mixed case JavaScript scheme should be rejected"""
        url = "JaVaScRiPt:alert('XSS')"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_data_scheme_rejected(self):
        """data: URLs must be rejected"""
        url = "data:text/html,<script>alert('XSS')</script>"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_vbscript_scheme_rejected(self):
        """vbscript: URLs must be rejected"""
        url = "vbscript:msgbox('XSS')"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_file_scheme_rejected(self):
        """file: URLs must be rejected"""
        url = "file:///etc/passwd"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_ftp_scheme_rejected(self):
        """ftp: URLs must be rejected"""
        url = "ftp://evil.com/malware"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_http_non_localhost_rejected(self):
        """HTTP to non-localhost must be rejected"""
        url = "http://evil.com/steal-tokens"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_http_spoofed_localhost_rejected(self):
        """HTTP to localhost.evil.com must be rejected"""
        url = "http://localhost.evil.com/callback"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_http_localhost_subdomain_rejected(self):
        """HTTP to subdomain.localhost must be rejected"""
        url = "http://evil.localhost/callback"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_empty_url_rejected(self):
        """Empty URL must be rejected"""
        result = validate_and_escape_oauth_url("")
        assert result is None
    
    def test_no_host_rejected(self):
        """URL without host must be rejected"""
        url = "https:///path/only"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_relative_url_rejected(self):
        """Relative URLs must be rejected"""
        url = "/oauth/callback"
        result = validate_and_escape_oauth_url(url)
        assert result is None
    
    def test_protocol_relative_url_rejected(self):
        """Protocol-relative URLs must be rejected"""
        url = "//evil.com/callback"
        result = validate_and_escape_oauth_url(url)
        assert result is None


class TestHtmlEscaping:
    """Test cases for HTML escaping to prevent attribute breakout"""
    
    def test_quotes_escaped(self):
        """Double quotes in URL should be HTML-escaped"""
        url = 'https://oauth.com/auth?param="value"'
        result = validate_and_escape_oauth_url(url)
        assert result is not None
        assert '"' not in result
        assert '&quot;' in result
    
    def test_single_quotes_escaped(self):
        """Single quotes in URL should be HTML-escaped"""
        url = "https://oauth.com/auth?param='value'"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
        assert "'" not in result
        assert '&#x27;' in result
    
    def test_angle_brackets_escaped(self):
        """Angle brackets should be HTML-escaped"""
        url = "https://oauth.com/auth?param=<script>"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
        assert '<' not in result
        assert '&lt;' in result
    
    def test_ampersand_escaped(self):
        """Ampersands should be HTML-escaped"""
        url = "https://oauth.com/auth?a=1&b=2"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
        assert '&amp;' in result
    
    def test_attribute_breakout_attempt_escaped(self):
        """Attribute breakout attempts should be escaped"""
        url = 'https://oauth.com/"><script>alert(1)</script><a href="'
        result = validate_and_escape_oauth_url(url)
        assert result is not None
        assert '<script>' not in result
        assert '&lt;script&gt;' in result


class TestEdgeCases:
    """Edge cases and boundary conditions"""
    
    def test_none_input_rejected(self):
        """None input should return None"""
        result = validate_and_escape_oauth_url(None)
        assert result is None
    
    def test_integer_input_rejected(self):
        """Integer input should return None"""
        result = validate_and_escape_oauth_url(12345)
        assert result is None
    
    def test_list_input_rejected(self):
        """List input should return None"""
        result = validate_and_escape_oauth_url(["https://example.com"])
        assert result is None
    
    def test_dict_input_rejected(self):
        """Dict input should return None"""
        result = validate_and_escape_oauth_url({"url": "https://example.com"})
        assert result is None
    
    def test_unicode_url_accepted(self):
        """Unicode in URL path should be accepted"""
        url = "https://oauth.com/auth?name=tëst"
        result = validate_and_escape_oauth_url(url)
        assert result is not None
    
    def test_very_long_url_accepted(self):
        """Very long but valid URL should be accepted"""
        url = "https://oauth.com/auth?" + "x" * 2000
        result = validate_and_escape_oauth_url(url)
        assert result is not None
