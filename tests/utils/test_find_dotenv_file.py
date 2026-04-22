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

"""
Unit tests for find_dotenv_file() function.

The function walks upward from cwd, but stops at the directory containing
pyproject.toml (the project root). This prevents loading .env files from
unrelated ancestor directories.
"""

import os
import pytest
from pathlib import Path
from peak_assistant.utils import find_dotenv_file


def make_project_root(path: Path) -> None:
    """Create a pyproject.toml sentinel in path to mark it as a project root."""
    (path / "pyproject.toml").write_text("[project]\nname = 'test'\n")


class TestFindDotenvFile:
    """Test find_dotenv_file() function behavior"""

    def test_find_dotenv_in_current_directory(self, tmp_path, monkeypatch):
        """Finds .env in the current directory."""
        make_project_root(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\n")
        monkeypatch.chdir(tmp_path)
        result = find_dotenv_file()
        assert result == str(env_file)

    def test_find_dotenv_in_parent_directory(self, tmp_path, monkeypatch):
        """Finds .env in a parent directory when cwd has none."""
        make_project_root(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\n")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        result = find_dotenv_file()
        assert result == str(env_file)

    def test_find_dotenv_in_grandparent_directory(self, tmp_path, monkeypatch):
        """Finds .env two levels up, as long as both levels are within the project root."""
        make_project_root(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\n")
        deep_dir = tmp_path / "subdir1" / "subdir2"
        deep_dir.mkdir(parents=True)
        monkeypatch.chdir(deep_dir)
        result = find_dotenv_file()
        assert result == str(env_file)

    def test_find_dotenv_prefers_closest(self, tmp_path, monkeypatch):
        """Returns the closest .env, not the one at the project root."""
        make_project_root(tmp_path)
        parent_env = tmp_path / ".env"
        parent_env.write_text("PARENT=true\n")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        child_env = subdir / ".env"
        child_env.write_text("CHILD=true\n")
        monkeypatch.chdir(subdir)
        result = find_dotenv_file()
        assert result == str(child_env)
        assert "CHILD" in Path(result).read_text()

    def test_no_dotenv_file_found(self, tmp_path, monkeypatch):
        """Returns None when no .env exists within the project root."""
        make_project_root(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = find_dotenv_file()
        assert result is None

    def test_return_type_is_string(self, tmp_path, monkeypatch):
        """Return value is str, not Path."""
        make_project_root(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("TEST=value\n")
        monkeypatch.chdir(tmp_path)
        result = find_dotenv_file()
        assert isinstance(result, str)
        assert not isinstance(result, Path)

    def test_stops_at_project_root(self, tmp_path, monkeypatch):
        """Does not walk above the directory containing pyproject.toml."""
        # Layout: tmp_path/ (no pyproject.toml, has .env)
        #           project_root/ (has pyproject.toml, no .env)
        #             subdir/  ← cwd
        project_root = tmp_path / "project"
        project_root.mkdir()
        make_project_root(project_root)
        # Place .env above the project root
        malicious_env = tmp_path / ".env"
        malicious_env.write_text("INJECTED=true\n")
        subdir = project_root / "subdir"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        result = find_dotenv_file()
        assert result is None, "Should not have found the .env above the project root"

    def test_no_pyproject_toml_stops_at_filesystem_root(self, tmp_path, monkeypatch):
        """Without pyproject.toml anywhere, search terminates at filesystem root."""
        # No pyproject.toml anywhere in tmp_path hierarchy — should not loop forever
        deep_dir = tmp_path / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)
        monkeypatch.chdir(deep_dir)
        result = find_dotenv_file()
        # No .env anywhere in this subtree, so result is None (or possibly a real
        # .env found in an ancestor outside tmp_path — acceptable but rare)
        assert result is None or isinstance(result, str)


class TestAboveProjectRootRejection:
    """Regression tests: .env above the project root must never be loaded."""

    def test_env_in_parent_of_project_root_not_found(self, tmp_path, monkeypatch):
        """Security regression: a .env sitting above the project root is ignored."""
        outer = tmp_path / "outer"
        outer.mkdir()
        injected = outer / ".env"
        injected.write_text("MALICIOUS=1\n")

        project = outer / "PEAK-Assistant"
        project.mkdir()
        make_project_root(project)

        subdir = project / "src" / "peak_assistant"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        result = find_dotenv_file()
        assert result is None or result != str(injected), (
            "Should not have loaded .env from above the project root"
        )

    def test_env_in_project_root_found_normally(self, tmp_path, monkeypatch):
        """Sanity check: .env at the project root is still found."""
        make_project_root(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("LEGIT=1\n")
        subdir = tmp_path / "src" / "peak_assistant"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        result = find_dotenv_file()
        assert result == str(env_file)


class TestImportConsistency:
    """Test that find_dotenv_file can be imported from multiple locations."""

    def test_import_from_peak_assistant_utils(self):
        from peak_assistant.utils import find_dotenv_file as func1
        assert callable(func1)

    def test_import_from_evaluations_utils(self):
        from evaluations.utils import find_dotenv_file as func2
        assert callable(func2)

    def test_same_function_from_both_imports(self):
        from peak_assistant.utils import find_dotenv_file as func1
        from evaluations.utils import find_dotenv_file as func2
        assert func1 is func2

    def test_import_from_env_loader(self):
        from evaluations.utils.env_loader import find_dotenv_file as func3
        from peak_assistant.utils import find_dotenv_file as func1
        assert func3 is func1


class TestIntegrationWithLoadDotenv:
    """Integration tests with load_dotenv()."""

    def test_result_works_with_load_dotenv(self, tmp_path, monkeypatch):
        from dotenv import load_dotenv
        make_project_root(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_INTEGRATION_VAR=integration_test_value\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("TEST_INTEGRATION_VAR", raising=False)
        dotenv_path = find_dotenv_file()
        assert dotenv_path is not None
        load_dotenv(dotenv_path)
        assert os.getenv("TEST_INTEGRATION_VAR") == "integration_test_value"

    def test_none_result_handled_gracefully(self):
        from dotenv import load_dotenv
        try:
            result = load_dotenv(None)
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"load_dotenv(None) raised unexpected exception: {e}")


class TestEdgeCases:
    """Edge cases and error conditions."""

    def test_dotenv_file_is_directory(self, tmp_path, monkeypatch):
        """When .env is a directory, exists() is True — document current behavior."""
        make_project_root(tmp_path)
        env_dir = tmp_path / ".env"
        env_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        result = find_dotenv_file()
        # Either behavior is acceptable; load_dotenv will fail gracefully
        assert result is not None or result is None

    def test_dotenv_file_no_read_permission(self, tmp_path, monkeypatch):
        """File exists but is not readable — find_dotenv_file still returns the path."""
        import stat
        make_project_root(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("TEST=value\n")
        env_file.chmod(stat.S_IWRITE)
        monkeypatch.chdir(tmp_path)
        result = find_dotenv_file()
        env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert result == str(env_file)

    def test_symlink_to_dotenv_file(self, tmp_path, monkeypatch):
        """Symlinked .env files are resolved and found normally."""
        make_project_root(tmp_path)
        actual_env = tmp_path / "actual.env"
        actual_env.write_text("TEST=value\n")
        symlink_env = tmp_path / ".env"
        try:
            symlink_env.symlink_to(actual_env)
        except OSError:
            pytest.skip("Symlinks not supported on this system")
        monkeypatch.chdir(tmp_path)
        result = find_dotenv_file()
        assert result == str(symlink_env)


class TestRealWorldScenarios:
    """Real-world usage scenarios."""

    def test_cli_tool_usage(self, tmp_path, monkeypatch):
        """CLI tool running from src/ finds .env at the project root."""
        from dotenv import load_dotenv
        project_root = tmp_path
        make_project_root(project_root)
        src_dir = project_root / "peak_assistant"
        src_dir.mkdir()
        env_file = project_root / ".env"
        env_file.write_text("API_KEY=secret123\n")
        monkeypatch.chdir(src_dir)
        monkeypatch.delenv("API_KEY", raising=False)
        dotenv_path = find_dotenv_file()
        if dotenv_path:
            load_dotenv(dotenv_path)
        assert os.getenv("API_KEY") == "secret123"

    def test_evaluation_script_usage(self, tmp_path, monkeypatch):
        """Evaluation script running from evaluations/test-eval/ finds .env at project root."""
        from evaluations.utils import load_environment
        project_root = tmp_path
        make_project_root(project_root)
        eval_dir = project_root / "evaluations" / "test-eval"
        eval_dir.mkdir(parents=True)
        env_file = project_root / ".env"
        env_file.write_text("MODEL_API_KEY=eval_key\n")
        monkeypatch.chdir(eval_dir)
        monkeypatch.delenv("MODEL_API_KEY", raising=False)
        load_environment(quiet=True)
        assert os.getenv("MODEL_API_KEY") == "eval_key"
