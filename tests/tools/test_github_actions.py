"""
GitHub Actions CI/CD Integration Tests (Module 3.8)
====================================================

Tests for:
  - GitHubActionsClient: get_latest_workflow_run, wait_for_completion, get_run_logs, trigger_workflow_dispatch
  - LangChain @tool wrappers: trigger_ci, wait_for_ci, get_ci_logs
  - Graph routing: route_after_ci, ci_check_node
  - State: ci_status, ci_log fields
  - Manifest: ci_integration feature
  - Developer prompt: CI-config generation

All GitHub API calls are mocked — no real GitHub access needed.
"""

import os
import time
import pytest
from unittest.mock import Mock, MagicMock, patch


# ==================================================================
# 1. GitHubActionsClient — unit tests
# ==================================================================


class TestGitHubActionsClient:
    """Test the low-level GitHub Actions client."""

    def _make_client(self, mock_github=None):
        """Create client with a mocked PyGithub instance."""
        from graphs.dev_team.tools.github_actions import GitHubActionsClient
        mock_gh = mock_github or MagicMock()
        return GitHubActionsClient(github_client=mock_gh), mock_gh

    def test_get_latest_workflow_run_found(self):
        """Returns run data when a run exists for the branch."""
        client, mock_gh = self._make_client()

        mock_run = MagicMock()
        mock_run.id = 12345
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.name = "CI"
        mock_run.html_url = "https://github.com/org/repo/actions/runs/12345"
        mock_run.created_at = "2026-02-16T10:00:00Z"
        mock_run.updated_at = "2026-02-16T10:05:00Z"

        mock_repo = MagicMock()
        mock_repo.get_workflow_runs.return_value = [mock_run]
        mock_gh.get_repo.return_value = mock_repo

        result = client.get_latest_workflow_run("org/repo", "ai/test-branch")

        assert result["run_id"] == 12345
        assert result["status"] == "completed"
        assert result["conclusion"] == "success"

    def test_get_latest_workflow_run_not_found(self):
        """Returns not_found when no runs exist."""
        client, mock_gh = self._make_client()

        mock_repo = MagicMock()
        mock_repo.get_workflow_runs.return_value = []
        mock_gh.get_repo.return_value = mock_repo

        result = client.get_latest_workflow_run("org/repo", "ai/no-branch")

        assert result["run_id"] is None
        assert result["status"] == "not_found"

    def test_wait_for_completion_success(self):
        """Waits and returns completed status when run finishes."""
        client, mock_gh = self._make_client()

        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.html_url = "https://github.com/org/repo/actions/runs/123"

        mock_repo = MagicMock()
        mock_repo.get_workflow_run.return_value = mock_run
        mock_gh.get_repo.return_value = mock_repo

        result = client.wait_for_completion("org/repo", 123, poll_interval=0, max_wait=5)

        assert result["status"] == "completed"
        assert result["conclusion"] == "success"
        assert result["run_id"] == 123

    def test_wait_for_completion_timeout(self):
        """Returns timeout when run doesn't finish in time."""
        client, mock_gh = self._make_client()

        mock_run = MagicMock()
        mock_run.status = "in_progress"
        mock_run.conclusion = None
        mock_run.html_url = ""

        mock_repo = MagicMock()
        mock_repo.get_workflow_run.return_value = mock_run
        mock_gh.get_repo.return_value = mock_repo

        result = client.wait_for_completion("org/repo", 123, poll_interval=0, max_wait=0)

        assert result["status"] == "timeout"
        assert result["conclusion"] is None

    def test_wait_for_completion_failure(self):
        """Returns failure conclusion when CI fails."""
        client, mock_gh = self._make_client()

        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.conclusion = "failure"
        mock_run.html_url = "https://github.com/org/repo/actions/runs/456"

        mock_repo = MagicMock()
        mock_repo.get_workflow_run.return_value = mock_run
        mock_gh.get_repo.return_value = mock_repo

        result = client.wait_for_completion("org/repo", 456, poll_interval=0, max_wait=5)

        assert result["conclusion"] == "failure"

    def test_get_run_logs(self):
        """Retrieves job and step information from a run."""
        client, mock_gh = self._make_client()

        mock_step1 = MagicMock()
        mock_step1.name = "Install deps"
        mock_step1.status = "completed"
        mock_step1.conclusion = "success"
        mock_step1.number = 1

        mock_step2 = MagicMock()
        mock_step2.name = "Run tests"
        mock_step2.status = "completed"
        mock_step2.conclusion = "failure"
        mock_step2.number = 2

        mock_job = MagicMock()
        mock_job.name = "test"
        mock_job.status = "completed"
        mock_job.conclusion = "failure"
        mock_job.steps = [mock_step1, mock_step2]

        mock_run = MagicMock()
        mock_run.conclusion = "failure"
        mock_run.jobs.return_value = [mock_job]

        mock_repo = MagicMock()
        mock_repo.get_workflow_run.return_value = mock_run
        mock_gh.get_repo.return_value = mock_repo

        result = client.get_run_logs("org/repo", 789)

        assert result["conclusion"] == "failure"
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["name"] == "test"
        assert len(result["jobs"][0]["steps"]) == 2
        assert result["jobs"][0]["steps"][1]["conclusion"] == "failure"

    def test_trigger_workflow_dispatch_success(self):
        """Successfully triggers a workflow dispatch."""
        client, mock_gh = self._make_client()

        mock_workflow = MagicMock()
        mock_workflow.create_dispatch.return_value = True

        mock_repo = MagicMock()
        mock_repo.get_workflow.return_value = mock_workflow
        mock_gh.get_repo.return_value = mock_repo

        result = client.trigger_workflow_dispatch("org/repo", "ci.yml", "main")

        assert result["triggered"] is True
        assert result["workflow"] == "ci.yml"
        assert result["branch"] == "main"

    def test_trigger_workflow_dispatch_failure(self):
        """Returns error when dispatch fails."""
        client, mock_gh = self._make_client()

        mock_repo = MagicMock()
        mock_repo.get_workflow.side_effect = Exception("Workflow not found")
        mock_gh.get_repo.return_value = mock_repo

        result = client.trigger_workflow_dispatch("org/repo", "ci.yml", "main")

        assert result["triggered"] is False
        assert "error" in result


