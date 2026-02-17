"""
Git Workspace Tools
===================

High-level LangChain tools for Git-based agent workflow (Wave 2 — Module 3.1).

These tools let agents work through GitHub branches instead of keeping
``code_files`` in memory.  The typical lifecycle is:

  1. ``create_working_branch``  — create ``ai/<task>-<timestamp>`` branch
  2. ``read_file_from_branch``  — read existing files
  3. ``write_file_to_branch``   — write / update a single file (auto-commit)
  4. ``write_files_to_branch``  — batch-write multiple files in one commit
  5. ``list_files_on_branch``   — list directory contents
  6. ``get_branch_diff``        — diff against base branch (for QA review)
  7. ``create_pull_request_from_branch`` — open a PR when done

All tools use PyGithub under the hood and share the same lazy-init client
from ``tools/github.py``.

Environment variables:
  - ``GITHUB_TOKEN`` — required for all operations
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from typing import Optional

import structlog
from langchain_core.tools import tool

from dev_team.tools.github import get_github_client

logger = structlog.get_logger()


# ─────────────────────────── Helpers ──────────────────────────


def _generate_branch_name(task_summary: str = "") -> str:
    """Generate a unique branch name for the task.

    Format: ``ai/<slug>-<YYYYMMDD>-<HHMMSS>``

    Args:
        task_summary: Short task description (used for slug).

    Returns:
        Branch name string.
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    # Create a short slug from the task summary
    slug = task_summary.lower().strip()
    # Keep only alphanumeric + spaces, then join with dashes
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split()[:5])  # max 5 words
    if not slug:
        slug = "task"
    return f"ai/{slug}-{timestamp}"


def _get_repo(repo_name: str):
    """Get a PyGithub Repository object.

    Args:
        repo_name: Full repo name (``owner/repo``).

    Returns:
        ``github.Repository.Repository`` instance.

    Raises:
        RuntimeError: If GITHUB_TOKEN is missing or repo not found.
    """
    client = get_github_client()
    if not client:
        raise RuntimeError(
            "GitHub client not configured. Set GITHUB_TOKEN environment variable."
        )
    return client.get_repo(repo_name)


# ──────────────────────── Branch management ──────────────────────


@tool
def create_working_branch(
    repo: str,
    base_branch: str = "main",
    task_summary: str = "",
) -> str:
    """Create a new working branch for the current task.

    The branch is named ``ai/<slug>-<timestamp>`` to avoid collisions.

    Args:
        repo: Full repository name (e.g. ``owner/repo``).
        base_branch: Branch to fork from (default ``main``).
        task_summary: Short task description used in the branch name.

    Returns:
        Name of the created branch.
    """
    try:
        repository = _get_repo(repo)
        branch_name = _generate_branch_name(task_summary)

        base = repository.get_branch(base_branch)
        repository.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base.commit.sha,
        )
        logger.info(
            "git_workspace.branch_created",
            repo=repo,
            branch=branch_name,
            base=base_branch,
            base_sha=base.commit.sha[:8],
        )
        return branch_name
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("git_workspace.create_branch_failed", error=str(exc))
        return f"Error creating branch: {exc}"


# ──────────────────────── File operations ────────────────────────


@tool
def read_file_from_branch(repo: str, branch: str, path: str) -> str:
    """Read a file from a specific branch.

    Args:
        repo: Full repository name (``owner/repo``).
        branch: Branch name.
        path: File path inside the repository.

    Returns:
        File content as a UTF-8 string, or an error message.
    """
    try:
        repository = _get_repo(repo)
        content_file = repository.get_contents(path, ref=branch)

        if isinstance(content_file, list):
            return f"Error: '{path}' is a directory, not a file."

        decoded = base64.b64decode(content_file.content).decode("utf-8")
        logger.debug(
            "git_workspace.file_read",
            repo=repo,
            branch=branch,
            path=path,
            size=len(decoded),
        )
        return decoded
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error reading file '{path}': {exc}"


