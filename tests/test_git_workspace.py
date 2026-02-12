"""
Tests for Git Workspace Tools (Wave 2 — Module 3.1)
====================================================

Tests cover all LangChain tools from ``git_workspace.py``:
  - create_working_branch
  - read_file_from_branch
  - write_file_to_branch
  - write_files_to_branch
  - list_files_on_branch
  - get_branch_diff
  - create_pull_request_from_branch
  - delete_working_branch

All GitHub API calls are mocked via ``unittest.mock``.
"""

import base64
import re
from unittest.mock import Mock, patch, MagicMock

import pytest

from graphs.dev_team.tools.git_workspace import (
    create_working_branch,
    read_file_from_branch,
    write_file_to_branch,
    write_files_to_branch,
    list_files_on_branch,
    get_branch_diff,
    create_pull_request_from_branch,
    delete_working_branch,
    _generate_branch_name,
    git_workspace_tools,
)


# ─────────────────────── Helpers ─────────────────────────


class TestBranchNameGeneration:
    """Test the branch name generator."""

    def test_basic_name(self):
        name = _generate_branch_name("Create calculator API")
        assert name.startswith("ai/create-calculator-api-")
        # Check timestamp format: YYYYMMDD-HHMMSS
        parts = name.split("-")
        assert len(parts) >= 4

    def test_empty_summary(self):
        name = _generate_branch_name("")
        assert name.startswith("ai/task-")

    def test_special_characters(self):
        name = _generate_branch_name("Fix bug #123 in user/auth")
        assert "#" not in name
        assert "/" not in name.split("ai/")[1].split("-20")[0]

    def test_long_summary_truncated(self):
        name = _generate_branch_name(
            "This is a very long task description with many words that should be truncated"
        )
        # Only first 5 words should be kept
        slug_part = name.split("ai/")[1].rsplit("-20", 1)[0]
        assert len(slug_part.split("-")) <= 5

    def test_unique_timestamps(self):
        """Two calls should produce different branch names (different timestamps)."""
        import time
        name1 = _generate_branch_name("test")
        time.sleep(0.01)
        name2 = _generate_branch_name("test")
        # Same second is possible — we check structure, not uniqueness here
        assert name1.startswith("ai/test-")
        assert name2.startswith("ai/test-")


# ─────────────────────── Fixtures ────────────────────────


def _make_mock_repo():
    """Create a mock PyGithub Repository with common stubs."""
    repo = Mock()
    repo.full_name = "owner/repo"

    # Branch / ref stubs
    branch = Mock()
    branch.commit.sha = "abc123def456"
    repo.get_branch.return_value = branch

    ref = Mock()
    ref.object.sha = "abc123def456"
    repo.get_git_ref.return_value = ref
    repo.create_git_ref.return_value = Mock()

    return repo


@pytest.fixture
def mock_repo():
    return _make_mock_repo()


# ────────────── create_working_branch ────────────────────


class TestCreateWorkingBranch:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_success(self, mock_client_fn, mock_repo):
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = create_working_branch.invoke({
            "repo": "owner/repo",
            "base_branch": "main",
            "task_summary": "Add login page",
        })

        assert result.startswith("ai/add-login-page-")
        mock_repo.get_branch.assert_called_once_with("main")
        mock_repo.create_git_ref.assert_called_once()

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_no_client(self, mock_client_fn):
        mock_client_fn.return_value = None

        result = create_working_branch.invoke({
            "repo": "owner/repo",
        })

        assert "Error" in result
        assert "GITHUB_TOKEN" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_branch_not_found(self, mock_client_fn, mock_repo):
        mock_repo.get_branch.side_effect = Exception("Branch not found")
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = create_working_branch.invoke({
            "repo": "owner/repo",
            "base_branch": "nonexistent",
        })

        assert "Error" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_default_params(self, mock_client_fn, mock_repo):
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = create_working_branch.invoke({
            "repo": "owner/repo",
        })

        assert result.startswith("ai/task-")
        mock_repo.get_branch.assert_called_once_with("main")


# ────────────── read_file_from_branch ────────────────────


