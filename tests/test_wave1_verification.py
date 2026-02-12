"""
Wave 1 Verification Tests
=========================

Comprehensive tests to verify that all Wave 1 modules are correctly
implemented.  These tests are designed to run WITHOUT external services
(no PostgreSQL, no Aegra, no LLM API).

Run with:
    pytest tests/test_wave1_verification.py -v

Sections:
    1. structlog integration
    2. agents.yaml configuration
    3. Retry + Fallback
    4. Langfuse callback propagation
    5. manifest.yaml
    6. State extension (task_type, task_complexity)
    7. Gateway models & config
    8. Gateway auth (JWT logic, no DB)
    9. Gateway router (Switch-Agent stub)
    10. Web tools
    11. Telegram bot structure
    12. Docker / infrastructure files
    13. Frontend files
"""

import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import yaml


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
GRAPHS_DIR = PROJECT_ROOT / "graphs" / "dev_team"
GATEWAY_DIR = PROJECT_ROOT / "gateway"
CONFIG_DIR = PROJECT_ROOT / "config"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
TELEGRAM_DIR = PROJECT_ROOT / "telegram"

# Ensure project root is on sys.path for gateway imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ══════════════════════════════════════════════════════════════
# 1. structlog — Module 2.1
# ══════════════════════════════════════════════════════════════


class TestStructlog:
    """Verify structlog is properly integrated across all modules."""

    def test_logging_config_exists(self):
        """logging_config.py exists and has configure_logging()."""
        path = GRAPHS_DIR / "logging_config.py"
        assert path.exists(), f"Missing: {path}"
        content = path.read_text(encoding="utf-8")
        assert "configure_logging" in content
        assert "structlog" in content

    def test_logging_config_importable(self):
        """logging_config module can be imported."""
        from graphs.dev_team.logging_config import configure_logging
        assert callable(configure_logging)

    @pytest.mark.parametrize("module_path", [
        GRAPHS_DIR / "agents" / "base.py",
        GRAPHS_DIR / "agents" / "pm.py",
        GRAPHS_DIR / "agents" / "analyst.py",
        GRAPHS_DIR / "agents" / "architect.py",
        GRAPHS_DIR / "agents" / "developer.py",
        GRAPHS_DIR / "agents" / "qa.py",
        GRAPHS_DIR / "graph.py",
    ])
    def test_agent_uses_structlog(self, module_path: Path):
        """Each agent module uses structlog, not stdlib logging."""
        assert module_path.exists(), f"Missing: {module_path}"
        content = module_path.read_text(encoding="utf-8")
        assert "structlog" in content, f"{module_path.name} does not import structlog"
        assert "structlog.get_logger()" in content, \
            f"{module_path.name} does not use structlog.get_logger()"

    def test_github_tools_uses_structlog(self):
        """github.py should use structlog (known gap)."""
        path = GRAPHS_DIR / "tools" / "github.py"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        uses_structlog = "structlog.get_logger()" in content
        uses_stdlib = "logging.getLogger(" in content
        if uses_stdlib and not uses_structlog:
            pytest.xfail("github.py still uses stdlib logging — needs migration")

    def test_configure_logging_modes(self):
        """configure_logging() handles LOCAL and PRODUCTION modes."""
        from graphs.dev_team.logging_config import configure_logging

        with patch.dict(os.environ, {"ENV_MODE": "LOCAL", "LOG_LEVEL": "DEBUG"}):
            configure_logging()

        with patch.dict(os.environ, {"ENV_MODE": "PRODUCTION", "LOG_LEVEL": "INFO"}):
            configure_logging()


# ══════════════════════════════════════════════════════════════
# 2. agents.yaml — Module 2.2
# ══════════════════════════════════════════════════════════════


