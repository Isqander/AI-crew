"""
Security Agent Tests
====================

Unit tests for:
  - SecurityAgent (static review, runtime check, parsing)
  - security_agent node function
  - Graph routing (route_after_developer)
  - Prompt loading

All LLM calls are mocked.
"""

from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest


# ==================================================================
# 1. SecurityAgent class tests
# ==================================================================


class TestSecurityAgent:
    """Test the SecurityAgent class with mocked LLM."""

    @pytest.fixture
    def agent(self):
        """Create a SecurityAgent with mocked LLM."""
        with patch("dev_team.agents.security.get_llm_with_fallback") as mock_get_llm:
            mock_llm = Mock()
            mock_get_llm.return_value = mock_llm
            from dev_team.agents.security import SecurityAgent
            agent = SecurityAgent()
            agent.llm = mock_llm
            return agent

    @pytest.fixture
    def sample_state_with_code(self):
        """State with code files for security review."""
        return {
            "task": "Create a user login API",
            "tech_stack": ["python", "fastapi", "postgresql"],
            "code_files": [
                {
                    "path": "main.py",
                    "content": 'import os\npassword = "hardcoded123"\nprint(password)',
                    "language": "python",
                },
                {
                    "path": "db.py",
                    "content": 'query = f"SELECT * FROM users WHERE id={user_id}"',
                    "language": "python",
                },
                {
                    "path": "requirements.txt",
                    "content": "fastapi>=0.115.0\nuvicorn>=0.30.0\npsycopg2-binary>=2.9.9",
                    "language": "",
                },
            ],
            "current_agent": "developer",
            "needs_clarification": False,
            "requirements": ["User login with JWT"],
            "user_stories": [],
            "architecture": {},
            "architecture_decisions": [],
            "implementation_notes": "",
            "review_comments": [],
            "test_results": {},
            "issues_found": [],
            "summary": "",
            "messages": [],
            "review_iteration_count": 0,
            "architect_escalated": False,
            "retry_count": 0,
        }

    @pytest.fixture
    def sample_state_empty(self):
        """State with no code files."""
        return {
            "task": "Test task",
            "tech_stack": [],
            "code_files": [],
            "current_agent": "developer",
            "needs_clarification": False,
            "requirements": [],
            "user_stories": [],
            "architecture": {},
            "architecture_decisions": [],
            "implementation_notes": "",
            "review_comments": [],
            "test_results": {},
            "issues_found": [],
            "summary": "",
            "messages": [],
            "review_iteration_count": 0,
            "architect_escalated": False,
            "retry_count": 0,
        }

    def test_static_review_with_issues(self, agent, sample_state_with_code):
        """Security review finds critical issues in code."""
        # Mock LLM response with security findings
        mock_response = Mock()
        mock_response.content = """
## Security Review Summary
**Overall Risk Level**: HIGH
**Total Findings**: 2 critical, 1 warnings, 1 info

## Critical Issues
- Hardcoded password found in main.py: `password = "hardcoded123"` — use environment variables instead
- SQL injection in db.py: `f"SELECT * FROM users WHERE id={user_id}"` — use parameterized queries

## Warnings
- Missing input validation on user_id parameter

## Informational
- Consider adding rate limiting to the login endpoint

## Dependencies
- Dependencies look clean
"""
        agent.llm.invoke = Mock(return_value=mock_response)

        # Use _invoke_chain mock
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.static_review(sample_state_with_code)

        assert "security_review" in result
        review = result["security_review"]
        assert review["risk_level"] == "HIGH"
        assert len(review["critical"]) == 2
        assert len(review["warnings"]) == 1
        assert len(review["info"]) == 1
        assert result["current_agent"] == "security"
        assert len(result["messages"]) == 1

    def test_static_review_clean_code(self, agent, sample_state_with_code):
        """Security review finds no issues."""
        mock_response = Mock()
        mock_response.content = """
## Security Review Summary
**Overall Risk Level**: LOW
**Total Findings**: 0 critical, 0 warnings, 0 info

## Critical Issues
- None found

## Warnings
- None found

## Informational
- No additional recommendations

## Dependencies
- Dependencies look clean
"""
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.static_review(sample_state_with_code)

        review = result["security_review"]
        assert review["risk_level"] == "LOW"
        assert len(review["critical"]) == 0
        assert len(review["warnings"]) == 0

    def test_static_review_no_code(self, agent, sample_state_empty):
        """Security review with no code files returns early."""
        result = agent.static_review(sample_state_empty)

        review = result["security_review"]
        assert review["risk_level"] == "LOW"
        assert review["summary"] == "No code files to review."
        assert result["current_agent"] == "security"

    def test_runtime_check_with_issues(self, agent):
        """Runtime check finds issues in infrastructure files."""
        state = {
            "task": "Deploy web app",
            "infra_files": [
                {
                    "path": "Dockerfile",
                    "content": "FROM python:3.11\nRUN pip install app\nUSER root\nEXPOSE 8000",
                },
                {
                    "path": "docker-compose.yml",
                    "content": "services:\n  app:\n    ports:\n      - '8000:8000'\n      - '5432:5432'",
                },
            ],
            "code_files": [],
            "current_agent": "devops",
            "needs_clarification": False,
        }

        mock_response = Mock()
        mock_response.content = """
## Security Review Summary
**Overall Risk Level**: MEDIUM

## Critical Issues
- None found

## Warnings
- Dockerfile runs as root — add USER directive with non-root user
- PostgreSQL port 5432 exposed to host — should be internal only

## Informational
- Consider using multi-stage build to reduce image size
"""
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.runtime_check(state)

        review = result["security_review"]
        assert review["risk_level"] == "MEDIUM"
        assert len(review["warnings"]) >= 1

    def test_runtime_check_no_infra(self, agent):
        """Runtime check with no infra files returns early."""
        state = {"task": "test", "infra_files": [], "code_files": [], "current_agent": "devops", "needs_clarification": False}
        result = agent.runtime_check(state)

        review = result["security_review"]
        assert review["risk_level"] == "LOW"
        assert "No infrastructure files" in review["summary"]