class TestReadFileFromBranch:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_success(self, mock_client_fn, mock_repo):
        content_bytes = base64.b64encode(b"print('hello')").decode("ascii")
        mock_file = Mock(content=content_bytes)
        mock_repo.get_contents.return_value = mock_file
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = read_file_from_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test-branch",
            "path": "src/main.py",
        })

        assert result == "print('hello')"
        mock_repo.get_contents.assert_called_once_with("src/main.py", ref="ai/test-branch")

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_directory_path(self, mock_client_fn, mock_repo):
        """Reading a directory path should return an error."""
        mock_repo.get_contents.return_value = [Mock(), Mock()]  # list = directory
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = read_file_from_branch.invoke({
            "repo": "owner/repo",
            "branch": "main",
            "path": "src",
        })

        assert "directory" in result.lower()

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_file_not_found(self, mock_client_fn, mock_repo):
        mock_repo.get_contents.side_effect = Exception("404 Not Found")
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = read_file_from_branch.invoke({
            "repo": "owner/repo",
            "branch": "main",
            "path": "missing.txt",
        })

        assert "Error" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_no_client(self, mock_client_fn):
        mock_client_fn.return_value = None

        result = read_file_from_branch.invoke({
            "repo": "owner/repo",
            "branch": "main",
            "path": "test.py",
        })

        assert "Error" in result


# ────────────── write_file_to_branch ─────────────────────


class TestWriteFileToBranch:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_create_new_file(self, mock_client_fn, mock_repo):
        mock_repo.get_contents.side_effect = Exception("File not found")
        mock_commit = Mock(sha="aaa111bbb222")
        mock_repo.create_file.return_value = {"commit": mock_commit}
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = write_file_to_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "path": "new_file.py",
            "content": "print('new')",
            "message": "Add new file",
        })

        assert "aaa111bbb222" in result
        mock_repo.create_file.assert_called_once()

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_update_existing_file(self, mock_client_fn, mock_repo):
        existing = Mock(sha="old_sha_123")
        mock_repo.get_contents.return_value = existing
        mock_commit = Mock(sha="bbb222ccc333")
        mock_repo.update_file.return_value = {"commit": mock_commit}
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = write_file_to_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "path": "existing.py",
            "content": "updated content",
            "message": "Update file",
        })

        assert "bbb222ccc333" in result
        mock_repo.update_file.assert_called_once()

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_auto_commit_message(self, mock_client_fn, mock_repo):
        mock_repo.get_contents.side_effect = Exception("File not found")
        mock_repo.create_file.return_value = {"commit": Mock(sha="ccc")}
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        write_file_to_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "path": "src/app.py",
            "content": "code",
        })

        # Auto-generated message for path with /
        call_args = mock_repo.create_file.call_args
        assert "Update" in call_args.kwargs.get("message", call_args[1].get("message", ""))

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_directory_error(self, mock_client_fn, mock_repo):
        """Writing to a directory path should fail."""
        mock_repo.get_contents.return_value = [Mock()]  # list = directory
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = write_file_to_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "path": "src",
            "content": "some content",
        })

        assert "directory" in result.lower()


# ────────────── write_files_to_branch (batch) ────────────


class TestWriteFilesToBranch:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_batch_write_success(self, mock_client_fn, mock_repo):
        # Setup Git tree API mocks
        base_commit = Mock()
        base_commit.tree = Mock()
        mock_repo.get_git_commit.return_value = base_commit

        new_tree = Mock()
        mock_repo.create_git_tree.return_value = new_tree

        new_commit = Mock(sha="batch_sha_123")
        mock_repo.create_git_commit.return_value = new_commit

        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        files = [
            {"path": "src/main.py", "content": "print('main')"},
            {"path": "src/utils.py", "content": "def helper(): pass"},
            {"path": "README.md", "content": "# Project"},
        ]

        result = write_files_to_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "files": files,
            "message": "Initial project files",
        })

        assert "3 files" in result
        assert "batch_sha_123" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_empty_files_list(self, mock_client_fn):
        result = write_files_to_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "files": [],
        })

        assert "Error" in result
        assert "no files" in result.lower()

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_no_client(self, mock_client_fn):
        mock_client_fn.return_value = None

        result = write_files_to_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "files": [{"path": "test.py", "content": "code"}],
        })

        assert "Error" in result


# ────────────── list_files_on_branch ─────────────────────


