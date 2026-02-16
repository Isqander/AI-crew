"""
Sandbox Tests
=============

Unit tests for the Sandbox module:
  - Models (validation, defaults)
  - Executor (Docker interaction — mocked)
  - Server (FastAPI endpoints — mocked executor)
  - Client tools (HTTP calls — mocked)

All Docker interactions are mocked — no real Docker daemon needed.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import io
import json


# ==================================================================
# 1. Models Tests
# ==================================================================


class TestSandboxModels:
    """Test Pydantic models for request/response validation."""

    def test_execute_request_defaults(self):
        from sandbox.models import SandboxExecuteRequest, CodeFileInput

        req = SandboxExecuteRequest(
            language="python",
            code_files=[CodeFileInput(path="main.py", content="print('hello')")],
            commands=["python main.py"],
        )
        assert req.timeout == 60
        assert req.memory_limit == "256m"
        assert req.network is False

    def test_execute_request_custom_values(self):
        from sandbox.models import SandboxExecuteRequest, CodeFileInput

        req = SandboxExecuteRequest(
            language="javascript",
            code_files=[
                CodeFileInput(path="index.js", content="console.log('hi')"),
                CodeFileInput(path="test.js", content="// tests"),
            ],
            commands=["npm test"],
            timeout=120,
            memory_limit="512m",
            network=True,
        )
        assert req.language == "javascript"
        assert len(req.code_files) == 2
        assert req.timeout == 120
        assert req.memory_limit == "512m"
        assert req.network is True

    def test_execute_request_validation_empty_files(self):
        from sandbox.models import SandboxExecuteRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SandboxExecuteRequest(
                language="python",
                code_files=[],  # min_length=1
                commands=["python main.py"],
            )

    def test_execute_request_validation_empty_commands(self):
        from sandbox.models import SandboxExecuteRequest, CodeFileInput
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SandboxExecuteRequest(
                language="python",
                code_files=[CodeFileInput(path="main.py", content="x")],
                commands=[],  # min_length=1
            )

    def test_execute_request_validation_timeout_bounds(self):
        from sandbox.models import SandboxExecuteRequest, CodeFileInput
        from pydantic import ValidationError

        # Too low
        with pytest.raises(ValidationError):
            SandboxExecuteRequest(
                language="python",
                code_files=[CodeFileInput(path="x.py", content="x")],
                commands=["python x.py"],
                timeout=0,  # ge=1
            )

        # Too high
        with pytest.raises(ValidationError):
            SandboxExecuteRequest(
                language="python",
                code_files=[CodeFileInput(path="x.py", content="x")],
                commands=["python x.py"],
                timeout=1000,  # le=600
            )

    def test_execute_response_defaults(self):
        from sandbox.models import SandboxExecuteResponse

        resp = SandboxExecuteResponse()
        assert resp.stdout == ""
        assert resp.stderr == ""
        assert resp.exit_code == 0
        assert resp.duration_seconds == 0.0
        assert resp.tests_passed is None
        assert resp.files_output == []
        assert resp.error is None

    def test_execute_response_full(self):
        from sandbox.models import SandboxExecuteResponse

        resp = SandboxExecuteResponse(
            stdout="test output",
            stderr="warning",
            exit_code=1,
            duration_seconds=5.2,
            tests_passed=False,
            error=None,
        )
        assert resp.stdout == "test output"
        assert resp.exit_code == 1
        assert resp.tests_passed is False

    def test_health_response(self):
        from sandbox.models import HealthResponse

        health = HealthResponse()
        assert health.status == "ok"
        assert health.docker_available is True
        assert health.active_containers == 0


# ==================================================================
# 2. Executor Tests (Docker mocked)
# ==================================================================


class TestSandboxExecutor:
    """Test the Docker-based executor with mocked Docker client."""

    def _make_executor(self, mock_client=None):
        """Create executor with a mocked Docker client."""
        from sandbox.executor import SandboxExecutor

        if mock_client is None:
            mock_client = self._make_mock_docker_client()
        return SandboxExecutor(docker_client=mock_client)

    def _make_mock_docker_client(
        self,
        exec_stdout: bytes = b"output",
        exec_stderr: bytes = b"",
        exec_exit_code: int = 0,
    ):
        """Create a mock Docker client with configurable exec results."""
        mock_client = MagicMock()

        # Mock version
        mock_client.version.return_value = {"Version": "24.0.0-test"}

        # Mock images
        mock_client.images.get.return_value = Mock()

        # Mock container
        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        mock_container.exec_run.return_value = Mock(
            exit_code=exec_exit_code,
            output=(exec_stdout, exec_stderr),
        )
        mock_container.put_archive.return_value = True
        mock_client.containers.create.return_value = mock_container
        mock_client.containers.list.return_value = []

        # Mock ping
        mock_client.ping.return_value = True

        return mock_client

    def test_execute_success(self):
        """Basic execution — single file, single command, exit 0."""
        executor = self._make_executor(
            self._make_mock_docker_client(
                exec_stdout=b"Hello, World!\n",
                exec_exit_code=0,
            )
        )

        result = executor.execute(
            language="python",
            code_files=[{"path": "main.py", "content": "print('Hello, World!')"}],
            commands=["python main.py"],
        )

        assert result["exit_code"] == 0
        assert "Hello, World!" in result["stdout"]
        assert result["error"] is None
        assert result["duration_seconds"] >= 0

    def test_execute_failure(self):
        """Execution with non-zero exit code."""
        executor = self._make_executor(
            self._make_mock_docker_client(
                exec_stdout=b"",
                exec_stderr=b"SyntaxError: invalid syntax\n",
                exec_exit_code=1,
            )
        )

        result = executor.execute(
            language="python",
            code_files=[{"path": "bad.py", "content": "def f("}],
            commands=["python bad.py"],
        )

        assert result["exit_code"] == 1
        assert "SyntaxError" in result["stderr"]

    def test_execute_multiple_commands_stops_on_failure(self):
        """When a command fails, subsequent commands are not executed."""
        mock_client = self._make_mock_docker_client()
        mock_container = mock_client.containers.create.return_value

        # First call succeeds, second fails
        mock_container.exec_run.side_effect = [
            Mock(exit_code=0, output=(b"mkdir ok\n", b"")),   # mkdir -p
            Mock(exit_code=0, output=(b"installed\n", b"")),  # pip install
            Mock(exit_code=1, output=(b"", b"test failed\n")),  # pytest
        ]

        executor = self._make_executor(mock_client)
        result = executor.execute(
            language="python",
            code_files=[{"path": "test_x.py", "content": "assert False"}],
            commands=["pip install pytest", "pytest"],
        )

        assert result["exit_code"] == 1

    def test_execute_docker_error(self):
        """Docker client raises an exception."""
        mock_client = MagicMock()
        mock_client.version.return_value = {"Version": "test"}
        mock_client.images.get.side_effect = Exception("Docker daemon not available")
        mock_client.images.pull.side_effect = Exception("Docker daemon not available")

        executor = self._make_executor(mock_client)
        result = executor.execute(
            language="python",
            code_files=[{"path": "x.py", "content": "x"}],
            commands=["python x.py"],
        )

        assert result["exit_code"] == -1
        assert result["error"] is not None
        assert "Docker" in result["error"]

    def test_execute_container_cleanup(self):
        """Container is stopped and removed after execution."""
        mock_client = self._make_mock_docker_client()
        mock_container = mock_client.containers.create.return_value

        executor = self._make_executor(mock_client)
        executor.execute(
            language="python",
            code_files=[{"path": "x.py", "content": "x"}],
            commands=["python x.py"],
        )

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)

    def test_is_docker_available_true(self):
        mock_client = self._make_mock_docker_client()
        executor = self._make_executor(mock_client)
        assert executor.is_docker_available() is True

    def test_is_docker_available_false(self):
        mock_client = MagicMock()
        mock_client.version.return_value = {"Version": "test"}
        mock_client.ping.side_effect = Exception("Cannot connect")
        executor = self._make_executor(mock_client)
        assert executor.is_docker_available() is False

    def test_network_mode_none(self):
        """When network=False, container should use network_mode='none'."""
        mock_client = self._make_mock_docker_client()
        executor = self._make_executor(mock_client)

        executor.execute(
            language="python",
            code_files=[{"path": "x.py", "content": "x"}],
            commands=["python x.py"],
            network=False,
        )

        create_kwargs = mock_client.containers.create.call_args
        assert create_kwargs.kwargs.get("network_mode") == "none" or \
               create_kwargs[1].get("network_mode") == "none"

    def test_network_mode_bridge(self):
        """When network=True, container should use named network (not 'none')."""
        mock_client = self._make_mock_docker_client()
        executor = self._make_executor(mock_client)

        executor.execute(
            language="python",
            code_files=[{"path": "x.py", "content": "x"}],
            commands=["python x.py"],
            network=True,
        )

        create_kwargs = mock_client.containers.create.call_args
        network_mode = create_kwargs.kwargs.get("network_mode", "")
        assert network_mode != "none", f"Expected non-'none' network mode, got {network_mode}"


# ==================================================================
# 3. Executor Helpers Tests
# ==================================================================


class TestExecutorHelpers:
    """Test helper functions in the executor module."""

    def test_get_image_for_language(self):
        from sandbox.executor import get_image_for_language

        assert "python" in get_image_for_language("python")
        assert "python" in get_image_for_language("Python")
        assert "python" in get_image_for_language("python3")
        assert "node" in get_image_for_language("javascript")
        assert "node" in get_image_for_language("js")
        assert "node" in get_image_for_language("typescript")
        assert "golang" in get_image_for_language("go")
        assert "rust" in get_image_for_language("rust")
        assert "ubuntu" in get_image_for_language("unknown_language")

    def test_detect_test_result_pytest_pass(self):
        from sandbox.executor import _detect_test_result

        result = _detect_test_result(
            "collected 5 items\npytest: 5 passed\n", "", 0
        )
        assert result is True

    def test_detect_test_result_pytest_fail(self):
        from sandbox.executor import _detect_test_result

        result = _detect_test_result(
            "collected 5 items\npytest: 2 failed, 3 passed\n", "", 1
        )
        assert result is False

    def test_detect_test_result_no_tests(self):
        from sandbox.executor import _detect_test_result

        result = _detect_test_result("Hello World\n", "", 0)
        assert result is None

    def test_detect_test_result_jest(self):
        from sandbox.executor import _detect_test_result

        result = _detect_test_result(
            "jest Tests: 3 passed, 3 total\n", "", 0
        )
        assert result is True

    def test_truncate_short(self):
        from sandbox.executor import _truncate

        text = "short text"
        assert _truncate(text) == text

    def test_truncate_long(self):
        from sandbox.executor import _truncate

        text = "x" * 200_000
        result = _truncate(text, max_len=100)
        assert len(result) < 200_000
        assert "truncated" in result

    def test_create_tar_archive(self):
        from sandbox.executor import _create_tar_archive
        import tarfile

        files = [
            {"path": "main.py", "content": "print('hello')"},
            {"path": "lib/utils.py", "content": "def add(a,b): return a+b"},
        ]
        tar_bytes = _create_tar_archive(files)

        # Verify it's a valid tar
        buf = io.BytesIO(tar_bytes)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            names = tar.getnames()
            assert "main.py" in names
            assert "lib/utils.py" in names


# ==================================================================
# 4. Server Endpoint Tests (Executor mocked)
# ==================================================================


class TestSandboxServer:
    """Test FastAPI endpoints with mocked executor."""

    @pytest.fixture
    def client(self):
        """Create a test client with mocked executor.

        We inject the mock *before* starting the TestClient so that
        the lifespan handler sees it and doesn't try to create a real
        Docker client (which would fail without the ``docker`` package).
        """
        from fastapi.testclient import TestClient
        from sandbox.server import app
        import sandbox.server as server_module

        # Create mock executor
        mock_executor = MagicMock()
        mock_executor.is_docker_available.return_value = True
        mock_executor.active_sandbox_containers.return_value = 0
        mock_executor.execute.return_value = {
            "stdout": "test output",
            "stderr": "",
            "exit_code": 0,
            "duration_seconds": 1.5,
            "tests_passed": None,
            "files_output": [],
            "error": None,
        }

        # Inject mock BEFORE the TestClient starts (lifespan won't overwrite it)
        server_module._executor = mock_executor

        # Patch SandboxExecutor so lifespan doesn't create a real one
        with patch("sandbox.server.SandboxExecutor", return_value=mock_executor):
            with TestClient(app) as test_client:
                yield test_client

        # Cleanup
        server_module._executor = None

    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["docker_available"] is True

    def test_health_degraded(self):
        """When executor is None, health reports degraded."""
        from fastapi.testclient import TestClient
        from sandbox.server import app
        import sandbox.server as server_module

        server_module._executor = None

        with TestClient(app) as test_client:
            resp = test_client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["docker_available"] is False

    def test_execute_success(self, client):
        resp = client.post("/execute", json={
            "language": "python",
            "code_files": [{"path": "main.py", "content": "print('hello')"}],
            "commands": ["python main.py"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["exit_code"] == 0
        assert data["stdout"] == "test output"

    def test_execute_validation_error(self, client):
        """Missing required fields."""
        resp = client.post("/execute", json={
            "language": "python",
            # missing code_files and commands
        })
        assert resp.status_code == 422  # Validation error

    def test_execute_docker_unavailable(self):
        """When Docker is not available, return 503."""
        from fastapi.testclient import TestClient
        from sandbox.server import app
        import sandbox.server as server_module

        mock_executor = MagicMock()
        mock_executor.is_docker_available.return_value = False
        server_module._executor = mock_executor

        with TestClient(app) as test_client:
            resp = test_client.post("/execute", json={
                "language": "python",
                "code_files": [{"path": "x.py", "content": "x"}],
                "commands": ["python x.py"],
            })
            assert resp.status_code == 503

        server_module._executor = None


# ==================================================================
# 5. Client Tool Tests (HTTP mocked)
# ==================================================================


class TestSandboxClientTools:
    """Test the LangChain @tool wrappers with mocked HTTP."""

    def _mock_response(self, data: dict, status_code: int = 200):
        """Create a mock httpx response."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = data
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    @patch("graphs.dev_team.tools.sandbox.httpx.Client")
    def test_sandbox_client_execute(self, mock_httpx_class):
        from graphs.dev_team.tools.sandbox import SandboxClient

        mock_client = MagicMock()
        mock_httpx_class.return_value.__enter__ = Mock(return_value=mock_client)
        mock_httpx_class.return_value.__exit__ = Mock(return_value=False)
        mock_client.post.return_value = self._mock_response({
            "stdout": "Hello!",
            "stderr": "",
            "exit_code": 0,
            "duration_seconds": 1.0,
            "tests_passed": None,
            "files_output": [],
            "error": None,
        })

        client = SandboxClient("http://test:8002")
        result = client.execute(
            language="python",
            code_files=[{"path": "main.py", "content": "print('Hello!')"}],
            commands=["python main.py"],
        )

        assert result["exit_code"] == 0
        assert result["stdout"] == "Hello!"

    @patch("graphs.dev_team.tools.sandbox.httpx.Client")
    def test_sandbox_client_http_error(self, mock_httpx_class):
        """HTTP error returns graceful error dict."""
        from graphs.dev_team.tools.sandbox import SandboxClient
        import httpx

        mock_client = MagicMock()
        mock_httpx_class.return_value.__enter__ = Mock(return_value=mock_client)
        mock_httpx_class.return_value.__exit__ = Mock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        client = SandboxClient("http://unreachable:8002")
        result = client.execute(
            language="python",
            code_files=[{"path": "x.py", "content": "x"}],
            commands=["python x.py"],
        )

        assert result["exit_code"] == -1
        assert result["error"] is not None
        assert "HTTP error" in result["error"] or "Connection" in result["error"]

    @patch("graphs.dev_team.tools.sandbox.httpx.Client")
    def test_sandbox_client_health(self, mock_httpx_class):
        from graphs.dev_team.tools.sandbox import SandboxClient

        mock_client = MagicMock()
        mock_httpx_class.return_value.__enter__ = Mock(return_value=mock_client)
        mock_httpx_class.return_value.__exit__ = Mock(return_value=False)
        mock_client.get.return_value = self._mock_response({
            "status": "ok",
            "docker_available": True,
            "active_containers": 0,
        })

        client = SandboxClient("http://test:8002")
        health = client.health()

        assert health["status"] == "ok"
        assert health["docker_available"] is True