# ==================================================================
# 2. Parsing Tests
# ==================================================================


class TestSecurityReviewParsing:
    """Test the _parse_security_review static method."""

    def test_parse_high_risk(self):
        from dev_team.agents.security import SecurityAgent

        content = """
## Security Review Summary
**Overall Risk Level**: HIGH

## Critical Issues
- SQL injection in auth.py
- Hardcoded API key in config.py

## Warnings
- Missing CSRF protection
- Weak password policy

## Informational
- Consider adding Content-Security-Policy header
"""
        review = SecurityAgent._parse_security_review(content)

        assert review["risk_level"] == "HIGH"
        assert len(review["critical"]) == 2
        assert "SQL injection" in review["critical"][0]
        assert len(review["warnings"]) == 2
        assert len(review["info"]) == 1

    def test_parse_low_risk(self):
        from dev_team.agents.security import SecurityAgent

        content = """
## Security Review Summary
**Overall Risk Level**: LOW

## Critical Issues
- None found

## Warnings
- None found

## Informational
- None found
"""
        review = SecurityAgent._parse_security_review(content)

        assert review["risk_level"] == "LOW"
        assert len(review["critical"]) == 0
        assert len(review["warnings"]) == 0
        assert len(review["info"]) == 0

    def test_parse_critical_risk(self):
        from dev_team.agents.security import SecurityAgent

        content = """
**Overall Risk Level**: CRITICAL

## Critical Issues
- Remote code execution via eval()
- No authentication on admin endpoints
- Exposed database credentials in source

## Warnings
- None found

## Informational
- None found
"""
        review = SecurityAgent._parse_security_review(content)

        assert review["risk_level"] == "CRITICAL"
        assert len(review["critical"]) == 3

    def test_parse_medium_risk(self):
        from dev_team.agents.security import SecurityAgent

        content = """
**Overall Risk Level**: MEDIUM

## Critical Issues
- None found

## Warnings
- Missing rate limiting
- Session tokens not rotated

## Informational
- Add security headers
"""
        review = SecurityAgent._parse_security_review(content)

        assert review["risk_level"] == "MEDIUM"
        assert len(review["critical"]) == 0
        assert len(review["warnings"]) == 2
        assert len(review["info"]) == 1

    def test_parse_auto_summary(self):
        """When no explicit summary section, auto-generate one."""
        from dev_team.agents.security import SecurityAgent

        content = """
**Overall Risk Level**: LOW

## Critical Issues
- None found

## Warnings
- None found

## Informational
- None found
"""
        review = SecurityAgent._parse_security_review(content)
        assert "LOW risk" in review["summary"]
        assert "0 critical" in review["summary"]

    def test_parse_empty_content(self):
        from dev_team.agents.security import SecurityAgent

        review = SecurityAgent._parse_security_review("")
        assert review["risk_level"] == "LOW"
        assert len(review["critical"]) == 0

    def test_parse_malformed_content(self):
        """Gracefully handle unexpected LLM output."""
        from dev_team.agents.security import SecurityAgent

        content = "This is not a properly formatted security review at all."
        review = SecurityAgent._parse_security_review(content)

        # Should not crash, returns defaults
        assert review["risk_level"] == "LOW"
        assert isinstance(review["critical"], list)