@tool
def write_file_to_branch(
    repo: str,
    branch: str,
    path: str,
    content: str,
    message: str = "",
) -> str:
    """Write or update a single file on a branch (creates a commit).

    If the file already exists it is updated; otherwise it is created.

    Args:
        repo: Full repository name (``owner/repo``).
        branch: Target branch name.
        path: File path inside the repository.
        content: New file content.
        message: Commit message (auto-generated if empty).

    Returns:
        Commit SHA of the new commit.
    """
    if not message:
        message = f"Update {path}" if "/" in path else f"Add {path}"

    try:
        repository = _get_repo(repo)

        # Check if file already exists
        try:
            existing = repository.get_contents(path, ref=branch)
            if isinstance(existing, list):
                return f"Error: '{path}' is a directory."
            result = repository.update_file(
                path=path,
                message=message,
                content=content,
                sha=existing.sha,
                branch=branch,
            )
        except Exception:
            # File does not exist — create
            result = repository.create_file(
                path=path,
                message=message,
                content=content,
                branch=branch,
            )

        sha = result["commit"].sha
        logger.info(
            "git_workspace.file_written",
            repo=repo,
            branch=branch,
            path=path,
            sha=sha[:8],
        )
        return f"Committed {path} → {sha}"
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("git_workspace.write_failed", path=path, error=str(exc))
        return f"Error writing file '{path}': {exc}"


@tool
def write_files_to_branch(
    repo: str,
    branch: str,
    files: list[dict],
    message: str = "Batch file update",
) -> str:
    """Write multiple files to a branch in a single Git commit.

    Uses the low-level Git tree API so that all changes appear in one
    commit (cleaner history, atomic update).

    Args:
        repo: Full repository name (``owner/repo``).
        branch: Target branch name.
        files: List of ``{"path": str, "content": str}`` dicts.
        message: Commit message for the batch.

    Returns:
        Commit SHA, or an error message.
    """
    if not files:
        return "Error: no files provided."

    try:
        repository = _get_repo(repo)

        # Get the current HEAD of the branch
        ref = repository.get_git_ref(f"heads/{branch}")
        base_sha = ref.object.sha
        base_commit = repository.get_git_commit(base_sha)
        base_tree = base_commit.tree

        # Build tree elements for each file
        from github import InputGitTreeElement

        tree_elements = []
        for f in files:
            tree_elements.append(
                InputGitTreeElement(
                    path=f["path"],
                    mode="100644",  # regular file
                    type="blob",
                    content=f["content"],
                )
            )

        # Create new tree and commit
        new_tree = repository.create_git_tree(tree_elements, base_tree=base_tree)
        new_commit = repository.create_git_commit(
            message=message,
            tree=new_tree,
            parents=[base_commit],
        )
        ref.edit(sha=new_commit.sha)

        logger.info(
            "git_workspace.batch_write",
            repo=repo,
            branch=branch,
            files_count=len(files),
            sha=new_commit.sha[:8],
        )
        return f"Committed {len(files)} files → {new_commit.sha}"
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("git_workspace.batch_write_failed", error=str(exc))
        return f"Error writing files: {exc}"


@tool
def list_files_on_branch(
    repo: str,
    branch: str,
    path: str = "",
    recursive: bool = False,
) -> str:
    """List files in a directory on a specific branch.

    Args:
        repo: Full repository name (``owner/repo``).
        branch: Branch name.
        path: Directory path (empty string for root).
        recursive: If True, list the entire tree recursively.

    Returns:
        Newline-separated list of file/directory names.
    """
    try:
        repository = _get_repo(repo)

        if recursive:
            # Use Git tree API for full recursive listing
            ref = repository.get_git_ref(f"heads/{branch}")
            tree = repository.get_git_tree(ref.object.sha, recursive=True)
            entries = []
            for item in tree.tree:
                if path and not item.path.startswith(path):
                    continue
                indicator = "dir" if item.type == "tree" else "file"
                entries.append(f"[{indicator}] {item.path}")
            logger.debug(
                "git_workspace.list_recursive",
                repo=repo,
                branch=branch,
                count=len(entries),
            )
            return "\n".join(entries) if entries else "Empty directory"

        # Non-recursive listing via Contents API
        contents = repository.get_contents(path or "", ref=branch)
        if not isinstance(contents, list):
            contents = [contents]

        entries = []
        for item in contents:
            indicator = "dir" if item.type == "dir" else "file"
            entries.append(f"[{indicator}] {item.path}")

        logger.debug(
            "git_workspace.list",
            repo=repo,
            branch=branch,
            path=path,
            count=len(entries),
        )
        return "\n".join(entries) if entries else "Empty directory"
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error listing files: {exc}"


# ──────────────────────── Diff & Review ──────────────────────────


