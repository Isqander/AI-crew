"""
Shared utility functions for all graphs.
=========================================

Formatting and data helpers used by multiple graph definitions.
"""


def build_code_summary(code_files: list, task: str) -> str:
    """Format generated code files into a readable summary for the chat.

    Used by git_commit nodes across all graphs when no repository is
    configured (the generated code is returned inline in the summary).

    Args:
        code_files: List of CodeFile dicts (path, language, content).
        task: Original task description.

    Returns:
        Markdown-formatted summary string.
    """
    if not code_files:
        return f"Task completed: {task}\nNo code files were generated."

    parts = [f"Task completed: {task}", f"{len(code_files)} file(s) generated:\n"]
    for cf in code_files:
        path = cf.get("path", "unknown")
        lang = cf.get("language", "")
        content = cf.get("content", "")
        parts.append(f"### {path}")
        parts.append(f"```{lang}\n{content}\n```\n")
    return "\n".join(parts)


def format_code_files(code_files: list) -> str:
    """Format code files into a string for LLM prompts.

    Common pattern used by multiple agents when they need to include
    code context in their prompts.

    Args:
        code_files: List of CodeFile dicts.

    Returns:
        Formatted string with file headers and code blocks.
    """
    if not code_files:
        return "No code files"

    return "\n\n".join(
        f"### {f['path']}\n```{f.get('language', '')}\n{f.get('content', '')}\n```"
        for f in code_files
    )
