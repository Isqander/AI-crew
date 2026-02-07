"""
GitHub Integration Tools

Provides LangChain tools for interacting with GitHub repositories:
  - create_pull_request: Create a PR
  - create_branch: Create a branch
  - commit_file: Commit/update a single file
  - get_file_content: Read a file from a repo
  - list_repository_files: List directory contents

All tools require GITHUB_TOKEN environment variable and PyGithub package.
"""

import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub client (lazy singleton)
# ---------------------------------------------------------------------------
_github_client = None


def get_github_client():
    """Get or create a PyGithub client using GITHUB_TOKEN env var.

    Returns:
        ``Github`` instance or ``None`` when the token is missing or
        PyGithub is not installed.
    """
    global _github_client
    if _github_client is None:
        try:
            from github import Github  # noqa: WPS433
            token = os.getenv("GITHUB_TOKEN")
            if token:
                _github_client = Github(token)
                logger.debug("GitHub client initialized")
            else:
                logger.debug("GITHUB_TOKEN not set — GitHub client unavailable")
        except ImportError:
            logger.warning("PyGithub not installed — GitHub tools disabled")
    return _github_client


@tool
def create_pull_request(
    repo_name: str,
    title: str,
    body: str,
    branch: str,
    base: str = "main"
) -> str:
    """
    Create a pull request in a GitHub repository.
    
    Args:
        repo_name: Full repository name (e.g., "owner/repo")
        title: PR title
        body: PR description
        branch: Source branch name
        base: Target branch name (default: main)
        
    Returns:
        URL of the created pull request
    """
    client = get_github_client()
    if not client:
        return "Error: GitHub client not configured. Set GITHUB_TOKEN environment variable."
    
    try:
        repo = client.get_repo(repo_name)
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base=base,
        )
        return f"Pull request created: {pr.html_url}"
    except Exception as e:
        return f"Error creating pull request: {str(e)}"


@tool
def create_branch(
    repo_name: str,
    branch_name: str,
    base_branch: str = "main"
) -> str:
    """
    Create a new branch in a GitHub repository.
    
    Args:
        repo_name: Full repository name (e.g., "owner/repo")
        branch_name: Name for the new branch
        base_branch: Branch to create from (default: main)
        
    Returns:
        Confirmation message
    """
    client = get_github_client()
    if not client:
        return "Error: GitHub client not configured. Set GITHUB_TOKEN environment variable."
    
    try:
        repo = client.get_repo(repo_name)
        base = repo.get_branch(base_branch)
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base.commit.sha
        )
        return f"Branch '{branch_name}' created from '{base_branch}'"
    except Exception as e:
        return f"Error creating branch: {str(e)}"


@tool
def commit_file(
    repo_name: str,
    file_path: str,
    content: str,
    commit_message: str,
    branch: str = "main"
) -> str:
    """
    Commit a file to a GitHub repository.
    
    Args:
        repo_name: Full repository name (e.g., "owner/repo")
        file_path: Path to the file in the repository
        content: File content
        commit_message: Commit message
        branch: Branch to commit to (default: main)
        
    Returns:
        Commit SHA
    """
    client = get_github_client()
    if not client:
        return "Error: GitHub client not configured. Set GITHUB_TOKEN environment variable."
    
    try:
        repo = client.get_repo(repo_name)
        
        # Check if file exists
        try:
            existing_file = repo.get_contents(file_path, ref=branch)
            # Update existing file
            result = repo.update_file(
                path=file_path,
                message=commit_message,
                content=content,
                sha=existing_file.sha,
                branch=branch,
            )
        except Exception:  # file does not exist yet
            # Create new file
            result = repo.create_file(
                path=file_path,
                message=commit_message,
                content=content,
                branch=branch,
            )
        
        return f"File committed: {result['commit'].sha}"
    except Exception as e:
        return f"Error committing file: {str(e)}"


@tool
def get_file_content(
    repo_name: str,
    file_path: str,
    branch: str = "main"
) -> str:
    """
    Get content of a file from a GitHub repository.
    
    Args:
        repo_name: Full repository name (e.g., "owner/repo")
        file_path: Path to the file in the repository
        branch: Branch to read from (default: main)
        
    Returns:
        File content
    """
    client = get_github_client()
    if not client:
        return "Error: GitHub client not configured. Set GITHUB_TOKEN environment variable."
    
    try:
        repo = client.get_repo(repo_name)
        content = repo.get_contents(file_path, ref=branch)
        return content.decoded_content.decode('utf-8')
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def list_repository_files(
    repo_name: str,
    path: str = "",
    branch: str = "main"
) -> str:
    """
    List files in a GitHub repository directory.
    
    Args:
        repo_name: Full repository name (e.g., "owner/repo")
        path: Directory path (empty for root)
        branch: Branch to list from (default: main)
        
    Returns:
        List of files and directories
    """
    client = get_github_client()
    if not client:
        return "Error: GitHub client not configured. Set GITHUB_TOKEN environment variable."
    
    try:
        repo = client.get_repo(repo_name)
        contents = repo.get_contents(path, ref=branch)
        
        if not isinstance(contents, list):
            contents = [contents]
        
        files = []
        for item in contents:
            type_indicator = "📁" if item.type == "dir" else "📄"
            files.append(f"{type_indicator} {item.path}")
        
        return "\n".join(files) if files else "Empty directory"
    except Exception as e:
        return f"Error listing files: {str(e)}"


# Export tools as a list
github_tools = [
    create_pull_request,
    create_branch,
    commit_file,
    get_file_content,
    list_repository_files,
]
