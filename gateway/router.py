"""
Switch-Agent Router
===================

Auto-classifies incoming tasks and selects the appropriate graph.

For now this is a **stub** that always returns ``dev_team``.
The real LLM-based classification will be implemented in Wave 2
(module 3.2) once a second graph exists.
"""

from __future__ import annotations

import structlog

from gateway.models import TaskClassification

logger = structlog.get_logger()


async def classify_task(task: str, available_graphs: list[dict]) -> TaskClassification:
    """Classify a task and pick the best graph.

    Currently returns a hardcoded ``dev_team`` classification.
    Will be replaced with an LLM call in Wave 2.

    Args:
        task: User's task description.
        available_graphs: List of graph manifests (from ``/graph/list``).

    Returns:
        TaskClassification with graph_id, complexity, reasoning.
    """
    logger.info("router.classify_task", task_len=len(task), graphs=len(available_graphs))

    # Stub — always select dev_team
    return TaskClassification(
        graph_id="dev_team",
        complexity=5,
        reasoning="Default routing to dev_team (Switch-Agent not yet implemented)",
    )
