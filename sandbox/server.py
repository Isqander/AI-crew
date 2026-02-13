"""
Sandbox Server
==============

FastAPI application exposing the code-execution sandbox.

Endpoints
---------
  ``POST /execute`` — run code in an isolated Docker container
  ``GET  /health``  — readiness check (Docker availability)

Environment Variables
---------------------
  ``SANDBOX_PORT``           — listen port (default 8002)
  ``SANDBOX_MAX_TIMEOUT``    — max allowed timeout (default 300s)
  ``SANDBOX_DEFAULT_MEMORY`` — default memory limit (default 256m)
  ``LOG_LEVEL``              — structlog level (default INFO)
  ``ENV_MODE``               — LOCAL | PRODUCTION
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException

from sandbox.models import (
    SandboxExecuteRequest,
    SandboxExecuteResponse,
    HealthResponse,
)
from sandbox.executor import SandboxExecutor

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
logger = structlog.get_logger()

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
MAX_TIMEOUT = int(os.getenv("SANDBOX_MAX_TIMEOUT", "300"))
DEFAULT_MEMORY = os.getenv("SANDBOX_DEFAULT_MEMORY", "256m")

# ------------------------------------------------------------------
# Global executor (initialised at startup)
# ------------------------------------------------------------------
_executor: SandboxExecutor | None = None


def get_executor() -> SandboxExecutor:
    """Return the global ``SandboxExecutor`` instance."""
    if _executor is None:
        raise RuntimeError("SandboxExecutor not initialised — server not started?")
    return _executor


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise Docker client on startup, cleanup on shutdown."""
    global _executor
    try:
        _executor = SandboxExecutor()
        logger.info("sandbox.server.started", docker_available=_executor.is_docker_available())
    except Exception as exc:
        logger.error("sandbox.server.docker_unavailable", error=str(exc)[:300])
        # Server starts anyway — /health will report docker_available=false
        _executor = None
    yield
    logger.info("sandbox.server.shutdown")


# ------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------
app = FastAPI(
    title="AI-crew Sandbox",
    description="Isolated Docker-based code execution",
    version="1.0.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.post("/execute", response_model=SandboxExecuteResponse)
async def execute_code(request: SandboxExecuteRequest) -> SandboxExecuteResponse:
    """Execute code in an isolated Docker container.

    The endpoint is synchronous from the Docker perspective (blocks
    until the container finishes or times out).  For the MVP this is
    acceptable because:
      1. Sandbox calls are rare (QA stage only)
      2. Typical execution < 60s
      3. Concurrency is limited by the host Docker daemon anyway

    In production, consider ``asyncio.to_thread`` or a task queue.
    """
    executor = _get_executor_or_503()

    # Enforce server-side timeout cap
    effective_timeout = min(request.timeout, MAX_TIMEOUT)

    logger.info(
        "sandbox.api.execute",
        language=request.language,
        files=len(request.code_files),
        commands=len(request.commands),
        timeout=effective_timeout,
        memory=request.memory_limit,
        network=request.network,
    )

    # Run in a thread to avoid blocking the event loop
    import asyncio
    result = await asyncio.to_thread(
        executor.execute,
        language=request.language,
        code_files=[f.model_dump() for f in request.code_files],
        commands=request.commands,
        timeout=effective_timeout,
        memory_limit=request.memory_limit,
        network=request.network,
    )

    return SandboxExecuteResponse(**result)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Readiness probe — check Docker daemon availability."""
    if _executor is None:
        return HealthResponse(status="degraded", docker_available=False, active_containers=0)

    docker_ok = _executor.is_docker_available()
    active = _executor.active_sandbox_containers() if docker_ok else 0

    return HealthResponse(
        status="ok" if docker_ok else "degraded",
        docker_available=docker_ok,
        active_containers=active,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_executor_or_503() -> SandboxExecutor:
    """Return executor or raise 503 if Docker is unavailable."""
    if _executor is None or not _executor.is_docker_available():
        raise HTTPException(
            status_code=503,
            detail="Docker is not available. Sandbox service is degraded.",
        )
    return _executor


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("SANDBOX_PORT", "8002"))
    uvicorn.run(
        "sandbox.server:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENV_MODE", "LOCAL") == "LOCAL",
    )