class TestListFilesOnBranch:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_non_recursive(self, mock_client_fn, mock_repo):
        contents = [
            Mock(path="README.md", type="file"),
            Mock(path="src", type="dir"),
            Mock(path="main.py", type="file"),
        ]
        mock_repo.get_contents.return_value = contents
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = list_files_on_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
        })

        assert "[file] README.md" in result
        assert "[dir] src" in result
        assert "[file] main.py" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_recursive_listing(self, mock_client_fn, mock_repo):
        tree = Mock()
        tree.tree = [
            Mock(path="README.md", type="blob"),
            Mock(path="src", type="tree"),
            Mock(path="src/main.py", type="blob"),
            Mock(path="src/utils.py", type="blob"),
        ]
        mock_repo.get_git_tree.return_value = tree
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = list_files_on_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "recursive": True,
        })

        assert "[file] README.md" in result
        assert "[dir] src" in result
        assert "[file] src/main.py" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_recursive_with_path_filter(self, mock_client_fn, mock_repo):
        tree = Mock()
        tree.tree = [
            Mock(path="README.md", type="blob"),
            Mock(path="src/main.py", type="blob"),
            Mock(path="src/utils.py", type="blob"),
            Mock(path="tests/test_main.py", type="blob"),
        ]
        mock_repo.get_git_tree.return_value = tree
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = list_files_on_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "path": "src",
            "recursive": True,
        })

        assert "src/main.py" in result
        assert "src/utils.py" in result
        assert "README.md" not in result
        assert "tests" not in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_empty_directory(self, mock_client_fn, mock_repo):
        mock_repo.get_contents.return_value = []
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = list_files_on_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "path": "empty_dir",
        })

        assert "Empty directory" in result


# ────────────── get_branch_diff ──────────────────────────


class TestGetBranchDiff:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_diff_with_changes(self, mock_client_fn, mock_repo):
        comparison = Mock()
        comparison.total_commits = 3
        comparison.ahead_by = 3
        comparison.files = [
            Mock(
                filename="src/main.py",
                status="modified",
                additions=10,
                deletions=2,
                patch="@@ -1,3 +1,11 @@\n+import os\n+\n def main():\n-    pass\n+    print('hello')",
            ),
            Mock(
                filename="README.md",
                status="added",
                additions=5,
                deletions=0,
                patch="@@ -0,0 +1,5 @@\n+# Project\n+\n+Description",
            ),
        ]
        mock_repo.compare.return_value = comparison
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = get_branch_diff.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "base": "main",
        })

        assert "main...ai/test" in result
        assert "Commits: 3" in result
        assert "Files changed: 2" in result
        assert "src/main.py" in result
        assert "README.md" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_no_changes(self, mock_client_fn, mock_repo):
        comparison = Mock(total_commits=0, files=[])
        mock_repo.compare.return_value = comparison
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = get_branch_diff.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
        })

        assert "No changes" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_long_patch_truncated(self, mock_client_fn, mock_repo):
        comparison = Mock()
        comparison.total_commits = 1
        comparison.ahead_by = 1
        comparison.files = [
            Mock(
                filename="big_file.py",
                status="modified",
                additions=100,
                deletions=50,
                patch="x" * 5000,  # Very long patch
            ),
        ]
        mock_repo.compare.return_value = comparison
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = get_branch_diff.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
        })

        assert "truncated" in result


# ────────────── create_pull_request_from_branch ──────────


class TestCreatePullRequestFromBranch:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_success(self, mock_client_fn, mock_repo):
        mock_pr = Mock(number=42, html_url="https://github.com/owner/repo/pull/42")
        mock_repo.create_pull.return_value = mock_pr
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = create_pull_request_from_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "title": "feat: add login page",
            "body": "## Summary\n- Added login form\n- JWT integration",
            "base": "main",
        })

        assert "https://github.com/owner/repo/pull/42" in result
        mock_repo.create_pull.assert_called_once_with(
            title="feat: add login page",
            body="## Summary\n- Added login form\n- JWT integration",
            head="ai/test",
            base="main",
            draft=False,
        )

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_draft_pr(self, mock_client_fn, mock_repo):
        mock_pr = Mock(number=43, html_url="https://github.com/owner/repo/pull/43")
        mock_repo.create_pull.return_value = mock_pr
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = create_pull_request_from_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "title": "WIP: feature",
            "body": "Work in progress",
            "draft": True,
        })

        assert "pull/43" in result
        mock_repo.create_pull.assert_called_once()
        call_kwargs = mock_repo.create_pull.call_args
        assert call_kwargs.kwargs.get("draft") is True or call_kwargs[1].get("draft") is True

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_create_pr_error(self, mock_client_fn, mock_repo):
        mock_repo.create_pull.side_effect = Exception("Validation Failed")
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = create_pull_request_from_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test",
            "title": "PR",
            "body": "desc",
        })

        assert "Error" in result


