"""
Integration Test: Reviewer + QA (Sandbox) Flow
===============================================

Tests the complete dev_team graph flow with:
  - All agents mocked
  - Reviewer approves -> QA (sandbox) tests -> git_commit
  - Reviewer approves -> QA fails -> Developer fixes -> Reviewer -> QA passes
  - QA sandbox skip (no code files)

These tests verify the correct wiring of the graph nodes and routing.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage


def _make_mock_agents(qa_results: list[dict] | None = None, reviewer_results: list[dict] | None = None):
    """Build standard mock agents for graph testing.

    Args:
        qa_results: List of dicts to return from QA (sandbox) in order.
        reviewer_results: List of dicts to return from Reviewer in order.
    """
    call_counts = {"pm": 0, "analyst": 0, "architect": 0, "developer": 0,
                   "reviewer": 0, "qa": 0, "security": 0}

    qa_results = qa_results or [
        {"approved": True, "exit_code": 0, "tests_passed": True, "stdout": "OK", "stderr": ""},
    ]
    reviewer_results = reviewer_results or [
        {"approved": True, "issues": []},
    ]

    def mock_pm(state, config=None):
        call_counts["pm"] += 1
        return {
            "messages": [AIMessage(content="Task decomposed", name="pm")],
            "current_agent": "pm",
        }

    def mock_analyst(state, config=None):
        call_counts["analyst"] += 1
        return {
            "messages": [AIMessage(content="Requirements gathered", name="analyst")],
            "requirements": ["Req 1"],
            "needs_clarification": False,
        }

    def mock_architect(state, config=None):
        call_counts["architect"] += 1
        return {
            "messages": [AIMessage(content="Architecture done", name="architect")],
            "architecture": {"design": "Simple"},
            "needs_clarification": False,
        }

    def mock_developer(state, config=None):
        call_counts["developer"] += 1
        return {
            "messages": [AIMessage(content=f"Code v{call_counts['developer']}", name="developer")],
            "code_files": [{"path": "main.py", "content": "print('hello')", "language": "python"}],
            "issues_found": [],
        }

    def mock_reviewer(state, config=None):
        call_counts["reviewer"] += 1
        idx = min(call_counts["reviewer"] - 1, len(reviewer_results) - 1)
        r = reviewer_results[idx]
        return {
            "messages": [AIMessage(content="Review done", name="reviewer")],
            "review_comments": ["OK"],
            "issues_found": r.get("issues", []),
            "test_results": {"approved": r["approved"]},
            "current_agent": "reviewer",
            "review_iteration_count": state.get("review_iteration_count", 0) + (1 if r.get("issues") else 0),
        }

    def mock_qa(state, config=None):
        call_counts["qa"] += 1
        idx = min(call_counts["qa"] - 1, len(qa_results) - 1)
        r = qa_results[idx]
        return {
            "messages": [AIMessage(content="QA sandbox done", name="qa")],
            "sandbox_results": {
                "exit_code": r["exit_code"],
                "tests_passed": r["tests_passed"],
                "stdout": r.get("stdout", ""),
                "stderr": r.get("stderr", ""),
            },
            "test_results": {"approved": r["approved"], "sandbox_exit_code": r["exit_code"]},
            "issues_found": r.get("issues", []),
            "current_agent": "qa",
            "review_iteration_count": state.get("review_iteration_count", 0) + (1 if r.get("issues") else 0),
        }

    def mock_security(state, config=None):
        call_counts["security"] += 1
        return {
            "messages": [AIMessage(content="Security OK", name="security")],
            "security_review": {"risk_level": "LOW", "critical": [], "warnings": [], "info": [], "summary": "OK"},
            "current_agent": "security",
        }

    return {
        "pm": mock_pm,
        "analyst": mock_analyst,
        "architect": mock_architect,
        "developer": mock_developer,
        "reviewer": mock_reviewer,
        "qa": mock_qa,
        "security": mock_security,
        "call_counts": call_counts,
    }


def _run_graph(mocks: dict, task: str = "Build API", repository: str = "test/repo") -> tuple[dict, dict]:
    """Create, compile, and invoke the dev_team graph with given mocks.

    Returns (final_state, call_counts).
    """
    from dev_team.graph import create_graph
    from dev_team.state import create_initial_state
    from langgraph.checkpoint.memory import MemorySaver

    with patch("dev_team.graph.pm_agent", mocks["pm"]), \
         patch("dev_team.graph.analyst_agent", mocks["analyst"]), \
         patch("dev_team.graph.architect_agent", mocks["architect"]), \
         patch("dev_team.graph.developer_agent", mocks["developer"]), \
         patch("dev_team.graph.reviewer_agent", mocks["reviewer"]), \
         patch("dev_team.graph.qa_agent", mocks["qa"]), \
         patch("dev_team.graph.security_agent", mocks["security"]):

        builder = create_graph()
        graph = builder.compile(checkpointer=MemorySaver())
        state = create_initial_state(task=task, repository=repository)
        config = {"configurable": {"thread_id": "integration-test"}}
        result = graph.invoke(state, config)

    return result, mocks["call_counts"]


# ==================================================================
# Integration Tests
# ==================================================================


class TestReviewerThenQAFlow:
    """Test: Developer -> Security -> Reviewer (approve) -> QA (pass) -> git_commit."""

    def test_happy_path(self):
        """Full flow: reviewer approves, QA sandbox passes -> commit."""
        mocks = _make_mock_agents(
            qa_results=[{"approved": True, "exit_code": 0, "tests_passed": True, "stdout": "OK", "stderr": ""}],
            reviewer_results=[{"approved": True, "issues": []}],
        )

        result, counts = _run_graph(mocks)

        assert result["current_agent"] in ("complete", "pm")
        assert "summary" in result
        assert counts["reviewer"] == 1
        assert counts["qa"] == 1
        assert counts["developer"] == 1


class TestQASandboxFailFlow:
    """Test: Reviewer approves -> QA fails -> Developer fixes -> Reviewer -> QA passes."""

    def test_qa_fail_then_pass(self):
        """QA sandbox fails once, developer fixes, reviewer re-approves, QA passes."""
        mocks = _make_mock_agents(
            qa_results=[
                {"approved": False, "exit_code": 1, "tests_passed": False,
                 "stdout": "FAILED", "stderr": "Error", "issues": ["Test failure"]},
                {"approved": True, "exit_code": 0, "tests_passed": True,
                 "stdout": "OK", "stderr": ""},
            ],
            reviewer_results=[
                {"approved": True, "issues": []},
                {"approved": True, "issues": []},
            ],
        )

        result, counts = _run_graph(mocks)

        assert result["current_agent"] in ("complete", "pm")
        # Developer called twice: initial + fix
        assert counts["developer"] >= 2
        # QA called twice: fail + pass (QA runs before Reviewer in new flow)
        assert counts["qa"] == 2
        # Reviewer called once: only after QA passes the second time
        # (QA fail routes back to Developer, not through Reviewer)
        assert counts["reviewer"] >= 1


class TestReviewerRejectsAndQAPasses:
    """Test: Reviewer rejects -> Developer fixes -> Reviewer approves -> QA passes."""

    def test_reviewer_reject_then_approve(self):
        """Reviewer finds issues, developer fixes, reviewer approves, QA passes.

        New flow: Dev → lint → Security → QA → Reviewer.
        Reviewer reject → Developer → lint → Security → QA → Reviewer.
        So QA is called on each pass through the pipeline.
        """
        mocks = _make_mock_agents(
            qa_results=[
                {"approved": True, "exit_code": 0, "tests_passed": True, "stdout": "OK", "stderr": ""},
            ],
            reviewer_results=[
                {"approved": False, "issues": ["Missing error handling"]},
                {"approved": True, "issues": []},
            ],
        )

        result, counts = _run_graph(mocks)

        assert result["current_agent"] in ("complete", "pm")
        assert counts["developer"] >= 2
        assert counts["reviewer"] >= 2
        # QA runs before Reviewer, so it's called on each pipeline pass
        assert counts["qa"] == 2


class TestQASkipNoCode:
    """Test: When developer generates no code, QA should be skipped or pass-through."""

    def test_no_code_files(self):
        """QA skips when no code files exist."""
        mocks = _make_mock_agents()

        # Override developer to return no code
        def mock_developer_no_code(state, config=None):
            mocks["call_counts"]["developer"] += 1
            return {
                "messages": [AIMessage(content="Nothing to generate", name="developer")],
                "code_files": [],
                "issues_found": [],
            }

        # Override QA to return skip result
        def mock_qa_skip(state, config=None):
            mocks["call_counts"]["qa"] += 1
            return {
                "messages": [AIMessage(content="QA skipped: no code", name="qa")],
                "sandbox_results": None,
                "test_results": {"approved": True, "skipped": True},
                "issues_found": [],
                "current_agent": "qa",
            }

        mocks["developer"] = mock_developer_no_code
        mocks["qa"] = mock_qa_skip

        result, counts = _run_graph(mocks)

        assert result["current_agent"] in ("complete", "pm")
        # QA was called but skipped
        assert counts["qa"] == 1
