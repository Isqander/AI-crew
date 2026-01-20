"""
Tests for DevTeamState
"""

import pytest
from graphs.dev_team.state import DevTeamState, create_initial_state, CodeFile, UserStory


class TestDevTeamState:
    """Test DevTeamState structure and initialization."""
    
    def test_create_initial_state_minimal(self):
        """Test creating initial state with minimal parameters."""
        state = create_initial_state(task="Test task")
        
        assert state["task"] == "Test task"
        assert state["repository"] is None
        assert state["context"] is None
        assert state["requirements"] == []
        assert state["messages"] == []
        assert state["current_agent"] == "pm"
        assert state["needs_clarification"] is False
        assert state["retry_count"] == 0
    
    def test_create_initial_state_full(self):
        """Test creating initial state with all parameters."""
        state = create_initial_state(
            task="Build API",
            repository="owner/repo",
            context="Use FastAPI and PostgreSQL",
        )
        
        assert state["task"] == "Build API"
        assert state["repository"] == "owner/repo"
        assert state["context"] == "Use FastAPI and PostgreSQL"
    
    def test_state_has_all_required_fields(self):
        """Test that initial state has all required fields."""
        state = create_initial_state(task="Test")
        
        required_fields = [
            "task", "repository", "context",
            "requirements", "user_stories", "architecture",
            "tech_stack", "architecture_decisions",
            "code_files", "implementation_notes",
            "review_comments", "test_results", "issues_found",
            "pr_url", "commit_sha", "summary",
            "messages", "current_agent", "next_agent",
            "needs_clarification", "clarification_question",
            "clarification_context", "clarification_response",
            "error", "retry_count",
        ]
        
        for field in required_fields:
            assert field in state, f"Missing required field: {field}"


class TestCodeFile:
    """Test CodeFile TypedDict."""
    
    def test_code_file_structure(self):
        """Test CodeFile structure."""
        code_file: CodeFile = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "python",
        }
        
        assert code_file["path"] == "src/main.py"
        assert code_file["content"] == "print('hello')"
        assert code_file["language"] == "python"


class TestUserStory:
    """Test UserStory TypedDict."""
    
    def test_user_story_structure(self):
        """Test UserStory structure."""
        story: UserStory = {
            "id": "US-1",
            "title": "User login",
            "description": "As a user, I want to log in",
            "acceptance_criteria": ["Can enter credentials", "Can submit form"],
            "priority": "high",
        }
        
        assert story["id"] == "US-1"
        assert story["priority"] == "high"
        assert len(story["acceptance_criteria"]) == 2
