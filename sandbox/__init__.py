"""
Sandbox — Code Execution Service
=================================

Isolated Docker-based code execution for the AI-crew platform.

Provides:
  - ``POST /execute`` — run code in a Docker container
  - ``GET /health`` — service + Docker availability check

Architecture:
  - FastAPI server wraps Docker SDK
  - Each execution gets an isolated container
  - Timeout, memory limits, optional network
  - Returns stdout, stderr, exit_code, duration
"""
