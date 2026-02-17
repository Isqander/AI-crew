"""
DevOps Agent Tests
==================

Unit tests for:
  - DevOpsAgent (infrastructure generation, parsing)
  - devops_agent node function
  - Graph routing (route_after_reviewer with devops, route_after_architect_escalation)
  - Prompt loading
  - _sanitize_app_name utility
  - _header_to_filepath utility
  - JSON / code-block parsing

All LLM calls are mocked.
"""

import json
from unittest.mock import Mock, patch

import pytest


# ==================================================================
# 1. Utility function tests
# ==================================================================


class TestSanitizeAppName:
    """Test the _sanitize_app_name utility."""

    def test_basic_task(self):
        from dev_team.agents.devops import _sanitize_app_name
        assert _sanitize_app_name("Build a TODO app with React") == "build-a-todo-app-with"

    def test_empty_task(self):
        from dev_team.agents.devops import _sanitize_app_name
        assert _sanitize_app_name("") == "app"

    def test_special_characters(self):
        from dev_team.agents.devops import _sanitize_app_name
        result = _sanitize_app_name("Create #1 best app!!!")
        assert result == "create-1-best-app"

    def test_long_task(self):
        from dev_team.agents.devops import _sanitize_app_name
        result = _sanitize_app_name("Build a very long task description with many words here")
        # Should take only first 5 words
        assert result == "build-a-very-long-task"

    def test_unicode_stripped(self):
        from dev_team.agents.devops import _sanitize_app_name
        result = _sanitize_app_name("Создать приложение")
        # Cyrillic stripped -> empty -> fallback "app"
        assert result == "app"


class TestHeaderToFilepath:
    """Test the _header_to_filepath utility."""

    def test_dockerfile(self):
        from dev_team.agents.devops import _header_to_filepath
        assert _header_to_filepath("Dockerfile") == "Dockerfile"
        assert _header_to_filepath("1. Dockerfile") == "Dockerfile"

    def test_docker_compose(self):
        from dev_team.agents.devops import _header_to_filepath
        assert _header_to_filepath("docker-compose.prod.yml") == "docker-compose.prod.yml"
        assert _header_to_filepath("Docker Compose Production") == "docker-compose.prod.yml"
        assert _header_to_filepath("docker-compose") == "docker-compose.yml"

    def test_deploy_workflow(self):
        from dev_team.agents.devops import _header_to_filepath
        assert _header_to_filepath("GitHub Actions deploy workflow") == ".github/workflows/deploy.yml"
        assert _header_to_filepath("deploy.yml") == ".github/workflows/deploy.yml"

    def test_pre_commit(self):
        from dev_team.agents.devops import _header_to_filepath
        assert _header_to_filepath(".pre-commit-config.yaml") == ".pre-commit-config.yaml"

    def test_nginx(self):
        from dev_team.agents.devops import _header_to_filepath
        assert _header_to_filepath("Nginx config") == "nginx.conf"

    def test_file_path(self):
        from dev_team.agents.devops import _header_to_filepath
        assert _header_to_filepath("src/config.json") == "src/config.json"

    def test_unknown(self):
        from dev_team.agents.devops import _header_to_filepath
        assert _header_to_filepath("Some random text") is None


# ==================================================================
# 2. DevOpsAgent class tests
# ==================================================================


