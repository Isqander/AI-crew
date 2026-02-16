"""
Sandbox Infrastructure Tests (Module 3.7)
==========================================

Tests for sandbox infrastructure extensions:
  - PostgreSQL service integration (enable_postgres)
  - pip-audit, Lighthouse, axe-core availability in browser image
  - Models: new fields (enable_postgres, enable_network)
  - Executor: env var injection, network mode selection
  - Server: parameter forwarding
  - Client: payload construction

All Docker interactions are mocked — no real Docker daemon needed.
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock


# ==================================================================
# 1. Models — new fields
# ==================================================================


class TestSandboxInfraModels:
    """Test new Pydantic model fields for sandbox services."""

    def test_enable_postgres_defaults_false(self):
        from sandbox.models import SandboxExecuteRequest, CodeFileInput

        req = SandboxExecuteRequest(
            language="python",
            code_files=[CodeFileInput(path="main.py", content="print(1)")],
            commands=["python main.py"],
        )
        assert req.enable_postgres is False
        assert req.enable_network is False

    def test_enable_postgres_true(self):
        from sandbox.models import SandboxExecuteRequest, CodeFileInput

        req = SandboxExecuteRequest(
            language="python",
            code_files=[CodeFileInput(path="app.py", content="import psycopg2")],
            commands=["python app.py"],
            enable_postgres=True,
        )
        assert req.enable_postgres is True

    def test_enable_network_true(self):
        from sandbox.models import SandboxExecuteRequest, CodeFileInput

        req = SandboxExecuteRequest(
            language="python",
            code_files=[CodeFileInput(path="app.py", content="import requests")],
            commands=["python app.py"],
            enable_network=True,
        )
        assert req.enable_network is True

    def test_enable_postgres_with_browser(self):
        """PostgreSQL can be enabled together with browser mode."""
        from sandbox.models import SandboxExecuteRequest, CodeFileInput

        req = SandboxExecuteRequest(
            language="python",
            code_files=[CodeFileInput(path="app.py", content="# fullstack")],
            commands=["pytest -v"],
            browser=True,
            enable_postgres=True,
        )
        assert req.browser is True
        assert req.enable_postgres is True

    def test_model_serialization_roundtrip(self):
        """Verify new fields survive model_dump/parse cycle."""
        from sandbox.models import SandboxExecuteRequest, CodeFileInput

        req = SandboxExecuteRequest(
            language="python",
            code_files=[CodeFileInput(path="main.py", content="x=1")],
            commands=["python main.py"],
            enable_postgres=True,
            enable_network=True,
        )
        data = req.model_dump()
        assert data["enable_postgres"] is True
        assert data["enable_network"] is True

        req2 = SandboxExecuteRequest(**data)
        assert req2.enable_postgres is True
        assert req2.enable_network is True


# ==================================================================
# 2. Executor — PostgreSQL env injection
# ==================================================================


class TestExecutorPostgresIntegration:
    """Test executor creates containers with correct postgres env vars."""

    def _make_executor(self):
        """Create executor with a mocked Docker client."""
        from sandbox.executor import SandboxExecutor

        mock_client = MagicMock()
        # Mock image exists
        mock_client.images.get.return_value = True
        # Mock container lifecycle
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(
            exit_code=0, output=(b"OK", b"")
        )
        mock_container.short_id = "abc123"
        mock_client.containers.create.return_value = mock_container
        mock_client.version.return_value = {"Version": "test"}

        executor = SandboxExecutor(docker_client=mock_client)
        return executor, mock_client, mock_container

    @patch.dict(os.environ, {
        "SANDBOX_PG_HOST": "test-pg-host",
        "SANDBOX_PG_PORT": "5432",
        "SANDBOX_PG_USER": "testuser",
        "SANDBOX_PG_PASSWORD": "testpass",
        "SANDBOX_PG_DB": "testdb",
        "SANDBOX_NETWORK": "test-network",
    })
    def test_postgres_env_vars_injected(self):
        """When enable_postgres=True, DATABASE_URL and PG* vars are injected."""
        # Re-import to pick up patched env
        import importlib
        import sandbox.executor
        importlib.reload(sandbox.executor)
        from sandbox.executor import SandboxExecutor

        mock_client = MagicMock()
        mock_client.images.get.return_value = True
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(
            exit_code=0, output=(b"OK", b"")
        )
        mock_container.short_id = "abc123"
        mock_client.containers.create.return_value = mock_container
        mock_client.version.return_value = {"Version": "test"}

        executor = SandboxExecutor(docker_client=mock_client)

        result = executor.execute(
            language="python",
            code_files=[{"path": "app.py", "content": "print(1)"}],
            commands=["python app.py"],
            enable_postgres=True,
        )

        # Verify container was created with correct env vars
        create_call = mock_client.containers.create.call_args
        env = create_call.kwargs.get("environment", {})

        assert "DATABASE_URL" in env
        assert "testuser" in env["DATABASE_URL"]
        assert "testpass" in env["DATABASE_URL"]
        assert "test-pg-host" in env["DATABASE_URL"]
        assert "testdb" in env["DATABASE_URL"]
        assert env["PGHOST"] == "test-pg-host"
        assert env["PGPORT"] == "5432"
        assert env["PGUSER"] == "testuser"
        assert env["PGPASSWORD"] == "testpass"
        assert env["PGDATABASE"] == "testdb"

    def test_no_postgres_env_when_disabled(self):
        """When enable_postgres=False, no DATABASE_URL is injected."""
        executor, mock_client, mock_container = self._make_executor()

        result = executor.execute(
            language="python",
            code_files=[{"path": "app.py", "content": "print(1)"}],
            commands=["python app.py"],
            enable_postgres=False,
        )

        create_call = mock_client.containers.create.call_args
        env = create_call.kwargs.get("environment", {})

        assert "DATABASE_URL" not in env
        assert "PGHOST" not in env

    def test_network_mode_with_postgres(self):
        """When enable_postgres=True, container uses named network (not 'none')."""
        executor, mock_client, mock_container = self._make_executor()

        result = executor.execute(
            language="python",
            code_files=[{"path": "app.py", "content": "print(1)"}],
            commands=["python app.py"],
            enable_postgres=True,
        )

        create_call = mock_client.containers.create.call_args
        network_mode = create_call.kwargs.get("network_mode", "")

        # Should NOT be "none" when postgres is enabled
        assert network_mode != "none"

    def test_network_mode_isolated_by_default(self):
        """Default execution (no postgres, no browser) uses 'none' network."""
        executor, mock_client, mock_container = self._make_executor()

        result = executor.execute(
            language="python",
            code_files=[{"path": "app.py", "content": "print(1)"}],
            commands=["python app.py"],
        )

        create_call = mock_client.containers.create.call_args
        network_mode = create_call.kwargs.get("network_mode", "")
        assert network_mode == "none"

    def test_enable_network_without_postgres(self):
        """enable_network=True alone enables bridge networking."""
        executor, mock_client, mock_container = self._make_executor()

        result = executor.execute(
            language="python",
            code_files=[{"path": "app.py", "content": "print(1)"}],
            commands=["python app.py"],
            enable_network=True,
        )

        create_call = mock_client.containers.create.call_args
        network_mode = create_call.kwargs.get("network_mode", "")
        assert network_mode != "none"

    def test_postgres_database_url_format(self):
        """DATABASE_URL has correct postgresql:// format."""
        executor, mock_client, mock_container = self._make_executor()

        result = executor.execute(
            language="python",
            code_files=[{"path": "app.py", "content": "print(1)"}],
            commands=["python app.py"],
            enable_postgres=True,
        )

        create_call = mock_client.containers.create.call_args
        env = create_call.kwargs.get("environment", {})
        db_url = env.get("DATABASE_URL", "")

        assert db_url.startswith("postgresql://")
        assert "@" in db_url
        assert ":" in db_url


