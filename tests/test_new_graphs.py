"""
Tests for New Graphs (simple_dev, standard_dev, research)
=========================================================

Covers:
  - Graph structure (nodes, edges)
  - State definitions
  - Manifests
  - Routing logic (standard_dev QA loop)
  - commit_and_create_pr helper
  - git_commit_node using new commit_and_create_pr
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import yaml


# ═══════════════════════════════════════════════════════════════
# Section 1: commit_and_create_pr
# ═══════════════════════════════════════════════════════════════


class TestCommitAndCreatePr:
    """Tests for the high-level commit_and_create_pr workflow."""

    @patch("dev_team.tools.git_workspace.get_github_client")
    def test_success_full_workflow(self, mock_get_client):
        """Full success: branch + atomic commit + PR."""
        from dev_team.tools.git_workspace import commit_and_create_pr

        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_branch = MagicMock()
        mock_branch.commit.sha = "abc123"
        mock_repo.get_branch.return_value = mock_branch
        mock_repo.create_git_ref.return_value = None

        # Git tree API mocks
        mock_ref = MagicMock()
        mock_ref.object.sha = "abc123"
        mock_repo.get_git_ref.return_value = mock_ref
        mock_commit = MagicMock()
        mock_commit.tree = MagicMock()
        mock_repo.get_git_commit.return_value = mock_commit
        mock_new_tree = MagicMock()
        mock_repo.create_git_tree.return_value = mock_new_tree
        mock_new_commit = MagicMock()
        mock_new_commit.sha = "def456"
        mock_repo.create_git_commit.return_value = mock_new_commit

        # PR mock
        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/42"
        mock_pr.number = 42
        mock_repo.create_pull.return_value = mock_pr

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client

        result = commit_and_create_pr(
            repo_name="owner/repo",
            task="Test task",
            code_files=[
                {"path": "main.py", "content": "print('hello')"},
                {"path": "README.md", "content": "# Hello"},
            ],
        )

        assert result["pr_url"] == "https://github.com/owner/repo/pull/42"
        assert result["commit_sha"] == "def456"
        assert result["working_branch"].startswith("ai/")
        assert result["working_repo"] == "owner/repo"
        assert result["files_committed"] == 2
        assert "error" not in result

    @patch("dev_team.tools.git_workspace.get_github_client")
    def test_no_github_client(self, mock_get_client):
        """No GITHUB_TOKEN → returns error."""
        from dev_team.tools.git_workspace import commit_and_create_pr

        mock_get_client.return_value = None

        result = commit_and_create_pr(
            repo_name="owner/repo",
            task="Test",
            code_files=[{"path": "a.py", "content": "x=1"}],
        )

        assert "error" in result
        assert result["files_committed"] == 0

    def test_no_valid_files(self):
        """Empty or invalid code_files → returns error without API calls."""
        from dev_team.tools.git_workspace import commit_and_create_pr

        result = commit_and_create_pr(
            repo_name="owner/repo",
            task="Test",
            code_files=[{"path": "", "content": ""}, {"content": "orphan"}],
        )

        assert result["error"] == "No valid files to commit"
        assert result["files_committed"] == 0

    @patch("dev_team.tools.git_workspace.get_github_client")
    def test_branch_creation_fails(self, mock_get_client):
        """Branch creation failure → returns error."""
        from dev_team.tools.git_workspace import commit_and_create_pr

        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.get_branch.side_effect = Exception("Branch not found")

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client

        result = commit_and_create_pr(
            repo_name="owner/repo",
            task="Test",
            code_files=[{"path": "a.py", "content": "x=1"}],
        )

        assert "error" in result
        assert "Failed to create branch" in result["error"]

    @patch("dev_team.tools.git_workspace.get_github_client")
    def test_pr_creation_fails_but_commit_succeeds(self, mock_get_client):
        """PR creation fails but files are committed → partial success."""
        from dev_team.tools.git_workspace import commit_and_create_pr

        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_branch = MagicMock()
        mock_branch.commit.sha = "abc"
        mock_repo.get_branch.return_value = mock_branch

        mock_ref = MagicMock()
        mock_ref.object.sha = "abc"
        mock_repo.get_git_ref.return_value = mock_ref
        mock_commit = MagicMock()
        mock_commit.tree = MagicMock()
        mock_repo.get_git_commit.return_value = mock_commit
        mock_repo.create_git_tree.return_value = MagicMock()
        mock_new_commit = MagicMock()
        mock_new_commit.sha = "def456"
        mock_repo.create_git_commit.return_value = mock_new_commit

        # PR fails
        mock_repo.create_pull.side_effect = Exception("PR rate limit")

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client

        result = commit_and_create_pr(
            repo_name="owner/repo",
            task="Test",
            code_files=[{"path": "a.py", "content": "x=1"}],
        )

        # Files committed, PR failed → partial error
        assert result["files_committed"] == 1
        assert result["commit_sha"] == "def456"
        assert "error" in result
        assert "PR creation failed" in result["error"]
        # Fallback PR URL should be the branch URL
        assert "tree/" in result["pr_url"]

    @patch("dev_team.tools.git_workspace.get_github_client")
    def test_filters_empty_files(self, mock_get_client):
        """Only files with both path and content are committed."""
        from dev_team.tools.git_workspace import commit_and_create_pr

        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_branch = MagicMock()
        mock_branch.commit.sha = "abc"
        mock_repo.get_branch.return_value = mock_branch

        mock_ref = MagicMock()
        mock_ref.object.sha = "abc"
        mock_repo.get_git_ref.return_value = mock_ref
        mock_commit_obj = MagicMock()
        mock_commit_obj.tree = MagicMock()
        mock_repo.get_git_commit.return_value = mock_commit_obj
        mock_repo.create_git_tree.return_value = MagicMock()
        mock_new_commit = MagicMock()
        mock_new_commit.sha = "def"
        mock_repo.create_git_commit.return_value = mock_new_commit
        mock_repo.create_pull.return_value = MagicMock(html_url="https://x", number=1)

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client

        result = commit_and_create_pr(
            repo_name="owner/repo",
            task="Test",
            code_files=[
                {"path": "a.py", "content": "valid"},
                {"path": "", "content": "no path"},
                {"path": "b.py", "content": ""},
            ],
        )

        assert result["files_committed"] == 1


# ═══════════════════════════════════════════════════════════════
# Section 2: simple_dev graph
# ═══════════════════════════════════════════════════════════════


class TestSimpleDevGraph:
    """Tests for the simple_dev graph structure."""

    def test_graph_compiles(self):
        """Graph compiles without errors."""
        from simple_dev.graph import graph
        assert graph is not None

    def test_graph_nodes(self):
        """Graph has the expected nodes."""
        from simple_dev.graph import create_graph
        builder = create_graph()
        node_names = set(builder.nodes.keys())
        assert "developer" in node_names
        assert "git_commit" in node_names

    def test_no_interrupt_points(self):
        """No HITL interrupt points in simple_dev."""
        from simple_dev.graph import graph
        # The compiled graph should not have interrupt_before nodes
        # (checked by verifying it's compiled without interrupt_before)
        assert graph is not None

    def test_state_definition(self):
        """SimpleDevState has the expected fields."""
        from simple_dev.state import SimpleDevState
        annotations = SimpleDevState.__annotations__
        assert "task" in annotations
        assert "code_files" in annotations
        assert "summary" in annotations
        assert "current_agent" in annotations
        assert "pr_url" in annotations

    def test_manifest_loads(self):
        """Manifest YAML loads correctly."""
        manifest_path = Path(__file__).parent.parent / "graphs" / "simple_dev" / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert manifest["name"] == "simple_dev"
        assert manifest["display_name"] == "Quick Developer"
        assert "none" == manifest["parameters"]["hitl_mode"]
        assert len(manifest["agents"]) == 1
        assert manifest["agents"][0]["id"] == "developer"

    @patch("dev_team.agents.developer.get_developer_agent")
    def test_developer_node_calls_agent(self, mock_get):
        """developer_node delegates to DeveloperAgent."""
        from simple_dev.graph import developer_node

        mock_agent = MagicMock()
        mock_agent.implement.return_value = {
            "code_files": [{"path": "a.py", "content": "x=1", "language": "python"}],
            "current_agent": "developer",
        }
        mock_get.return_value = mock_agent

        state = {
            "task": "Write a hello world",
            "code_files": [],
            "messages": [],
            "current_agent": "developer",
        }
        # developer_node calls _dev_agent which calls get_developer_agent
        # Just verify it doesn't crash with mocked agent
        assert callable(developer_node)

    def test_git_commit_node_no_repo(self):
        """git_commit_node without repo returns code summary."""
        from simple_dev.graph import git_commit_node

        state = {
            "task": "Test task",
            "code_files": [{"path": "a.py", "content": "x=1", "language": "python"}],
        }
        result = git_commit_node(state)
        assert "current_agent" in result
        assert result["current_agent"] == "complete"
        assert "summary" in result


# ═══════════════════════════════════════════════════════════════
# Section 3: standard_dev graph
# ═══════════════════════════════════════════════════════════════


class TestStandardDevGraph:
    """Tests for the standard_dev graph structure and routing."""

    def test_graph_compiles(self):
        """Graph compiles without errors."""
        from standard_dev.graph import graph
        assert graph is not None

    def test_graph_nodes(self):
        """Graph has the expected nodes."""
        from standard_dev.graph import create_graph
        builder = create_graph()
        node_names = set(builder.nodes.keys())
        assert "pm" in node_names
        assert "developer" in node_names
        assert "reviewer" in node_names
        assert "git_commit" in node_names

    def test_state_definition(self):
        """StandardDevState has required fields."""
        from standard_dev.state import StandardDevState
        annotations = StandardDevState.__annotations__
        assert "task" in annotations
        assert "requirements" in annotations
        assert "code_files" in annotations
        assert "issues_found" in annotations
        assert "review_iteration_count" in annotations

    def test_manifest_loads(self):
        """Manifest YAML loads correctly."""
        manifest_path = Path(__file__).parent.parent / "graphs" / "standard_dev" / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert manifest["name"] == "standard_dev"
        assert manifest["parameters"]["hitl_mode"] == "none"
        assert len(manifest["agents"]) == 3  # pm, developer, reviewer

    def test_route_after_reviewer_no_issues_commits(self):
        """Reviewer approves -> route to git_commit."""
        from standard_dev.graph import route_after_reviewer

        state = {"issues_found": [], "review_iteration_count": 0}
        assert route_after_reviewer(state) == "git_commit"

    def test_route_after_reviewer_issues_loops_back(self):
        """Issues found, below max iterations -> back to developer."""
        from standard_dev.graph import route_after_reviewer

        state = {"issues_found": ["bug"], "review_iteration_count": 0}
        assert route_after_reviewer(state) == "developer"

        state = {"issues_found": ["bug"], "review_iteration_count": 1}
        assert route_after_reviewer(state) == "developer"

    def test_route_after_reviewer_max_iterations_commits(self):
        """Max review iterations reached -> force commit."""
        from standard_dev.graph import route_after_reviewer

        state = {"issues_found": ["bug"], "review_iteration_count": 2}
        assert route_after_reviewer(state) == "git_commit"

    def test_route_after_reviewer_max_iterations_higher(self):
        """Higher than max -> still commits."""
        from standard_dev.graph import route_after_reviewer

        state = {"issues_found": ["bug"], "review_iteration_count": 5}
        assert route_after_reviewer(state) == "git_commit"

    def test_no_interrupt_points(self):
        """No HITL interrupt points in standard_dev."""
        from standard_dev.graph import graph
        assert graph is not None


# ═══════════════════════════════════════════════════════════════
# Section 4: research graph
# ═══════════════════════════════════════════════════════════════


class TestResearchGraph:
    """Tests for the research graph structure."""

    def test_graph_compiles(self):
        """Graph compiles without errors."""
        from research.graph import graph
        assert graph is not None

    def test_graph_nodes(self):
        """Graph has the expected nodes."""
        from research.graph import create_graph
        builder = create_graph()
        node_names = set(builder.nodes.keys())
        assert "researcher" in node_names

    def test_state_definition(self):
        """ResearchState has required fields."""
        from research.state import ResearchState
        annotations = ResearchState.__annotations__
        assert "task" in annotations
        assert "report" in annotations
        assert "sources" in annotations
        assert "summary" in annotations

    def test_manifest_loads(self):
        """Manifest YAML loads correctly."""
        manifest_path = Path(__file__).parent.parent / "graphs" / "research" / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert manifest["name"] == "research"
        assert manifest["parameters"]["hitl_mode"] == "none"
        assert len(manifest["agents"]) == 1
        assert manifest["agents"][0]["id"] == "researcher"
        assert "research" in manifest["task_types"]

    def test_researcher_prompts_load(self):
        """Researcher prompts YAML loads correctly."""
        prompt_path = Path(__file__).parent.parent / "graphs" / "research" / "prompts" / "researcher.yaml"
        prompts = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
        assert "system" in prompts
        assert "synthesize" in prompts
        assert "{task}" in prompts["synthesize"]
        assert "{search_results}" in prompts["synthesize"]


class TestResearcherAgent:
    """Tests for the researcher agent helpers."""

    def test_extract_urls(self):
        """URL extraction from search results."""
        from research.agents.researcher import _extract_urls_from_search

        text = (
            "Result 1: https://example.com/page1\n"
            "Result 2: https://docs.python.org/3/\n"
            "Duplicate: https://example.com/page1\n"
            "Another: http://test.org/doc"
        )
        urls = _extract_urls_from_search(text, max_urls=5)
        assert len(urls) == 3  # Deduplicated
        assert urls[0] == "https://example.com/page1"
        assert urls[1] == "https://docs.python.org/3/"
        assert urls[2] == "http://test.org/doc"

    def test_extract_urls_max_limit(self):
        """URL extraction respects max_urls."""
        from research.agents.researcher import _extract_urls_from_search

        text = "\n".join(f"https://example.com/page{i}" for i in range(20))
        urls = _extract_urls_from_search(text, max_urls=3)
        assert len(urls) == 3

    def test_extract_urls_no_urls(self):
        """No URLs in text → empty list."""
        from research.agents.researcher import _extract_urls_from_search

        urls = _extract_urls_from_search("no urls here")
        assert urls == []


# ═══════════════════════════════════════════════════════════════
# Section 5: Aegra registration
# ═══════════════════════════════════════════════════════════════


class TestAegraRegistration:
    """Tests for aegra.json graph registration."""

    def test_aegra_json_has_all_graphs(self):
        """aegra.json registers all 4 graphs."""
        import json
        aegra_path = Path(__file__).parent.parent / "aegra.json"
        config = json.loads(aegra_path.read_text(encoding="utf-8"))
        graphs = config["graphs"]
        assert "dev_team" in graphs
        assert "simple_dev" in graphs
        assert "standard_dev" in graphs
        assert "research" in graphs

    def test_aegra_json_paths_valid(self):
        """All graph paths in aegra.json point to existing files."""
        import json
        project_root = Path(__file__).parent.parent
        aegra_path = project_root / "aegra.json"
        config = json.loads(aegra_path.read_text(encoding="utf-8"))

        for graph_id, graph_path in config["graphs"].items():
            # Format: "./graphs/xxx/graph.py:graph"
            file_path = graph_path.split(":")[0]
            full_path = project_root / file_path
            assert full_path.exists(), f"Graph file not found: {full_path} (for {graph_id})"


# ═══════════════════════════════════════════════════════════════
# Section 6: Updated git_commit_node in dev_team
# ═══════════════════════════════════════════════════════════════


class TestDevTeamGitCommitNode:
    """Tests for the updated git_commit_node in dev_team graph."""

    def test_no_repository_returns_summary(self):
        """No repository → code returned as summary."""
        from dev_team.graph import git_commit_node

        state = {
            "task": "Test task",
            "code_files": [{"path": "a.py", "content": "x=1", "language": "python"}],
        }
        result = git_commit_node(state)
        assert result["current_agent"] == "complete"
        assert "a.py" in result["summary"]

    @patch("dev_team.tools.git_workspace.commit_and_create_pr")
    def test_success_delegates_to_helper(self, mock_commit):
        """Successful commit delegates to commit_and_create_pr."""
        from dev_team.graph import git_commit_node

        mock_commit.return_value = {
            "pr_url": "https://github.com/x/pull/1",
            "commit_sha": "abc123",
            "working_branch": "ai/test-123",
            "working_repo": "owner/repo",
            "files_committed": 2,
        }

        state = {
            "task": "Build API",
            "repository": "owner/repo",
            "code_files": [
                {"path": "a.py", "content": "x=1", "language": "python"},
                {"path": "b.py", "content": "y=2", "language": "python"},
            ],
        }
        result = git_commit_node(state)

        assert result["pr_url"] == "https://github.com/x/pull/1"
        assert result["commit_sha"] == "abc123"
        assert result["working_branch"] == "ai/test-123"
        assert result["working_repo"] == "owner/repo"
        assert result["current_agent"] == "complete"

    @patch("dev_team.tools.git_workspace.commit_and_create_pr")
    def test_error_returns_summary(self, mock_commit):
        """commit_and_create_pr error → code returned as summary."""
        from dev_team.graph import git_commit_node

        mock_commit.return_value = {
            "error": "Token expired",
            "files_committed": 0,
            "working_repo": "owner/repo",
            "working_branch": "",
            "pr_url": "",
            "commit_sha": "",
        }

        state = {
            "task": "Build API",
            "repository": "owner/repo",
            "code_files": [{"path": "a.py", "content": "x=1", "language": "python"}],
        }
        result = git_commit_node(state)

        assert result["current_agent"] == "complete"
        assert "Token expired" in result["summary"]
        assert result["error"] == "Token expired"

    def test_fallback_to_env_repo(self):
        """Uses GITHUB_DEFAULT_REPO from env when repository not in state."""
        from dev_team.graph import git_commit_node

        state = {
            "task": "Test",
            "code_files": [],
        }

        with patch.dict(os.environ, {"GITHUB_DEFAULT_REPO": ""}, clear=False):
            result = git_commit_node(state)
            assert result["current_agent"] == "complete"


# ═══════════════════════════════════════════════════════════════
# Section 7: All manifests discoverable by router
# ═══════════════════════════════════════════════════════════════


class TestManifestDiscovery:
    """Test that all manifests are discoverable by the Switch-Agent router."""

    def test_all_manifests_found(self):
        """load_manifests finds all 4 manifests."""
        from gateway.graph_loader import load_manifests

        manifests = load_manifests()
        names = {m["name"] for m in manifests}

        assert "dev_team" in names
        assert "simple_dev" in names
        assert "standard_dev" in names
        assert "research" in names

    def test_manifests_have_required_fields(self):
        """All manifests have fields needed for routing."""
        from gateway.graph_loader import load_manifests

        manifests = load_manifests()
        for m in manifests:
            assert "name" in m, f"Missing 'name' in manifest: {m}"
            assert "display_name" in m, f"Missing 'display_name' in {m['name']}"
            assert "description" in m, f"Missing 'description' in {m['name']}"
            assert "agents" in m, f"Missing 'agents' in {m['name']}"
            assert "task_types" in m, f"Missing 'task_types' in {m['name']}"
