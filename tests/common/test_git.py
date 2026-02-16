"""Tests for graphs/common/git.py — make_git_commit_node factory."""

from unittest.mock import patch, MagicMock

from common.git import make_git_commit_node


class TestMakeGitCommitNode:
    def test_factory_returns_callable(self):
        node = make_git_commit_node("test_graph")
        assert callable(node)
        assert "test_graph" in (node.__doc__ or "")

    def test_no_repository_returns_summary(self):
        node = make_git_commit_node("test")
        state = {
            "code_files": [{"path": "a.py", "language": "python", "content": "x=1"}],
            "repository": "",
            "task": "test task",
        }
        result = node(state)
        assert result["current_agent"] == "complete"
        assert "test task" in result["summary"]
        assert "pr_url" not in result

    @patch("common.git.os.getenv", return_value="")
    def test_no_env_repo_fallback(self, _mock_env):
        node = make_git_commit_node("test")
        state = {"code_files": [], "task": "task"}
        result = node(state)
        assert result["current_agent"] == "complete"

    @patch("dev_team.tools.git_workspace.commit_and_create_pr")
    def test_success_returns_pr_url(self, mock_commit):
        mock_commit.return_value = {
            "pr_url": "https://github.com/test/pull/1",
            "commit_sha": "abc123def456",
            "working_branch": "ai/test",
            "files_committed": 2,
        }
        node = make_git_commit_node("test")
        state = {
            "code_files": [{"path": "a.py", "language": "python", "content": "x"}],
            "repository": "org/repo",
            "task": "task",
        }
        result = node(state)
        assert result["pr_url"] == "https://github.com/test/pull/1"
        assert result["current_agent"] == "complete"
        assert "2 file(s)" in result["summary"]
        mock_commit.assert_called_once()

    @patch("dev_team.tools.git_workspace.commit_and_create_pr")
    def test_commit_failure_graceful(self, mock_commit):
        mock_commit.return_value = {
            "error": "Auth failed",
            "files_committed": 0,
        }
        node = make_git_commit_node("test")
        state = {
            "code_files": [{"path": "a.py", "language": "python", "content": "x"}],
            "repository": "org/repo",
            "task": "task",
        }
        result = node(state)
        assert result["current_agent"] == "complete"
        assert "Auth failed" in result.get("error", "")
        assert "Warning" in result["summary"]