class TestDevOpsAgent:
    """Test the DevOpsAgent class with mocked LLM."""

    @pytest.fixture
    def agent(self):
        """Create a DevOpsAgent with mocked LLM."""
        with patch("dev_team.agents.devops.get_llm_with_fallback") as mock_get_llm:
            mock_llm = Mock()
            mock_get_llm.return_value = mock_llm
            from dev_team.agents.devops import DevOpsAgent
            agent = DevOpsAgent()
            agent.llm = mock_llm
            return agent

    @pytest.fixture
    def sample_state(self):
        """State with code files for DevOps."""
        return {
            "task": "Create a REST API for user management",
            "tech_stack": ["python", "fastapi", "postgresql"],
            "code_files": [
                {
                    "path": "main.py",
                    "content": "from fastapi import FastAPI\napp = FastAPI()\n",
                    "language": "python",
                },
                {
                    "path": "requirements.txt",
                    "content": "fastapi>=0.115.0\nuvicorn>=0.30.0\n",
                    "language": "",
                },
            ],
            "architecture": {"type": "REST API", "database": "PostgreSQL"},
            "requirements": ["User CRUD", "JWT auth", "PostgreSQL storage"],
            "current_agent": "devops",
            "needs_clarification": False,
            "user_stories": [],
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
        """State without code files."""
        return {
            "task": "Create something",
            "tech_stack": [],
            "code_files": [],
            "architecture": {},
            "requirements": [],
            "current_agent": "devops",
            "needs_clarification": False,
            "user_stories": [],
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

    # --- generate_infra tests ---

    def test_generate_infra_no_code(self, agent, sample_state_empty):
        """DevOps should skip when no code files."""
        result = agent.generate_infra(sample_state_empty)
        assert result["infra_files"] == []
        assert result["deploy_url"] == ""
        assert result["current_agent"] == "devops"
        assert len(result["messages"]) == 1
        assert "no code files" in result["messages"][0].content.lower()

    def test_generate_infra_json_response(self, agent, sample_state):
        """DevOps parses a JSON LLM response correctly."""
        llm_response_text = json.dumps({
            "infra_files": [
                {"path": "Dockerfile", "content": "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nCMD [\"uvicorn\", \"main:app\"]"},
                {"path": "docker-compose.prod.yml", "content": "version: '3.8'\nservices:\n  app:\n    build: .\n    ports:\n      - 8000:8000"},
                {"path": ".github/workflows/deploy.yml", "content": "name: Deploy\non:\n  push:\n    branches: [main]"},
            ],
            "deploy_url": "https://create-a-rest-api.31.59.58.143.nip.io",
            "env_vars_needed": ["DATABASE_URL", "SECRET_KEY"],
            "notes": "Deploy via SSH to VPS",
        })

        from langchain_core.messages import AIMessage as LCAIMessage
        mock_response = LCAIMessage(content=llm_response_text)

        with patch("dev_team.agents.base.invoke_with_retry", return_value=mock_response):
            result = agent.generate_infra(sample_state)

        assert len(result["infra_files"]) == 3
        assert result["deploy_url"] == "https://create-a-rest-api.31.59.58.143.nip.io"
        assert result["current_agent"] == "devops"
        assert any("Dockerfile" in f["path"] for f in result["infra_files"])
        assert any("docker-compose" in f["path"] for f in result["infra_files"])
        assert any("deploy.yml" in f["path"] for f in result["infra_files"])

    def test_generate_infra_markdown_response(self, agent, sample_state):
        """DevOps handles code-block formatted LLM response."""
        llm_response_text = """Here are the infrastructure files:

### Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]
```

### docker-compose.prod.yml
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - 8000:8000
```

### GitHub Actions deploy workflow
```yaml
name: Deploy
on:
  push:
    branches: [main]
```
"""
        from langchain_core.messages import AIMessage as LCAIMessage
        mock_response = LCAIMessage(content=llm_response_text)

        with patch("dev_team.agents.base.invoke_with_retry", return_value=mock_response):
            result = agent.generate_infra(sample_state)

        assert len(result["infra_files"]) == 3
        paths = [f["path"] for f in result["infra_files"]]
        assert "Dockerfile" in paths
        assert "docker-compose.prod.yml" in paths
        assert ".github/workflows/deploy.yml" in paths

    def test_generate_infra_json_in_markdown_fences(self, agent, sample_state):
        """DevOps handles JSON wrapped in markdown code fences."""
        json_data = {
            "infra_files": [
                {"path": "Dockerfile", "content": "FROM node:20-alpine"},
            ],
            "deploy_url": "https://app.10.0.0.1.nip.io",
            "env_vars_needed": [],
            "notes": "Minimal setup",
        }
        llm_response_text = f"```json\n{json.dumps(json_data)}\n```"

        from langchain_core.messages import AIMessage as LCAIMessage
        mock_response = LCAIMessage(content=llm_response_text)

        with patch("dev_team.agents.base.invoke_with_retry", return_value=mock_response):
            result = agent.generate_infra(sample_state)

        assert len(result["infra_files"]) == 1
        assert result["infra_files"][0]["path"] == "Dockerfile"
        assert result["deploy_url"] == "https://app.10.0.0.1.nip.io"


# ==================================================================
# 3. JSON / code-block parsing tests
# ==================================================================


class TestDevOpsResponseParsing:
    """Test the parsing utilities of DevOpsAgent."""

    def test_extract_json_from_raw(self):
        from dev_team.agents.devops import DevOpsAgent
        data = DevOpsAgent._extract_json('{"infra_files": [], "deploy_url": "x"}')
        assert data is not None
        assert data["deploy_url"] == "x"

    def test_extract_json_from_fenced(self):
        from dev_team.agents.devops import DevOpsAgent
        content = '```json\n{"infra_files": [{"path": "Dockerfile", "content": "FROM node"}]}\n```'
        data = DevOpsAgent._extract_json(content)
        assert data is not None
        assert len(data["infra_files"]) == 1

    def test_extract_json_invalid(self):
        from dev_team.agents.devops import DevOpsAgent
        data = DevOpsAgent._extract_json("no json here at all")
        assert data is None

    def test_parse_code_blocks_basic(self):
        from dev_team.agents.devops import DevOpsAgent
        content = """### Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
```

### docker-compose.prod.yml
```yaml
version: '3.8'
```
"""
        result = DevOpsAgent._parse_code_blocks(content, "test-app", "10.0.0.1")
        assert len(result.infra_files) == 2
        assert result.infra_files[0].path == "Dockerfile"
        assert result.infra_files[1].path == "docker-compose.prod.yml"
        assert result.deploy_url == "https://test-app.10.0.0.1.nip.io"


# ==================================================================
# 4. Node function tests
# ==================================================================


class TestDevOpsNodeFunction:
    """Test the devops_agent node function."""

    def test_node_function_invokes_agent(self):
        """The node function should invoke DevOpsAgent.generate_infra."""
        with patch("dev_team.agents.devops.get_devops_agent") as mock_get:
            mock_agent = Mock()
            mock_agent.generate_infra.return_value = {
                "infra_files": [{"path": "Dockerfile", "content": "FROM python:3.12"}],
                "deploy_url": "https://app.nip.io",
                "current_agent": "devops",
                "messages": [],
            }
            mock_get.return_value = mock_agent

            from dev_team.agents.devops import devops_agent
            state = {"task": "test", "code_files": []}
            result = devops_agent(state)

            mock_agent.generate_infra.assert_called_once()
            assert result["deploy_url"] == "https://app.nip.io"

    def test_node_function_passes_config(self):
        """Config (Langfuse callbacks) should be forwarded."""
        with patch("dev_team.agents.devops.get_devops_agent") as mock_get:
            mock_agent = Mock()
            mock_agent.generate_infra.return_value = {
                "infra_files": [],
                "deploy_url": "",
                "current_agent": "devops",
                "messages": [],
            }
            mock_get.return_value = mock_agent

            from dev_team.agents.devops import devops_agent
            config = {"callbacks": ["test_cb"]}
            devops_agent({"task": "t"}, config=config)

            _, kwargs = mock_agent.generate_infra.call_args
            assert kwargs["config"] == config


# ==================================================================
# 5. Graph routing tests
# ==================================================================


class TestRoutingWithDevOps:
    """Test graph routing with DevOps agent enabled/disabled."""

    def test_route_after_reviewer_to_devops_enabled(self):
        """When approved and USE_DEVOPS_AGENT=True, route to devops."""
        with patch("dev_team.graph.USE_DEVOPS_AGENT", True):
            from dev_team.graph import route_after_reviewer
            state = {
                "issues_found": [],
                "test_results": {"approved": True},
                "review_iteration_count": 0,
                "architect_escalated": False,
            }
            result = route_after_reviewer(state)
            assert result == "devops"

    def test_route_after_reviewer_to_git_commit_disabled(self):
        """When approved and USE_DEVOPS_AGENT=False, route to git_commit."""
        with patch("dev_team.graph.USE_DEVOPS_AGENT", False):
            from dev_team.graph import route_after_reviewer
            state = {
                "issues_found": [],
                "test_results": {"approved": True},
                "review_iteration_count": 0,
                "architect_escalated": False,
            }
            result = route_after_reviewer(state)
            assert result == "git_commit"

    def test_route_after_reviewer_issues_to_developer(self):
        """Issues found should route back to developer."""
        from dev_team.graph import route_after_reviewer
        state = {
            "issues_found": ["bug found"],
            "review_iteration_count": 1,
            "architect_escalated": False,
        }
        result = route_after_reviewer(state)
        assert result == "developer"

    def test_route_after_architect_escalation_to_devops(self):
        """Architect escalation approved with DevOps enabled -> devops."""
        with patch("dev_team.graph.USE_DEVOPS_AGENT", True):
            from dev_team.graph import route_after_architect_escalation
            state = {"test_results": {"approved": True}}
            result = route_after_architect_escalation(state)
            assert result == "devops"

    def test_route_after_architect_escalation_to_git_commit(self):
        """Architect escalation approved with DevOps disabled -> git_commit."""
        with patch("dev_team.graph.USE_DEVOPS_AGENT", False):
            from dev_team.graph import route_after_architect_escalation
            state = {"test_results": {"approved": True}}
            result = route_after_architect_escalation(state)
            assert result == "git_commit"


# ==================================================================
# 6. Prompt loading tests
# ==================================================================


class TestDevOpsPrompts:
    """Test that devops prompts load correctly."""

    def test_prompts_load(self):
        from dev_team.agents.base import load_prompts
        prompts = load_prompts("devops")
        assert "system" in prompts
        assert "generate_infra" in prompts
        assert "analyse_existing_infra" in prompts

    def test_system_prompt_content(self):
        from dev_team.agents.base import load_prompts
        prompts = load_prompts("devops")
        assert "DevOps Engineer" in prompts["system"]
        assert "Dockerfile" in prompts["system"]
        assert "Traefik" in prompts["system"]

    def test_generate_infra_template_variables(self):
        from dev_team.agents.base import load_prompts
        prompts = load_prompts("devops")
        template = prompts["generate_infra"]
        assert "{task}" in template
        assert "{tech_stack}" in template
        assert "{deploy_ip}" in template
        assert "{app_name}" in template
        assert "{code_files}" in template


# ==================================================================
# 7. Schema tests
# ==================================================================


class TestDevOpsSchemas:
    """Test Pydantic schemas for DevOps agent."""

    def test_infra_file_output(self):
        from dev_team.agents.schemas import InfraFileOutput
        f = InfraFileOutput(path="Dockerfile", content="FROM python:3.12")
        assert f.path == "Dockerfile"
        assert f.content == "FROM python:3.12"

    def test_devops_response_defaults(self):
        from dev_team.agents.schemas import DevOpsResponse
        r = DevOpsResponse()
        assert r.infra_files == []
        assert r.deploy_url == ""
        assert r.env_vars_needed == []
        assert r.notes == ""

    def test_devops_response_full(self):
        from dev_team.agents.schemas import DevOpsResponse, InfraFileOutput
        r = DevOpsResponse(
            infra_files=[InfraFileOutput(path="Dockerfile", content="FROM node")],
            deploy_url="https://app.nip.io",
            env_vars_needed=["DB_URL"],
            notes="Ready to deploy",
        )
        assert len(r.infra_files) == 1
        assert r.deploy_url == "https://app.nip.io"

        d = r.model_dump()
        assert d["infra_files"][0]["path"] == "Dockerfile"


# ==================================================================
# 8. Git commit node with infra_files merge test
# ==================================================================


class TestGitCommitWithInfraFiles:
    """Test that git_commit_node merges infra_files into code_files."""

    def test_infra_files_merged(self):
        """infra_files should be merged into code_files for commit."""
        with patch("dev_team.tools.git_workspace.commit_and_create_pr") as mock_commit:
            mock_commit.return_value = {
                "pr_url": "https://github.com/test/repo/pull/1",
                "commit_sha": "abc123def456",
                "working_branch": "ai/test-branch",
                "files_committed": 3,
            }

            from common.git import make_git_commit_node
            node = make_git_commit_node("test")

            state = {
                "task": "Test task",
                "repository": "test/repo",
                "code_files": [
                    {"path": "main.py", "content": "print('hello')"},
                ],
                "infra_files": [
                    {"path": "Dockerfile", "content": "FROM python:3.12"},
                    {"path": "docker-compose.prod.yml", "content": "version: '3.8'"},
                ],
            }

            result = node(state)

            # Verify commit_and_create_pr received merged files
            call_args = mock_commit.call_args
            committed_files = call_args.kwargs.get("code_files") or call_args[1].get("code_files") or call_args[0][2]
            assert len(committed_files) == 3  # 1 code + 2 infra

    def test_infra_files_no_duplicates(self):
        """infra_files with same path as code_files should not duplicate."""
        with patch("dev_team.tools.git_workspace.commit_and_create_pr") as mock_commit:
            mock_commit.return_value = {
                "pr_url": "https://github.com/test/repo/pull/1",
                "commit_sha": "abc123def456",
                "working_branch": "ai/test-branch",
                "files_committed": 2,
            }

            from common.git import make_git_commit_node
            node = make_git_commit_node("test")

            state = {
                "task": "Test task",
                "repository": "test/repo",
                "code_files": [
                    {"path": "main.py", "content": "print('hello')"},
                    {"path": "Dockerfile", "content": "FROM python:3.12  # v1"},
                ],
                "infra_files": [
                    {"path": "Dockerfile", "content": "FROM python:3.12  # v2"},
                ],
            }

            node(state)

            call_args = mock_commit.call_args
            committed_files = call_args.kwargs.get("code_files") or call_args[1].get("code_files") or call_args[0][2]
            # Dockerfile from code_files takes priority (no duplicate)
            assert len(committed_files) == 2

    def test_empty_infra_files(self):
        """No infra_files should work normally."""
        with patch("dev_team.tools.git_workspace.commit_and_create_pr") as mock_commit:
            mock_commit.return_value = {
                "pr_url": "https://github.com/test/repo/pull/1",
                "commit_sha": "abc",
                "working_branch": "ai/b",
                "files_committed": 1,
            }

            from common.git import make_git_commit_node
            node = make_git_commit_node("test")

            state = {
                "task": "Test task",
                "repository": "test/repo",
                "code_files": [{"path": "main.py", "content": "x"}],
            }

            result = node(state)
            assert result["pr_url"] == "https://github.com/test/repo/pull/1"