class TestAgentsYaml:
    """Verify agents.yaml configuration loading."""

    def test_agents_yaml_exists(self):
        """config/agents.yaml exists."""
        path = CONFIG_DIR / "agents.yaml"
        assert path.exists(), f"Missing: {path}"

    def test_agents_yaml_valid(self):
        """agents.yaml is valid YAML with required structure."""
        path = CONFIG_DIR / "agents.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "defaults" in data, "Missing 'defaults' section"
        assert "endpoints" in data, "Missing 'endpoints' section"
        assert "agents" in data, "Missing 'agents' section"

    def test_agents_yaml_has_all_roles(self):
        """agents.yaml defines configuration for all 5 agent roles."""
        path = CONFIG_DIR / "agents.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        agents = data.get("agents", {})
        required_roles = {"pm", "analyst", "architect", "developer", "qa"}
        actual_roles = set(agents.keys())
        missing = required_roles - actual_roles
        assert not missing, f"Missing agent roles in agents.yaml: {missing}"

    def test_agents_yaml_has_model_for_each(self):
        """Each agent in agents.yaml has a 'model' field."""
        path = CONFIG_DIR / "agents.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        agents = data.get("agents", {})
        for role, cfg in agents.items():
            assert "model" in cfg, f"Agent '{role}' has no 'model' field"

    def test_load_agent_config_function(self):
        """load_agent_config() works and returns cached result."""
        from graphs.dev_team.agents.base import load_agent_config, _reset_agent_config_cache
        _reset_agent_config_cache()
        config = load_agent_config()
        assert isinstance(config, dict)
        assert "agents" in config

        config2 = load_agent_config()
        assert config is config2  # Same object (cached)
        _reset_agent_config_cache()

    def test_load_agent_config_env_substitution(self):
        """Environment variables are substituted in agents.yaml."""
        from graphs.dev_team.agents.base import load_agent_config, _reset_agent_config_cache
        _reset_agent_config_cache()
        with patch.dict(os.environ, {"LLM_API_KEY": "test-key-12345"}):
            _reset_agent_config_cache()
            config = load_agent_config()
            raw_yaml = (CONFIG_DIR / "agents.yaml").read_text(encoding="utf-8")
            if "${LLM_API_KEY}" in raw_yaml:
                yaml_str = yaml.dump(config)
                assert "test-key-12345" in yaml_str or "${LLM_API_KEY}" not in yaml_str
        _reset_agent_config_cache()


# ══════════════════════════════════════════════════════════════
# 3. Retry + Fallback — Module 2.3
# ══════════════════════════════════════════════════════════════


class TestRetryFallback:
    """Verify retry and fallback mechanisms."""

    def test_invoke_with_retry_exists(self):
        """invoke_with_retry function exists and is importable."""
        from graphs.dev_team.agents.base import invoke_with_retry
        assert callable(invoke_with_retry)

    def test_get_llm_with_fallback_exists(self):
        """get_llm_with_fallback function exists."""
        from graphs.dev_team.agents.base import get_llm_with_fallback
        assert callable(get_llm_with_fallback)

    def test_invoke_with_retry_success(self):
        """invoke_with_retry succeeds on first attempt."""
        from graphs.dev_team.agents.base import invoke_with_retry

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "success"

        result = invoke_with_retry(mock_chain, {"input": "test"})
        assert result == "success"
        mock_chain.invoke.assert_called_once()

    def test_invoke_with_retry_retries_on_connection_error(self):
        """invoke_with_retry retries on ConnectionError."""
        from graphs.dev_team.agents.base import invoke_with_retry

        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = [ConnectionError("fail"), "success"]

        result = invoke_with_retry(mock_chain, {"input": "test"}, max_attempts=3)
        assert result == "success"
        assert mock_chain.invoke.call_count == 2

    def test_invoke_with_retry_passes_callbacks(self):
        """invoke_with_retry forwards callbacks from config."""
        from graphs.dev_team.agents.base import invoke_with_retry

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "ok"
        mock_callback = MagicMock()

        invoke_with_retry(
            mock_chain,
            {"input": "test"},
            config={"callbacks": [mock_callback]},
        )

        call_args = mock_chain.invoke.call_args
        config_arg = call_args[1].get("config", {})
        assert "callbacks" in config_arg, "Callbacks not forwarded to chain.invoke"
        assert mock_callback in config_arg["callbacks"]

    def test_invoke_with_retry_does_not_retry_value_error(self):
        """invoke_with_retry does NOT retry on non-transient errors."""
        from graphs.dev_team.agents.base import invoke_with_retry

        mock_chain = MagicMock()
        mock_chain.invoke.side_effect = ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            invoke_with_retry(mock_chain, {"input": "test"})
        assert mock_chain.invoke.call_count == 1

    def test_retryable_exceptions_defined(self):
        """RETRYABLE_EXCEPTIONS tuple includes expected exception types."""
        from graphs.dev_team.agents.base import RETRYABLE_EXCEPTIONS
        assert ConnectionError in RETRYABLE_EXCEPTIONS
        assert TimeoutError in RETRYABLE_EXCEPTIONS


