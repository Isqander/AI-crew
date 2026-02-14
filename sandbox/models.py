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

    # === Browser mode (Visual QA Phase 1) ===
    browser: bool = Field(
        default=False,
        description="Use the browser sandbox image (Playwright + Chromium)",
    )
    collect_screenshots: bool = Field(
        default=False,
        description="Collect screenshots from /screenshots/ after execution",
    )
    app_start_command: str | None = Field(
        default=None,
        description="Command to start the web app in background before tests (e.g. 'npm run dev')",
    )
    app_ready_timeout: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Seconds to wait for the app to become ready (port listening)",
    )


class FileOutput(BaseModel):
    """A file produced by the sandbox execution."""

    path: str
    content: str


class ScreenshotOutput(BaseModel):
    """A screenshot collected from the sandbox container."""

    name: str = Field(..., description="Screenshot filename (e.g. 'homepage.png')")
    base64: str = Field(..., description="Base64-encoded PNG image data")


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

    # === Browser mode outputs (Visual QA Phase 1) ===
    screenshots: list[ScreenshotOutput] = Field(
        default_factory=list,
        description="Screenshots collected from /screenshots/ (browser mode)",
    )
    browser_console: str = Field(
        default="",
        description="Browser console output captured during tests",
    )
    network_errors: list[str] = Field(
        default_factory=list,
        description="Failed network requests captured during browser tests",
    )


class HealthResponse(BaseModel):
    """Response for ``GET /health``."""

    status: str = "ok"
    docker_available: bool = True
    active_containers: int = 0
