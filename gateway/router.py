"""
Switch-Agent Router
===================

Classifies incoming tasks and selects the most appropriate graph.

The router uses a lightweight LLM call (OpenAI-compatible API via httpx)
to analyse the task description against available graph manifests and
pick the best match.

Fallback: when the LLM is unreachable, only one graph exists, or the
task explicitly specifies a ``graph_id`` — no classification happens.

Configuration:
  - ``LLM_API_URL``  — OpenAI-compatible endpoint (from gateway/config)
  - ``LLM_API_KEY``  — API key
  - ``LLM_ROUTER_MODEL``  — model name for the router (env var override)
  - ``LLM_DEFAULT_MODEL``  — fallback model name (env var)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import structlog

from gateway.config import settings
from gateway.models import TaskClassification

logger = structlog.get_logger()

# Router-specific model (can be a fast/cheap model for classification)
_DEFAULT_ROUTER_MODEL = "gemini-3-flash-preview"

# Paths — used to load manifests when called from gateway context
_GRAPHS_DIR = Path(__file__).parent.parent / "graphs"


# ────────────────────── Manifest loading ─────────────────────


def _load_graph_manifests() -> list[dict]:
    """Load all ``manifest.yaml`` files from ``graphs/*/``."""
    import yaml  # noqa: WPS433 — deferred to avoid import at module load if unused

    manifests: list[dict] = []
    if not _GRAPHS_DIR.exists():
        return manifests

    for manifest_path in _GRAPHS_DIR.glob("*/manifest.yaml"):
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if data:
                manifests.append(data)
        except Exception as exc:
            logger.warning("router.manifest_error", path=str(manifest_path), error=str(exc))
    return manifests


def _manifests_to_prompt(manifests: list[dict]) -> str:
    """Convert manifest list into a concise prompt block for the LLM.

    Each graph is described with its name, description, task_types and
    agent list — just enough for the LLM to make a routing decision.
    """
    parts = []
    for m in manifests:
        agents = ", ".join(a.get("display_name", a["id"]) for a in m.get("agents", []))
        task_types = ", ".join(m.get("task_types", []))
        parts.append(
            f"- **{m['name']}** — {m.get('display_name', m['name'])}\n"
            f"  Description: {m.get('description', 'N/A')}\n"
            f"  Task types: {task_types}\n"
            f"  Agents: {agents}"
        )
    return "\n".join(parts)


# ────────────────────── LLM call ─────────────────────────


def _get_router_model() -> str:
    """Get the model name for the router (fast/cheap preferred)."""
    return (
        os.getenv("LLM_ROUTER_MODEL")
        or os.getenv("LLM_DEFAULT_MODEL")
        or _DEFAULT_ROUTER_MODEL
    )