@tool
def get_branch_diff(
    repo: str,
    branch: str,
    base: str = "main",
) -> str:
    """Get the diff between a working branch and its base branch.

    Useful for QA review: shows all changed files and their patches.

    Args:
        repo: Full repository name (``owner/repo``).
        branch: Working branch name.
        base: Base branch to compare against (default ``main``).

    Returns:
        Human-readable diff summary with patches.
    """
    try:
        repository = _get_repo(repo)
        comparison = repository.compare(base, branch)

        if comparison.total_commits == 0:
            return "No changes between branches."

        parts = [
            f"Comparing {base}...{branch}",
            f"Commits: {comparison.total_commits}",
            f"Files changed: {len(comparison.files)}",
            f"Additions: +{comparison.ahead_by} commits ahead",
            "",
        ]

        for f in comparison.files:
            parts.append(f"--- {f.filename} ({f.status}, +{f.additions}/-{f.deletions})")
            if f.patch:
                # Truncate very long patches
                patch = f.patch
                if len(patch) > 3000:
                    patch = patch[:3000] + "\n... (truncated)"
                parts.append(patch)
            parts.append("")

        diff_text = "\n".join(parts)
        logger.info(
            "git_workspace.diff",
            repo=repo,
            branch=branch,
            base=base,
            files=len(comparison.files),
            commits=comparison.total_commits,
        )
        return diff_text
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error getting diff: {exc}"


# ──────────────────────── Pull Request ───────────────────────────


@tool
def create_pull_request_from_branch(
    repo: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
    draft: bool = False,
) -> str:
    """Create a Pull Request from the working branch.

    Args:
        repo: Full repository name (``owner/repo``).
        branch: Source branch (the working branch).
        title: PR title.
        body: PR description (markdown).
        base: Target branch (default ``main``).
        draft: Create as draft PR (default ``False``).

    Returns:
        URL of the created PR.
    """
    try:
        repository = _get_repo(repo)
        pr = repository.create_pull(
            title=title,
            body=body,
            head=branch,
            base=base,
            draft=draft,
        )
        logger.info(
            "git_workspace.pr_created",
            repo=repo,
            branch=branch,
            pr_number=pr.number,
            pr_url=pr.html_url,
        )
        return pr.html_url
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.error("git_workspace.pr_failed", error=str(exc))
        return f"Error creating PR: {exc}"


# ──────────────────────── Cleanup ────────────────────────────────


@tool
def delete_working_branch(repo: str, branch: str) -> str:
    """Delete a working branch (cleanup after merge / abandon).

    Args:
        repo: Full repository name (``owner/repo``).
        branch: Branch name to delete.

    Returns:
        Confirmation message.
    """
    if not branch.startswith("ai/"):
        return f"Error: refusing to delete non-ai branch '{branch}'. Only ai/* branches can be deleted."

    try:
        repository = _get_repo(repo)
        ref = repository.get_git_ref(f"heads/{branch}")
        ref.delete()
        logger.info("git_workspace.branch_deleted", repo=repo, branch=branch)
        return f"Branch '{branch}' deleted."
    except RuntimeError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error deleting branch: {exc}"


# ──────────────────────── High-level workflow ────────────────────