# ══════════════════════════════════════════════════════════════
# 4. Langfuse Fix — Module 2.4
# ══════════════════════════════════════════════════════════════


class TestLangfuseFix:
    """Verify Langfuse callback propagation."""

    def test_base_agent_has_invoke_chain(self):
        """BaseAgent has _invoke_chain method."""
        from graphs.dev_team.agents.base import BaseAgent
        assert hasattr(BaseAgent, "_invoke_chain")

    def test_base_agent_has_get_callbacks(self):
        """BaseAgent has _get_callbacks static method."""
        from graphs.dev_team.agents.base import BaseAgent
        assert hasattr(BaseAgent, "_get_callbacks")
        assert isinstance(
            BaseAgent.__dict__["_get_callbacks"],
            staticmethod
        )

    def test_get_callbacks_extracts_from_config(self):
        """_get_callbacks correctly extracts callbacks from config."""
        from graphs.dev_team.agents.base import BaseAgent

        mock_cb = MagicMock()
        config = {"callbacks": [mock_cb]}
        result = BaseAgent._get_callbacks(config)
        assert result == [mock_cb]

    def test_get_callbacks_returns_empty_for_none(self):
        """_get_callbacks returns [] when config is None."""
        from graphs.dev_team.agents.base import BaseAgent
        assert BaseAgent._get_callbacks(None) == []

    @pytest.mark.parametrize("agent_file", [
        "pm.py", "analyst.py", "architect.py", "developer.py", "qa.py",
    ])
    def test_node_functions_accept_config(self, agent_file: str):
        """All agent node functions accept a 'config' parameter."""
        path = GRAPHS_DIR / "agents" / agent_file
        content = path.read_text(encoding="utf-8")
        assert "config" in content, \
            f"{agent_file}: node function should accept config parameter"


# ══════════════════════════════════════════════════════════════
# 5. manifest.yaml — Module 2.5
# ══════════════════════════════════════════════════════════════


class TestManifest:
    """Verify manifest.yaml structure and content."""

    def test_manifest_exists(self):
        """graphs/dev_team/manifest.yaml exists."""
        path = GRAPHS_DIR / "manifest.yaml"
        assert path.exists(), f"Missing: {path}"

    def test_manifest_valid_yaml(self):
        """manifest.yaml is valid YAML."""
        path = GRAPHS_DIR / "manifest.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_manifest_required_fields(self):
        """manifest.yaml has required fields."""
        path = GRAPHS_DIR / "manifest.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))

        required = ["name", "display_name", "description", "version",
                     "task_types", "agents"]
        for field in required:
            assert field in data, f"manifest.yaml missing '{field}'"

    def test_manifest_name_is_dev_team(self):
        """manifest.yaml name matches the graph directory."""
        path = GRAPHS_DIR / "manifest.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["name"] == "dev_team"

    def test_manifest_has_all_agents(self):
        """manifest.yaml lists all 5 agents."""
        path = GRAPHS_DIR / "manifest.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        agents = data.get("agents", [])
        agent_ids = {a["id"] for a in agents}
        expected = {"pm", "analyst", "architect", "developer", "qa"}
        missing = expected - agent_ids
        assert not missing, f"Missing agents in manifest: {missing}"

    def test_manifest_task_types(self):
        """manifest.yaml defines expected task types."""
        path = GRAPHS_DIR / "manifest.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        task_types = data.get("task_types", [])
        assert len(task_types) > 0, "No task types defined"
        for tt in ["feature", "bugfix"]:
            assert tt in task_types, f"Missing task_type: {tt}"


# ══════════════════════════════════════════════════════════════
# 6. State Extension — Module 2.12
# ══════════════════════════════════════════════════════════════


