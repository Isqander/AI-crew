"""
Sandbox Client Tools
====================

LangChain ``@tool`` wrappers for the Sandbox code-execution service.

These tools can be used by agents (QA, Developer, Security) to:
  - Run tests on generated code
  - Execute lint checks
  - Run arbitrary commands in a sandboxed environment

The tools communicate with the Sandbox service via HTTP.
URL is configured via ``SANDBOX_URL`` env var (default: ``http://sandbox:8002``).
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()

# Sandbox service URL (internal docker network)
SANDBOX_URL = os.getenv("SANDBOX_URL", "http://sandbox:8002")

# Shared HTTP client timeout (long — code execution can take a while)
_TIMEOUT = httpx.Timeout(timeout=120.0, connect=10.0)


# ------------------------------------------------------------------
# Low-level client
# ------------------------------------------------------------------


class SandboxClient:
    """HTTP client for the Sandbox service.

    Can be used directly or through the ``@tool`` wrappers below.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or SANDBOX_URL).rstrip("/")

    def execute(
        self,
        language: str,
        code_files: list[dict[str, str]],
        commands: list[str],
        timeout: int = 60,
        memory_limit: str = "256m",
        network: bool = False,
        browser: bool = False,
        collect_screenshots: bool = False,
        app_start_command: str | None = None,
        app_ready_timeout: int = 30,
    ) -> dict[str, Any]:
        """Send an execution request to the sandbox.

        Returns the full response dict (stdout, stderr, exit_code, etc.).
        When *browser* is True, the response may also contain
        ``screenshots``, ``browser_console``, and ``network_errors``.

        Raises ``httpx.HTTPError`` on transport-level failures.
        """
        payload: dict[str, Any] = {
            "language": language,
            "code_files": code_files,
            "commands": commands,
            "timeout": timeout,
            "memory_limit": memory_limit,
            "network": network,
        }

        # Browser mode fields (only sent when browser=True)
        if browser:
            payload["browser"] = True
            payload["collect_screenshots"] = collect_screenshots
            if app_start_command:
                payload["app_start_command"] = app_start_command
            payload["app_ready_timeout"] = app_ready_timeout

        logger.info(
            "sandbox.client.execute",
            url=self.base_url,
            language=language,
            files=len(code_files),
            commands=len(commands),
        )

        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                response = client.post(f"{self.base_url}/execute", json=payload)
                response.raise_for_status()
                result = response.json()

            logger.info(
                "sandbox.client.result",
                exit_code=result.get("exit_code"),
                duration=result.get("duration_seconds"),
                tests_passed=result.get("tests_passed"),
            )
            return result

        except httpx.HTTPError as exc:
            logger.error("sandbox.client.http_error", error=str(exc)[:300])
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "duration_seconds": 0.0,
                "tests_passed": None,
                "files_output": [],
                "error": f"Sandbox HTTP error: {exc}",
            }

    def health(self) -> dict:
        """Check sandbox service health."""
        try:
            with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
                resp = client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            return {"status": "unavailable", "docker_available": False, "error": str(exc)}


# Global client singleton
_sandbox_client: SandboxClient | None = None


def get_sandbox_client() -> SandboxClient:
    """Get or create the global sandbox client."""
    global _sandbox_client
    if _sandbox_client is None:
        _sandbox_client = SandboxClient()
    return _sandbox_client


# ------------------------------------------------------------------
# LangChain @tool wrappers
# ------------------------------------------------------------------


@tool
def run_code(
    language: str,
    code: str,
    filename: str = "main.py",
    command: str | None = None,
) -> str:
    """Execute a single code file in an isolated sandbox container.

    Args:
        language: Runtime language (python, javascript, go, rust, bash)
        code: Source code content
        filename: Filename for the code (default: main.py)
        command: Custom command to run. If None, auto-detected from language.

    Returns:
        Execution output (stdout + stderr) as a string.
    """
    client = get_sandbox_client()

    # Auto-detect run command
    if command is None:
        command = _auto_command(language, filename)

    result = client.execute(
        language=language,
        code_files=[{"path": filename, "content": code}],
        commands=[command],
        timeout=60,
    )

    return _format_result(result)


@tool
def run_tests(
    language: str,
    code_files: list[dict],
    test_command: str | None = None,
    timeout: int = 120,
) -> str:
    """Run tests on code files in an isolated sandbox container.

    Args:
        language: Runtime language (python, javascript, etc.)
        code_files: List of {path, content} dicts — source code + test files
        test_command: Custom test command. If None, auto-detected.
        timeout: Max execution time in seconds (default 120)

    Returns:
        Test output with pass/fail summary.
    """
    client = get_sandbox_client()

    # Auto-detect test command
    if test_command is None:
        test_command = _auto_test_command(language, code_files)

    # For Python: install deps if requirements.txt is present
    commands = []
    has_requirements = any(f["path"] == "requirements.txt" for f in code_files)
    if language.lower() in ("python", "python3") and has_requirements:
        commands.append("pip install -r requirements.txt -q")
    commands.append(test_command)

    result = client.execute(
        language=language,
        code_files=code_files,
        commands=commands,
        timeout=timeout,
    )

    return _format_test_result(result)


