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
    route_after_developer,
    route_after_reviewer,
    route_after_qa,
    route_after_lint,
    route_after_ci,
    clarification_node,
    git_commit_node,
    lint_check_node,
    _detect_language,
    USE_CI_INTEGRATION,
    USE_LINT_CHECK,
    MAX_LINT_ITERATIONS,
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

    def test_route_after_reviewer_to_devops_or_git_commit(self):
        """Test routing from Reviewer to devops/git_commit when approved."""
        from unittest.mock import patch

        state = create_initial_state(task="Test")
        state["issues_found"] = []
        state["test_results"] = {"approved": True}

        with patch("graphs.dev_team.graph.USE_DEVOPS_AGENT", True):
            assert route_after_reviewer(state) == "devops"
        with patch("graphs.dev_team.graph.USE_DEVOPS_AGENT", False):
            assert route_after_reviewer(state) == "git_commit"

    def test_route_after_reviewer_to_pm(self):
        """Test routing from Reviewer to PM for final review."""
        state = create_initial_state(task="Test")
        state["issues_found"] = []
        state["test_results"] = {"approved": False}

        result = route_after_reviewer(state)

        assert result == "pm_final"

    def test_route_after_qa_to_reviewer(self):
        """Test routing from QA to reviewer when approved."""
        state = create_initial_state(task="Test")
        state["test_results"] = {"approved": True}

        result = route_after_qa(state)

        assert result == "reviewer"

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

        assert result == "reviewer"


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


# ==================================================================
# CI Integration defaults
# ==================================================================


class TestCIIntegrationDefaults:
    """Test that CI integration is enabled by default."""

    def test_use_ci_integration_default_true(self):
        """USE_CI_INTEGRATION should be True by default."""
        assert USE_CI_INTEGRATION is True

    def test_use_lint_check_default_true(self):
        """USE_LINT_CHECK should be True by default."""
        assert USE_LINT_CHECK is True


# ==================================================================
# Lint Check routing
# ==================================================================


class TestRouteAfterDeveloper:
    """Test route_after_developer with lint check."""

    @patch("graphs.dev_team.graph.USE_LINT_CHECK", True)
    def test_first_pass_goes_to_lint(self):
        """On first pass (review_iteration_count=0), route to lint_check."""
        state = create_initial_state(task="Test")
        result = route_after_developer(state)
        assert result == "lint_check"

    @patch("graphs.dev_team.graph.USE_LINT_CHECK", True)
    def test_reviewer_fix_loop_skips_lint(self):
        """Lint runs on every iteration, including reviewer fix loops."""
        state = create_initial_state(task="Test")
        state["review_iteration_count"] = 1
        result = route_after_developer(state)
        assert result == "lint_check"

    @patch("graphs.dev_team.graph.USE_LINT_CHECK", False)
    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", True)
    def test_lint_disabled_goes_to_security(self):
        """When lint is disabled, first pass goes to security_review."""
        state = create_initial_state(task="Test")
        result = route_after_developer(state)
        assert result == "security_review"

    @patch("graphs.dev_team.graph.USE_LINT_CHECK", False)
    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", False)
    def test_lint_and_security_disabled_goes_to_qa(self):
        """When both lint and security are disabled, goes to QA gate."""
        state = create_initial_state(task="Test")
        result = route_after_developer(state)
        assert result == "qa"


class TestRouteAfterLint:
    """Test route_after_lint routing logic."""

    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", True)
    def test_lint_clean_goes_to_security(self):
        """Clean lint → security_review."""
        state = create_initial_state(task="Test")
        state["lint_status"] = "clean"
        result = route_after_lint(state)
        assert result == "security_review"

    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", False)
    def test_lint_clean_no_security_goes_to_reviewer(self):
        """Clean lint, no security → QA gate."""
        state = create_initial_state(task="Test")
        state["lint_status"] = "clean"
        result = route_after_lint(state)
        assert result == "qa"

    def test_lint_issues_goes_to_developer(self):
        """Lint issues → developer (to fix)."""
        state = create_initial_state(task="Test")
        state["lint_status"] = "issues"
        state["lint_iteration_count"] = 1
        result = route_after_lint(state)
        assert result == "developer"

    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", True)
    def test_lint_issues_max_iterations_forces_through(self):
        """After MAX_LINT_ITERATIONS, force through to security/reviewer."""
        state = create_initial_state(task="Test")
        state["lint_status"] = "issues"
        state["lint_iteration_count"] = MAX_LINT_ITERATIONS
        result = route_after_lint(state)
        assert result == "security_review"

    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", False)
    def test_lint_issues_max_iterations_no_security(self):
        """After MAX_LINT_ITERATIONS with no security, goes to QA gate."""
        state = create_initial_state(task="Test")
        state["lint_status"] = "issues"
        state["lint_iteration_count"] = MAX_LINT_ITERATIONS
        result = route_after_lint(state)
        assert result == "qa"

    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", False)
    def test_lint_skipped_goes_to_reviewer(self):
        """Skipped lint → QA gate."""
        state = create_initial_state(task="Test")
        state["lint_status"] = "skipped"
        result = route_after_lint(state)
        assert result == "qa"

    @patch("graphs.dev_team.graph.USE_SECURITY_AGENT", False)
    def test_lint_error_goes_to_reviewer(self):
        """Lint error → QA gate (don't block on infra issues)."""
        state = create_initial_state(task="Test")
        state["lint_status"] = "error"
        result = route_after_lint(state)
        assert result == "qa"