class TestStateExtension:
    """Verify task_type and task_complexity fields in DevTeamState."""

    def test_state_has_task_type(self):
        """DevTeamState type hints include task_type."""
        from graphs.dev_team.state import DevTeamState
        annotations = DevTeamState.__annotations__
        assert "task_type" in annotations, "Missing task_type in DevTeamState"

    def test_state_has_task_complexity(self):
        """DevTeamState type hints include task_complexity."""
        from graphs.dev_team.state import DevTeamState
        annotations = DevTeamState.__annotations__
        assert "task_complexity" in annotations, "Missing task_complexity in DevTeamState"

    def test_task_type_is_not_required(self):
        """task_type is NotRequired (optional)."""
        from graphs.dev_team.state import create_initial_state
        state = create_initial_state(task="test")
        assert "task_type" not in state

    def test_task_complexity_is_not_required(self):
        """task_complexity is NotRequired (optional)."""
        from graphs.dev_team.state import create_initial_state
        state = create_initial_state(task="test")
        assert "task_complexity" not in state

    def test_state_accepts_task_type(self):
        """State can be created with task_type set."""
        from graphs.dev_team.state import create_initial_state
        state = create_initial_state(task="test")
        state["task_type"] = "feature"
        assert state["task_type"] == "feature"

    def test_state_accepts_task_complexity(self):
        """State can be created with task_complexity set."""
        from graphs.dev_team.state import create_initial_state
        state = create_initial_state(task="test")
        state["task_complexity"] = 7
        assert state["task_complexity"] == 7


# ══════════════════════════════════════════════════════════════
# 7. Gateway Models & Config — Module 2.6
# ══════════════════════════════════════════════════════════════


class TestGatewayModels:
    """Verify Gateway Pydantic models."""

    def test_gateway_package_structure(self):
        """Gateway has required files."""
        required = [
            "main.py", "config.py", "models.py", "database.py",
            "auth.py", "proxy.py", "router.py",
        ]
        for fname in required:
            path = GATEWAY_DIR / fname
            assert path.exists(), f"Missing gateway/{fname}"

    def test_gateway_endpoints_directory(self):
        """Gateway has endpoints/ subdirectory with required files."""
        ep_dir = GATEWAY_DIR / "endpoints"
        assert ep_dir.exists(), "Missing gateway/endpoints/"
        assert (ep_dir / "graph.py").exists(), "Missing gateway/endpoints/graph.py"
        assert (ep_dir / "run.py").exists(), "Missing gateway/endpoints/run.py"

    def test_gateway_init_py_exists(self):
        """gateway/__init__.py exists (package marker)."""
        init = GATEWAY_DIR / "__init__.py"
        if not init.exists():
            pytest.xfail("gateway/__init__.py is MISSING — needs to be created")

    def test_gateway_endpoints_init_py_exists(self):
        """gateway/endpoints/__init__.py exists."""
        init = GATEWAY_DIR / "endpoints" / "__init__.py"
        if not init.exists():
            pytest.xfail("gateway/endpoints/__init__.py is MISSING — needs to be created")

    def test_gateway_models_importable(self):
        """Gateway models can be imported."""
        from gateway.models import (
            UserCreate, UserLogin, User, TokenPair,
            AuthResponse, RefreshRequest,
            GraphListItem, AgentConfig, PromptInfo,
            GraphTopologyResponse,
            CreateRunRequest, TaskClassification, RunResponse,
        )
        from pydantic import BaseModel
        for cls in [UserCreate, UserLogin, User, TokenPair, AuthResponse,
                    CreateRunRequest, RunResponse, TaskClassification]:
            assert issubclass(cls, BaseModel), f"{cls.__name__} is not a Pydantic model"

    def test_user_create_validation(self):
        """UserCreate validates email format."""
        from gateway.models import UserCreate
        user = UserCreate(email="test@example.com", password="12345678",
                         display_name="Test")
        assert user.email == "test@example.com"

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            UserCreate(email="not-an-email", password="12345678",
                      display_name="Test")

    def test_create_run_request_defaults(self):
        """CreateRunRequest has sensible defaults."""
        from gateway.models import CreateRunRequest
        req = CreateRunRequest(task="Build a landing page")
        assert req.task == "Build a landing page"
        assert req.graph_id is None
        assert req.execution_mode == "auto"
        assert req.thread_id is None


