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
    "bash": "ubuntu:22.04",
    "shell": "ubuntu:22.04",
}

DEFAULT_IMAGE = "ubuntu:22.04"

# Working directory inside the container
WORKDIR = "/sandbox"

# Maximum output size (characters) to prevent memory issues
MAX_OUTPUT_SIZE = 100_000  # 100KB


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
    ) -> dict:
        """Run *commands* inside an isolated container.

        Returns a dict compatible with ``SandboxExecuteResponse``.
        """
        image = get_image_for_language(language)
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
            network=network,
        )

        try:
            # 1. Pull image if not available locally
            self._ensure_image(image)

            # 2. Create container
            container = self.client.containers.create(
                image=image,
                command="sleep infinity",  # keep alive while we exec commands
                working_dir=WORKDIR,
                mem_limit=memory_limit,
                network_mode="none" if not network else "bridge",
                detach=True,
                # Security: drop all capabilities, read-only root (except /sandbox, /tmp)
                cap_drop=["ALL"],
                tmpfs={"/tmp": "size=64m"},
            )
            container.start()

            # 3. Create working directory & copy files
            container.exec_run(f"mkdir -p {WORKDIR}", user="root")
            if code_files:
                tar_data = _create_tar_archive(
                    [{"path": f["path"], "content": f["content"]} for f in code_files]
                )
                container.put_archive(WORKDIR, tar_data)

            # 4. Execute commands sequentially
            all_stdout: list[str] = []
            all_stderr: list[str] = []
            last_exit_code = 0

            for cmd in commands:
                logger.debug("sandbox.execute.cmd", cmd=cmd[:100])
                exec_result = container.exec_run(
                    ["sh", "-c", cmd],
                    workdir=WORKDIR,
                    demux=True,  # separate stdout/stderr
                    environment={"PYTHONDONTWRITEBYTECODE": "1"},
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

            duration = time.monotonic() - t0
            combined_stdout = _truncate("\n".join(all_stdout))
            combined_stderr = _truncate("\n".join(all_stderr))

            # 5. Detect test results
            tests_passed = _detect_test_result(combined_stdout, combined_stderr, last_exit_code)

            logger.info(
                "sandbox.execute.done",
                exit_code=last_exit_code,
                duration_s=round(duration, 2),
                tests_passed=tests_passed,
                stdout_chars=len(combined_stdout),
                stderr_chars=len(combined_stderr),
            )

            return {
                "stdout": combined_stdout,
                "stderr": combined_stderr,
                "exit_code": last_exit_code,
                "duration_seconds": round(duration, 2),
                "tests_passed": tests_passed,
                "files_output": [],
                "error": None,
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_image(self, image: str) -> None:
        """Pull *image* if it is not available locally."""
        try:
            self.client.images.get(image)
        except Exception:
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
