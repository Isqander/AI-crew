"""
GitHub Actions CI/CD Tools (Module 3.8)
=======================================

LangChain ``@tool`` wrappers for interacting with GitHub Actions CI/CD.

Tools:
  ``trigger_ci``  — push triggers CI automatically; this dispatches a workflow
  ``wait_for_ci`` — poll workflow run status until completion
  ``get_ci_logs`` — retrieve logs from a completed workflow run

These tools use PyGithub (``github.Github``) for API access.
``GITHUB_TOKEN`` env var must be set with ``repo`` + ``actions`` scopes.
"""

from __future__ import annotations

import os
import time
from typing import Any

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Default CI polling parameters
CI_POLL_INTERVAL = int(os.getenv("CI_POLL_INTERVAL", "15"))    # seconds
CI_MAX_WAIT = int(os.getenv("CI_MAX_WAIT", "600"))              # 10 min max


# ------------------------------------------------------------------
# Low-level GitHub Actions client
# ------------------------------------------------------------------


class GitHubActionsClient:
    """Wrapper around PyGithub for CI/CD operations.

    Provides methods to trigger, monitor and retrieve logs from
    GitHub Actions workflow runs.
    """

    def __init__(self, token: str | None = None, github_client: Any = None):
        """Initialise with a GitHub token or an existing PyGithub client.

        Parameters
        ----------
        token:
            GitHub personal access token.  Defaults to ``GITHUB_TOKEN`` env var.
        github_client:
            Injected ``github.Github`` instance (useful for testing).
        """
        if github_client is not None:
            self._gh = github_client
        else:
            try:
                from github import Github
                self._gh = Github(token or GITHUB_TOKEN)
            except ImportError:
                raise RuntimeError(
                    "PyGithub is required for GitHub Actions tools. "
                    "Install it with: pip install PyGithub"
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_latest_workflow_run(
        self,
        repo: str,
        branch: str,
        event: str = "push",
    ) -> dict:
        """Get the latest workflow run for a branch.

        Parameters
        ----------
        repo:
            Repository in ``owner/name`` format.
        branch:
            Branch name (e.g. ``ai/task-20260216-123456``).
        event:
            GitHub Actions trigger event (default: ``push``).

        Returns
        -------
        dict with keys:
            ``run_id``, ``status``, ``conclusion``, ``name``,
            ``html_url``, ``created_at``, ``updated_at``.
        """
        gh_repo = self._gh.get_repo(repo)
        runs = gh_repo.get_workflow_runs(branch=branch, event=event)

        for run in runs:
            return {
                "run_id": run.id,
                "status": run.status,
                "conclusion": run.conclusion,
                "name": run.name,
                "html_url": run.html_url,
                "created_at": str(run.created_at),
                "updated_at": str(run.updated_at),
            }

        return {"run_id": None, "status": "not_found", "conclusion": None}

    def wait_for_completion(
        self,
        repo: str,
        run_id: int,
        poll_interval: int = CI_POLL_INTERVAL,
        max_wait: int = CI_MAX_WAIT,
    ) -> dict:
        """Poll a workflow run until it completes or times out.

        Parameters
        ----------
        repo:
            Repository in ``owner/name`` format.
        run_id:
            GitHub Actions workflow run ID.
        poll_interval:
            Seconds between status checks.
        max_wait:
            Maximum seconds to wait before timing out.

        Returns
        -------
        dict with final run state:
            ``run_id``, ``status``, ``conclusion``, ``elapsed_seconds``,
            ``html_url``.
        """
        gh_repo = self._gh.get_repo(repo)
        start = time.monotonic()
        elapsed = 0.0

        logger.info("ci.wait_start", repo=repo, run_id=run_id, max_wait=max_wait)

        while elapsed < max_wait:
            run = gh_repo.get_workflow_run(run_id)
            elapsed = time.monotonic() - start

            logger.debug(
                "ci.poll",
                run_id=run_id,
                status=run.status,
                conclusion=run.conclusion,
                elapsed_s=round(elapsed, 1),
            )

            if run.status == "completed":
                logger.info(
                    "ci.completed",
                    run_id=run_id,
                    conclusion=run.conclusion,
                    elapsed_s=round(elapsed, 1),
                )
                return {
                    "run_id": run_id,
                    "status": "completed",
                    "conclusion": run.conclusion,  # "success", "failure", "cancelled"
                    "elapsed_seconds": round(elapsed, 1),
                    "html_url": run.html_url,
                }

            time.sleep(poll_interval)

        logger.warning("ci.timeout", run_id=run_id, elapsed_s=round(elapsed, 1))
        return {
            "run_id": run_id,
            "status": "timeout",
            "conclusion": None,
            "elapsed_seconds": round(elapsed, 1),
            "html_url": "",
        }

    def get_run_logs(self, repo: str, run_id: int) -> dict:
        """Retrieve logs from a completed workflow run.

        Extracts job names and their log content (truncated to avoid
        excessive token usage).

        Parameters
        ----------
        repo:
            Repository in ``owner/name`` format.
        run_id:
            GitHub Actions workflow run ID.

        Returns
        -------
        dict with keys:
            ``run_id``, ``conclusion``, ``jobs`` (list of
            ``{name, status, conclusion, steps}``).
        """
        gh_repo = self._gh.get_repo(repo)
        run = gh_repo.get_workflow_run(run_id)
        jobs_data = []

        for job in run.jobs():
            steps = []
            for step in job.steps:
                steps.append({
                    "name": step.name,
                    "status": step.status,
                    "conclusion": step.conclusion,
                    "number": step.number,
                })
            jobs_data.append({
                "name": job.name,
                "status": job.status,
                "conclusion": job.conclusion,
                "steps": steps,
            })

        return {
            "run_id": run_id,
            "conclusion": run.conclusion,
            "jobs": jobs_data,
        }

    def trigger_workflow_dispatch(
        self,
        repo: str,
        workflow_file: str,
        branch: str,
        inputs: dict[str, str] | None = None,
    ) -> dict:
        """Trigger a workflow via workflow_dispatch event.

        Not all workflows support this — the workflow YAML must have
        ``on: workflow_dispatch``.

        Parameters
        ----------
        repo:
            Repository in ``owner/name`` format.
        workflow_file:
            Workflow filename (e.g. ``ci.yml``).
        branch:
            Branch to run the workflow on.
        inputs:
            Optional inputs for the workflow.

        Returns
        -------
        dict: ``{triggered: bool, workflow: str, branch: str}``
        """
        gh_repo = self._gh.get_repo(repo)

        try:
            workflow = None
            try:
                workflow = gh_repo.get_workflow(workflow_file)
            except Exception:
                # Fallback: try resolve by iterating known workflows and matching file name suffix.
                try:
                    target = workflow_file.lower().split("/")[-1]
                    for wf in gh_repo.get_workflows():
                        wf_path = (getattr(wf, "path", "") or "").lower()
                        wf_name = (getattr(wf, "name", "") or "").lower()
                        if wf_path.endswith(f"/{target}") or wf_path.endswith(target) or wf_name == target.replace(".yml", "").replace(".yaml", ""):
                            workflow = wf
                            break
                except Exception:
                    workflow = None

            if workflow is None:
                return {
                    "triggered": False,
                    "workflow": workflow_file,
                    "branch": branch,
                    "error": f"workflow '{workflow_file}' not found (or inaccessible) in repo metadata",
                }

            success = workflow.create_dispatch(branch, inputs or {})

            logger.info(
                "ci.dispatch",
                repo=repo,
                workflow=workflow_file,
                branch=branch,
                success=success,
            )
            return {
                "triggered": bool(success),
                "workflow": workflow_file,
                "branch": branch,
            }
        except Exception as exc:
            logger.error("ci.dispatch.error", error=str(exc)[:300])
            return {
                "triggered": False,
                "workflow": workflow_file,
                "branch": branch,
                "error": str(exc)[:300],
            }


# ------------------------------------------------------------------
# Global client singleton
# ------------------------------------------------------------------

_ci_client: GitHubActionsClient | None = None


def get_ci_client() -> GitHubActionsClient:
    """Get or create the global GitHubActionsClient."""
    global _ci_client
    if _ci_client is None:
        _ci_client = GitHubActionsClient()
    return _ci_client


# ------------------------------------------------------------------
# LangChain @tool wrappers
# ------------------------------------------------------------------


@tool
def trigger_ci(
    repo: str,
    branch: str,
    workflow_file: str = "ci.yml",
) -> str:
    """Trigger a CI workflow via workflow_dispatch on GitHub Actions.

    Args:
        repo: Repository in owner/name format (e.g. 'myorg/myapp')
        branch: Branch to run CI on (e.g. 'ai/task-20260216-123456')
        workflow_file: Workflow filename (default: 'ci.yml')

    Returns:
        Status message indicating whether the workflow was triggered.
    """
    client = get_ci_client()
    result = client.trigger_workflow_dispatch(repo, workflow_file, branch)

    if result.get("triggered"):
        return f"CI workflow '{workflow_file}' triggered on branch '{branch}' in {repo}."
    error = result.get("error", "unknown error")
    return f"Failed to trigger CI: {error}"


@tool
def wait_for_ci(
    repo: str,
    branch: str,
    run_id: int | None = None,
    max_wait: int = 600,
) -> str:
    """Wait for a CI workflow run to complete on GitHub Actions.

    If run_id is not provided, finds the latest run for the branch.

    Args:
        repo: Repository in owner/name format
        branch: Branch name to look for CI runs
        run_id: Optional specific workflow run ID to monitor
        max_wait: Maximum seconds to wait (default: 600)

    Returns:
        CI result: status, conclusion, elapsed time, and URL.
    """
    client = get_ci_client()

    if run_id is None:
        latest = client.get_latest_workflow_run(repo, branch)
        run_id = latest.get("run_id")
        if run_id is None:
            return f"No CI workflow run found for branch '{branch}' in {repo}."

    result = client.wait_for_completion(repo, run_id, max_wait=max_wait)

    status = result.get("status", "unknown")
    conclusion = result.get("conclusion", "unknown")
    elapsed = result.get("elapsed_seconds", 0)
    url = result.get("html_url", "")

    if status == "completed":
        return (
            f"CI {conclusion.upper()}: {repo} run #{run_id}\n"
            f"Elapsed: {elapsed}s\n"
            f"URL: {url}"
        )
    if status == "timeout":
        return f"CI TIMEOUT: waited {elapsed}s for run #{run_id}. Check manually."

    return f"CI status: {status}, conclusion: {conclusion}"


@tool
def get_ci_logs(
    repo: str,
    run_id: int,
) -> str:
    """Get CI workflow run logs from GitHub Actions.

    Returns job names, step results, and failure details.

    Args:
        repo: Repository in owner/name format
        run_id: GitHub Actions workflow run ID

    Returns:
        Formatted CI log summary with job/step results.
    """
    client = get_ci_client()
    result = client.get_run_logs(repo, run_id)

    parts = [f"CI Run #{run_id} — {result.get('conclusion', 'unknown').upper()}"]

    for job in result.get("jobs", []):
        icon = "PASS" if job["conclusion"] == "success" else "FAIL"
        parts.append(f"\n[{icon}] Job: {job['name']}")

        for step in job.get("steps", []):
            step_icon = "ok" if step["conclusion"] == "success" else "FAIL"
            parts.append(f"  [{step_icon}] Step {step['number']}: {step['name']}")

    if not result.get("jobs"):
        parts.append("No jobs found (workflow may still be running).")

    return "\n".join(parts)


# Convenient export list
github_actions_tools = [trigger_ci, wait_for_ci, get_ci_logs]