class TestGatewayConfig:
    """Verify Gateway configuration."""

    def test_settings_has_required_fields(self):
        """Settings has all required configuration fields."""
        from gateway.config import Settings
        fields = Settings.model_fields
        required_fields = [
            "aegra_url", "database_url", "jwt_secret",
            "jwt_access_ttl", "jwt_refresh_ttl", "cors_origins",
        ]
        for field in required_fields:
            assert field in fields, f"Missing field: {field}"

    def test_settings_defaults(self):
        """Settings has sensible defaults."""
        from gateway.config import Settings
        s = Settings(
            _env_file=None,
            aegra_url="http://test:8000",
            database_url="postgresql://test:test@localhost/test",
        )
        assert s.jwt_algorithm == "HS256"
        assert s.jwt_access_ttl == 1800
        assert isinstance(s.cors_origins, list)


# ══════════════════════════════════════════════════════════════
# 8. Gateway Auth (JWT) — Module 2.6
# ══════════════════════════════════════════════════════════════


class TestGatewayAuth:
    """Verify JWT auth logic (without database)."""

    def test_password_hashing(self):
        """Password hashing and verification works."""
        from gateway.auth import _hash_password, _verify_password
        hashed = _hash_password("testpassword123")
        assert hashed != "testpassword123"
        assert _verify_password("testpassword123", hashed)
        assert not _verify_password("wrongpassword", hashed)

    def test_jwt_create_and_decode(self):
        """JWT creation and decoding works."""
        from gateway.auth import _create_token, _decode_token
        token = _create_token("user-123", "test@test.com", "access")
        assert isinstance(token, str)

        payload = _decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@test.com"
        assert payload["type"] == "access"

    def test_jwt_refresh_token(self):
        """Refresh tokens have different type."""
        from gateway.auth import _create_token, _decode_token
        token = _create_token("user-123", "test@test.com", "refresh")
        payload = _decode_token(token)
        assert payload["type"] == "refresh"

    def test_jwt_invalid_token_raises(self):
        """Invalid JWT raises HTTPException."""
        from gateway.auth import _decode_token
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _decode_token("invalid.token.here")

    def test_jwt_has_expiration(self):
        """JWT tokens include expiration."""
        from gateway.auth import _create_token, _decode_token
        token = _create_token("user-123", "test@test.com", "access")
        payload = _decode_token(token)
        assert "exp" in payload
        assert "iat" in payload


# ══════════════════════════════════════════════════════════════
# 9. Gateway Router (Switch-Agent) — Module 2.6
# ══════════════════════════════════════════════════════════════


class TestGatewayRouter:
    """Verify Switch-Agent router stub."""

    @pytest.mark.asyncio
    async def test_classify_task_returns_dev_team(self):
        """Stub classifier always returns dev_team."""
        from gateway.router import classify_task
        result = await classify_task("Build a REST API", [])
        assert result.graph_id == "dev_team"
        assert result.complexity == 5
        assert isinstance(result.reasoning, str)

    @pytest.mark.asyncio
    async def test_classify_task_different_inputs(self):
        """Stub classifier returns same result for any input."""
        from gateway.router import classify_task
        r1 = await classify_task("Fix a bug", [])
        r2 = await classify_task("Design microservices architecture", [])
        assert r1.graph_id == r2.graph_id == "dev_team"


# ══════════════════════════════════════════════════════════════
# 10. Web Tools — Module 2.10
# ══════════════════════════════════════════════════════════════


class TestWebTools:
    """Verify web tools definition."""

    def test_web_tools_file_exists(self):
        """tools/web.py exists."""
        path = GRAPHS_DIR / "tools" / "web.py"
        assert path.exists(), f"Missing: {path}"

    def test_web_tools_importable(self):
        """Web tools can be imported."""
        from graphs.dev_team.tools.web import web_search, fetch_url, download_file
        # LangChain @tool creates StructuredTool instances
        for tool_fn in [web_search, fetch_url, download_file]:
            assert tool_fn is not None
            assert hasattr(tool_fn, "invoke"), f"{tool_fn} is not invokable"

    def test_web_tools_are_langchain_tools(self):
        """Web tools are decorated with @tool (StructuredTool)."""
        from graphs.dev_team.tools.web import web_search, fetch_url, download_file
        from langchain_core.tools import BaseTool
        for tool_fn in [web_search, fetch_url, download_file]:
            assert isinstance(tool_fn, BaseTool), \
                f"{tool_fn} is not a LangChain BaseTool"
            assert hasattr(tool_fn, "name")
            assert hasattr(tool_fn, "description")

    def test_web_search_has_description(self):
        """web_search tool has a meaningful description."""
        from graphs.dev_team.tools.web import web_search
        assert len(web_search.description) > 10