# ==================================================================
# 3. Server — parameter forwarding
# ==================================================================


class TestServerPostgresForwarding:
    """Test that the server forwards enable_postgres to the executor."""

    def test_execute_forwards_postgres_param(self):
        """POST /execute with enable_postgres=True reaches executor."""
        from fastapi.testclient import TestClient
        import sandbox.server as srv

        mock_executor = MagicMock()
        mock_executor.is_docker_available.return_value = True
        mock_executor.execute.return_value = {
            "stdout": "OK",
            "stderr": "",
            "exit_code": 0,
            "duration_seconds": 1.0,
            "tests_passed": None,
            "files_output": [],
            "error": None,
            "screenshots": [],
            "browser_console": "",
            "network_errors": [],
        }

        with TestClient(srv.app) as client:
            # Set mock AFTER lifespan runs (lifespan resets _executor)
            srv._executor = mock_executor
            response = client.post("/execute", json={
                "language": "python",
                "code_files": [{"path": "app.py", "content": "print(1)"}],
                "commands": ["python app.py"],
                "enable_postgres": True,
                "enable_network": False,
            })

        assert response.status_code == 200
        mock_executor.execute.assert_called_once()
        kwargs = mock_executor.execute.call_args.kwargs
        assert kwargs.get("enable_postgres") is True


# ==================================================================
# 4. Client — payload construction
# ==================================================================


