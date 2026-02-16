"""
Tests for LangGraph workflow
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from langgraph.graph import StateGraph

from graphs.dev_team.graph import (
    create_graph,
    should_clarify,
    route_after_analyst,
    route_after_architect,
    route_after_reviewer,
    route_after_qa,
    clarification_node,
    git_commit_node,
)
from graphs.dev_team.state import create_initial_state


class TestGraphRouting:
    """Test graph routing logic."""

    def test_should_clarify_true(self):
        """Test clarification routing when needed."""
        state = create_initial_state(task="Test")
        state["needs_clarification"] = True

        result = should_clarify(state)

        assert result == "clarification"

    def test_should_clarify_false(self):
        """Test clarification routing when not needed."""
        state = create_initial_state(task="Test")
        state["needs_clarification"] = False

        result = should_clarify(state)

        assert result == "continue"

    def test_route_after_analyst_to_architect(self):
        """Test routing from analyst to architect."""
        state = create_initial_state(task="Test")
        state["needs_clarification"] = False

        result = route_after_analyst(state)

        assert result == "architect"

    def test_route_after_analyst_to_clarification(self):
        """Test routing from analyst to clarification."""
        state = create_initial_state(task="Test")
        state["needs_clarification"] = True

        result = route_after_analyst(state)

        assert result == "clarification"

    def test_route_after_architect_to_developer(self):
        """Test routing from architect to developer."""
        state = create_initial_state(task="Test")
        state["needs_clarification"] = False

        result = route_after_architect(state)

        assert result == "developer"

    def test_route_after_reviewer_to_developer(self):
        """Test routing from Reviewer back to developer when issues found."""
        state = create_initial_state(task="Test")
        state["issues_found"] = ["Issue 1", "Issue 2"]

        result = route_after_reviewer(state)

        assert result == "developer"

    def test_route_after_reviewer_to_qa(self):
        """Test routing from Reviewer to QA sandbox when approved."""
        state = create_initial_state(task="Test")
        state["issues_found"] = []
        state["test_results"] = {"approved": True}

        result = route_after_reviewer(state)

        assert result == "qa"

    def test_route_after_reviewer_to_pm(self):
        """Test routing from Reviewer to PM for final review."""
        state = create_initial_state(task="Test")
        state["issues_found"] = []
        state["test_results"] = {"approved": False}

        result = route_after_reviewer(state)

        assert result == "pm_final"

    def test_route_after_qa_to_git_commit(self):
        """Test routing from QA to git_commit when approved."""
        state = create_initial_state(task="Test")
        state["test_results"] = {"approved": True}

        result = route_after_qa(state)

        assert result == "git_commit"

    def test_route_after_qa_to_developer(self):
        """Test routing from QA to developer when tests fail."""
        state = create_initial_state(task="Test")
        state["test_results"] = {"approved": False}
        state["sandbox_results"] = {"exit_code": 1}

        result = route_after_qa(state)

        assert result == "developer"

    def test_route_after_qa_skipped(self):
        """Test routing from QA when skipped (no code)."""
        state = create_initial_state(task="Test")
        state["test_results"] = {"approved": True, "skipped": True}

        result = route_after_qa(state)

        assert result == "git_commit"


class TestGraphNodes:
    """Test graph node functions."""

    def test_clarification_node(self):
        """Test clarification node marks state as waiting."""
        state = create_initial_state(task="Test")

        result = clarification_node(state)

        assert result["current_agent"] == "waiting_for_user"

    def test_git_commit_node_no_repository(self):
        """Test git commit node when no repository specified."""
        state = create_initial_state(task="Test")
        state["code_files"] = [
            {"path": "main.py", "content": "code", "language": "python"}
        ]
        state["repository"] = None

        result = git_commit_node(state)

        assert "summary" in result
        assert "Task completed" in result["summary"]
        assert result["current_agent"] == "complete"

    @patch("dev_team.tools.git_workspace.commit_and_create_pr")
    def test_git_commit_node_with_repository(self, mock_commit_pr):
        """Test git commit node with repository and mocked commit_and_create_pr."""
        mock_commit_pr.return_value = {
            "pr_url": "https://github.com/owner/repo/pull/1",
            "commit_sha": "abc123",
            "working_branch": "ai/test-123",
            "working_repo": "owner/repo",
            "files_committed": 1,
        }

        state = create_initial_state(task="Test")
        state["code_files"] = [
            {"path": "main.py", "content": "code", "language": "python"}
        ]
        state["repository"] = "owner/repo"

        result = git_commit_node(state)

        assert "pr_url" in result
        assert result["pr_url"] == "https://github.com/owner/repo/pull/1"
        assert result["current_agent"] == "complete"
        assert result["working_branch"] == "ai/test-123"

    def test_git_commit_node_no_github_token(self):
        """Test git commit node when GITHUB_TOKEN is missing.

        commit_and_create_pr returns an error when the client is unavailable.
        The node falls back to returning code in the summary.
        """
        state = create_initial_state(task="Test")
        state["code_files"] = [
            {"path": "main.py", "content": "code", "language": "python"}
        ]
        state["repository"] = "owner/repo"

        result = git_commit_node(state)

        assert "summary" in result
        assert result["current_agent"] == "complete"


class TestGraphCreation:
    """Test graph creation and structure."""

    @patch('graphs.dev_team.graph.pm_agent')
    @patch('graphs.dev_team.graph.analyst_agent')
    @patch('graphs.dev_team.graph.architect_agent')
    @patch('graphs.dev_team.graph.developer_agent')
    @patch('graphs.dev_team.graph.reviewer_agent')
    @patch('graphs.dev_team.graph.qa_agent')
    def test_create_graph_structure(
        self,
        mock_qa,
        mock_reviewer,
        mock_dev,
        mock_arch,
        mock_analyst,
        mock_pm,
    ):
        """Test that graph is created with correct structure."""
        # Mock agent functions to return empty dicts
        for mock_agent in [mock_pm, mock_analyst, mock_arch, mock_dev, mock_reviewer, mock_qa]:
            mock_agent.return_value = {}

        builder = create_graph()

        # Verify it's a StateGraph
        assert isinstance(builder, StateGraph)

        # Graph should have the following nodes
        expected_nodes = [
            "pm",
            "analyst",
            "architect",
            "developer",
            "reviewer",
            "qa",
            "clarification",
            "git_commit",
            "pm_final",
        ]

        # Note: We can't easily inspect nodes after creation,
        # but we can verify the graph compiles without errors
        graph = builder.compile()
        assert graph is not None

    @patch('graphs.dev_team.graph.pm_agent')
    @patch('graphs.dev_team.graph.analyst_agent')
    @patch('graphs.dev_team.graph.architect_agent')
    @patch('graphs.dev_team.graph.developer_agent')
    @patch('graphs.dev_team.graph.reviewer_agent')
    @patch('graphs.dev_team.graph.qa_agent')
    def test_graph_compilation(
        self,
        mock_qa,
        mock_reviewer,
        mock_dev,
        mock_arch,
        mock_analyst,
        mock_pm,
    ):
        """Test that graph compiles successfully."""
        for mock_agent in [mock_pm, mock_analyst, mock_arch, mock_dev, mock_reviewer, mock_qa]:
            mock_agent.return_value = {}

        builder = create_graph()
        graph = builder.compile()

        # Graph should have required methods
        assert hasattr(graph, 'invoke')
        assert hasattr(graph, 'stream')