# ══════════════════════════════════════════════════════════════
# 11. Telegram Bot — Module 2.11
# ══════════════════════════════════════════════════════════════


class TestTelegramBot:
    """Verify Telegram bot structure."""

    def test_telegram_directory_exists(self):
        """telegram/ directory exists."""
        assert TELEGRAM_DIR.exists(), f"Missing: {TELEGRAM_DIR}"

    def test_telegram_required_files(self):
        """Telegram bot has required files."""
        required = ["bot.py", "handlers.py", "gateway_client.py",
                     "Dockerfile", "requirements.txt"]
        for fname in required:
            path = TELEGRAM_DIR / fname
            assert path.exists(), f"Missing telegram/{fname}"

    def test_telegram_handlers_has_commands(self):
        """Telegram handlers define /start, /help, /task commands."""
        content = (TELEGRAM_DIR / "handlers.py").read_text(encoding="utf-8")
        for cmd in ["start", "help", "task"]:
            assert cmd in content, f"Missing /{cmd} command handler"

    def test_telegram_gateway_client(self):
        """Gateway client has expected methods."""
        content = (TELEGRAM_DIR / "gateway_client.py").read_text(encoding="utf-8")
        for method in ["login", "create_run"]:
            assert method in content, f"Missing method: {method}"


# ══════════════════════════════════════════════════════════════
# 12. Infrastructure — Docker, env, requirements
# ══════════════════════════════════════════════════════════════


class TestInfrastructure:
    """Verify Docker and infrastructure files."""

    def test_docker_compose_exists(self):
        """docker-compose.yml exists and is valid YAML."""
        path = PROJECT_ROOT / "docker-compose.yml"
        assert path.exists()
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "services" in data

    def test_docker_compose_services(self):
        """docker-compose.yml defines all required services."""
        path = PROJECT_ROOT / "docker-compose.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        services = set(data.get("services", {}).keys())
        required = {"postgres", "aegra", "gateway", "langfuse", "frontend"}
        missing = required - services
        assert not missing, f"Missing Docker services: {missing}"

    def test_aegra_not_exposed_externally(self):
        """Aegra service uses 'expose' (not 'ports') — internal only."""
        path = PROJECT_ROOT / "docker-compose.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        aegra = data["services"].get("aegra", {})
        assert "ports" not in aegra, \
            "Aegra should NOT have 'ports' (use 'expose' only)"
        assert "expose" in aegra, \
            "Aegra should have 'expose' for internal access"

    def test_gateway_has_ports(self):
        """Gateway service exposes port 8080."""
        path = PROJECT_ROOT / "docker-compose.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        gateway = data["services"].get("gateway", {})
        ports = gateway.get("ports", [])
        assert any("8080" in str(p) for p in ports), \
            "Gateway should expose port 8080"

    def test_gateway_dockerfile_exists(self):
        """gateway/Dockerfile exists."""
        assert (GATEWAY_DIR / "Dockerfile").exists()

    def test_gateway_dockerfile_installs_correct_deps(self):
        """Gateway Dockerfile installs gateway-specific deps (PyJWT, bcrypt)."""
        dockerfile = (GATEWAY_DIR / "Dockerfile").read_text(encoding="utf-8")
        # The Dockerfile should either:
        # 1. COPY and install gateway/requirements.txt, OR
        # 2. Use a requirements.txt that includes PyJWT and bcrypt
        if "gateway/requirements.txt" in dockerfile or "requirements.txt" in dockerfile:
            # Check which requirements.txt it actually installs
            # Since docker-compose context is ".", and Dockerfile copies requirements.txt
            # it copies the ROOT requirements.txt. Check if it has PyJWT.
            root_reqs = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
            gateway_reqs = (GATEWAY_DIR / "requirements.txt").read_text(encoding="utf-8").lower()
            if "pyjwt" not in root_reqs and "pyjwt" in gateway_reqs:
                pytest.xfail(
                    "Gateway Dockerfile installs root requirements.txt which lacks "
                    "PyJWT and bcrypt — needs to also install gateway/requirements.txt"
                )

    def test_gateway_requirements_has_jwt(self):
        """gateway/requirements.txt includes PyJWT and bcrypt."""
        path = GATEWAY_DIR / "requirements.txt"
        assert path.exists()
        content = path.read_text(encoding="utf-8").lower()
        assert "pyjwt" in content, "gateway/requirements.txt missing PyJWT"
        assert "bcrypt" in content, "gateway/requirements.txt missing bcrypt"

    def test_env_example_exists(self):
        """env.example exists with key variables."""
        path = PROJECT_ROOT / "env.example"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        for var in ["JWT_SECRET", "LLM_API_KEY"]:
            assert var in content, f"env.example missing {var}"

    def test_root_requirements_has_structlog(self):
        """Root requirements.txt includes structlog."""
        path = PROJECT_ROOT / "requirements.txt"
        content = path.read_text(encoding="utf-8").lower()
        assert "structlog" in content

    def test_root_requirements_has_web_tools_deps(self):
        """Root requirements.txt includes web tools dependencies."""
        path = PROJECT_ROOT / "requirements.txt"
        content = path.read_text(encoding="utf-8").lower()
        assert "duckduckgo-search" in content
        assert "trafilatura" in content