# ==================================================================
# 6. Auto-detection Tests
# ==================================================================


class TestAutoDetection:
    """Test auto-detection of commands, test runners, and linters."""

    def test_auto_command_python(self):
        from graphs.dev_team.tools.sandbox import _auto_command

        assert "python" in _auto_command("python", "main.py")
        assert "python" in _auto_command("python3", "script.py")

    def test_auto_command_javascript(self):
        from graphs.dev_team.tools.sandbox import _auto_command

        assert "node" in _auto_command("javascript", "index.js")
        assert "node" in _auto_command("js", "app.js")

    def test_auto_command_go(self):
        from graphs.dev_team.tools.sandbox import _auto_command

        assert "go run" in _auto_command("go", "main.go")

    def test_auto_command_bash(self):
        from graphs.dev_team.tools.sandbox import _auto_command

        assert "bash" in _auto_command("bash", "script.sh")

    def test_auto_command_unknown(self):
        from graphs.dev_team.tools.sandbox import _auto_command

        # Unknown language defaults to cat
        result = _auto_command("cobol", "program.cob")
        assert "cat" in result

    def test_auto_test_command_python_pytest(self):
        from graphs.dev_team.tools.sandbox import _auto_test_command

        files = [
            {"path": "main.py", "content": "x"},
            {"path": "test_main.py", "content": "def test_x(): pass"},
        ]
        cmd = _auto_test_command("python", files)
        assert "pytest" in cmd

    def test_auto_test_command_python_conftest(self):
        from graphs.dev_team.tools.sandbox import _auto_test_command

        files = [
            {"path": "conftest.py", "content": "x"},
            {"path": "test_api.py", "content": "x"},
        ]
        cmd = _auto_test_command("python", files)
        assert "pytest" in cmd

    def test_auto_test_command_javascript(self):
        from graphs.dev_team.tools.sandbox import _auto_test_command

        files = [{"path": "package.json", "content": "{}"}]
        cmd = _auto_test_command("javascript", files)
        assert "jest" in cmd or "vitest" in cmd

    def test_auto_test_command_go(self):
        from graphs.dev_team.tools.sandbox import _auto_test_command

        files = [{"path": "main_test.go", "content": "x"}]
        cmd = _auto_test_command("go", files)
        assert "go test" in cmd

    def test_auto_lint_command_python(self):
        from graphs.dev_team.tools.sandbox import _auto_lint_command

        cmd = _auto_lint_command("python")
        assert "ruff" in cmd

    def test_auto_lint_command_javascript(self):
        from graphs.dev_team.tools.sandbox import _auto_lint_command

        cmd = _auto_lint_command("javascript")
        assert "eslint" in cmd

    def test_auto_lint_command_go(self):
        from graphs.dev_team.tools.sandbox import _auto_lint_command

        cmd = _auto_lint_command("go")
        assert "vet" in cmd