@tool
def run_lint(
    language: str,
    code_files: list[dict],
    lint_command: str | None = None,
) -> str:
    """Run linter/formatter checks on code files in the sandbox.

    Args:
        language: Runtime language (python, javascript, etc.)
        code_files: List of {path, content} dicts
        lint_command: Custom lint command. If None, auto-detected.

    Returns:
        Lint output with summary.
    """
    client = get_sandbox_client()

    if lint_command is None:
        lint_command = _auto_lint_command(language)

    # Install linter tools first
    install_cmds = _lint_install_commands(language)
    commands = install_cmds + [lint_command]

    result = client.execute(
        language=language,
        code_files=code_files,
        commands=commands,
        timeout=60,
        memory_limit="128m",
    )

    return _format_lint_result(result)


# ------------------------------------------------------------------
# Auto-detection helpers
# ------------------------------------------------------------------


def _auto_command(language: str, filename: str) -> str:
    """Auto-detect the run command for a given language/file."""
    lang = language.lower()
    if lang in ("python", "python3"):
        return f"python {filename}"
    if lang in ("javascript", "js", "node"):
        return f"node {filename}"
    if lang in ("typescript", "ts"):
        return f"npx tsx {filename}"
    if lang in ("go", "golang"):
        return f"go run {filename}"
    if lang == "rust":
        return f"rustc {filename} -o /tmp/out && /tmp/out"
    if lang in ("bash", "shell"):
        return f"bash {filename}"
    return f"cat {filename}"


def _auto_test_command(language: str, code_files: list[dict]) -> str:
    """Auto-detect test command based on language and files."""
    lang = language.lower()
    filenames = [f["path"] for f in code_files]

    if lang in ("python", "python3"):
        # Check for pytest.ini or conftest.py
        if any("conftest" in f or "pytest" in f for f in filenames):
            return "python -m pytest -v"
        # Check for test files
        test_files = [f for f in filenames if f.startswith("test_") or f.endswith("_test.py")]
        if test_files:
            return "python -m pytest -v " + " ".join(test_files)
        return "python -m pytest -v"

    if lang in ("javascript", "js", "node", "typescript", "ts"):
        if any("jest" in f or "package.json" in f for f in filenames):
            return "npx jest --no-cache"
        return "npx vitest run"

    if lang in ("go", "golang"):
        return "go test -v ./..."

    if lang == "rust":
        return "cargo test"

    return "echo 'No test runner detected for this language'"


def _auto_lint_command(language: str) -> str:
    """Auto-detect lint command."""
    lang = language.lower()
    if lang in ("python", "python3"):
        return "ruff check . && ruff format --check ."
    if lang in ("javascript", "js", "node", "typescript", "ts"):
        return "npx eslint ."
    if lang in ("go", "golang"):
        return "go vet ./..."
    return "echo 'No linter detected for this language'"


def _lint_install_commands(language: str) -> list[str]:
    """Commands to install lint tools."""
    lang = language.lower()
    if lang in ("python", "python3"):
        return ["pip install ruff -q"]
    return []


# ------------------------------------------------------------------
# Output formatting
# ------------------------------------------------------------------


def _format_result(result: dict) -> str:
    """Format execution result for LLM consumption."""
    parts = []
    if result.get("error"):
        parts.append(f"**Error:** {result['error']}")
    parts.append(f"**Exit code:** {result.get('exit_code', -1)}")
    parts.append(f"**Duration:** {result.get('duration_seconds', 0):.1f}s")

    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()

    if stdout:
        parts.append(f"\n**stdout:**\n```\n{stdout}\n```")
    if stderr:
        parts.append(f"\n**stderr:**\n```\n{stderr}\n```")

    return "\n".join(parts)


def _format_test_result(result: dict) -> str:
    """Format test result with pass/fail summary."""
    parts = []

    tests_passed = result.get("tests_passed")
    if tests_passed is True:
        parts.append("**Tests: PASSED**")
    elif tests_passed is False:
        parts.append("**Tests: FAILED**")
    else:
        parts.append("**Tests: status unknown**")

    parts.append(f"**Exit code:** {result.get('exit_code', -1)}")
    parts.append(f"**Duration:** {result.get('duration_seconds', 0):.1f}s")

    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()

    if stdout:
        parts.append(f"\n**Output:**\n```\n{stdout}\n```")
    if stderr:
        parts.append(f"\n**Errors:**\n```\n{stderr}\n```")

    if result.get("error"):
        parts.append(f"\n**Sandbox error:** {result['error']}")

    return "\n".join(parts)


def _format_lint_result(result: dict) -> str:
    """Format lint result."""
    exit_code = result.get("exit_code", -1)
    parts = []

    if exit_code == 0:
        parts.append("**Lint: CLEAN** (no issues found)")
    else:
        parts.append("**Lint: ISSUES FOUND**")

    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()

    if stdout:
        parts.append(f"\n**Output:**\n```\n{stdout}\n```")
    if stderr:
        parts.append(f"\n**Errors:**\n```\n{stderr}\n```")

    return "\n".join(parts)