# ══════════════════════════════════════════════════════════════
# 13. Frontend Files Verification
# ══════════════════════════════════════════════════════════════


class TestFrontendFiles:
    """Verify frontend file structure (no build required)."""

    def test_frontend_src_exists(self):
        """frontend/src/ exists."""
        assert (FRONTEND_DIR / "src").exists()

    @pytest.mark.parametrize("file_path", [
        "src/store/authStore.ts",
        "src/hooks/useAuth.ts",
        "src/hooks/useStreamingTask.ts",
        "src/pages/Login.tsx",
        "src/pages/Register.tsx",
        "src/components/GraphVisualization.tsx",
        "src/api/aegra.ts",
    ])
    def test_frontend_file_exists(self, file_path: str):
        """Required frontend files exist."""
        path = FRONTEND_DIR / file_path
        assert path.exists(), f"Missing: frontend/{file_path}"

    def test_auth_store_has_zustand(self):
        """authStore uses Zustand with persist."""
        content = (FRONTEND_DIR / "src/store/authStore.ts").read_text(encoding="utf-8")
        assert "zustand" in content, "authStore should use zustand"
        assert "persist" in content, "authStore should use persist middleware"

    def test_login_page_has_form(self):
        """Login page has email and password fields."""
        content = (FRONTEND_DIR / "src/pages/Login.tsx").read_text(encoding="utf-8")
        assert "email" in content.lower()
        assert "password" in content.lower()

    def test_register_page_has_form(self):
        """Register page has display name, email, password fields."""
        content = (FRONTEND_DIR / "src/pages/Register.tsx").read_text(encoding="utf-8")
        assert "email" in content.lower()
        assert "password" in content.lower()

    def test_api_client_uses_gateway(self):
        """API client points to Gateway (port 8080), not Aegra (8000)."""
        content = (FRONTEND_DIR / "src/api/aegra.ts").read_text(encoding="utf-8")
        assert "8080" in content or "VITE_API_URL" in content, \
            "API client should use Gateway (8080) or VITE_API_URL"

    def test_api_client_sends_auth_header(self):
        """API client includes Authorization header."""
        content = (FRONTEND_DIR / "src/api/aegra.ts").read_text(encoding="utf-8")
        assert "Authorization" in content
        assert "Bearer" in content

    def test_graph_visualization_uses_react_flow(self):
        """GraphVisualization uses @xyflow/react."""
        content = (FRONTEND_DIR / "src/components/GraphVisualization.tsx").read_text(
            encoding="utf-8"
        )
        assert "xyflow" in content or "ReactFlow" in content

    def test_vite_config_proxy_target(self):
        """Vite config proxy should point to Gateway, not Aegra directly."""
        content = (FRONTEND_DIR / "vite.config.ts").read_text(encoding="utf-8")
        if "localhost:8000" in content and "localhost:8080" not in content:
            pytest.xfail(
                "Vite proxy points to Aegra (8000) instead of Gateway (8080)"
            )

    def test_package_json_has_dependencies(self):
        """package.json has required dependencies."""
        pkg = json.loads(
            (FRONTEND_DIR / "package.json").read_text(encoding="utf-8")
        )
        deps = pkg.get("dependencies", {})
        required = ["react", "react-dom", "zustand", "@xyflow/react",
                     "react-router-dom"]
        for dep in required:
            assert dep in deps, f"Missing dependency: {dep}"