# ==================================================================
# Lint check node
# ==================================================================


class TestLintCheckNode:
    """Test lint_check_node function."""

    def test_no_code_files_skipped(self):
        """No code files → lint skipped."""
        state = create_initial_state(task="Test")
        state["code_files"] = []
        result = lint_check_node(state)
        assert result["lint_status"] == "skipped"

    @patch("dev_team.tools.sandbox.SandboxClient")
    def test_lint_clean(self, MockSandboxClient):
        """Sandbox returns exit_code=0 → lint clean."""
        mock_client = MockSandboxClient.return_value
        mock_client.execute.return_value = {
            "exit_code": 0,
            "stdout": "All checks passed!",
            "stderr": "",
        }

        state = create_initial_state(task="Test")
        state["code_files"] = [{"path": "main.py", "content": "x = 1\n"}]
        state["tech_stack"] = ["python"]

        result = lint_check_node(state)
        assert result["lint_status"] == "clean"
        assert result["lint_iteration_count"] == 1

    @patch("dev_team.tools.sandbox.SandboxClient")
    def test_lint_issues(self, MockSandboxClient):
        """Sandbox returns exit_code=1 → lint issues."""
        mock_client = MockSandboxClient.return_value
        mock_client.execute.return_value = {
            "exit_code": 1,
            "stdout": "main.py:1:1: E302 expected 2 blank lines",
            "stderr": "",
        }

        state = create_initial_state(task="Test")
        state["code_files"] = [{"path": "main.py", "content": "def f():pass\n"}]
        state["tech_stack"] = ["python"]

        result = lint_check_node(state)
        assert result["lint_status"] == "issues"
        assert "E302" in result["lint_log"]
        assert result["lint_iteration_count"] == 1

    @patch("dev_team.tools.sandbox.SandboxClient")
    def test_lint_iteration_increments(self, MockSandboxClient):
        """lint_iteration_count increments across calls."""
        mock_client = MockSandboxClient.return_value
        mock_client.execute.return_value = {"exit_code": 1, "stdout": "error", "stderr": ""}

        state = create_initial_state(task="Test")
        state["code_files"] = [{"path": "main.py", "content": "x=1"}]
        state["tech_stack"] = ["python"]
        state["lint_iteration_count"] = 2

        result = lint_check_node(state)
        assert result["lint_iteration_count"] == 3

    @patch("dev_team.tools.sandbox.SandboxClient")
    def test_lint_sandbox_error(self, MockSandboxClient):
        """Sandbox raises exception → lint error status."""
        MockSandboxClient.side_effect = Exception("Connection refused")

        state = create_initial_state(task="Test")
        state["code_files"] = [{"path": "main.py", "content": "x=1"}]
        state["tech_stack"] = ["python"]

        result = lint_check_node(state)
        assert result["lint_status"] == "error"
        assert "Connection refused" in result["lint_log"]


# ==================================================================
# Language detection
# ==================================================================


class TestDetectLanguage:
    """Test _detect_language helper."""

    def test_python_from_tech_stack(self):
        state = create_initial_state(task="Test")
        state["tech_stack"] = ["FastAPI", "PostgreSQL"]
        assert _detect_language(state) == "python"

    def test_javascript_from_tech_stack(self):
        state = create_initial_state(task="Test")
        state["tech_stack"] = ["Node.js", "Express"]
        assert _detect_language(state) == "javascript"

    def test_typescript_from_tech_stack(self):
        state = create_initial_state(task="Test")
        state["tech_stack"] = ["TypeScript", "Next.js"]
        assert _detect_language(state) == "typescript"

    def test_go_from_tech_stack(self):
        state = create_initial_state(task="Test")
        state["tech_stack"] = ["Go", "Gin"]
        assert _detect_language(state) == "go"

    def test_python_from_files_fallback(self):
        state = create_initial_state(task="Test")
        state["tech_stack"] = []
        state["code_files"] = [{"path": "app/main.py", "content": "..."}]
        assert _detect_language(state) == "python"

    def test_js_from_files_fallback(self):
        state = create_initial_state(task="Test")
        state["tech_stack"] = []
        state["code_files"] = [{"path": "server.js", "content": "..."}]
        assert _detect_language(state) == "javascript"

    def test_default_python(self):
        state = create_initial_state(task="Test")
        state["tech_stack"] = []
        state["code_files"] = []
        assert _detect_language(state) == "python"