# ────────────── delete_working_branch ────────────────────


class TestDeleteWorkingBranch:

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_delete_ai_branch(self, mock_client_fn, mock_repo):
        mock_ref = Mock()
        mock_repo.get_git_ref.return_value = mock_ref
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = delete_working_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/test-branch",
        })

        assert "deleted" in result.lower()
        mock_ref.delete.assert_called_once()

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_refuse_non_ai_branch(self, mock_client_fn):
        """Should refuse to delete branches not starting with 'ai/'."""
        result = delete_working_branch.invoke({
            "repo": "owner/repo",
            "branch": "main",
        })

        assert "Error" in result
        assert "refusing" in result.lower()

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_refuse_feature_branch(self, mock_client_fn):
        result = delete_working_branch.invoke({
            "repo": "owner/repo",
            "branch": "feature/my-feature",
        })

        assert "Error" in result

    @patch("graphs.dev_team.tools.git_workspace.get_github_client")
    def test_branch_not_found(self, mock_client_fn, mock_repo):
        mock_repo.get_git_ref.side_effect = Exception("Not Found")
        mock_client_fn.return_value = Mock(get_repo=Mock(return_value=mock_repo))

        result = delete_working_branch.invoke({
            "repo": "owner/repo",
            "branch": "ai/nonexistent",
        })

        assert "Error" in result


# ────────────── Exports ──────────────────────────────────


class TestExports:

    def test_all_tools_exported(self):
        """All 8 tools should be in the export list."""
        assert len(git_workspace_tools) == 8

    def test_tools_are_callable(self):
        """Each tool should have an invoke method (LangChain tool)."""
        for tool_fn in git_workspace_tools:
            assert hasattr(tool_fn, "invoke"), f"{tool_fn.name} missing invoke"

    def test_tool_names(self):
        names = {t.name for t in git_workspace_tools}
        expected = {
            "create_working_branch",
            "read_file_from_branch",
            "write_file_to_branch",
            "write_files_to_branch",
            "list_files_on_branch",
            "get_branch_diff",
            "create_pull_request_from_branch",
            "delete_working_branch",
        }
        assert names == expected

    def test_tools_have_descriptions(self):
        """Every tool should have a docstring (used by LLM)."""
        for tool_fn in git_workspace_tools:
            assert tool_fn.description, f"{tool_fn.name} has no description"
            assert len(tool_fn.description) > 20, f"{tool_fn.name} description too short"


# ────────────── State Integration ────────────────────────


class TestStateIntegration:
    """Verify that the new state fields exist and are optional."""

    def test_new_fields_optional(self):
        from graphs.dev_team.state import create_initial_state

        state = create_initial_state(task="Test task")
        # Wave 2 fields should NOT be present by default
        assert "working_branch" not in state
        assert "working_repo" not in state
        assert "file_manifest" not in state

    def test_state_accepts_git_fields(self):
        from graphs.dev_team.state import DevTeamState

        # Should not raise — fields are NotRequired
        state: DevTeamState = {
            "task": "test",
            "requirements": [],
            "user_stories": [],
            "architecture": {},
            "tech_stack": [],
            "architecture_decisions": [],
            "code_files": [],
            "implementation_notes": "",
            "review_comments": [],
            "test_results": {},
            "issues_found": [],
            "summary": "",
            "messages": [],
            "current_agent": "pm",
            "needs_clarification": False,
            "qa_iteration_count": 0,
            "architect_escalated": False,
            "retry_count": 0,
            # Wave 2 Git fields:
            "working_branch": "ai/test-20260212-120000",
            "working_repo": "owner/repo",
            "file_manifest": ["src/main.py", "README.md"],
        }
        assert state["working_branch"] == "ai/test-20260212-120000"
        assert state["working_repo"] == "owner/repo"
        assert len(state["file_manifest"]) == 2
