"""
Sandbox Data Models
===================

Pydantic models for the Sandbox API (see ARCHITECTURE_V2 §4.6).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CodeFileInput(BaseModel):
    """A single file to place inside the sandbox container."""

    path: str = Field(..., description="Relative path inside the container (e.g. 'main.py')")
    content: str = Field(..., description="File content as UTF-8 text")


class SandboxExecuteRequest(BaseModel):
    """Request body for ``POST /execute``."""

    language: str = Field(
        ...,
        description="Runtime language: python, javascript, go, rust, etc.",
        examples=["python", "javascript"],
    )
    code_files: list[CodeFileInput] = Field(
        ...,
        description="Files to write inside the sandbox before execution",
        min_length=1,
    )
    commands: list[str] = Field(
        ...,
        description="Shell commands to run sequentially",
        min_length=1,
        examples=[["pip install -r requirements.txt", "pytest -v"]],
    )
    timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        description="Max execution time in seconds",
    )
    memory_limit: str = Field(
        default="256m",
        description="Docker memory limit (e.g. '256m', '512m', '1g')",
    )
    network: bool = Field(
        default=False,
        description="Whether to allow network access inside the sandbox",
    )


class FileOutput(BaseModel):
    """A file produced by the sandbox execution."""

    path: str
    content: str


class SandboxExecuteResponse(BaseModel):
    """Response body for ``POST /execute``."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.0
    tests_passed: bool | None = Field(
        default=None,
        description="True/False if test commands were detected, None otherwise",
    )
    files_output: list[FileOutput] = Field(
        default_factory=list,
        description="Files created/modified by the execution",
    )
    error: str | None = Field(
        default=None,
        description="Internal error message (container creation failure, timeout, etc.)",
    )


class HealthResponse(BaseModel):
    """Response for ``GET /health``."""

    status: str = "ok"
    docker_available: bool = True
    active_containers: int = 0
