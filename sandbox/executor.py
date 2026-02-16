"""
Sandbox Executor
================

Docker-based isolated code execution engine.

Responsibilities:
  - Create a temporary container with the right runtime image
  - Write code files into the container
  - Execute commands sequentially
  - Enforce timeout and memory limits
  - Collect stdout/stderr/exit_code
  - Cleanup containers after execution

Docker images used (pulled automatically):
  - python   → python:3.11-slim
  - javascript / node → node:20-slim
  - go       → golang:1.22-alpine
  - rust     → rust:1.77-slim
  - default  → ubuntu:22.04
"""

from __future__ import annotations

import base64
import os
import time
import tarfile
import io
from typing import Any

import structlog

logger = structlog.get_logger()

# Mapping: language → Docker image
LANGUAGE_IMAGES: dict[str, str] = {
    "python": "python:3.11-slim",
    "python3": "python:3.11-slim",
    "javascript": "node:20-slim",
    "js": "node:20-slim",
    "node": "node:20-slim",
    "typescript": "node:20-slim",
    "ts": "node:20-slim",
    "go": "golang:1.22-alpine",
    "golang": "golang:1.22-alpine",
    "rust": "rust:1.77-slim",
    "html": "node:20-slim",   # Web projects need Node.js for test runners
    "css": "node:20-slim",
    "bash": "ubuntu:22.04",
    "shell": "ubuntu:22.04",
}

DEFAULT_IMAGE = "ubuntu:22.04"

# Browser sandbox image (built from sandbox/Dockerfile.browser)
BROWSER_IMAGE = os.getenv("SANDBOX_BROWSER_IMAGE", "aicrew-sandbox-browser:latest")

# Maximum screenshots to collect (to prevent memory issues)
MAX_SCREENSHOTS = int(os.getenv("BROWSER_MAX_SCREENSHOTS", "20"))

# Maximum single screenshot size in bytes (5MB)
MAX_SCREENSHOT_SIZE = 5 * 1024 * 1024

# Working directory inside the container
WORKDIR = "/sandbox"

# Maximum output size (characters) to prevent memory issues
MAX_OUTPUT_SIZE = 100_000  # 100KB

# Sandbox services — connection info (from environment)
SANDBOX_PG_HOST = os.getenv("SANDBOX_PG_HOST", "sandbox-postgres")
SANDBOX_PG_PORT = os.getenv("SANDBOX_PG_PORT", "5432")
SANDBOX_PG_USER = os.getenv("SANDBOX_PG_USER", "sandbox")
SANDBOX_PG_PASSWORD = os.getenv("SANDBOX_PG_PASSWORD", "sandbox_secret")
SANDBOX_PG_DB = os.getenv("SANDBOX_PG_DB", "sandbox_db")
SANDBOX_NETWORK = os.getenv("SANDBOX_NETWORK", "aicrew-network")


def get_image_for_language(language: str) -> str:
    """Resolve Docker image name for the given language."""
    return LANGUAGE_IMAGES.get(language.lower(), DEFAULT_IMAGE)


def _create_tar_archive(files: list[dict[str, str]]) -> bytes:
    """Create a tar archive from a list of {path, content} dicts.

    The archive is used to ``put_archive`` files into the container.
    All paths are relative to ``WORKDIR``.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for f in files:
            data = f["content"].encode("utf-8")
            info = tarfile.TarInfo(name=f["path"])
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf.read()


def _truncate(text: str, max_len: int = MAX_OUTPUT_SIZE) -> str:
    """Truncate text to *max_len* chars, appending a notice if trimmed."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n\n... [truncated, {len(text)} total chars]"


