"""
Agent tools (LangChain ``@tool`` functions).

- ``github_tools``         — interact with GitHub repos (PRs, commits, branches)
- ``filesystem_tools``     — read/write files in a local workspace directory
- ``git_workspace_tools``  — high-level Git-based workflow (Wave 2)
- ``web_tools``            — web search, fetch URL, download file
- ``sandbox``              — code execution in isolated Docker containers (Wave 2)
- ``browser_runner``       — browser E2E test runner template (Visual QA Phase 1)
- ``github_actions_tools`` — CI/CD integration with GitHub Actions (Module 3.8)
- ``repo_manager``         — deploy repo management + GitHub Secrets injection
- ``deploy_pipeline``      — deploy health verification helpers
"""
from .github import github_tools
from .filesystem import filesystem_tools
from .git_workspace import git_workspace_tools
from .web import web_search, fetch_url, download_file
from .sandbox import run_code, run_tests, run_lint, SandboxClient, get_sandbox_client
from .browser_runner import build_runner_script, detect_framework_defaults
from .github_actions import (
    trigger_ci, wait_for_ci, get_ci_logs,
    github_actions_tools, GitHubActionsClient, get_ci_client,
)
from .repo_manager import RepoManager, DeploySecretsManager, get_repo_manager
from .deploy_pipeline import verify_deploy_health

# Convenient bundle for binding web tools to agents
web_tools = [web_search, fetch_url, download_file]

__all__ = [
    "github_tools",
    "filesystem_tools",
    "git_workspace_tools",
    "web_tools",
    "web_search",
    "fetch_url",
    "download_file",
    "run_code",
    "run_tests",
    "run_lint",
    "SandboxClient",
    "get_sandbox_client",
    "build_runner_script",
    "detect_framework_defaults",
    # CI/CD (Module 3.8)
    "trigger_ci",
    "wait_for_ci",
    "get_ci_logs",
    "github_actions_tools",
    "GitHubActionsClient",
    "get_ci_client",
    # Deploy pipeline
    "RepoManager",
    "DeploySecretsManager",
    "get_repo_manager",
    "verify_deploy_health",
]
