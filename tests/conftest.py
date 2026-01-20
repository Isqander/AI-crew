"""
Pytest Configuration and Fixtures
"""

import os
import pytest
from unittest.mock import Mock, AsyncMock
from typing import Generator

# Set test environment variables
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["ANTHROPIC_API_KEY"] = "test-key"


@pytest.fixture
def mock_llm():
    """Mock LLM for testing agents."""
    mock = Mock()
    mock.invoke = Mock(return_value=Mock(content="Test response"))
    return mock


@pytest.fixture
async def mock_async_llm():
    """Mock async LLM for testing."""
    mock = AsyncMock()
    mock.ainvoke = AsyncMock(return_value=Mock(content="Test async response"))
    return mock


@pytest.fixture
def sample_task():
    """Sample task for testing."""
    return {
        "task": "Create a simple calculator API",
        "repository": "test-org/test-repo",
        "context": "Use Python and FastAPI",
    }


@pytest.fixture
def sample_state():
    """Sample DevTeamState for testing."""
    from graphs.dev_team.state import create_initial_state
    
    return create_initial_state(
        task="Create a simple calculator API",
        repository="test-org/test-repo",
        context="Use Python and FastAPI",
    )


@pytest.fixture
def mock_github_client():
    """Mock GitHub client."""
    mock = Mock()
    mock.get_repo = Mock()
    mock.create_pull = Mock(return_value=Mock(html_url="https://github.com/test/pull/1"))
    return mock
