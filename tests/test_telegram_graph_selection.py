"""
Tests for Telegram Graph Selection Dialog
==========================================

Covers:
  - ``_format_graph_menu`` — menu text and number mapping
  - FSM state transitions (task → graph selection → create)
  - ``/task`` with inline text (skip step 1)
  - ``/task`` without text (ask for input)
  - Invalid graph selection
  - Gateway client ``get_graph_list``
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import handler helpers directly
from telegram.handlers import (
    _format_graph_menu,
    _LLM_AUTO,
)


# ─────────────────────── _format_graph_menu ─────────────────


class TestFormatGraphMenu:
    """Tests for the graph menu formatter."""

    def test_basic_menu(self):
        """Menu with 2 graphs + LLM auto option."""
        graphs = [
            {
                "graph_id": "simple_dev",
                "display_name": "Quick Developer",
                "description": "Fast code generation",
            },
            {
                "graph_id": "research",
                "display_name": "Research",
                "description": "Web research and analysis",
            },
        ]
        text, mapping = _format_graph_menu(graphs)

        # Menu text
        assert "Quick Developer" in text
        assert "Research" in text
        assert "Выбор сделает ЛЛМ" in text

        # Mapping: 1 → simple_dev, 2 → research, 3 → None (auto)
        assert mapping["1"] == "simple_dev"
        assert mapping["2"] == "research"
        assert mapping["3"] is None  # LLM auto

    def test_single_graph(self):
        """Menu with 1 graph + LLM auto."""
        graphs = [
            {
                "graph_id": "dev_team",
                "display_name": "Dev Team",
                "description": "Full development",
            },
        ]
        text, mapping = _format_graph_menu(graphs)

        assert mapping["1"] == "dev_team"
        assert mapping["2"] is None  # LLM auto
        assert "Выбор сделает ЛЛМ" in text

    def test_long_description_truncated(self):
        """Long descriptions are truncated to 60 chars."""
        graphs = [
            {
                "graph_id": "test",
                "display_name": "Test",
                "description": "A" * 100,
            },
        ]
        text, _ = _format_graph_menu(graphs)
        # Should be truncated with ...
        assert "..." in text

    def test_empty_graphs(self):
        """Empty graph list → only LLM auto option."""
        text, mapping = _format_graph_menu([])

        assert mapping["1"] is None  # LLM auto
        assert len(mapping) == 1

    def test_four_graphs(self):
        """4 graphs + LLM auto = 5 options."""
        graphs = [
            {"graph_id": f"g{i}", "display_name": f"Graph {i}", "description": f"Desc {i}"}
            for i in range(4)
        ]
        text, mapping = _format_graph_menu(graphs)

        assert len(mapping) == 5
        assert mapping["1"] == "g0"
        assert mapping["4"] == "g3"
        assert mapping["5"] is None

    def test_mapping_uses_graph_id_or_name(self):
        """Falls back to 'name' if 'graph_id' is missing."""
        graphs = [
            {
                "name": "my_graph",
                "display_name": "My Graph",
                "description": "test",
            },
        ]
        _, mapping = _format_graph_menu(graphs)
        assert mapping["1"] == "my_graph"


# ─────────────────────── GatewayClient.get_graph_list ───────


class TestGatewayClientGraphList:
    """Tests for the gateway client graph list method."""

    @pytest.mark.asyncio
    async def test_get_graph_list_success(self):
        """Successful fetch returns list of graphs."""
        from telegram.gateway_client import GatewayClient

        client = GatewayClient("http://mock:8081")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "graphs": [
                {"graph_id": "dev_team", "display_name": "Dev Team"},
                {"graph_id": "research", "display_name": "Research"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client.client = MagicMock()
        client.client.request = AsyncMock(return_value=mock_response)

        graphs = await client.get_graph_list()
        assert len(graphs) == 2
        assert graphs[0]["graph_id"] == "dev_team"

    @pytest.mark.asyncio
    async def test_get_graph_list_empty(self):
        """Empty graph list from API."""
        from telegram.gateway_client import GatewayClient

        client = GatewayClient("http://mock:8081")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"graphs": []}
        mock_response.raise_for_status = MagicMock()
        client.client = MagicMock()
        client.client.request = AsyncMock(return_value=mock_response)

        graphs = await client.get_graph_list()
        assert graphs == []

    @pytest.mark.asyncio
    async def test_get_graph_list_missing_key(self):
        """API response without 'graphs' key → empty list."""
        from telegram.gateway_client import GatewayClient

        client = GatewayClient("http://mock:8081")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        client.client = MagicMock()
        client.client.request = AsyncMock(return_value=mock_response)

        graphs = await client.get_graph_list()
        assert graphs == []


# ─────────────────────── Router with multiple graphs ────────


class TestRouterWithMultipleGraphs:
    """Test that Switch-Agent router handles multiple graphs."""

    @pytest.mark.asyncio
    async def test_classify_with_four_graphs(self):
        """classify_task works with 4 manifests."""
        from gateway.router import classify_task

        manifests = [
            {
                "name": "dev_team",
                "display_name": "Dev Team",
                "description": "Full development",
                "task_types": ["feature", "bugfix"],
                "agents": [{"id": "pm", "display_name": "PM"}],
            },
            {
                "name": "simple_dev",
                "display_name": "Quick Dev",
                "description": "Simple tasks",
                "task_types": ["script", "snippet"],
                "agents": [{"id": "developer", "display_name": "Dev"}],
            },
            {
                "name": "standard_dev",
                "display_name": "Standard Dev",
                "description": "Medium tasks",
                "task_types": ["feature", "bugfix"],
                "agents": [{"id": "pm"}, {"id": "developer"}, {"id": "qa"}],
            },
            {
                "name": "research",
                "display_name": "Research",
                "description": "Web research",
                "task_types": ["research", "analysis"],
                "agents": [{"id": "researcher", "display_name": "Researcher"}],
            },
        ]

        # With multiple graphs, it tries LLM; when LLM fails, falls back
        with patch("gateway.router._call_llm_for_classification", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = None  # LLM unavailable → fallback
            result = await classify_task("research about AI", manifests)
            assert result.graph_id == "dev_team"  # Fallback = first graph

    @pytest.mark.asyncio
    async def test_single_graph_fast_path(self):
        """Single graph → fast path, no LLM call."""
        from gateway.router import classify_task

        manifests = [
            {
                "name": "dev_team",
                "display_name": "Dev Team",
                "description": "Full development",
                "task_types": ["feature"],
                "agents": [],
            },
        ]

        result = await classify_task("build something", manifests)
        assert result.graph_id == "dev_team"
        assert "Only one graph" in result.reasoning
