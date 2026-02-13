"""
Tests for Agent implementations

Note: These are simplified smoke tests that verify agents can be initialized
and called without errors. Deep unit testing of agent logic is intentionally
omitted as agents are frequently modified (prompts, models, logic).

For comprehensive testing, see integration tests which test the full workflow.
"""

import pytest
from unittest.mock import Mock, patch

from graphs.dev_team.agents.pm import ProjectManagerAgent
from graphs.dev_team.agents.analyst import AnalystAgent
from graphs.dev_team.agents.architect import ArchitectAgent
from graphs.dev_team.agents.developer import DeveloperAgent
from graphs.dev_team.agents.qa import QAAgent


class TestAgentInitialization:
    """Test that all agents can be initialized."""
    
    @patch('graphs.dev_team.agents.pm.get_llm_with_fallback')
    @patch('graphs.dev_team.agents.pm.load_prompts')
    def test_pm_agent_initialization(self, mock_load_prompts, mock_get_llm):
        """Test PM agent can be initialized."""
        mock_load_prompts.return_value = {
            "system": "Test",
            "task_decomposition": "Test",
            "progress_check": "Test",
            "final_review": "Test",
        }
        mock_get_llm.return_value = Mock()
        
        agent = ProjectManagerAgent()
        
        assert agent.name == "pm"
        assert agent.llm is not None
    
    @patch('graphs.dev_team.agents.analyst.get_llm_with_fallback')
    @patch('graphs.dev_team.agents.analyst.load_prompts')
    def test_analyst_initialization(self, mock_load_prompts, mock_get_llm):
        """Test Analyst agent initialization."""
        mock_load_prompts.return_value = {
            "system": "Test",
            "requirements_gathering": "Test",
        }
        mock_get_llm.return_value = Mock()
        
        agent = AnalystAgent()
        
        assert agent.name == "analyst"
    
    @patch('graphs.dev_team.agents.architect.get_llm_with_fallback')
    @patch('graphs.dev_team.agents.architect.load_prompts')
    def test_architect_initialization(self, mock_load_prompts, mock_get_llm):
        """Test Architect agent initialization."""
        mock_load_prompts.return_value = {
            "system": "Test",
            "architecture_design": "Test",
            "implementation_spec": "Test",
        }
        mock_get_llm.return_value = Mock()
        
        agent = ArchitectAgent()
        
        assert agent.name == "architect"
    
    @patch('graphs.dev_team.agents.developer.get_llm_with_fallback')
    @patch('graphs.dev_team.agents.developer.load_prompts')
    def test_developer_initialization(self, mock_load_prompts, mock_get_llm):
        """Test Developer agent initialization."""
        mock_load_prompts.return_value = {
            "system": "Test",
            "implementation": "Test",
            "fix_issues": "Test",
        }
        mock_get_llm.return_value = Mock()
        
        agent = DeveloperAgent()
        
        assert agent.name == "developer"
    
    @patch('graphs.dev_team.agents.qa.get_llm_with_fallback')
    @patch('graphs.dev_team.agents.qa.load_prompts')
    def test_qa_initialization(self, mock_load_prompts, mock_get_llm):
        """Test QA agent initialization."""
        mock_load_prompts.return_value = {
            "system": "Test",
            "code_review": "Test",
            "verify_fixes": "Test",
            "final_approval": "Test",
        }
        mock_get_llm.return_value = Mock()
        
        agent = QAAgent()
        
        assert agent.name == "qa"



class TestAgentPrompts:
    """Test that agent prompts can be loaded."""
    
    def test_all_prompts_exist(self):
        """Verify all agent prompt files exist."""
        from pathlib import Path
        
        prompts_dir = Path("graphs/dev_team/prompts")
        
        expected_prompts = ["pm.yaml", "analyst.yaml", "architect.yaml", "developer.yaml", "qa.yaml"]
        
        for prompt_file in expected_prompts:
            assert (prompts_dir / prompt_file).exists(), f"Missing prompt file: {prompt_file}"
