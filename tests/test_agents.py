"""
Tests for Agent implementations
"""

import pytest
from unittest.mock import Mock, patch
from langchain_core.messages import AIMessage

from graphs.dev_team.agents.pm import pm_agent, ProjectManagerAgent
from graphs.dev_team.agents.analyst import analyst_agent, AnalystAgent
from graphs.dev_team.agents.architect import architect_agent, ArchitectAgent
from graphs.dev_team.agents.developer import developer_agent, DeveloperAgent
from graphs.dev_team.agents.qa import qa_agent, QAAgent


class TestProjectManagerAgent:
    """Test Project Manager agent."""
    
    @patch('graphs.dev_team.agents.pm.get_llm')
    @patch('graphs.dev_team.agents.pm.load_prompts')
    def test_pm_agent_initialization(self, mock_load_prompts, mock_get_llm):
        """Test PM agent can be initialized."""
        mock_load_prompts.return_value = {
            "system": "Test system prompt",
            "task_decomposition": "Test task prompt",
            "progress_check": "Test progress prompt",
            "final_review": "Test review prompt",
        }
        mock_llm = Mock()
        mock_get_llm.return_value = mock_llm
        
        agent = ProjectManagerAgent()
        
        assert agent.name == "pm"
        assert agent.llm == mock_llm
    
    @patch('graphs.dev_team.agents.pm.get_llm')
    @patch('graphs.dev_team.agents.pm.load_prompts')
    def test_pm_decompose_task(self, mock_load_prompts, mock_get_llm, sample_state):
        """Test PM task decomposition."""
        mock_load_prompts.return_value = {
            "system": "System",
            "task_decomposition": "Decompose: {task}\nContext: {context}",
            "progress_check": "Check",
            "final_review": "Review",
        }
        mock_llm = Mock()
        mock_response = Mock(content="Task decomposed into 3 subtasks")
        mock_llm.invoke = Mock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        agent = ProjectManagerAgent()
        result = agent.decompose_task(sample_state)
        
        assert "messages" in result
        assert result["current_agent"] == "pm"
        assert result["next_agent"] == "analyst"
        assert isinstance(result["messages"][0], AIMessage)


class TestAnalystAgent:
    """Test Business Analyst agent."""
    
    @patch('graphs.dev_team.agents.analyst.get_llm')
    @patch('graphs.dev_team.agents.analyst.load_prompts')
    def test_analyst_initialization(self, mock_load_prompts, mock_get_llm):
        """Test Analyst agent initialization."""
        mock_load_prompts.return_value = {
            "system": "System",
            "requirements_gathering": "Gather requirements",
        }
        mock_get_llm.return_value = Mock()
        
        agent = AnalystAgent()
        
        assert agent.name == "analyst"
    
    @patch('graphs.dev_team.agents.analyst.get_llm')
    @patch('graphs.dev_team.agents.analyst.load_prompts')
    def test_analyst_gather_requirements_no_clarification(
        self, mock_load_prompts, mock_get_llm, sample_state
    ):
        """Test analyst gathering requirements without needing clarification."""
        mock_load_prompts.return_value = {
            "system": "System",
            "requirements_gathering": "Gather: {task}",
        }
        mock_llm = Mock()
        mock_response = Mock(content="Requirements:\n- REQ-1: API endpoint\n- REQ-2: Database")
        mock_llm.invoke = Mock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        agent = AnalystAgent()
        result = agent.gather_requirements(sample_state)
        
        assert "requirements" in result
        assert result["needs_clarification"] is False
        assert result["next_agent"] == "architect"
    
    @patch('graphs.dev_team.agents.analyst.get_llm')
    @patch('graphs.dev_team.agents.analyst.load_prompts')
    def test_analyst_needs_clarification(
        self, mock_load_prompts, mock_get_llm, sample_state
    ):
        """Test analyst requesting clarification."""
        mock_load_prompts.return_value = {
            "system": "System",
            "requirements_gathering": "Gather: {task}",
        }
        mock_llm = Mock()
        mock_response = Mock(
            content="I need clarification: What database should we use?"
        )
        mock_llm.invoke = Mock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        agent = AnalystAgent()
        result = agent.gather_requirements(sample_state)
        
        assert result["needs_clarification"] is True
        assert result["clarification_question"] is not None