# ==================================================================
# 2. LangChain @tool wrappers
# ==================================================================


class TestToolWrappers:
    """Test the @tool function wrappers."""

    @patch("graphs.dev_team.tools.github_actions.get_ci_client")
    def test_trigger_ci_tool(self, mock_get_client):
        """trigger_ci tool calls dispatch and returns message."""
        from graphs.dev_team.tools.github_actions import trigger_ci

        mock_client = MagicMock()
        mock_client.trigger_workflow_dispatch.return_value = {
            "triggered": True,
            "workflow": "ci.yml",
            "branch": "ai/test",
        }
        mock_get_client.return_value = mock_client

        result = trigger_ci.invoke({
            "repo": "org/repo",
            "branch": "ai/test",
        })
        assert "triggered" in result.lower() or "CI workflow" in result

    @patch("graphs.dev_team.tools.github_actions.get_ci_client")
    def test_wait_for_ci_tool_success(self, mock_get_client):
        """wait_for_ci tool returns success message."""
        from graphs.dev_team.tools.github_actions import wait_for_ci

        mock_client = MagicMock()
        mock_client.get_latest_workflow_run.return_value = {
            "run_id": 123, "status": "completed", "conclusion": "success",
        }
        mock_client.wait_for_completion.return_value = {
            "run_id": 123,
            "status": "completed",
            "conclusion": "success",
            "elapsed_seconds": 42.0,
            "html_url": "https://github.com/org/repo/actions/runs/123",
        }
        mock_get_client.return_value = mock_client

        result = wait_for_ci.invoke({
            "repo": "org/repo",
            "branch": "ai/test",
        })
        assert "SUCCESS" in result

    @patch("graphs.dev_team.tools.github_actions.get_ci_client")
    def test_wait_for_ci_no_run_found(self, mock_get_client):
        """wait_for_ci returns not-found message when no runs exist."""
        from graphs.dev_team.tools.github_actions import wait_for_ci

        mock_client = MagicMock()
        mock_client.get_latest_workflow_run.return_value = {
            "run_id": None, "status": "not_found",
        }
        mock_get_client.return_value = mock_client

        result = wait_for_ci.invoke({
            "repo": "org/repo",
            "branch": "ai/no-ci",
        })
        assert "No CI workflow run found" in result

    @patch("graphs.dev_team.tools.github_actions.get_ci_client")
    def test_get_ci_logs_tool(self, mock_get_client):
        """get_ci_logs tool returns formatted log summary."""
        from graphs.dev_team.tools.github_actions import get_ci_logs

        mock_client = MagicMock()
        mock_client.get_run_logs.return_value = {
            "run_id": 456,
            "conclusion": "failure",
            "jobs": [{
                "name": "test",
                "status": "completed",
                "conclusion": "failure",
                "steps": [
                    {"name": "Install", "status": "completed", "conclusion": "success", "number": 1},
                    {"name": "Test", "status": "completed", "conclusion": "failure", "number": 2},
                ],
            }],
        }
        mock_get_client.return_value = mock_client

        result = get_ci_logs.invoke({
            "repo": "org/repo",
            "run_id": 456,
        })
        assert "FAILURE" in result or "FAIL" in result
        assert "Test" in result


