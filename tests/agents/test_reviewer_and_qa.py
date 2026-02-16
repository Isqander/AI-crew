"""
Tests for Reviewer and QA (Sandbox) Agents
===========================================

Covers:
  - ReviewerAgent: initialization, review_code, verify_fixes, final_approval
  - QAAgent: initialization, test_code, _detect_language, _build_commands,
    _parse_verdict, _parse_issues, _analyse_results
  - Node functions: reviewer_agent, qa_agent
  - Graph routing: route_after_reviewer, route_after_qa
  - Prompts loading
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest
import yaml


# ==================================================================
# 1. ReviewerAgent Tests
# ==================================================================


class TestReviewerAgent:
    """Test the ReviewerAgent class with mocked LLM."""

    @pytest.fixture
    def agent(self):
        """Create a ReviewerAgent with mocked LLM."""
        with patch("dev_team.agents.reviewer.get_llm_with_fallback") as mock_get_llm, \
             patch("dev_team.agents.reviewer.load_prompts") as mock_load_prompts:
            mock_load_prompts.return_value = {
                "system": "You are a reviewer.",
                "code_review": "Review: {task}\n{requirements}\n{code_files}",
                "verify_fixes": "Verify: {original_issues}\n{updated_code}",
                "final_approval": "Approve: {task}\n{requirements_status}\n{code_quality}\n{test_results}\n{notes}",
            }
            mock_llm = Mock()
            mock_get_llm.return_value = mock_llm
            from dev_team.agents.reviewer import ReviewerAgent
            agent = ReviewerAgent()
            agent.llm = mock_llm
            return agent

    @pytest.fixture
    def sample_state(self):
        return {
            "task": "Build REST API",
            "requirements": ["Auth", "CRUD"],
            "code_files": [
                {"path": "main.py", "content": "print('hello')", "language": "python"},
            ],
            "issues_found": [],
            "review_comments": [],
            "test_results": {},
            "review_iteration_count": 0,
            "messages": [],
            "current_agent": "developer",
            "needs_clarification": False,
        }

    def test_review_code_approved(self, agent, sample_state):
        """Reviewer approves clean code."""
        mock_response = Mock()
        mock_response.content = (
            "## Overall Assessment\n"
            "Approved: Code looks good.\n\n"
            "## Issues Found\n"
            "- None found\n\n"
            "## Suggestions\n- Consider adding docstrings\n"
        )
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.review_code(sample_state)

        assert result["current_agent"] == "reviewer"
        assert result["test_results"]["approved"] is True
        assert result["next_agent"] == "qa"
        assert len(result["issues_found"]) == 0
        assert result["review_iteration_count"] == 0

    def test_review_code_issues_found(self, agent, sample_state):
        """Reviewer finds critical issues."""
        mock_response = Mock()
        mock_response.content = (
            "## Issues Found\n"
            "### Critical\n"
            "- Critical: SQL injection vulnerability\n"
            "### Major\n"
            "- Major: No error handling\n"
        )
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.review_code(sample_state)

        assert result["next_agent"] == "developer"
        assert len(result["issues_found"]) > 0
        assert result["review_iteration_count"] == 1

    def test_review_code_no_code_files(self, agent, sample_state):
        """Review with no code files still works."""
        sample_state["code_files"] = []
        mock_response = Mock()
        mock_response.content = "No code to review. Approved."
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.review_code(sample_state)
        assert result["current_agent"] == "reviewer"

    def test_verify_fixes_all_fixed(self, agent, sample_state):
        """verify_fixes when all issues are fixed."""
        mock_response = Mock()
        mock_response.content = "All issues have been fixed. Code is clean."
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.verify_fixes(sample_state)
        assert result["next_agent"] == "qa"
        assert result["issues_found"] == []

    def test_verify_fixes_not_fixed(self, agent, sample_state):
        """verify_fixes when issues remain."""
        sample_state["issues_found"] = ["Bug X"]
        mock_response = Mock()
        mock_response.content = "Issue X is not fixed."
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.verify_fixes(sample_state)
        assert result["next_agent"] == "developer"


class TestReviewerNodeFunction:
    """Test the reviewer_agent node function."""

    @patch("dev_team.agents.reviewer.get_reviewer_agent")
    def test_node_calls_review_code(self, mock_get_agent):
        from dev_team.agents.reviewer import reviewer_agent

        mock_agent = Mock()
        mock_agent.review_code.return_value = {
            "current_agent": "reviewer",
            "issues_found": [],
            "test_results": {"approved": True},
            "messages": [],
        }
        mock_get_agent.return_value = mock_agent

        state = {"code_files": [], "task": "test"}
        result = reviewer_agent(state)

        mock_agent.review_code.assert_called_once()
        assert result["current_agent"] == "reviewer"


# ==================================================================
# 2. QAAgent Tests
# ==================================================================


class TestQAAgent:
    """Test the QAAgent class with mocked sandbox and LLM."""

    @pytest.fixture
    def mock_sandbox(self):
        """Create a mock SandboxClient."""
        sandbox = Mock()
        sandbox.execute.return_value = {
            "stdout": "3 passed, 0 failed",
            "stderr": "",
            "exit_code": 0,
            "tests_passed": True,
            "duration_seconds": 2.5,
        }
        sandbox.health.return_value = {"status": "ok", "docker_available": True}
        return sandbox

    @pytest.fixture
    def agent(self, mock_sandbox):
        """Create a QAAgent with mocked LLM and sandbox."""
        with patch("dev_team.agents.qa.get_llm_with_fallback") as mock_get_llm, \
             patch("dev_team.agents.qa.load_prompts") as mock_load_prompts:
            mock_load_prompts.return_value = {
                "system": "You are QA.",
                "analyse_sandbox": "Analyse: {task} {files} {exit_code} {stdout} {stderr} {tests_passed}",
            }
            mock_llm = Mock()
            mock_get_llm.return_value = mock_llm
            from dev_team.agents.qa import QAAgent
            agent = QAAgent(sandbox_client=mock_sandbox)
            agent.llm = mock_llm
            return agent

    @pytest.fixture
    def sample_state(self):
        return {
            "task": "Build REST API",
            "code_files": [
                {"path": "main.py", "content": "print('hello')", "language": "python"},
                {"path": "test_main.py", "content": "def test_main(): pass", "language": "python"},
            ],
            "issues_found": [],
            "test_results": {},
            "review_iteration_count": 0,
            "messages": [],
            "current_agent": "reviewer",
        }

    def test_test_code_pass(self, agent, sample_state, mock_sandbox):
        """QA passes when sandbox returns exit_code=0."""
        mock_response = Mock()
        mock_response.content = (
            "## Verdict: PASS\n\n"
            "## Summary\nAll tests passed.\n\n"
            "## Issues\n- None\n"
        )
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.test_code(sample_state)

        assert result["test_results"]["approved"] is True
        assert result["next_agent"] == "git_commit"
        assert result["sandbox_results"]["exit_code"] == 0
        assert len(result["issues_found"]) == 0
        mock_sandbox.execute.assert_called_once()

    def test_test_code_fail(self, agent, sample_state, mock_sandbox):
        """QA fails when sandbox returns non-zero exit_code."""
        mock_sandbox.execute.return_value = {
            "stdout": "1 passed, 2 failed",
            "stderr": "AssertionError: expected True",
            "exit_code": 1,
            "tests_passed": False,
            "duration_seconds": 3.0,
        }
        mock_response = Mock()
        mock_response.content = (
            "## Verdict: FAIL\n\n"
            "## Summary\n2 tests failed.\n\n"
            "## Issues\n- AssertionError in test_main.py\n"
        )
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.test_code(sample_state)

        assert result["test_results"]["approved"] is False
        assert result["next_agent"] == "developer"
        assert result["sandbox_results"]["exit_code"] == 1
        assert result["review_iteration_count"] == 1

    def test_test_code_no_files(self, agent, mock_sandbox):
        """QA skips when there are no code files."""
        state = {
            "task": "Test",
            "code_files": [],
            "review_iteration_count": 0,
            "messages": [],
        }
        result = agent.test_code(state)

        assert result["test_results"]["approved"] is True
        assert result["test_results"]["skipped"] is True
        assert result["next_agent"] == "git_commit"
        mock_sandbox.execute.assert_not_called()

    def test_sandbox_http_error(self, agent, sample_state, mock_sandbox):
        """QA handles sandbox HTTP errors gracefully."""
        mock_sandbox.execute.return_value = {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "tests_passed": None,
            "duration_seconds": 0.0,
            "error": "Sandbox HTTP error: connection refused",
        }
        mock_response = Mock()
        mock_response.content = (
            "## Verdict: FAIL\n\n"
            "## Summary\nSandbox unavailable.\n\n"
            "## Issues\n- Sandbox connection error\n"
        )
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.test_code(sample_state)

        assert result["sandbox_results"]["exit_code"] == -1
        assert result["next_agent"] == "developer"


class TestQAAgentHelpers:
    """Test QAAgent static helper methods."""

    def test_detect_language_python(self):
        from dev_team.agents.qa import QAAgent

        files = [
            {"path": "main.py", "content": "x=1", "language": "python"},
            {"path": "test.py", "content": "def t(): pass", "language": "python"},
        ]
        assert QAAgent._detect_language(files) == "python"

    def test_detect_language_javascript(self):
        from dev_team.agents.qa import QAAgent

        files = [
            {"path": "index.js", "content": "console.log(1)", "language": "javascript"},
        ]
        assert QAAgent._detect_language(files) == "javascript"

    def test_detect_language_from_extension(self):
        from dev_team.agents.qa import QAAgent

        files = [
            {"path": "main.go", "content": "package main", "language": ""},
        ]
        assert QAAgent._detect_language(files) == "go"

    def test_detect_language_default(self):
        from dev_team.agents.qa import QAAgent

        files = [{"path": "unknown", "content": "x", "language": ""}]
        assert QAAgent._detect_language(files) == "python"

    def test_build_commands_python_with_tests(self):
        from dev_team.agents.qa import QAAgent

        files = [
            {"path": "main.py", "content": "x=1"},
            {"path": "test_main.py", "content": "def test(): pass"},
        ]
        commands = QAAgent._build_commands("python", files)
        assert any("pytest" in cmd for cmd in commands)

    def test_build_commands_python_no_tests(self):
        from dev_team.agents.qa import QAAgent

        files = [{"path": "main.py", "content": "print('hi')"}]
        commands = QAAgent._build_commands("python", files)
        assert any("py_compile" in cmd for cmd in commands)

    def test_build_commands_javascript_with_package_json(self):
        from dev_team.agents.qa import QAAgent

        files = [
            {"path": "index.js", "content": "console.log(1)"},
            {"path": "test.js", "content": "test('x', () => {})"},
            {"path": "package.json", "content": '{"name": "test"}'},
        ]
        commands = QAAgent._build_commands("javascript", files)
        assert any("jest" in cmd or "vitest" in cmd for cmd in commands)

    def test_build_commands_javascript_no_package_json(self):
        """Without package.json, JS test files get node --check (syntax check)."""
        from dev_team.agents.qa import QAAgent

        files = [
            {"path": "index.js", "content": "console.log(1)"},
            {"path": "test.js", "content": "test('x', () => {})"},
        ]
        commands = QAAgent._build_commands("javascript", files)
        assert any("node --check" in cmd for cmd in commands)

    def test_build_commands_go(self):
        from dev_team.agents.qa import QAAgent

        files = [{"path": "main.go", "content": "package main"}]
        commands = QAAgent._build_commands("go", files)
        assert any("go build" in cmd for cmd in commands)

    def test_build_commands_with_requirements(self):
        from dev_team.agents.qa import QAAgent

        files = [
            {"path": "main.py", "content": "import flask"},
            {"path": "requirements.txt", "content": "flask>=2.0"},
            {"path": "test_main.py", "content": "def test(): pass"},
        ]
        commands = QAAgent._build_commands("python", files)
        assert any("pip install" in cmd for cmd in commands)

    def test_parse_verdict_pass(self):
        from dev_team.agents.qa import QAAgent

        content = "## Verdict: PASS\nAll good."
        assert QAAgent._parse_verdict(content, 0) is True

    def test_parse_verdict_fail(self):
        from dev_team.agents.qa import QAAgent

        content = "## Verdict: FAIL\nTests failed."
        assert QAAgent._parse_verdict(content, 1) is False

    def test_parse_verdict_fallback_exit_code(self):
        from dev_team.agents.qa import QAAgent

        content = "Everything looks fine."
        assert QAAgent._parse_verdict(content, 0) is True

    def test_parse_verdict_fallback_exit_code_nonzero(self):
        from dev_team.agents.qa import QAAgent

        content = "Something went wrong."
        assert QAAgent._parse_verdict(content, 1) is False

    def test_parse_issues(self):
        from dev_team.agents.qa import QAAgent

        content = (
            "## Issues\n"
            "- ImportError in main.py\n"
            "- AssertionError in test_main.py\n"
            "\n## Recommendations\n"
            "- Fix imports\n"
        )
        issues = QAAgent._parse_issues(content)
        assert len(issues) == 2
        assert "ImportError" in issues[0]

    def test_parse_issues_none(self):
        from dev_team.agents.qa import QAAgent

        content = "## Issues\n- None\n"
        issues = QAAgent._parse_issues(content)
        assert len(issues) == 0

    def test_make_skip_result(self):
        from dev_team.agents.qa import QAAgent

        result = QAAgent._make_skip_result("No code")
        assert result["test_results"]["approved"] is True
        assert result["test_results"]["skipped"] is True
        assert result["next_agent"] == "git_commit"


class TestQANodeFunction:
    """Test the qa_agent node function."""

    @patch("dev_team.agents.qa.get_qa_agent")
    def test_node_calls_test_code(self, mock_get_agent):
        from dev_team.agents.qa import qa_agent

        mock_agent = Mock()
        mock_agent.test_code.return_value = {
            "current_agent": "qa",
            "sandbox_results": {"exit_code": 0},
            "test_results": {"approved": True},
            "issues_found": [],
            "messages": [],
        }
        mock_agent.has_ui.return_value = False  # No UI → skip browser tests
        mock_get_agent.return_value = mock_agent

        state = {"code_files": [], "task": "test", "tech_stack": []}
        result = qa_agent(state)

        mock_agent.test_code.assert_called_once()
        assert result["current_agent"] == "qa"


# ==================================================================
# 3. Routing Tests (dev_team graph)
# ==================================================================


class TestRouteAfterReviewer:
    """Test route_after_reviewer in dev_team graph."""

    def test_issues_found_developer(self):
        from dev_team.graph import route_after_reviewer

        state = {"issues_found": ["bug"], "review_iteration_count": 0, "architect_escalated": False}
        assert route_after_reviewer(state) == "developer"

    def test_issues_architect_escalation(self):
        from dev_team.graph import route_after_reviewer

        state = {"issues_found": ["bug"], "review_iteration_count": 3, "architect_escalated": False}
        assert route_after_reviewer(state) == "architect_escalation"

    def test_issues_human_escalation(self):
        from dev_team.graph import route_after_reviewer

        state = {"issues_found": ["bug"], "review_iteration_count": 3, "architect_escalated": True}
        assert route_after_reviewer(state) == "human_escalation"

    def test_approved_to_qa(self):
        from dev_team.graph import route_after_reviewer

        state = {"issues_found": [], "test_results": {"approved": True}}
        assert route_after_reviewer(state) == "qa"

    def test_not_approved_to_pm(self):
        from dev_team.graph import route_after_reviewer

        state = {"issues_found": [], "test_results": {"approved": False}}
        assert route_after_reviewer(state) == "pm_final"


class TestRouteAfterQA:
    """Test route_after_qa in dev_team graph."""

    def test_approved_to_git_commit(self):
        from dev_team.graph import route_after_qa

        state = {"test_results": {"approved": True}, "sandbox_results": {"exit_code": 0}}
        assert route_after_qa(state) == "git_commit"

    def test_skipped_to_git_commit(self):
        from dev_team.graph import route_after_qa

        state = {"test_results": {"approved": True, "skipped": True}}
        assert route_after_qa(state) == "git_commit"

    def test_exit_code_0_fallback(self):
        from dev_team.graph import route_after_qa

        state = {"test_results": {}, "sandbox_results": {"exit_code": 0}}
        assert route_after_qa(state) == "git_commit"

    def test_failed_to_developer(self):
        from dev_team.graph import route_after_qa

        state = {"test_results": {"approved": False}, "sandbox_results": {"exit_code": 1}}
        assert route_after_qa(state) == "developer"


# ==================================================================
# 4. Prompts Tests
# ==================================================================


class TestReviewerPrompts:
    """Test that reviewer prompts load correctly."""

    def test_prompts_file_exists(self):
        prompts_path = Path(__file__).parent.parent.parent / "graphs" / "dev_team" / "prompts" / "reviewer.yaml"
        assert prompts_path.exists()

    def test_prompts_load(self):
        from dev_team.agents.base import load_prompts
        prompts = load_prompts("reviewer")
        assert "system" in prompts
        assert "code_review" in prompts
        assert "verify_fixes" in prompts
        assert "final_approval" in prompts

    def test_prompts_have_placeholders(self):
        from dev_team.agents.base import load_prompts
        prompts = load_prompts("reviewer")
        assert "{task}" in prompts["code_review"]
        assert "{requirements}" in prompts["code_review"]
        assert "{code_files}" in prompts["code_review"]


class TestQAPrompts:
    """Test that QA prompts load correctly."""

    def test_prompts_file_exists(self):
        prompts_path = Path(__file__).parent.parent.parent / "graphs" / "dev_team" / "prompts" / "qa.yaml"
        assert prompts_path.exists()

    def test_prompts_load(self):
        from dev_team.agents.base import load_prompts
        prompts = load_prompts("qa")
        assert "system" in prompts
        assert "analyse_sandbox" in prompts

    def test_prompts_have_placeholders(self):
        from dev_team.agents.base import load_prompts
        prompts = load_prompts("qa")
        assert "{task}" in prompts["analyse_sandbox"]
        assert "{exit_code}" in prompts["analyse_sandbox"]
        assert "{stdout}" in prompts["analyse_sandbox"]
        assert "{stderr}" in prompts["analyse_sandbox"]


# ==================================================================
# 5. Graph Compilation Tests
# ==================================================================


class TestGraphWithReviewerAndQA:
    """Test that the dev_team graph compiles with both reviewer and QA nodes."""

    def test_graph_has_reviewer_node(self):
        from dev_team.graph import graph
        node_names = list(graph.nodes.keys())
        assert "reviewer" in node_names

    def test_graph_has_qa_node(self):
        from dev_team.graph import graph
        node_names = list(graph.nodes.keys())
        assert "qa" in node_names

    def test_graph_compiles(self):
        from dev_team.graph import create_graph
        builder = create_graph()
        compiled = builder.compile()
        assert compiled is not None

    def test_graph_topology_includes_reviewer_and_qa(self):
        from dev_team.graph import graph
        topology = graph.get_graph().to_json()
        topology_str = str(topology)
        assert "reviewer" in topology_str
        assert "qa" in topology_str

    def test_manifest_includes_both_agents(self):
        manifest_path = Path(__file__).parent.parent.parent / "graphs" / "dev_team" / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        agent_ids = [a["id"] for a in manifest["agents"]]
        assert "reviewer" in agent_ids
        assert "qa" in agent_ids
        assert "review_loop" in manifest["features"]
        assert "sandbox_testing" in manifest["features"]
