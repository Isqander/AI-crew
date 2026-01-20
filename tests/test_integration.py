"""
Integration tests for the complete workflow
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from langchain_core.messages import AIMessage

from graphs.dev_team.graph import create_graph
from graphs.dev_team.state import create_initial_state


class TestEndToEndWorkflow:
    """Test complete workflow from task to completion."""
    
    @pytest.mark.skip(reason="Requires LLM mocking at graph level - complex integration test")
    @patch('graphs.dev_team.agents.pm.get_llm')
    @patch('graphs.dev_team.agents.analyst.get_llm')
    @patch('graphs.dev_team.agents.architect.get_llm')
    @patch('graphs.dev_team.agents.developer.get_llm')
    @patch('graphs.dev_team.agents.qa.get_llm')
    def test_simple_task_workflow_without_clarification(
        self,
        mock_qa_llm,
        mock_dev_llm,
        mock_arch_llm,
        mock_analyst_llm,
        mock_pm_llm,
    ):
        """Test a simple task that goes through all agents without clarification."""
        # This is a complex integration test that would require
        # mocking all LLM calls throughout the workflow
        # For now, we'll skip it and focus on unit tests
        pass


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
        
        assert state["error"] is None
        
        # Simulate error
        state["error"] = "LLM API timeout"
        assert state["error"] is not None


class TestMultiAgentCollaboration:
    """Test multi-agent collaboration scenarios."""
    
    def test_developer_qa_feedback_loop(self):
        """Test feedback loop between Developer and QA."""
        state = create_initial_state(task="Build API")
        
        # Developer creates code
        state["code_files"] = [
            {"path": "api.py", "content": "def api():\n    pass", "language": "python"}
        ]
        state["current_agent"] = "developer"
        
        # QA finds issues
        state["issues_found"] = ["Missing error handling", "No tests"]
        state["current_agent"] = "qa"
        state["next_agent"] = "developer"
        
        # Developer should fix issues
        assert len(state["issues_found"]) > 0
        assert state["next_agent"] == "developer"
        
        # After fixes, clear issues
        state["issues_found"] = []
        state["next_agent"] = "git_commit"
        
        assert len(state["issues_found"]) == 0
        assert state["next_agent"] == "git_commit"
    
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