# ==================================================================
# 7. Output Formatting Tests
# ==================================================================


class TestOutputFormatting:
    """Test result formatting for LLM consumption."""

    def test_format_result_success(self):
        from graphs.dev_team.tools.sandbox import _format_result

        result = {
            "stdout": "Hello World",
            "stderr": "",
            "exit_code": 0,
            "duration_seconds": 1.5,
            "error": None,
        }
        formatted = _format_result(result)
        assert "Exit code:** 0" in formatted
        assert "Hello World" in formatted

    def test_format_result_error(self):
        from graphs.dev_team.tools.sandbox import _format_result

        result = {
            "stdout": "",
            "stderr": "error msg",
            "exit_code": 1,
            "duration_seconds": 0.5,
            "error": "Docker failed",
        }
        formatted = _format_result(result)
        assert "Docker failed" in formatted
        assert "error msg" in formatted

    def test_format_test_result_passed(self):
        from graphs.dev_team.tools.sandbox import _format_test_result

        result = {
            "stdout": "5 passed",
            "stderr": "",
            "exit_code": 0,
            "duration_seconds": 3.0,
            "tests_passed": True,
        }
        formatted = _format_test_result(result)
        assert "PASSED" in formatted

    def test_format_test_result_failed(self):
        from graphs.dev_team.tools.sandbox import _format_test_result

        result = {
            "stdout": "2 failed",
            "stderr": "",
            "exit_code": 1,
            "duration_seconds": 3.0,
            "tests_passed": False,
        }
        formatted = _format_test_result(result)
        assert "FAILED" in formatted

    def test_format_lint_result_clean(self):
        from graphs.dev_team.tools.sandbox import _format_lint_result

        result = {"stdout": "All good", "stderr": "", "exit_code": 0}
        formatted = _format_lint_result(result)
        assert "CLEAN" in formatted

    def test_format_lint_result_issues(self):
        from graphs.dev_team.tools.sandbox import _format_lint_result

        result = {"stdout": "3 issues found", "stderr": "", "exit_code": 1}
        formatted = _format_lint_result(result)
        assert "ISSUES FOUND" in formatted
