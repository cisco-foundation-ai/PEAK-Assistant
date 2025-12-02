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

"""Integration tests for validate-config command"""

import json
import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory for test configs"""
    return tmp_path


def test_validate_config_valid_config(temp_config_dir):
    """Test validate-config with a valid configuration"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-openai": {
                "type": "openai",
                "config": {
                    "api_key": "$OPENAI_API_KEY"
                }
            }
        },
        "defaults": {
            "provider": "test-openai",
            "model": "gpt-4o"
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file), "-q"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Expected success, got: {result.stderr}"


def test_validate_config_missing_file(temp_config_dir):
    """Test validate-config with missing config file"""
    config_file = temp_config_dir / "nonexistent.json"
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1
    assert "not found" in result.stdout.lower()


def test_validate_config_invalid_json(temp_config_dir):
    """Test validate-config with invalid JSON"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text("{ invalid json }")
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file), "-q"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1
    assert "error" in result.stdout.lower()


def test_validate_config_missing_provider(temp_config_dir):
    """Test validate-config with missing provider type"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-provider": {
                "config": {
                    "api_key": "test"
                }
            }
        },
        "defaults": {
            "provider": "test-provider",
            "model": "test-model"
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file), "-q"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1
    assert "error" in result.stdout.lower()


def test_validate_config_invalid_provider_type(temp_config_dir):
    """Test validate-config with invalid provider type"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-provider": {
                "type": "invalid-type",
                "config": {
                    "api_key": "test"
                }
            }
        },
        "defaults": {
            "provider": "test-provider",
            "model": "test-model"
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file), "-q"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1
    assert "Invalid type" in result.stdout


def test_validate_config_missing_required_fields_azure(temp_config_dir):
    """Test validate-config with Azure provider missing required fields"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-azure": {
                "type": "azure",
                "config": {
                    "api_key": "test"
                    # Missing endpoint and api_version
                }
            }
        },
        "defaults": {
            "provider": "test-azure",
            "model": "gpt-4"
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file), "-q"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1
    assert "Missing required fields" in result.stdout


def test_validate_config_full_report(temp_config_dir):
    """Test validate-config full report output (not quiet mode)"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-openai": {
                "type": "openai",
                "config": {
                    "api_key": "$OPENAI_API_KEY"
                }
            },
            "test-anthropic": {
                "type": "anthropic",
                "config": {
                    "api_key": "$ANTHROPIC_API_KEY"
                }
            }
        },
        "defaults": {
            "provider": "test-openai",
            "model": "gpt-4o"
        },
        "agents": {
            "hypothesizer_agent": {
                "provider": "test-anthropic",
                "model": "claude-3-5-sonnet-20241022"
            }
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    # Check for report sections
    assert "Validation Report" in result.stdout
    assert "Providers" in result.stdout
    assert "Agent Model Assignments" in result.stdout
    assert "Provider Usage Summary" in result.stdout
    assert "✓" in result.stdout  # Success indicator


def test_validate_config_unused_provider_warning(temp_config_dir):
    """Test validate-config warns about unused providers"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-openai": {
                "type": "openai",
                "config": {
                    "api_key": "$OPENAI_API_KEY"
                }
            },
            "unused-provider": {
                "type": "openai",
                "config": {
                    "api_key": "$OPENAI_API_KEY"
                }
            }
        },
        "defaults": {
            "provider": "test-openai",
            "model": "gpt-4o"
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0  # Warnings don't cause failure
    assert "warning" in result.stdout.lower()
    assert "unused-provider" in result.stdout


def test_validate_config_azure_deployment_required(temp_config_dir):
    """Test validate-config checks for Azure deployment field"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-azure": {
                "type": "azure",
                "config": {
                    "api_key": "$AZURE_OPENAI_API_KEY",
                    "endpoint": "https://test.openai.azure.com/",
                    "api_version": "2024-02-01"
                }
            }
        },
        "defaults": {
            "provider": "test-azure",
            "model": "gpt-4"
            # Missing deployment
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file), "-q"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1
    assert "deployment" in result.stdout.lower()


def test_validate_config_anthropic_valid(temp_config_dir):
    """Test validate-config with valid Anthropic configuration"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "test-anthropic": {
                "type": "anthropic",
                "config": {
                    "api_key": "$ANTHROPIC_API_KEY"
                }
            }
        },
        "defaults": {
            "provider": "test-anthropic",
            "model": "claude-3-5-sonnet-20241022"
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file), "-q"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0


def test_validate_config_groups(temp_config_dir):
    """Test validate-config with agent groups"""
    config_file = temp_config_dir / "model_config.json"
    config_file.write_text(json.dumps({
        "version": "1.0",
        "providers": {
            "openai-provider": {
                "type": "openai",
                "config": {
                    "api_key": "$OPENAI_API_KEY"
                }
            },
            "anthropic-provider": {
                "type": "anthropic",
                "config": {
                    "api_key": "$ANTHROPIC_API_KEY"
                }
            }
        },
        "defaults": {
            "provider": "openai-provider",
            "model": "gpt-4o"
        },
        "groups": {
            "critics": {
                "match": ["*_critic*"],
                "provider": "anthropic-provider",
                "model": "claude-3-5-sonnet-20241022"
            }
        }
    }))
    
    result = subprocess.run(
        ["uv", "run", "validate-config", "-c", str(config_file)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    # Check that groups are shown in the report
    assert "critics" in result.stdout.lower() or "group" in result.stdout.lower()
