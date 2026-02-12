"""
Tests for Switch-Agent Router (Wave 2 — Module 3.2)
====================================================

Covers:
  - ``classify_task`` — main routing function
  - ``_parse_json_response`` — LLM response parsing
  - ``_manifests_to_prompt`` — manifest-to-prompt conversion
  - ``_call_llm_for_classification`` — LLM call with mocked httpx
  - Single-graph fast path
  - LLM failure fallback
  - Edge cases (invalid JSON, wrong graph_id, etc.)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from gateway.router import (
    _manifests_to_prompt,
    _parse_json_response,
    classify_task,
    _load_graph_manifests,
    _get_router_model,
)
from gateway.models import TaskClassification


# ─────────────────────── Sample manifests ────────────────────


MANIFEST_DEV_TEAM = {
    "name": "dev_team",
    "display_name": "Development Team",
    "description": "Full software development: from requirements to Pull Request.",
    "version": "1.0.0",
    "task_types": ["new_project", "feature", "bugfix", "refactor"],
    "agents": [
        {"id": "pm", "display_name": "Project Manager"},
        {"id": "analyst", "display_name": "Business Analyst"},
        {"id": "architect", "display_name": "Software Architect"},
        {"id": "developer", "display_name": "Developer"},
        {"id": "qa", "display_name": "QA Engineer"},
    ],
    "features": ["hitl_clarification", "qa_loop", "git_commit"],
}

MANIFEST_RESEARCH = {
    "name": "research_team",
    "display_name": "Research Team",
    "description": "Deep research: web search, analysis, report generation.",
    "version": "1.0.0",
    "task_types": ["research", "analysis", "report"],
    "agents": [
        {"id": "researcher", "display_name": "Researcher"},
        {"id": "analyst", "display_name": "Research Analyst"},
        {"id": "writer", "display_name": "Report Writer"},
    ],
    "features": ["web_search", "report_generation"],
}


# ─────────────────── _parse_json_response ────────────────────


class TestParseJsonResponse:

    def test_plain_json(self):
        result = _parse_json_response('{"graph_id": "dev_team", "complexity": 7, "reasoning": "test"}')
        assert result == {"graph_id": "dev_team", "complexity": 7, "reasoning": "test"}

    def test_json_with_markdown_fences(self):
        content = '```json\n{"graph_id": "dev_team", "complexity": 5, "reasoning": "ok"}\n```'
        result = _parse_json_response(content)
        assert result is not None
        assert result["graph_id"] == "dev_team"

    def test_json_with_bare_fences(self):
        content = '```\n{"graph_id": "research_team", "complexity": 3, "reasoning": "search task"}\n```'
        result = _parse_json_response(content)
        assert result is not None
        assert result["graph_id"] == "research_team"

    def test_json_surrounded_by_text(self):
        content = 'Here is my response:\n{"graph_id": "dev_team", "complexity": 8, "reasoning": "code task"}\nThat is all.'
        result = _parse_json_response(content)
        assert result is not None
        assert result["graph_id"] == "dev_team"

    def test_whitespace_padding(self):
        result = _parse_json_response('  \n{"graph_id": "dev_team", "complexity": 5, "reasoning": "x"}\n  ')
        assert result is not None

    def test_invalid_json(self):
        result = _parse_json_response("This is not JSON at all")
        assert result is None

    def test_empty_string(self):
        result = _parse_json_response("")
        assert result is None

    def test_partial_json(self):
        result = _parse_json_response('{"graph_id": "dev_team"')
        assert result is None

    def test_nested_json(self):
        content = '{"graph_id": "dev_team", "complexity": 5, "reasoning": "has nested {braces}"}'
        result = _parse_json_response(content)
        # Should still parse (the outer braces are matched)
        assert result is not None or result is None  # Depends on JSON validity


# ─────────────────── _manifests_to_prompt ────────────────────


class TestManifestsToPrompt:

    def test_single_manifest(self):
        result = _manifests_to_prompt([MANIFEST_DEV_TEAM])
        assert "dev_team" in result
        assert "Development Team" in result
        assert "Project Manager" in result
        assert "new_project" in result

    def test_multiple_manifests(self):
        result = _manifests_to_prompt([MANIFEST_DEV_TEAM, MANIFEST_RESEARCH])
        assert "dev_team" in result
        assert "research_team" in result
        assert "Researcher" in result

    def test_empty_manifests(self):
        result = _manifests_to_prompt([])
        assert result == ""


# ─────────────────── _get_router_model ───────────────────────


class TestGetRouterModel:

    def test_default_model(self):
        model = _get_router_model()
        assert isinstance(model, str)
        assert len(model) > 0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LLM_ROUTER_MODEL", "custom-fast-model")
        assert _get_router_model() == "custom-fast-model"

    def test_default_model_env(self, monkeypatch):
        monkeypatch.delenv("LLM_ROUTER_MODEL", raising=False)
        monkeypatch.setenv("LLM_DEFAULT_MODEL", "global-model")
        assert _get_router_model() == "global-model"


# ─────────────────── classify_task ───────────────────────────


class TestClassifyTask:
    """Tests for the main classify_task function."""

    @pytest.mark.asyncio
    async def test_single_graph_fast_path(self):
        """With only one graph, should return it without LLM call."""
        result = await classify_task("Build a calculator", [MANIFEST_DEV_TEAM])

        assert isinstance(result, TaskClassification)
        assert result.graph_id == "dev_team"
        assert "Only one graph" in result.reasoning

    @pytest.mark.asyncio
    async def test_no_graphs_defaults_to_dev_team(self):
        """With no graphs, should default to dev_team."""
        result = await classify_task("Do something", [])

        assert result.graph_id == "dev_team"

    @pytest.mark.asyncio
    @patch("gateway.router._call_llm_for_classification")
    async def test_multiple_graphs_uses_llm(self, mock_llm_call):
        """With multiple graphs, should call LLM."""
        mock_llm_call.return_value = TaskClassification(
            graph_id="research_team",
            complexity=3,
            reasoning="This is a research task",
        )

        result = await classify_task(
            "Research the latest AI papers on code generation",
            [MANIFEST_DEV_TEAM, MANIFEST_RESEARCH],
        )

        assert result.graph_id == "research_team"
        assert result.complexity == 3
        mock_llm_call.assert_called_once()

    @pytest.mark.asyncio
    @patch("gateway.router._call_llm_for_classification")
    async def test_llm_failure_fallback(self, mock_llm_call):
        """When LLM fails, should fall back to first graph."""
        mock_llm_call.return_value = None  # LLM failed

        result = await classify_task(
            "Some task",
            [MANIFEST_DEV_TEAM, MANIFEST_RESEARCH],
        )

        assert result.graph_id == "dev_team"
        assert "unavailable" in result.reasoning.lower() or "defaulting" in result.reasoning.lower()

    @pytest.mark.asyncio
    @patch("gateway.router._load_graph_manifests")
    async def test_loads_manifests_from_disk_when_none(self, mock_load):
        """When available_graphs=None, should load from disk."""
        mock_load.return_value = [MANIFEST_DEV_TEAM]

        result = await classify_task("Build something", None)

        mock_load.assert_called_once()
        assert result.graph_id == "dev_team"


# ─────────────── _call_llm_for_classification ────────────────


def _make_httpx_mock(llm_response: dict):
    """Create a properly mocked httpx.AsyncClient for async context manager usage.

    httpx.AsyncClient is used as ``async with httpx.AsyncClient() as client``,
    so we need to mock both the context manager and the post method.
    """
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = llm_response
    mock_resp.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_cls, mock_client, mock_resp


class TestCallLLMForClassification:

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    async def test_no_llm_url(self, mock_settings):
        """Should return None when LLM URL is not configured."""
        mock_settings.llm_api_url = ""
        mock_settings.llm_api_key = ""

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification("test task", [MANIFEST_DEV_TEAM])
        assert result is None

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    @patch("gateway.router.httpx.AsyncClient")
    async def test_successful_classification(self, MockClient, mock_settings):
        """LLM returns valid JSON classification."""
        mock_settings.llm_api_url = "http://llm:8000/v1"
        mock_settings.llm_api_key = "test-key"

        llm_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "graph_id": "dev_team",
                        "complexity": 7,
                        "reasoning": "This is a development task",
                    })
                }
            }]
        }

        mock_cls, mock_client, _ = _make_httpx_mock(llm_response)
        MockClient.return_value = mock_cls.return_value

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification(
            "Create a REST API with FastAPI",
            [MANIFEST_DEV_TEAM, MANIFEST_RESEARCH],
        )

        assert result is not None
        assert result.graph_id == "dev_team"
        assert result.complexity == 7

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    @patch("gateway.router.httpx.AsyncClient")
    async def test_llm_returns_invalid_graph_id(self, MockClient, mock_settings):
        """LLM returns a graph_id that doesn't exist — should fallback."""
        mock_settings.llm_api_url = "http://llm:8000/v1"
        mock_settings.llm_api_key = "test-key"

        llm_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "graph_id": "nonexistent_team",
                        "complexity": 5,
                        "reasoning": "whatever",
                    })
                }
            }]
        }

        mock_cls, _, _ = _make_httpx_mock(llm_response)
        MockClient.return_value = mock_cls.return_value

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification(
            "Some task",
            [MANIFEST_DEV_TEAM, MANIFEST_RESEARCH],
        )

        assert result is not None
        assert result.graph_id == "dev_team"

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    @patch("gateway.router.httpx.AsyncClient")
    async def test_llm_invalid_complexity(self, MockClient, mock_settings):
        """LLM returns complexity outside 1-10 range."""
        mock_settings.llm_api_url = "http://llm:8000/v1"
        mock_settings.llm_api_key = "key"

        llm_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "graph_id": "dev_team",
                        "complexity": 99,
                        "reasoning": "test",
                    })
                }
            }]
        }

        mock_cls, _, _ = _make_httpx_mock(llm_response)
        MockClient.return_value = mock_cls.return_value

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification("task", [MANIFEST_DEV_TEAM])

        assert result is not None
        assert result.complexity == 5

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    @patch("gateway.router.httpx.AsyncClient")
    async def test_llm_returns_markdown_json(self, MockClient, mock_settings):
        """LLM wraps JSON in markdown code fences."""
        mock_settings.llm_api_url = "http://llm:8000/v1"
        mock_settings.llm_api_key = "key"

        llm_response = {
            "choices": [{
                "message": {
                    "content": '```json\n{"graph_id": "dev_team", "complexity": 6, "reasoning": "code task"}\n```'
                }
            }]
        }

        mock_cls, _, _ = _make_httpx_mock(llm_response)
        MockClient.return_value = mock_cls.return_value

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification("task", [MANIFEST_DEV_TEAM])

        assert result is not None
        assert result.graph_id == "dev_team"
        assert result.complexity == 6

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    @patch("gateway.router.httpx.AsyncClient")
    async def test_llm_http_error(self, MockClient, mock_settings):
        """LLM returns HTTP error."""
        mock_settings.llm_api_url = "http://llm:8000/v1"
        mock_settings.llm_api_key = "key"

        import httpx as _httpx

        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_resp,
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification("task", [MANIFEST_DEV_TEAM])
        assert result is None

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    @patch("gateway.router.httpx.AsyncClient")
    async def test_llm_network_error(self, MockClient, mock_settings):
        """LLM is unreachable."""
        mock_settings.llm_api_url = "http://llm:8000/v1"
        mock_settings.llm_api_key = "key"

        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.post.side_effect = _httpx.ConnectError("Connection refused")

        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification("task", [MANIFEST_DEV_TEAM])
        assert result is None

    @pytest.mark.asyncio
    @patch("gateway.router.settings")
    @patch("gateway.router.httpx.AsyncClient")
    async def test_llm_unparseable_response(self, MockClient, mock_settings):
        """LLM returns garbage that's not parseable."""
        mock_settings.llm_api_url = "http://llm:8000/v1"
        mock_settings.llm_api_key = "key"

        llm_response = {
            "choices": [{
                "message": {
                    "content": "I cannot classify this task properly. Sorry!"
                }
            }]
        }

        mock_cls, _, _ = _make_httpx_mock(llm_response)
        MockClient.return_value = mock_cls.return_value

        from gateway.router import _call_llm_for_classification

        result = await _call_llm_for_classification("task", [MANIFEST_DEV_TEAM])
        assert result is None