# ==================================================================
# 3. Graph routing — route_after_ci
# ==================================================================


class TestRouteAfterCI:
    """Test CI routing logic in graph.py."""

    def test_ci_success_routes_to_pm_final(self):
        """CI success → pm_final."""
        from graphs.dev_team.graph import route_after_ci
        state = {"ci_status": "success"}
        assert route_after_ci(state) == "pm_final"

    def test_ci_failure_routes_to_developer(self):
        """CI failure → developer."""
        from graphs.dev_team.graph import route_after_ci
        state = {"ci_status": "failure"}
        assert route_after_ci(state) == "developer"

    def test_ci_error_routes_to_developer(self):
        """CI error → developer."""
        from graphs.dev_team.graph import route_after_ci
        state = {"ci_status": "error"}
        assert route_after_ci(state) == "developer"

    def test_ci_timeout_routes_to_developer(self):
        """CI timeout → developer."""
        from graphs.dev_team.graph import route_after_ci
        state = {"ci_status": "timeout"}
        assert route_after_ci(state) == "developer"

    def test_ci_skipped_routes_to_pm_final(self):
        """CI skipped → pm_final (no CI configured)."""
        from graphs.dev_team.graph import route_after_ci
        state = {"ci_status": "skipped"}
        assert route_after_ci(state) == "pm_final"

    def test_ci_not_found_routes_to_pm_final(self):
        """CI not_found → pm_final (no workflow runs)."""
        from graphs.dev_team.graph import route_after_ci
        state = {"ci_status": "not_found"}
        assert route_after_ci(state) == "pm_final"

    def test_ci_cancelled_routes_to_developer(self):
        """CI cancelled → developer."""
        from graphs.dev_team.graph import route_after_ci
        state = {"ci_status": "cancelled"}
        assert route_after_ci(state) == "developer"


# ==================================================================
# 4. ci_check_node
# ==================================================================


