"""
Run Endpoint
============

``POST /api/run`` — create a new task run with optional auto-routing.

This endpoint:
  1. Validates the JWT
  2. Optionally classifies the task (Switch-Agent) if no ``graph_id``
  3. Creates a thread in Aegra (if needed)
  4. Creates a run in Aegra
  5. Returns thread_id, run_id, graph_id
"""

from __future__ import annotations

import structlog
import httpx
from fastapi import APIRouter, Depends, HTTPException

from gateway.auth import get_current_user
from gateway.config import settings
from gateway.models import CreateRunRequest, RunResponse, User
from gateway.router import classify_task

logger = structlog.get_logger()
router = APIRouter(tags=["run"])

_CLIENT_TIMEOUT = httpx.Timeout(timeout=60.0, connect=10.0)


@router.post("/api/run", response_model=RunResponse)
async def create_run(
    data: CreateRunRequest,
    user: User = Depends(get_current_user),
) -> RunResponse:
    """Create a task run — the main entry point for new tasks."""
    logger.info("run.create", user=user.id, task_len=len(data.task), graph_id=data.graph_id)

    # --- 1. Determine graph_id ------------------------------------------------
    classification = None
    graph_id = data.graph_id
    if not graph_id:
        classification = await classify_task(data.task, [])
        graph_id = classification.graph_id
        logger.info("run.auto_routed", graph_id=graph_id, complexity=classification.complexity)

    # --- 2. Create or reuse thread --------------------------------------------
    thread_id = data.thread_id
    if not thread_id:
        thread_id = await _create_thread(graph_id)

    # --- 3. Create run in Aegra -----------------------------------------------
    run_id = await _create_aegra_run(
        thread_id=thread_id,
        graph_id=graph_id,
        task=data.task,
        repository=data.repository,
        context=data.context,
    )

    return RunResponse(
        thread_id=thread_id,
        run_id=run_id,
        graph_id=graph_id,
        classification=classification,
    )


async def _create_thread(graph_id: str) -> str:
    """Create a new thread in Aegra."""
    async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{settings.aegra_url}/threads",
                json={"metadata": {"graph_id": graph_id}},
            )
            resp.raise_for_status()
            data = resp.json()
            thread_id = data.get("thread_id") or data.get("id", "")
            logger.debug("run.thread_created", thread_id=thread_id)
            return thread_id
        except httpx.HTTPError as exc:
            logger.error("run.thread_create_failed", error=str(exc))
            raise HTTPException(status_code=502, detail=f"Failed to create thread: {exc}")


async def _create_aegra_run(
    thread_id: str,
    graph_id: str,
    task: str,
    repository: str | None = None,
    context: str | None = None,
) -> str:
    """Create a new run in Aegra for the given thread."""
    input_state: dict = {"task": task}
    if repository:
        input_state["repository"] = repository
    if context:
        input_state["context"] = context

    async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{settings.aegra_url}/threads/{thread_id}/runs",
                json={
                    "assistant_id": graph_id,
                    "input": input_state,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            run_id = data.get("run_id") or data.get("id", "")
            logger.info("run.created", thread_id=thread_id, run_id=run_id, graph_id=graph_id)
            return run_id
        except httpx.HTTPError as exc:
            logger.error("run.create_failed", error=str(exc))
            raise HTTPException(status_code=502, detail=f"Failed to create run: {exc}")