def commit_and_create_pr(
    repo_name: str,
    task: str,
    code_files: list[dict],
    *,
    base_branch: str = "",
    draft: bool = False,
) -> dict:
    """Create a branch, commit all files atomically, and open a PR.

    This is a high-level convenience function used by ``git_commit`` nodes
    across different graphs.  It uses the Git tree API for a single atomic
    commit (instead of one commit per file).

    Args:
        repo_name: Full repository name (``owner/repo``).
        task: Task description (used for branch name & PR title).
        code_files: ``[{"path": str, "content": str, ...}, ...]``.
        base_branch: Branch to fork from (empty → repo default).
        draft: Create the PR as a draft.

    Returns:
        Dict with keys:
          - ``pr_url`` — URL of the created PR (or branch URL on failure)
          - ``commit_sha`` — SHA of the new commit
          - ``working_branch`` — name of the created branch
          - ``working_repo`` — repo_name echo
          - ``files_committed`` — number of files committed
          - ``error`` — error string if something went wrong (absent on success)
    """
    from github import InputGitTreeElement

    result: dict = {
        "working_repo": repo_name,
        "working_branch": "",
        "pr_url": "",
        "commit_sha": "",
        "files_committed": 0,
    }

    # ── Validate inputs ──────────────────────────────────────────
    valid_files = [
        f for f in code_files if f.get("path") and f.get("content")
    ]
    if not valid_files:
        result["error"] = "No valid files to commit"
        return result

    # ── Get repo ─────────────────────────────────────────────────
    try:
        repository = _get_repo(repo_name)
    except RuntimeError as exc:
        result["error"] = str(exc)
        return result

    # Resolve base branch robustly:
    # 1) explicit base_branch
    # 2) repository.default_branch
    # 3) common fallbacks (main/master)
    preferred = base_branch or repository.default_branch or ""
    env_default = os.getenv("GITHUB_DEFAULT_BRANCH", "").strip()
    branch_candidates = [preferred, env_default, "main", "master"]
    # Preserve order, remove empties/duplicates
    branch_candidates = list(dict.fromkeys([b for b in branch_candidates if b]))
    resolved_base_branch = ""
    branch_errors: list[str] = []
    for candidate in branch_candidates:
        try:
            repository.get_branch(candidate)
            resolved_base_branch = candidate
            break
        except Exception as exc:
            branch_errors.append(f"{candidate}: {exc}")
            continue

    # Fallback: pick first existing branch if direct checks failed
    if not resolved_base_branch:
        try:
            branches = list(repository.get_branches())
            if branches:
                resolved_base_branch = branches[0].name
                logger.info(
                    "git_workflow.base_branch_fallback",
                    repo=repo_name,
                    base=resolved_base_branch,
                    checked=branch_candidates,
                )
        except Exception as exc:
            branch_errors.append(f"list_branches: {exc}")

    if not resolved_base_branch:
        result["error"] = (
            "Failed to resolve base branch. "
            f"Checked={branch_candidates}. "
            f"Errors={'; '.join(branch_errors[-3:]) or 'n/a'}. "
            "Repository may be empty or inaccessible with current token."
        )
        return result

    # ── 1. Create branch ─────────────────────────────────────────
    branch_name = _generate_branch_name(task[:50])
    try:
        base = repository.get_branch(resolved_base_branch)
        repository.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base.commit.sha,
        )
        result["working_branch"] = branch_name
        logger.info(
            "git_workflow.branch_created",
            repo=repo_name,
            branch=branch_name,
            base=resolved_base_branch,
        )
    except Exception as exc:
        logger.error("git_workflow.branch_failed", error=str(exc))
        result["error"] = f"Failed to create branch: {exc}"
        return result

    # ── 2. Atomic batch commit via Git tree API ──────────────────
    try:
        ref = repository.get_git_ref(f"heads/{branch_name}")
        base_sha = ref.object.sha
        base_commit = repository.get_git_commit(base_sha)

        tree_elements = [
            InputGitTreeElement(
                path=f["path"],
                mode="100644",
                type="blob",
                content=f["content"],
            )
            for f in valid_files
        ]

        new_tree = repository.create_git_tree(
            tree_elements, base_tree=base_commit.tree,
        )
        commit_msg = f"feat: AI-crew implementation — {task[:80]}"
        new_commit = repository.create_git_commit(
            message=commit_msg,
            tree=new_tree,
            parents=[base_commit],
        )
        ref.edit(sha=new_commit.sha)

        result["commit_sha"] = new_commit.sha
        result["files_committed"] = len(valid_files)
        logger.info(
            "git_workflow.committed",
            repo=repo_name,
            branch=branch_name,
            files=len(valid_files),
            sha=new_commit.sha[:8],
        )
    except Exception as exc:
        logger.error("git_workflow.commit_failed", error=str(exc))
        result["error"] = f"Commit failed: {exc}"
        return result

    # ── 3. Create PR ─────────────────────────────────────────────
    pr_title = f"[AI-crew] {task[:80]}"
    pr_body = (
        f"## AI-Generated Code\n\n"
        f"**Task:** {task}\n\n"
        f"**Files ({len(valid_files)}):**\n"
        + "\n".join(f"- `{f['path']}`" for f in valid_files)
        + "\n\n---\n*Created automatically by AI-crew.*"
    )

    try:
        pr = repository.create_pull(
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base=resolved_base_branch,
            draft=draft,
        )
        result["pr_url"] = pr.html_url
        logger.info(
            "git_workflow.pr_created",
            repo=repo_name,
            pr_url=pr.html_url,
            pr_number=pr.number,
        )
    except Exception as exc:
        logger.error("git_workflow.pr_failed", error=str(exc))
        result["pr_url"] = f"https://github.com/{repo_name}/tree/{branch_name}"
        result["error"] = f"PR creation failed (branch exists): {exc}"

    return result


# ──────────────────────── Exports ────────────────────────────────

git_workspace_tools = [
    create_working_branch,
    read_file_from_branch,
    write_file_to_branch,
    write_files_to_branch,
    list_files_on_branch,
    get_branch_diff,
    create_pull_request_from_branch,
    delete_working_branch,
]