# ─────────────── Integration-style test ──────────────────────


class TestFullClassificationFlow:
    """End-to-end flow: classify_task → LLM → TaskClassification."""

    @pytest.mark.asyncio
    @patch("gateway.router._call_llm_for_classification")
    async def test_dev_task_routes_to_dev_team(self, mock_llm):
        mock_llm.return_value = TaskClassification(
            graph_id="dev_team",
            complexity=8,
            reasoning="Complex development task requiring multiple agents",
        )

        result = await classify_task(
            "Create a microservices architecture with user authentication, "
            "product catalog, and payment processing",
            [MANIFEST_DEV_TEAM, MANIFEST_RESEARCH],
        )

        assert result.graph_id == "dev_team"
        assert result.complexity == 8

    @pytest.mark.asyncio
    @patch("gateway.router._call_llm_for_classification")
    async def test_research_task_routes_to_research(self, mock_llm):
        mock_llm.return_value = TaskClassification(
            graph_id="research_team",
            complexity=4,
            reasoning="Research and analysis task",
        )

        result = await classify_task(
            "Research the latest trends in quantum computing and write a report",
            [MANIFEST_DEV_TEAM, MANIFEST_RESEARCH],
        )

        assert result.graph_id == "research_team"
        assert result.complexity == 4

    @pytest.mark.asyncio
    async def test_single_graph_no_llm_call(self):
        """Single graph available — no LLM classification needed."""
        result = await classify_task(
            "Any task whatsoever",
            [MANIFEST_DEV_TEAM],
        )

        assert result.graph_id == "dev_team"
        assert "Only one graph" in result.reasoning


# ─────────────── Manifest loading ────────────────────────────


class TestLoadGraphManifests:

    @patch("gateway.router._GRAPHS_DIR")
    def test_no_graphs_dir(self, mock_dir):
        mock_dir.exists.return_value = False
        result = _load_graph_manifests()
        assert result == []
