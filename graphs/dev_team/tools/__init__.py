"""
Agent tools (LangChain ``@tool`` functions).

- ``github_tools``        — interact with GitHub repos (PRs, commits, branches)
- ``filesystem_tools``    — read/write files in a local workspace directory
- ``git_workspace_tools`` — high-level Git-based workflow (Wave 2)
- ``web_tools``           — web search, fetch URL, download file
- ``sandbox``             — code execution in isolated Docker containers (Wave 2)
- ``browser_runner``      — browser E2E test runner template (Visual QA Phase 1)
"""
from .github import github_tools
from .filesystem import filesystem_tools
from .git_workspace import git_workspace_tools
from .sandbox import run_code, run_tests, run_lint, SandboxClient, get_sandbox_client
from .browser_runner import build_runner_script, detect_framework_defaults

__all__ = [
    "github_tools",
    "filesystem_tools",
    "git_workspace_tools",
    "run_code",
    "run_tests",
    "run_lint",
    "SandboxClient",
    "get_sandbox_client",
    "build_runner_script",
    "detect_framework_defaults",
]
