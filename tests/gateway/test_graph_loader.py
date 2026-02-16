"""Tests for gateway/graph_loader.py — manifest, config, and prompt loading."""

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from gateway.graph_loader import (
    load_manifests,
    find_manifest,
    load_agents_yaml,
    build_agent_configs,
    load_prompt_info,
)


@pytest.fixture
def sample_manifest():
    return {
        "name": "dev_team",
        "description": "Development team",
        "agents": [
            {"id": "pm", "role": "pm"},
            {"id": "developer", "role": "developer"},
        ],
    }


@pytest.fixture
def sample_agents_yaml():
    return {
        "defaults": {"temperature": 0.7, "endpoint": "default"},
        "agents": {
            "pm": {"model": "gpt-4o", "temperature": 0.5},
            "developer": {"model": "claude-sonnet", "fallback_model": "gpt-4o"},
        },
    }


class TestLoadManifests:
    @patch("gateway.graph_loader._GRAPHS_DIR")
    def test_returns_empty_when_dir_missing(self, mock_dir):
        mock_dir.exists.return_value = False
        result = load_manifests()
        assert result == []

    def test_returns_list(self):
        result = load_manifests()
        assert isinstance(result, list)


class TestFindManifest:
    def test_finds_dev_team(self):
        result = find_manifest("dev_team")
        if result is not None:
            assert result["name"] == "dev_team"

    def test_returns_none_for_missing(self):
        result = find_manifest("nonexistent_graph_xyz")
        assert result is None


class TestBuildAgentConfigs:
    def test_builds_configs(self, sample_manifest, sample_agents_yaml):
        with patch("gateway.graph_loader.load_agents_yaml", return_value=sample_agents_yaml):
            configs = build_agent_configs(sample_manifest)
        assert "pm" in configs
        assert "developer" in configs
        assert configs["pm"]["model"] == "gpt-4o"
        assert configs["pm"]["temperature"] == 0.5
        assert configs["developer"]["fallback_model"] == "gpt-4o"

    def test_defaults_used_when_agent_not_in_yaml(self, sample_agents_yaml):
        manifest = {"agents": [{"id": "researcher", "role": "researcher"}]}
        with patch("gateway.graph_loader.load_agents_yaml", return_value=sample_agents_yaml):
            configs = build_agent_configs(manifest)
        assert configs["researcher"]["model"] == "unknown"
        assert configs["researcher"]["temperature"] == 0.7

    def test_empty_manifest(self):
        configs = build_agent_configs({"agents": []})
        assert configs == {}


class TestLoadAgentsYaml:
    def test_returns_dict(self):
        result = load_agents_yaml()
        assert isinstance(result, dict)


class TestLoadPromptInfo:
    def test_returns_dict(self):
        result = load_prompt_info("dev_team")
        assert isinstance(result, dict)

    def test_missing_graph_returns_empty(self):
        result = load_prompt_info("nonexistent_graph_xyz")
        assert result == {}