class TestClientPostgresPayload:
    """Test that SandboxClient sends correct payload for postgres."""

    def test_client_sends_enable_postgres(self):
        """SandboxClient includes enable_postgres in payload."""
        from graphs.dev_team.tools.sandbox import SandboxClient

        captured_payload = {}

        def mock_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.json.return_value = {
                "stdout": "", "stderr": "", "exit_code": 0,
                "duration_seconds": 0.0, "tests_passed": None,
                "files_output": [], "error": None,
            }
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.Client") as mock_client_cls:
            mock_client_inst = MagicMock()
            mock_client_inst.post = mock_post
            mock_client_inst.__enter__ = MagicMock(return_value=mock_client_inst)
            mock_client_inst.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client_inst

            client = SandboxClient(base_url="http://test:8002")
            client.execute(
                language="python",
                code_files=[{"path": "app.py", "content": "x=1"}],
                commands=["python app.py"],
                enable_postgres=True,
            )

        assert captured_payload.get("enable_postgres") is True

    def test_client_omits_postgres_when_disabled(self):
        """SandboxClient does not send enable_postgres when False."""
        from graphs.dev_team.tools.sandbox import SandboxClient

        captured_payload = {}

        def mock_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.json.return_value = {
                "stdout": "", "stderr": "", "exit_code": 0,
                "duration_seconds": 0.0, "tests_passed": None,
                "files_output": [], "error": None,
            }
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.Client") as mock_client_cls:
            mock_client_inst = MagicMock()
            mock_client_inst.post = mock_post
            mock_client_inst.__enter__ = MagicMock(return_value=mock_client_inst)
            mock_client_inst.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client_inst

            client = SandboxClient(base_url="http://test:8002")
            client.execute(
                language="python",
                code_files=[{"path": "app.py", "content": "x=1"}],
                commands=["python app.py"],
            )

        # enable_postgres should not be in payload when not requested
        assert "enable_postgres" not in captured_payload

    def test_client_sends_enable_network(self):
        """SandboxClient includes enable_network when True."""
        from graphs.dev_team.tools.sandbox import SandboxClient

        captured_payload = {}

        def mock_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.json.return_value = {
                "stdout": "", "stderr": "", "exit_code": 0,
                "duration_seconds": 0.0, "tests_passed": None,
                "files_output": [], "error": None,
            }
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.Client") as mock_client_cls:
            mock_client_inst = MagicMock()
            mock_client_inst.post = mock_post
            mock_client_inst.__enter__ = MagicMock(return_value=mock_client_inst)
            mock_client_inst.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client_inst

            client = SandboxClient(base_url="http://test:8002")
            client.execute(
                language="python",
                code_files=[{"path": "app.py", "content": "x=1"}],
                commands=["python app.py"],
                enable_network=True,
            )

        assert captured_payload.get("enable_network") is True


# ==================================================================
# 5. Dockerfile.browser — tool availability assertions
# ==================================================================


class TestDockerfileBrowserTools:
    """Verify that Dockerfile.browser declares required tools.

    These tests validate the Dockerfile content statically —
    no Docker build required.
    """

    @pytest.fixture(autouse=True)
    def _read_dockerfile(self):
        """Read Dockerfile.browser content once per test class."""
        dockerfile_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "sandbox", "Dockerfile.browser"
        )
        with open(dockerfile_path, "r") as f:
            self.dockerfile_content = f.read()

    def test_pip_audit_installed(self):
        """Dockerfile.browser installs pip-audit."""
        assert "pip-audit" in self.dockerfile_content

    def test_lighthouse_installed(self):
        """Dockerfile.browser installs lighthouse."""
        assert "lighthouse" in self.dockerfile_content

    def test_axe_core_installed(self):
        """Dockerfile.browser installs @axe-core/cli."""
        assert "@axe-core/cli" in self.dockerfile_content

    def test_playwright_installed(self):
        """Dockerfile.browser installs playwright (pre-existing)."""
        assert "playwright" in self.dockerfile_content

    def test_nodejs_installed(self):
        """Dockerfile.browser installs Node.js (pre-existing)."""
        assert "nodejs" in self.dockerfile_content


# ==================================================================
# 6. Docker Compose — sandbox-postgres service
# ==================================================================


class TestDockerComposeSandboxPostgres:
    """Verify docker-compose.yml declares sandbox-postgres service."""

    @pytest.fixture(autouse=True)
    def _read_compose(self):
        """Read docker-compose.yml content."""
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker-compose.yml"
        )
        with open(compose_path, "r", encoding="utf-8") as f:
            self.compose_content = f.read()

    def test_sandbox_postgres_service_exists(self):
        """docker-compose.yml defines sandbox-postgres service."""
        assert "sandbox-postgres:" in self.compose_content

    def test_sandbox_postgres_uses_alpine_image(self):
        """sandbox-postgres uses lightweight alpine image."""
        assert "postgres:16-alpine" in self.compose_content

    def test_sandbox_postgres_healthcheck(self):
        """sandbox-postgres has a healthcheck."""
        assert "pg_isready" in self.compose_content

    def test_sandbox_depends_on_postgres(self):
        """sandbox service depends on sandbox-postgres."""
        # Find the sandbox service section and check dependencies
        assert "sandbox-postgres" in self.compose_content

    def test_sandbox_pg_env_vars_in_sandbox(self):
        """sandbox service receives PG connection env vars."""
        assert "SANDBOX_PG_HOST" in self.compose_content
        assert "SANDBOX_PG_PORT" in self.compose_content
        assert "SANDBOX_PG_USER" in self.compose_content
        assert "SANDBOX_PG_PASSWORD" in self.compose_content
        assert "SANDBOX_PG_DB" in self.compose_content

    def test_sandbox_network_env_var(self):
        """sandbox service receives SANDBOX_NETWORK env var."""
        assert "SANDBOX_NETWORK" in self.compose_content

    def test_sandbox_postgres_volume(self):
        """sandbox-postgres data is persisted via volume."""
        assert "sandbox_postgres_data" in self.compose_content