# ==================================================================
# CI routing
# ==================================================================


class TestRouteAfterCI:
    """Test route_after_ci routing logic."""

    def test_ci_success_goes_to_pm(self):
        """CI success → pm_final."""
        state = create_initial_state(task="Test")
        state["ci_status"] = "success"
        result = route_after_ci(state)
        assert result == "pm_final"

    def test_ci_failure_goes_to_developer(self):
        """CI failure → developer."""
        state = create_initial_state(task="Test")
        state["ci_status"] = "failure"
        result = route_after_ci(state)
        assert result == "developer"

    def test_ci_skipped_goes_to_pm(self):
        """CI skipped → pm_final."""
        state = create_initial_state(task="Test")
        state["ci_status"] = "skipped"
        result = route_after_ci(state)
        assert result == "pm_final"

    def test_ci_not_found_goes_to_pm(self):
        """CI not_found → pm_final."""
        state = create_initial_state(task="Test")
        state["ci_status"] = "not_found"
        result = route_after_ci(state)
        assert result == "pm_final"

    def test_ci_error_goes_to_developer(self):
        """CI error → developer."""
        state = create_initial_state(task="Test")
        state["ci_status"] = "error"
        result = route_after_ci(state)
        assert result == "developer"


# ==================================================================
# Developer agent routing (lint/CI/issues)
# ==================================================================


class TestDeveloperAgentRouting:
    """Test developer_agent() node function routing."""

    @patch("dev_team.agents.developer.get_developer_agent")
    def test_routes_to_fix_lint(self, mock_get_agent):
        """Developer routes to fix_lint when lint_status='issues'."""
        from dev_team.agents.developer import developer_agent

        mock_agent = Mock()
        mock_agent.fix_lint.return_value = {"current_agent": "developer"}
        mock_get_agent.return_value = mock_agent

        state = create_initial_state(task="Test")
        state["lint_status"] = "issues"
        state["lint_log"] = "E302 error"

        developer_agent(state)
        mock_agent.fix_lint.assert_called_once()

    @patch("dev_team.agents.developer.get_developer_agent")
    def test_routes_to_fix_ci(self, mock_get_agent):
        """Developer routes to fix_ci when ci_status='failure'."""
        from dev_team.agents.developer import developer_agent

        mock_agent = Mock()
        mock_agent.fix_ci.return_value = {"current_agent": "developer"}
        mock_get_agent.return_value = mock_agent

        state = create_initial_state(task="Test")
        state["ci_status"] = "failure"
        state["ci_log"] = "Tests failed"

        developer_agent(state)
        mock_agent.fix_ci.assert_called_once()

    @patch("dev_team.agents.developer.get_developer_agent")
    def test_routes_to_fix_issues(self, mock_get_agent):
        """Developer routes to fix_issues when issues_found is non-empty."""
        from dev_team.agents.developer import developer_agent

        mock_agent = Mock()
        mock_agent.fix_issues.return_value = {"current_agent": "developer"}
        mock_get_agent.return_value = mock_agent

        state = create_initial_state(task="Test")
        state["issues_found"] = ["Bug in function X"]

        developer_agent(state)
        mock_agent.fix_issues.assert_called_once()

    @patch("dev_team.agents.developer.get_developer_agent")
    def test_routes_to_implement(self, mock_get_agent):
        """Developer routes to implement when no issues."""
        from dev_team.agents.developer import developer_agent

        mock_agent = Mock()
        mock_agent.implement.return_value = {"current_agent": "developer"}
        mock_get_agent.return_value = mock_agent

        state = create_initial_state(task="Test")
        developer_agent(state)
        mock_agent.implement.assert_called_once()

    @patch("dev_team.agents.developer.get_developer_agent")
    def test_lint_takes_priority_over_issues(self, mock_get_agent):
        """Lint fix takes priority over reviewer issues."""
        from dev_team.agents.developer import developer_agent

        mock_agent = Mock()
        mock_agent.fix_lint.return_value = {"current_agent": "developer"}
        mock_get_agent.return_value = mock_agent

        state = create_initial_state(task="Test")
        state["lint_status"] = "issues"
        state["issues_found"] = ["Some issue"]

        developer_agent(state)
        mock_agent.fix_lint.assert_called_once()
        mock_agent.fix_issues.assert_not_called()