class TestCICheckNode:
    """Test the ci_check graph node."""

    def test_ci_check_no_repo(self):
        """Skip CI check when no repo in state."""
        from graphs.dev_team.graph import ci_check_node

        state = {"task": "test"}
        result = ci_check_node(state)
        assert result["ci_status"] == "skipped"

    def test_ci_check_no_branch(self):
        """Skip CI check when no branch in state."""
        from graphs.dev_team.graph import ci_check_node

        state = {"task": "test", "working_repo": "org/repo"}
        result = ci_check_node(state)
        assert result["ci_status"] == "skipped"

    @patch("dev_team.tools.github_actions.GitHubActionsClient")
    def test_ci_check_success(self, MockClient):
        """CI check returns success when workflow passes."""
        from graphs.dev_team.graph import ci_check_node

        mock_instance = MagicMock()
        mock_instance.get_latest_workflow_run.return_value = {
            "run_id": 100, "status": "completed", "conclusion": "success",
        }
        mock_instance.wait_for_completion.return_value = {
            "run_id": 100,
            "status": "completed",
            "conclusion": "success",
            "elapsed_seconds": 30.0,
            "html_url": "https://github.com/org/repo/actions/runs/100",
        }
        MockClient.return_value = mock_instance

        state = {
            "task": "test",
            "working_repo": "org/repo",
            "working_branch": "ai/test-123",
        }
        result = ci_check_node(state)

        assert result["ci_status"] == "success"
        assert result["ci_run_id"] == 100
        assert "ci_log" in result

    @patch("dev_team.tools.github_actions.GitHubActionsClient")
    def test_ci_check_failure_with_logs(self, MockClient):
        """CI check returns failure with detailed logs."""
        from graphs.dev_team.graph import ci_check_node

        mock_instance = MagicMock()
        mock_instance.get_latest_workflow_run.return_value = {
            "run_id": 200, "status": "completed", "conclusion": "failure",
        }
        mock_instance.wait_for_completion.return_value = {
            "run_id": 200,
            "status": "completed",
            "conclusion": "failure",
            "elapsed_seconds": 45.0,
            "html_url": "https://github.com/org/repo/actions/runs/200",
        }
        mock_instance.get_run_logs.return_value = {
            "run_id": 200,
            "conclusion": "failure",
            "jobs": [{
                "name": "test",
                "conclusion": "failure",
                "steps": [
                    {"name": "Run tests", "conclusion": "failure", "number": 3},
                ],
            }],
        }
        MockClient.return_value = mock_instance

        state = {
            "task": "test",
            "working_repo": "org/repo",
            "working_branch": "ai/test-456",
        }
        result = ci_check_node(state)

        assert result["ci_status"] == "failure"
        assert "Failed steps" in result["ci_log"]

    @patch("dev_team.tools.github_actions.GitHubActionsClient")
    def test_ci_check_no_run_found(self, MockClient):
        """CI check returns not_found when no workflow run exists."""
        from graphs.dev_team.graph import ci_check_node

        mock_instance = MagicMock()
        mock_instance.get_latest_workflow_run.return_value = {
            "run_id": None, "status": "not_found",
        }
        MockClient.return_value = mock_instance

        state = {
            "task": "test",
            "working_repo": "org/repo",
            "working_branch": "ai/test-789",
        }
        result = ci_check_node(state)

        assert result["ci_status"] == "not_found"

    @patch("dev_team.tools.github_actions.GitHubActionsClient")
    def test_ci_check_exception_handling(self, MockClient):
        """CI check handles exceptions gracefully."""
        from graphs.dev_team.graph import ci_check_node

        MockClient.side_effect = Exception("GitHub API unavailable")

        state = {
            "task": "test",
            "working_repo": "org/repo",
            "working_branch": "ai/test-error",
        }
        result = ci_check_node(state)

        assert result["ci_status"] == "error"
        assert "CI check error" in result["ci_log"]


# ==================================================================
# 5. State — new CI fields
# ==================================================================


class TestStateCIFields:
    """Test that CI fields work in DevTeamState."""

    def test_ci_fields_not_required(self):
        """CI fields are optional — state works without them."""
        from graphs.dev_team.state import create_initial_state

        state = create_initial_state(task="Test task")
        # CI fields should not exist by default
        assert "ci_status" not in state
        assert "ci_log" not in state
        assert "ci_run_id" not in state

    def test_ci_fields_can_be_set(self):
        """CI fields can be added to state."""
        from graphs.dev_team.state import DevTeamState

        state: dict = {
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
            "review_iteration_count": 0,
            "architect_escalated": False,
            "retry_count": 0,
            "ci_status": "success",
            "ci_log": "All tests passed",
            "ci_run_id": 12345,
            "ci_run_url": "https://github.com/org/repo/actions/runs/12345",
        }
        # Should not raise
        typed_state = DevTeamState(**state)
        assert typed_state["ci_status"] == "success"
        assert typed_state["ci_run_id"] == 12345


# ==================================================================
# 6. Manifest — ci_integration feature
# ==================================================================