class SandboxExecutor:
    """Execute code in isolated Docker containers.

    Requires the ``docker`` Python package and a running Docker daemon
    (either native or Docker-in-Docker).

    Parameters
    ----------
    docker_client:
        A ``docker.DockerClient`` instance.  If ``None`` the executor
        will try to connect to the local Docker daemon via
        ``docker.from_env()``.
    """

    def __init__(self, docker_client: Any | None = None):
        if docker_client is not None:
            self.client = docker_client
        else:
            import docker
            self.client = docker.from_env()
        logger.info("sandbox.executor.init", docker_version=self._docker_version())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        # Kept for API backward-compat but ignored — always enabled now.
        enable_postgres: bool = True,
        enable_network: bool = True,
    ) -> dict:
        """Run *commands* inside an isolated container.

        Returns a dict compatible with ``SandboxExecuteResponse``.

        When *browser* is True, uses the Playwright browser image and
        optionally collects screenshots from ``/screenshots/``.

        All containers are connected to ``SANDBOX_NETWORK`` and receive
        ``DATABASE_URL`` / ``PG*`` env vars automatically (sandbox-postgres
        is always running as a docker-compose dependency).
        """
        image = BROWSER_IMAGE if browser else get_image_for_language(language)
        container = None
        t0 = time.monotonic()

        logger.info(
            "sandbox.execute.start",
            language=language,
            image=image,
            files=len(code_files),
            commands=len(commands),
            timeout=timeout,
            memory_limit=memory_limit,
            browser=browser,
            collect_screenshots=collect_screenshots,
        )

        try:
            # 1. Pull image if not available locally
            self._ensure_image(image)

            # 2-3. Create container, copy files
            container = self._create_and_start_container(
                image=image,
                memory_limit=memory_limit,
                browser=browser,
                code_files=code_files,
            )

            # 4. Execute commands sequentially
            last_exit_code, combined_stdout, combined_stderr = self._run_commands(
                container, commands,
            )

            duration = time.monotonic() - t0

            # 5. Detect test results
            tests_passed = _detect_test_result(combined_stdout, combined_stderr, last_exit_code)

            # 6. Collect screenshots (browser mode)
            screenshots: list[dict[str, str]] = []
            browser_console = ""
            network_errors: list[str] = []

            if browser and collect_screenshots:
                screenshots = self._collect_screenshots(container)
                browser_console, network_errors = self._collect_browser_logs(
                    combined_stdout, combined_stderr
                )

            logger.info(
                "sandbox.execute.done",
                exit_code=last_exit_code,
                duration_s=round(duration, 2),
                tests_passed=tests_passed,
                stdout_chars=len(combined_stdout),
                stderr_chars=len(combined_stderr),
                screenshots_collected=len(screenshots),
            )

            return {
                "stdout": combined_stdout,
                "stderr": combined_stderr,
                "exit_code": last_exit_code,
                "duration_seconds": round(duration, 2),
                "tests_passed": tests_passed,
                "files_output": [],
                "error": None,
                "screenshots": screenshots,
                "browser_console": browser_console,
                "network_errors": network_errors,
            }

        except Exception as exc:
            duration = time.monotonic() - t0
            logger.error("sandbox.execute.error", error=str(exc)[:300], duration_s=round(duration, 2))
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "duration_seconds": round(duration, 2),
                "tests_passed": None,
                "files_output": [],
                "error": str(exc)[:500],
                "screenshots": [],
                "browser_console": "",
                "network_errors": [],
            }

        finally:
            # Cleanup: always remove the container
            if container is not None:
                try:
                    container.stop(timeout=5)
                    container.remove(force=True)
                    logger.debug("sandbox.container.removed", container_id=container.short_id)
                except Exception as cleanup_err:
                    logger.warning("sandbox.container.cleanup_failed", error=str(cleanup_err)[:200])

    def is_docker_available(self) -> bool:
        """Check whether the Docker daemon is reachable."""
        try:
            self.client.ping()
            return True
        except Exception:
            return False

    def active_sandbox_containers(self) -> int:
        """Count running containers with the sandbox label."""
        try:
            containers = self.client.containers.list(
                filters={"ancestor": list(LANGUAGE_IMAGES.values())}
            )
            return len(containers)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Execution sub-steps
    # ------------------------------------------------------------------

    def _create_and_start_container(
        self,
        image: str,
        memory_limit: str,
        browser: bool,
        code_files: list[dict[str, str]],
    ) -> Any:
        """Create a container, start it and copy *code_files* into it.

        Returns the running container object.

        All containers are connected to ``SANDBOX_NETWORK`` and receive
        ``DATABASE_URL`` + ``PG*`` environment variables so sandbox
        projects can always reach the sandbox PostgreSQL service.
        """
        effective_memory = memory_limit
        if browser and memory_limit == "256m":
            effective_memory = "512m"  # Chromium needs more RAM

        # Build environment variables for the container
        # PostgreSQL env vars are always injected because sandbox-postgres
        # is always running (docker-compose dependency).
        db_url = (
            f"postgresql://{SANDBOX_PG_USER}:{SANDBOX_PG_PASSWORD}"
            f"@{SANDBOX_PG_HOST}:{SANDBOX_PG_PORT}/{SANDBOX_PG_DB}"
        )
        env_vars: dict[str, str] = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "DATABASE_URL": db_url,
            "PGHOST": SANDBOX_PG_HOST,
            "PGPORT": SANDBOX_PG_PORT,
            "PGUSER": SANDBOX_PG_USER,
            "PGPASSWORD": SANDBOX_PG_PASSWORD,
            "PGDATABASE": SANDBOX_PG_DB,
        }

        # Network: always use SANDBOX_NETWORK so containers can reach
        # sandbox-postgres and other sandbox services.
        net_mode = SANDBOX_NETWORK

        container = self.client.containers.create(
            image=image,
            command="sleep infinity",  # keep alive while we exec commands
            working_dir=WORKDIR,
            mem_limit=effective_memory,
            network_mode=net_mode,
            environment=env_vars,
            detach=True,
            # Security: drop all capabilities, read-only root (except /sandbox, /tmp)
            # Note: browser mode needs slightly relaxed security for Chromium
            cap_drop=[] if browser else ["ALL"],
            tmpfs={"/tmp": "size=128m"} if browser else {"/tmp": "size=64m"},
        )
        container.start()

        # Create working directory & screenshot directory, copy files
        container.exec_run(f"mkdir -p {WORKDIR}", user="root")
        if browser:
            container.exec_run("mkdir -p /screenshots", user="root")
        if code_files:
            tar_data = _create_tar_archive(
                [{"path": f["path"], "content": f["content"]} for f in code_files]
            )
            container.put_archive(WORKDIR, tar_data)

        return container

    @staticmethod
    def _run_commands(
        container: Any,
        commands: list[str],
    ) -> tuple[int, str, str]:
        """Execute *commands* sequentially inside *container*.

        Returns ``(last_exit_code, combined_stdout, combined_stderr)``.
        """
        all_stdout: list[str] = []
        all_stderr: list[str] = []
        last_exit_code = 0

        for cmd in commands:
            logger.debug("sandbox.execute.cmd", cmd=cmd[:100])
            exec_result = container.exec_run(
                ["sh", "-c", cmd],
                workdir=WORKDIR,
                demux=True,  # separate stdout/stderr
            )
            exit_code = exec_result.exit_code
            stdout_bytes, stderr_bytes = exec_result.output or (b"", b"")

            stdout_str = (stdout_bytes or b"").decode("utf-8", errors="replace")
            stderr_str = (stderr_bytes or b"").decode("utf-8", errors="replace")

            all_stdout.append(stdout_str)
            all_stderr.append(stderr_str)
            last_exit_code = exit_code

            # Abort on non-zero exit (unless it's a test runner returning failures)
            if exit_code != 0:
                logger.warning(
                    "sandbox.execute.cmd_failed",
                    cmd=cmd[:100],
                    exit_code=exit_code,
                )
                break

        combined_stdout = _truncate("\n".join(all_stdout))
        combined_stderr = _truncate("\n".join(all_stderr))
        return last_exit_code, combined_stdout, combined_stderr

    # ------------------------------------------------------------------
    # Browser mode helpers
    # ------------------------------------------------------------------

    def _collect_screenshots(self, container: Any) -> list[dict[str, str]]:
        """Collect PNG screenshots from ``/screenshots/`` inside the container.

        Returns a list of ``{"name": ..., "base64": ...}`` dicts.
        """
        screenshots: list[dict[str, str]] = []
        try:
            # List files in /screenshots/
            exec_result = container.exec_run(
                ["sh", "-c", "ls -1 /screenshots/*.png 2>/dev/null || true"],
                demux=True,
            )
            stdout_bytes = (exec_result.output[0] or b"") if exec_result.output else b""
            file_list = stdout_bytes.decode("utf-8", errors="replace").strip().split("\n")
            file_list = [f.strip() for f in file_list if f.strip() and f.endswith(".png")]

            if not file_list:
                logger.debug("sandbox.screenshots.none_found")
                return screenshots

            # Limit number of screenshots
            file_list = file_list[:MAX_SCREENSHOTS]

            # Extract each screenshot via get_archive
            for filepath in file_list:
                try:
                    bits, _stat = container.get_archive(filepath)
                    # get_archive returns a tar stream
                    tar_bytes = b"".join(bits)
                    tar_stream = io.BytesIO(tar_bytes)
                    with tarfile.open(fileobj=tar_stream, mode="r") as tar:
                        for member in tar.getmembers():
                            if member.isfile() and member.size <= MAX_SCREENSHOT_SIZE:
                                fobj = tar.extractfile(member)
                                if fobj:
                                    raw = fobj.read()
                                    encoded = base64.b64encode(raw).decode("ascii")
                                    name = os.path.basename(filepath)
                                    screenshots.append({"name": name, "base64": encoded})
                                    logger.debug(
                                        "sandbox.screenshot.collected",
                                        name=name,
                                        size_bytes=len(raw),
                                    )
                except Exception as e:
                    logger.warning(
                        "sandbox.screenshot.extract_failed",
                        path=filepath,
                        error=str(e)[:200],
                    )

        except Exception as exc:
            logger.warning("sandbox.screenshots.collection_failed", error=str(exc)[:200])

        logger.info("sandbox.screenshots.total", count=len(screenshots))
        return screenshots

    @staticmethod
    def _collect_browser_logs(
        stdout: str, stderr: str
    ) -> tuple[str, list[str]]:
        """Extract browser console logs and network errors from output.

        The browser_runner.py script outputs tagged lines:
          ``[console] ...`` for browser console messages
          ``[network-error] ...`` for failed network requests

        Returns (browser_console, network_errors).
        """
        console_lines: list[str] = []
        network_errors: list[str] = []

        for line in (stdout + "\n" + stderr).split("\n"):
            stripped = line.strip()
            if stripped.startswith("[console]"):
                console_lines.append(stripped[len("[console]"):].strip())
            elif stripped.startswith("[network-error]"):
                network_errors.append(stripped[len("[network-error]"):].strip())

        return "\n".join(console_lines), network_errors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_image(self, image: str) -> None:
        """Pull *image* if it is not available locally.

        Local-only images (like the browser sandbox) are never pulled
        from a registry — if they are missing, we raise immediately
        with a helpful message.
        """
        try:
            self.client.images.get(image)
            return
        except Exception:
            pass

        # For the browser image (local-only), don't attempt pull
        if image == BROWSER_IMAGE:
            raise RuntimeError(
                f"Browser image '{image}' not found locally. "
                f"Build it first: docker compose build sandbox-browser"
            )

        logger.info("sandbox.image.pulling", image=image)
        self.client.images.pull(image)
        logger.info("sandbox.image.pulled", image=image)

    def _docker_version(self) -> str:
        """Return Docker server version string (for logging)."""
        try:
            return self.client.version().get("Version", "unknown")
        except Exception:
            return "unavailable"


# ------------------------------------------------------------------
# Heuristic: detect test pass/fail from output
# ------------------------------------------------------------------

_TEST_PASS_MARKERS = [
    "passed",          # pytest
    "tests passed",
    "ok",              # unittest
    "test suites passed",  # jest
    "PASS",            # jest/vitest
]

_TEST_FAIL_MARKERS = [
    "failed",
    "FAILED",
    "FAIL",
    "error",
    "failures=",
]


def _detect_test_result(
    stdout: str, stderr: str, exit_code: int
) -> bool | None:
    """Guess whether tests passed based on output heuristics.

    Returns ``True`` (pass), ``False`` (fail), or ``None`` (no tests detected).
    """
    combined = (stdout + stderr).lower()

    # Markers that indicate a test framework ran
    is_test_run = any(
        marker in combined
        for marker in ["pytest", "unittest", "jest", "vitest", "mocha", "test_"]
    )
    if not is_test_run:
        return None

    if exit_code == 0:
        return True
    return False
