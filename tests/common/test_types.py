"""Tests for graphs/common/types.py — shared TypedDicts."""

from common.types import CodeFile, UserStory, ArchitectureDecision


def test_code_file_creation():
    """CodeFile can be created with all required fields."""
    cf: CodeFile = {"path": "main.py", "content": "print('hi')", "language": "python"}
    assert cf["path"] == "main.py"
    assert cf["language"] == "python"
    assert "print" in cf["content"]


def test_user_story_creation():
    """UserStory includes all expected fields."""
    us: UserStory = {
        "id": "US-1",
        "title": "Login",
        "description": "User can log in",
        "acceptance_criteria": ["User sees form", "JWT returned"],
        "priority": "high",
    }
    assert us["id"] == "US-1"
    assert len(us["acceptance_criteria"]) == 2
    assert us["priority"] == "high"


def test_architecture_decision_creation():
    """ArchitectureDecision has component, technology, rationale."""
    ad: ArchitectureDecision = {
        "component": "auth",
        "technology": "JWT",
        "rationale": "Stateless auth",
    }
    assert ad["component"] == "auth"
    assert ad["technology"] == "JWT"