class TestArchitectAgent:
    """Test Software Architect agent."""
    
    @patch('graphs.dev_team.agents.architect.get_llm')
    @patch('graphs.dev_team.agents.architect.load_prompts')
    def test_architect_initialization(self, mock_load_prompts, mock_get_llm):
        """Test Architect agent initialization."""
        mock_load_prompts.return_value = {
            "system": "System",
            "architecture_design": "Design",
            "implementation_spec": "Spec",
        }
        mock_get_llm.return_value = Mock()
        
        agent = ArchitectAgent()
        
        assert agent.name == "architect"
    
    @patch('graphs.dev_team.agents.architect.get_llm')
    @patch('graphs.dev_team.agents.architect.load_prompts')
    def test_architect_design_architecture(
        self, mock_load_prompts, mock_get_llm, sample_state
    ):
        """Test architect designing system architecture."""
        mock_load_prompts.return_value = {
            "system": "System",
            "architecture_design": "Design: {task}",
            "implementation_spec": "Spec",
        }
        mock_llm = Mock()
        mock_response = Mock(
            content="Architecture: Use FastAPI with PostgreSQL database. React frontend."
        )
        mock_llm.invoke = Mock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        sample_state["requirements"] = ["REQ-1", "REQ-2"]
        agent = ArchitectAgent()
        result = agent.design_architecture(sample_state)
        
        assert "architecture" in result
        assert "tech_stack" in result
        assert result["next_agent"] == "developer"


class TestDeveloperAgent:
    """Test Developer agent."""
    
    @patch('graphs.dev_team.agents.developer.get_llm')
    @patch('graphs.dev_team.agents.developer.load_prompts')
    def test_developer_initialization(self, mock_load_prompts, mock_get_llm):
        """Test Developer agent initialization."""
        mock_load_prompts.return_value = {
            "system": "System",
            "implementation": "Implement",
            "fix_issues": "Fix",
        }
        mock_get_llm.return_value = Mock()
        
        agent = DeveloperAgent()
        
        assert agent.name == "developer"
    
    @patch('graphs.dev_team.agents.developer.get_llm')
    @patch('graphs.dev_team.agents.developer.load_prompts')
    def test_developer_implement_code(
        self, mock_load_prompts, mock_get_llm, sample_state
    ):
        """Test developer implementing code."""
        mock_load_prompts.return_value = {
            "system": "System",
            "implementation": "Implement: {task}",
            "fix_issues": "Fix",
        }
        mock_llm = Mock()
        code_response = """
Here is the implementation:

```python:src/main.py
def add(a, b):
    return a + b
```

```python:tests/test_main.py
def test_add():
    assert add(1, 2) == 3
```
"""
        mock_response = Mock(content=code_response)
        mock_llm.invoke = Mock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        sample_state["architecture"] = {"design": "Simple calculator"}
        agent = DeveloperAgent()
        result = agent.implement(sample_state)
        
        assert "code_files" in result
        assert len(result["code_files"]) == 2
        assert result["code_files"][0]["path"] == "src/main.py"
        assert result["code_files"][1]["path"] == "tests/test_main.py"


class TestQAAgent:
    """Test QA Engineer agent."""
    
    @patch('graphs.dev_team.agents.qa.get_llm')
    @patch('graphs.dev_team.agents.qa.load_prompts')
    def test_qa_initialization(self, mock_load_prompts, mock_get_llm):
        """Test QA agent initialization."""
        mock_load_prompts.return_value = {
            "system": "System",
            "code_review": "Review",
            "verify_fixes": "Verify",
            "final_approval": "Approve",
        }
        mock_get_llm.return_value = Mock()
        
        agent = QAAgent()
        
        assert agent.name == "qa"
    
    @patch('graphs.dev_team.agents.qa.get_llm')
    @patch('graphs.dev_team.agents.qa.load_prompts')
    def test_qa_review_approved(
        self, mock_load_prompts, mock_get_llm, sample_state
    ):
        """Test QA reviewing and approving code."""
        mock_load_prompts.return_value = {
            "system": "System",
            "code_review": "Review: {code_files}",
            "verify_fixes": "Verify",
            "final_approval": "Approve",
        }
        mock_llm = Mock()
        mock_response = Mock(
            content="Code review complete. All checks passed. Approved for deployment."
        )
        mock_llm.invoke = Mock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        sample_state["code_files"] = [
            {"path": "main.py", "content": "print('hello')", "language": "python"}
        ]
        sample_state["requirements"] = ["REQ-1"]
        
        agent = QAAgent()
        result = agent.review_code(sample_state)
        
        assert "test_results" in result
        assert result["test_results"]["reviewed"] is True
    
    @patch('graphs.dev_team.agents.qa.get_llm')
    @patch('graphs.dev_team.agents.qa.load_prompts')
    def test_qa_review_with_issues(
        self, mock_load_prompts, mock_get_llm, sample_state
    ):
        """Test QA finding issues in code."""
        mock_load_prompts.return_value = {
            "system": "System",
            "code_review": "Review: {code_files}",
            "verify_fixes": "Verify",
            "final_approval": "Approve",
        }
        mock_llm = Mock()
        mock_response = Mock(
            content="Issues found:\n- Critical: Missing error handling\n- Major: No input validation"
        )
        mock_llm.invoke = Mock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        sample_state["code_files"] = [
            {"path": "main.py", "content": "print('hello')", "language": "python"}
        ]
        sample_state["requirements"] = ["REQ-1"]
        
        agent = QAAgent()
        result = agent.review_code(sample_state)
        
        assert len(result["issues_found"]) > 0
        assert result["next_agent"] == "developer"