# ==================================================================
# 3. Dependency Extraction Tests
# ==================================================================


class TestDependencyExtraction:
    """Test the _extract_dependencies helper."""

    def test_extract_requirements_txt(self):
        from dev_team.agents.security import SecurityAgent

        code_files = [
            {"path": "main.py", "content": "print('hello')"},
            {"path": "requirements.txt", "content": "flask>=2.0\nrequests>=2.28"},
            {"path": "utils.py", "content": "# utils"},
        ]

        result = SecurityAgent._extract_dependencies(code_files)
        assert "requirements.txt" in result
        assert "flask" in result

    def test_extract_package_json(self):
        from dev_team.agents.security import SecurityAgent

        code_files = [
            {"path": "index.js", "content": "console.log('hi')"},
            {"path": "package.json", "content": '{"dependencies": {"express": "^4.18"}}'},
        ]

        result = SecurityAgent._extract_dependencies(code_files)
        assert "package.json" in result
        assert "express" in result

    def test_extract_go_mod(self):
        from dev_team.agents.security import SecurityAgent

        code_files = [
            {"path": "main.go", "content": "package main"},
            {"path": "go.mod", "content": "module example.com/app\ngo 1.22"},
        ]

        result = SecurityAgent._extract_dependencies(code_files)
        assert "go.mod" in result

    def test_extract_no_deps(self):
        from dev_team.agents.security import SecurityAgent

        code_files = [
            {"path": "main.py", "content": "print('hello')"},
        ]

        result = SecurityAgent._extract_dependencies(code_files)
        assert result == ""

    def test_extract_nested_path(self):
        """Dependency file in a subdirectory."""
        from dev_team.agents.security import SecurityAgent

        code_files = [
            {"path": "backend/requirements.txt", "content": "django>=4.0"},
        ]

        result = SecurityAgent._extract_dependencies(code_files)
        assert "requirements.txt" in result


# ==================================================================
# 4. Graph Routing Tests
# ==================================================================


class TestRouteAfterDeveloper:
    """Test the route_after_developer conditional edge."""

    def test_route_to_security_first_pass(self):
        """On first pass (review_iteration_count=0), route to security_review."""
        from dev_team.graph import route_after_developer

        state = {"review_iteration_count": 0}
        with patch("dev_team.graph.USE_SECURITY_AGENT", True):
            result = route_after_developer(state)
            assert result == "security_review"

    def test_route_to_reviewer_fix_loop(self):
        """During fix loops (review_iteration_count > 0), skip security."""
        from dev_team.graph import route_after_developer

        state = {"review_iteration_count": 1}
        # Even with security enabled, skip on fix loops
        with patch("dev_team.graph.USE_SECURITY_AGENT", True):
            result = route_after_developer(state)
            assert result == "reviewer"

    def test_route_to_reviewer_security_disabled(self):
        """When security agent is disabled, always route to reviewer."""
        from dev_team.graph import route_after_developer

        state = {"review_iteration_count": 0}
        with patch("dev_team.graph.USE_SECURITY_AGENT", False):
            result = route_after_developer(state)
            assert result == "reviewer"