async def _call_llm_for_classification(
    task: str,
    manifests: list[dict],
) -> TaskClassification | None:
    """Call the LLM to classify the task and select a graph.

    Uses OpenAI-compatible chat completions API with JSON response format.

    Returns:
        ``TaskClassification`` or ``None`` if the call fails.
    """
    api_url = settings.llm_api_url
    api_key = settings.llm_api_key
    model = _get_router_model()

    if not api_url:
        logger.warning("router.no_llm_url", hint="Set LLM_API_URL to enable LLM routing")
        return None

    graphs_description = _manifests_to_prompt(manifests)
    graph_ids = [m["name"] for m in manifests]

    system_prompt = (
        "You are a task router for an AI agent platform. "
        "Your job is to analyse a user's task and select the most appropriate "
        "graph (team of AI agents) to handle it.\n\n"
        "Available graphs:\n"
        f"{graphs_description}\n\n"
        "Respond ONLY with a JSON object (no markdown, no extra text):\n"
        "{\n"
        '  "graph_id": "<one of: ' + ", ".join(graph_ids) + '>",\n'
        '  "complexity": <1-10>,\n'
        '  "reasoning": "<short explanation>"\n'
        "}"
    )

    user_prompt = f"Task: {task}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 256,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract the assistant message content
        choices = data.get("choices")
        if not choices:
            logger.warning("router.null_choices", response_keys=list(data.keys()))
            return None
        content = choices[0]["message"]["content"].strip()
        logger.debug("router.llm_response", content=content[:200])

        # Parse JSON from the response (handle potential markdown wrapping)
        parsed = _parse_json_response(content)
        if not parsed:
            logger.warning("router.json_parse_failed", content=content[:200])
            return None

        # Validate graph_id
        graph_id = parsed.get("graph_id", "")
        if graph_id not in graph_ids:
            logger.warning(
                "router.invalid_graph_id",
                returned=graph_id,
                available=graph_ids,
            )
            # Try to find the closest match
            graph_id = graph_ids[0] if graph_ids else "dev_team"

        complexity = parsed.get("complexity", 5)
        if not isinstance(complexity, int) or complexity < 1 or complexity > 10:
            complexity = 5

        reasoning = parsed.get("reasoning", "LLM classification")

        return TaskClassification(
            graph_id=graph_id,
            complexity=complexity,
            reasoning=reasoning,
        )

    except httpx.HTTPStatusError as exc:
        logger.error(
            "router.llm_http_error",
            status=exc.response.status_code,
            body=exc.response.text[:200],
        )
        return None
    except httpx.HTTPError as exc:
        logger.error("router.llm_network_error", error=str(exc))
        return None
    except Exception as exc:
        logger.error("router.llm_unexpected_error", error=str(exc))
        return None


def _parse_json_response(content: str) -> dict | None:
    """Parse JSON from LLM response, handling common issues.

    Handles:
      - Plain JSON: ``{"graph_id": ...}``
      - Markdown-wrapped: ````json\\n{...}\\n````
      - Extra whitespace
    """
    content = content.strip()

    # Try direct parse first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown code fences
    if "```" in content:
        # Extract content between ``` markers
        lines = content.split("\n")
        json_lines = []
        inside = False
        for line in lines:
            if line.strip().startswith("```"):
                inside = not inside
                continue
            if inside:
                json_lines.append(line)
        if json_lines:
            try:
                return json.loads("\n".join(json_lines))
            except json.JSONDecodeError:
                pass

    # Try finding JSON object in the text
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ────────────────────── Public API ───────────────────────


async def classify_task(
    task: str,
    available_graphs: list[dict] | None = None,
) -> TaskClassification:
    """Classify a task and pick the best graph.

    Decision logic:
      1. If only one graph exists → use it (no LLM needed)
      2. If LLM is configured → call LLM for classification
      3. Fallback → default to ``dev_team``

    Args:
        task: User's task description.
        available_graphs: Pre-loaded manifests. If ``None``, loads from disk.

    Returns:
        TaskClassification with graph_id, complexity, reasoning.
    """
    # Load manifests if not provided
    manifests = available_graphs if available_graphs is not None else _load_graph_manifests()

    logger.info("router.classify_task", task_len=len(task), graphs=len(manifests))

    # Fast path: only one graph → skip LLM
    if len(manifests) <= 1:
        graph_id = manifests[0]["name"] if manifests else "dev_team"
        logger.info("router.single_graph", graph_id=graph_id)
        return TaskClassification(
            graph_id=graph_id,
            complexity=5,
            reasoning=f"Only one graph available: {graph_id}",
        )

    # Try LLM classification
    result = await _call_llm_for_classification(task, manifests)
    if result:
        logger.info(
            "router.classified",
            graph_id=result.graph_id,
            complexity=result.complexity,
            reasoning=result.reasoning[:100],
        )
        return result

    # Fallback — default to first graph (usually dev_team)
    fallback_id = manifests[0]["name"] if manifests else "dev_team"
    logger.warning("router.fallback", graph_id=fallback_id)
    return TaskClassification(
        graph_id=fallback_id,
        complexity=5,
        reasoning=f"LLM classification unavailable, defaulting to {fallback_id}",
    )


async def get_available_graphs() -> list[dict]:
    """Load and return available graph manifests.

    Convenience function for use in endpoint handlers that need
    both the manifest data and the classification result.
    """
    return _load_graph_manifests()
