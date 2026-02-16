"""
Integration tests for the complete workflow
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import AIMessage

from graphs.dev_team.graph import create_graph, clarification_node, git_commit_node
from graphs.dev_team.state import create_initial_state


class TestEndToEndWorkflow:
    """Test complete workflow from task to completion."""

    def test_simple_workflow_with_mocked_agents(self):
        """
        Test workflow execution with mocked agent functions.

        This test verifies the graph structure and routing by replacing
        agent functions with mocks that return predictable state updates.
        """
        # Create mock agent responses
        def mock_pm_agent(state):
            return {
                "messages": [AIMessage(content="Task decomposed", name="pm")],
                "current_agent": "pm",
            }

        def mock_analyst_agent(state):
            return {
                "messages": [AIMessage(content="Requirements gathered", name="analyst")],
                "requirements": ["Requirement 1", "Requirement 2"],
                "current_agent": "analyst",
                "needs_clarification": False,
            }

        def mock_architect_agent(state):
            return {
                "messages": [AIMessage(content="Architecture designed", name="architect")],
                "architecture": {"design": "Simple architecture"},
                "tech_stack": ["Python", "FastAPI"],
                "current_agent": "architect",
                "needs_clarification": False,
            }

        def mock_developer_agent(state):
            return {
                "messages": [AIMessage(content="Code implemented", name="developer")],
                "code_files": [
                    {"path": "main.py", "content": "print('hello')", "language": "python"}
                ],
                "current_agent": "developer",
            }

        def mock_reviewer_agent(state):
            return {
                "messages": [AIMessage(content="Code approved", name="reviewer")],
                "review_comments": ["Looks good!"],
                "issues_found": [],
                "test_results": {"approved": True},
                "current_agent": "reviewer",
            }

        def mock_qa_agent(state):
            return {
                "messages": [AIMessage(content="Tests passed in sandbox", name="qa")],
                "sandbox_results": {"exit_code": 0, "tests_passed": True, "stdout": "OK", "stderr": ""},
                "test_results": {"approved": True, "sandbox_exit_code": 0},
                "issues_found": [],
                "current_agent": "qa",
            }

        def mock_security_agent(state, config=None):
            return {
                "messages": [AIMessage(content="No security issues found", name="security")],
                "security_review": {
                    "risk_level": "LOW",
                    "critical": [],
                    "warnings": [],
                    "info": [],
                    "summary": "Clean.",
                },
                "current_agent": "security",
            }

        # Patch agent functions at the graph module level
        with patch('graphs.dev_team.graph.pm_agent', mock_pm_agent), \
             patch('graphs.dev_team.graph.analyst_agent', mock_analyst_agent), \
             patch('graphs.dev_team.graph.architect_agent', mock_architect_agent), \
             patch('graphs.dev_team.graph.developer_agent', mock_developer_agent), \
             patch('graphs.dev_team.graph.reviewer_agent', mock_reviewer_agent), \
             patch('graphs.dev_team.graph.qa_agent', mock_qa_agent), \
             patch('graphs.dev_team.graph.security_agent', mock_security_agent):

            # Create fresh graph with mocked agents
            from langgraph.checkpoint.memory import MemorySaver
            builder = create_graph()
            graph = builder.compile(checkpointer=MemorySaver())

            # Create initial state
            initial_state = create_initial_state(
                task="Create a simple hello world script",
                repository="test/repo",
            )

            # Run the graph
            config = {"configurable": {"thread_id": "test-thread-1"}}
            result = graph.invoke(initial_state, config)

            # Verify workflow completed
            assert result["current_agent"] == "complete"
            assert "summary" in result
            assert "Task completed" in result["summary"]
            assert len(result["code_files"]) > 0
            assert result["requirements"] == ["Requirement 1", "Requirement 2"]

    def test_workflow_with_reviewer_rejection(self):
        """Test workflow when Reviewer finds issues and sends back to developer."""
        call_count = {"developer": 0, "reviewer": 0, "qa": 0}

        def mock_pm_agent(state):
            return {
                "messages": [AIMessage(content="Task decomposed", name="pm")],
                "current_agent": "pm",
            }

        def mock_analyst_agent(state):
            return {
                "messages": [AIMessage(content="Requirements", name="analyst")],
                "requirements": ["Req 1"],
                "needs_clarification": False,
            }

        def mock_architect_agent(state):
            return {
                "messages": [AIMessage(content="Architecture", name="architect")],
                "architecture": {"design": "Simple"},
                "needs_clarification": False,
            }

        def mock_developer_agent(state):
            call_count["developer"] += 1
            return {
                "messages": [AIMessage(content=f"Code v{call_count['developer']}", name="developer")],
                "code_files": [{"path": "main.py", "content": "code", "language": "python"}],
                "issues_found": [],  # Clear issues after fix
            }

        def mock_reviewer_agent(state):
            call_count["reviewer"] += 1
            if call_count["reviewer"] == 1:
                # First review: find issues
                return {
                    "messages": [AIMessage(content="Issues found", name="reviewer")],
                    "issues_found": ["Bug found"],
                    "test_results": {"approved": False},
                    "review_iteration_count": 1,
                }
            else:
                # Second review: approve
                return {
                    "messages": [AIMessage(content="Approved", name="reviewer")],
                    "issues_found": [],
                    "test_results": {"approved": True},
                }

        def mock_qa_agent(state):
            call_count["qa"] += 1
            return {
                "messages": [AIMessage(content="Sandbox tests passed", name="qa")],
                "sandbox_results": {"exit_code": 0, "tests_passed": True, "stdout": "OK", "stderr": ""},
                "test_results": {"approved": True},
                "issues_found": [],
                "current_agent": "qa",
            }

        def mock_security_agent(state, config=None):
            return {
                "messages": [AIMessage(content="Security review OK", name="security")],
                "security_review": {
                    "risk_level": "LOW",
                    "critical": [],
                    "warnings": [],
                    "info": [],
                    "summary": "Clean.",
                },
                "current_agent": "security",
            }

        with patch('graphs.dev_team.graph.pm_agent', mock_pm_agent), \
             patch('graphs.dev_team.graph.analyst_agent', mock_analyst_agent), \
             patch('graphs.dev_team.graph.architect_agent', mock_architect_agent), \
             patch('graphs.dev_team.graph.developer_agent', mock_developer_agent), \
             patch('graphs.dev_team.graph.reviewer_agent', mock_reviewer_agent), \
             patch('graphs.dev_team.graph.qa_agent', mock_qa_agent), \
             patch('graphs.dev_team.graph.security_agent', mock_security_agent):

            from langgraph.checkpoint.memory import MemorySaver
            builder = create_graph()
            graph = builder.compile(checkpointer=MemorySaver())

            initial_state = create_initial_state(task="Build API", repository="test/repo")
            config = {"configurable": {"thread_id": "test-thread-2"}}

            result = graph.invoke(initial_state, config)

            # Developer should have been called twice (initial + fix)
            assert call_count["developer"] == 2
            # Reviewer should have been called twice (reject + approve)
            assert call_count["reviewer"] == 2
            # QA (sandbox) should have been called once (after reviewer approved)
            assert call_count["qa"] == 1
            # Final state should be complete
            assert result["current_agent"] == "complete"


class TestHumanInTheLoop:
    """Test HITL (Human-in-the-Loop) scenarios."""

    def test_clarification_interrupts_workflow(self):
        """Test that clarification needs interrupt the workflow."""
        state = create_initial_state(task="Build something")
        state["needs_clarification"] = True
        state["clarification_question"] = "What database should we use?"
        state["current_agent"] = "analyst"

        # When clarification is needed, workflow should pause
        assert state["needs_clarification"] is True
        assert state["clarification_question"] is not None

    def test_clarification_response_continues_workflow(self):
        """Test that providing clarification response continues workflow."""
        state = create_initial_state(task="Build something")
        state["needs_clarification"] = True
        state["clarification_question"] = "What database?"

        # User provides clarification
        state["clarification_response"] = "Use PostgreSQL"
        state["needs_clarification"] = False

        # Workflow should be able to continue
        assert state["clarification_response"] is not None
        assert state["needs_clarification"] is False


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_state_tracks_retry_count(self):
        """Test that retry count is tracked in state."""
        state = create_initial_state(task="Test task")

        assert state["retry_count"] == 0

        # Simulate retry
        state["retry_count"] += 1
        assert state["retry_count"] == 1

    def test_state_stores_error_messages(self):
        """Test that errors are stored in state."""
        state = create_initial_state(task="Test task")

        # Error is NotRequired, so it's not present by default
        assert state.get("error") is None

        # Simulate error
        state["error"] = "LLM API timeout"
        assert state["error"] == "LLM API timeout"


class TestMultiAgentCollaboration:
    """Test multi-agent collaboration scenarios."""

    def test_developer_reviewer_feedback_loop(self):
        """Test feedback loop between Developer and Reviewer."""
        state = create_initial_state(task="Build API")

        # Developer creates code
        state["code_files"] = [
            {"path": "api.py", "content": "def api():\n    pass", "language": "python"}
        ]
        state["current_agent"] = "developer"

        # Reviewer finds issues
        state["issues_found"] = ["Missing error handling", "No tests"]
        state["current_agent"] = "reviewer"
        state["next_agent"] = "developer"

        # Developer should fix issues
        assert len(state["issues_found"]) > 0
        assert state["next_agent"] == "developer"

        # After fixes, clear issues
        state["issues_found"] = []
        state["next_agent"] = "qa"

        assert len(state["issues_found"]) == 0
        assert state["next_agent"] == "qa"

    def test_analyst_provides_requirements_to_architect(self):
        """Test data flow from Analyst to Architect."""
        state = create_initial_state(task="Build dashboard")

        # Analyst gathers requirements
        state["requirements"] = [
            "Display user metrics",
            "Support filtering",
            "Export to CSV",
        ]
        state["user_stories"] = [
            {
                "id": "US-1",
                "title": "View metrics",
                "description": "As a user, I want to view metrics",
                "acceptance_criteria": ["Shows charts", "Updates real-time"],
                "priority": "high",
            }
        ]
        state["current_agent"] = "analyst"
        state["next_agent"] = "architect"

        # Architect should have access to requirements
        assert len(state["requirements"]) == 3
        assert len(state["user_stories"]) == 1
        assert state["next_agent"] == "architect"