# ==================================================================
# 5. Node Function Tests
# ==================================================================


class TestSecurityAgentNode:
    """Test the security_agent node function."""

    @patch("dev_team.agents.security.get_security_agent")
    def test_node_calls_static_review(self, mock_get_agent):
        """Node function invokes static_review and returns result."""
        from dev_team.agents.security import security_agent

        mock_agent = Mock()
        mock_agent.static_review.return_value = {
            "security_review": {
                "risk_level": "LOW",
                "critical": [],
                "warnings": [],
                "info": [],
                "summary": "Clean.",
            },
            "current_agent": "security",
            "messages": [],
        }
        mock_get_agent.return_value = mock_agent

        state = {"code_files": [], "task": "test"}
        result = security_agent(state)

        mock_agent.static_review.assert_called_once()
        assert result["current_agent"] == "security"

    @patch("dev_team.agents.security.get_security_agent")
    def test_node_passes_config(self, mock_get_agent):
        """Node function passes LangGraph config to agent."""
        from dev_team.agents.security import security_agent

        mock_agent = Mock()
        mock_agent.static_review.return_value = {
            "security_review": {"risk_level": "LOW", "critical": [], "warnings": [], "info": [], "summary": "ok"},
            "current_agent": "security",
            "messages": [],
        }
        mock_get_agent.return_value = mock_agent

        config = {"callbacks": ["langfuse_callback"]}
        security_agent({"code_files": [], "task": "test"}, config=config)

        # Verify config was passed through
        call_args = mock_agent.static_review.call_args
        assert call_args[1].get("config") == config or call_args[0][1] == config


# ==================================================================
# 6. Prompt Loading Tests
# ==================================================================


class TestSecurityPrompts:
    """Test that security prompts load correctly."""

    def test_prompts_file_exists(self):
        prompts_path = Path(__file__).parent.parent / "graphs" / "dev_team" / "prompts" / "security.yaml"
        assert prompts_path.exists(), f"Security prompts not found at {prompts_path}"

    def test_prompts_load(self):
        from dev_team.agents.base import load_prompts

        prompts = load_prompts("security")
        assert "system" in prompts
        assert "security_static_review" in prompts
        assert "security_runtime_check" in prompts
        assert "dependency_check" in prompts

    def test_prompts_have_placeholders(self):
        from dev_team.agents.base import load_prompts

        prompts = load_prompts("security")

        # Static review should have these placeholders
        assert "{task}" in prompts["security_static_review"]
        assert "{tech_stack}" in prompts["security_static_review"]
        assert "{code_files}" in prompts["security_static_review"]
        assert "{dependencies}" in prompts["security_static_review"]

        # Runtime check
        assert "{task}" in prompts["security_runtime_check"]
        assert "{infra_files}" in prompts["security_runtime_check"]

    def test_system_prompt_mentions_security(self):
        from dev_team.agents.base import load_prompts

        prompts = load_prompts("security")
        system = prompts["system"].lower()
        assert "security" in system
        assert "vulnerabilit" in system  # vulnerability/vulnerabilities
        assert "critical" in system


# ==================================================================
# 7. Integration: Graph compilation test
# ==================================================================


class TestGraphIntegration:
    """Test that the graph compiles correctly with the security node."""

    def test_graph_has_security_node(self):
        """Graph should include security_review node."""
        from dev_team.graph import graph

        # Get node names from the compiled graph
        node_names = list(graph.nodes.keys())
        assert "security_review" in node_names

    def test_graph_compiles(self):
        """Graph should compile without errors."""
        from dev_team.graph import create_graph

        builder = create_graph()
        compiled = builder.compile()
        assert compiled is not None

    def test_graph_topology_includes_security(self):
        """Graph JSON topology should mention security_review."""
        from dev_team.graph import graph

        topology = graph.get_graph().to_json()
        # The topology should have security_review as a node
        assert "security_review" in str(topology)
