"""
Shared git_commit_node factory for all graphs.
================================================

Provides ``make_git_commit_node`` — a factory that creates a
graph-specific ``git_commit_node`` function.  The returned node
uses ``commit_and_create_pr`` for atomic Git operations and
gracefully falls back to inline code summary when no repository
is configured.
"""

import os
import time as _time

import structlog

from .utils import build_code_summary

logger = structlog.get_logger()


def make_git_commit_node(graph_name: str = "graph"):
    """Create a git_commit_node function for a specific graph.

    The returned node function:
      1. Reads ``code_files``, ``repository``, ``task`` from state
      2. If no repository → returns code as inline summary
      3. Otherwise → uses ``commit_and_create_pr`` for atomic commit + PR
      4. Returns ``pr_url``, ``commit_sha``, ``working_branch``, ``summary``

    Args:
        graph_name: Name used in log messages (e.g. "dev_team", "simple_dev").

    Returns:
        A node function ``git_commit_node(state) -> dict``.
    """

    def git_commit_node(state: dict) -> dict:
        # Deferred import to avoid circular deps at module load time
        from dev_team.tools.git_workspace import commit_and_create_pr

        t0 = _time.monotonic()
        code_files = list(state.get("code_files", []))
        infra_files = state.get("infra_files") or []
        repository = state.get("repository") or os.getenv("GITHUB_DEFAULT_REPO", "")
        task = state.get("task", "AI-generated task")
        github_token_set = bool(os.getenv("GITHUB_TOKEN"))

        # Merge infra_files (from DevOps agent) into code_files for a single commit
        if infra_files:
            existing_paths = {f.get("path") for f in code_files}
            for inf in infra_files:
                if inf.get("path") and inf.get("path") not in existing_paths:
                    code_files.append({"path": inf["path"], "content": inf.get("content", "")})
            logger.info(f"{graph_name}.git_commit.infra_merged",
                         infra_files=len(infra_files),
                         total_files=len(code_files))

        logger.info(f"{graph_name}.git_commit.enter",
                     repository=repository or "none",
                     files=len(code_files),
                     github_token_set=github_token_set,
                     task_preview=task[:80])

        # Guard: no repository -> return code in summary
        if not repository:
            elapsed_ms = (_time.monotonic() - t0) * 1000
            logger.warning(f"{graph_name}.git_commit.skip",
                           reason="no_repository",
                           elapsed_ms=round(elapsed_ms))
            return {
                "summary": build_code_summary(code_files, task),
                "current_agent": "complete",
            }

        # Delegate to commit_and_create_pr (atomic commit + PR)
        logger.info(f"{graph_name}.git_commit.committing",
                     repository=repository, files=len(code_files))
        result = commit_and_create_pr(
            repo_name=repository,
            task=task,
            code_files=code_files,
        )

        elapsed_ms = (_time.monotonic() - t0) * 1000

        # Handle errors gracefully
        if result.get("error") and result.get("files_committed", 0) == 0:
            logger.error(f"{graph_name}.git_commit.failed",
                         error=result["error"],
                         elapsed_ms=round(elapsed_ms))
            summary = build_code_summary(code_files, task)
            return {
                "summary": f"Warning: Git commit failed: {result['error']}\n\n{summary}",
                "current_agent": "complete",
                "error": result["error"],
            }

        pr_url = result.get("pr_url", "")
        commit_sha = result.get("commit_sha", "")
        branch = result.get("working_branch", "")
        committed = result.get("files_committed", 0)

        logger.info(f"{graph_name}.git_commit.success",
                     pr_url=pr_url, branch=branch,
                     commit_sha=commit_sha[:12] if commit_sha else "",
                     files_committed=committed,
                     elapsed_ms=round(elapsed_ms))

        return {
            "pr_url": pr_url,
            "commit_sha": commit_sha,
            "working_branch": branch,
            "working_repo": repository,
            "summary": (
                f"Created PR with {committed} file(s) on {repository}\n"
                f"Branch: {branch}\n"
                f"PR: {pr_url}"
            ),
            "current_agent": "complete",
        }

    git_commit_node.__doc__ = (
        f"Commit generated code to GitHub ({graph_name}).\n\n"
        "Uses atomic Git tree API for single-commit operations.\n"
        "Falls back to inline code summary when no repo is configured."
    )

    return git_commit_node