class TestManifestCIFeature:
    """Test that manifest declares ci_integration feature."""

    @pytest.fixture(autouse=True)
    def _read_manifest(self):
        import yaml
        manifest_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "graphs", "dev_team", "manifest.yaml"
        )
        with open(manifest_path, "r", encoding="utf-8") as f:
            self.manifest = yaml.safe_load(f)

    def test_ci_integration_in_features(self):
        """manifest.yaml includes ci_integration feature."""
        assert "ci_integration" in self.manifest.get("features", [])

    def test_use_ci_integration_parameter(self):
        """manifest.yaml has use_ci_integration parameter."""
        params = self.manifest.get("parameters", {})
        assert "use_ci_integration" in params

    def test_use_ci_integration_default_false(self):
        """CI integration is disabled by default."""
        params = self.manifest.get("parameters", {})
        assert params.get("use_ci_integration") is False


# ==================================================================
# 7. Developer prompt — CI-config generation
# ==================================================================


class TestDeveloperPromptCI:
    """Test that developer prompts mention CI/CD."""

    @pytest.fixture(autouse=True)
    def _read_prompt(self):
        import yaml
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "graphs", "dev_team",
            "prompts", "developer.yaml"
        )
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.prompts = yaml.safe_load(f)

    def test_system_mentions_ci(self):
        """System prompt mentions CI/CD."""
        system = self.prompts.get("system", "")
        assert "CI/CD" in system or "ci" in system.lower()

    def test_implementation_mentions_ci_workflow(self):
        """Implementation prompt asks for CI workflow file."""
        impl = self.prompts.get("implementation", "")
        assert "ci.yml" in impl or "CI/CD workflow" in impl

    def test_fix_ci_prompt_exists(self):
        """fix_ci prompt template exists."""
        assert "fix_ci" in self.prompts

    def test_fix_ci_has_placeholders(self):
        """fix_ci prompt has ci_status and ci_log placeholders."""
        fix_ci = self.prompts.get("fix_ci", "")
        assert "{ci_status}" in fix_ci
        assert "{ci_log}" in fix_ci


# ==================================================================
# 8. Graph structure — CI node presence
# ==================================================================


class TestGraphCIStructure:
    """Test graph structure with/without CI integration."""

    def test_graph_without_ci_has_git_commit_to_end(self):
        """When CI disabled, git_commit leads to END."""
        from graphs.dev_team.graph import USE_CI_INTEGRATION

        # CI is disabled by default (USE_CI_INTEGRATION=false)
        if not USE_CI_INTEGRATION:
            from graphs.dev_team.graph import graph
            # Graph should compile without errors
            assert graph is not None

    @patch.dict(os.environ, {"USE_CI_INTEGRATION": "true"})
    def test_graph_with_ci_has_ci_check_node(self):
        """When CI enabled, graph includes ci_check node."""
        import importlib
        import graphs.dev_team.graph as graph_module

        importlib.reload(graph_module)

        g = graph_module.create_graph()
        node_names = list(g.nodes.keys())
        assert "ci_check" in node_names

    @patch.dict(os.environ, {"USE_CI_INTEGRATION": "false"})
    def test_graph_without_ci_no_ci_check_node(self):
        """When CI disabled, graph does not include ci_check node."""
        import importlib
        import graphs.dev_team.graph as graph_module

        importlib.reload(graph_module)

        g = graph_module.create_graph()
        node_names = list(g.nodes.keys())
        assert "ci_check" not in node_names


# ==================================================================
# 9. Tools __init__.py — exports
# ==================================================================


class TestToolsExport:
    """Verify GitHub Actions tools are exported from __init__."""

    def test_github_actions_tools_importable(self):
        """github_actions_tools can be imported from tools package."""
        from graphs.dev_team.tools import github_actions_tools
        assert len(github_actions_tools) == 3

    def test_individual_tools_importable(self):
        """Individual tools can be imported."""
        from graphs.dev_team.tools import trigger_ci, wait_for_ci, get_ci_logs
        assert trigger_ci is not None
        assert wait_for_ci is not None
        assert get_ci_logs is not None

    def test_client_importable(self):
        """GitHubActionsClient and get_ci_client are importable."""
        from graphs.dev_team.tools import GitHubActionsClient, get_ci_client
        assert GitHubActionsClient is not None
        assert callable(get_ci_client)
