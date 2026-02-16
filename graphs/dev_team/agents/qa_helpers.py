"""
QA Helpers — shared static parsing utilities.

Used by qa_sandbox, qa_browser, and qa_exploration submodules.
"""

from __future__ import annotations

import json
import re


def parse_verdict(content: str, fallback_exit_code: int = -1) -> bool:
    """Parse PASS/FAIL verdict from LLM response.

    Looks for ``verdict: pass/fail`` (or ``approved/rejected``)
    in the LLM output.  Falls back to *fallback_exit_code* when
    no explicit verdict is found.
    """
    content_lower = content.lower()

    if "verdict: pass" in content_lower or "verdict: approved" in content_lower:
        return True
    if "verdict: fail" in content_lower or "verdict: rejected" in content_lower:
        return False

    # Fallback: exit_code == 0 and no "fail" keywords
    if fallback_exit_code == 0 and "fail" not in content_lower:
        return True

    return False


def parse_issues(content: str) -> list[str]:
    """Extract issue lines from LLM analysis."""
    issues: list[str] = []
    in_issues = False
    for line in content.split("\n"):
        stripped = line.strip()
        lower = stripped.lower()
        if "## issues" in lower or "## failures" in lower or "## problems" in lower:
            in_issues = True
            continue
        if in_issues and stripped.startswith("#"):
            in_issues = False
            continue
        if in_issues and stripped.startswith("- ") and "none" not in lower:
            issues.append(stripped[2:])
    return issues


def parse_defects(content: str) -> list[dict]:
    """Extract defect descriptions from ``## Visual Issues``
    and ``## Functional Issues`` sections."""
    defects: list[dict] = []
    in_section = False
    current_severity = "medium"

    for line in content.split("\n"):
        stripped = line.strip()
        lower = stripped.lower()

        if "## visual issues" in lower:
            in_section = True
            current_severity = "medium"
            continue
        if "## functional issues" in lower:
            in_section = True
            current_severity = "high"
            continue
        if in_section and stripped.startswith("#"):
            in_section = False
            continue
        if in_section and stripped.startswith("- ") and "none" not in lower:
            defects.append({
                "description": stripped[2:],
                "severity": current_severity,
            })

    return defects


def extract_code_block(content: str) -> str:
    """Extract the first fenced code block from LLM output.

    Supports ```python ... ``` and ``` ... ``` formats.
    Returns the code without the fences, or empty string if none found.
    """
    pattern = r"```(?:python)?\s*\n(.*?)```"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback: if the entire response looks like code, return it
    if "import " in content and "def " in content:
        return content.strip()

    return ""


def extract_json(content: str) -> dict | None:
    """Extract a JSON object from LLM output.

    Tries several strategies:
      1. Direct ``json.loads`` on the full content
      2. Extract from ```json ... ``` fences
      3. Find the first ``{ ... }`` block
    """
    content = content.strip()

    # Strategy 1: direct parse
    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: fenced JSON
    match = re.search(r"```(?:json)?\s*\n(.*?)```", content, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: find outermost { ... }
    brace_start = content.find("{")
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(content[brace_start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break

    return None


def summarize_code_files(code_files: list[dict]) -> str:
    """Build a compact summary of code files for the LLM prompt.

    For UI files (HTML, CSS, JS) the full content is included so the
    LLM can see actual DOM selectors, class names, and element IDs.
    """
    if not code_files:
        return "(no code files)"

    ui_extensions = (".html", ".css", ".js", ".jsx", ".tsx", ".vue", ".svelte")
    max_full_content = 3000
    max_preview = 500

    parts: list[str] = []
    for f in code_files[:15]:
        path = f.get("path", "unknown")
        content = f.get("content", "")
        lines = len(content.split("\n"))

        is_ui_file = any(path.lower().endswith(ext) for ext in ui_extensions)

        if is_ui_file and len(content) <= max_full_content:
            parts.append(f"  {path} ({lines} lines):\n{content}")
        else:
            preview = content[:max_preview]
            if len(content) > max_preview:
                preview += f"\n    ... [{lines} lines total]"
            parts.append(f"  {path} ({lines} lines):\n    {preview}")

    if len(code_files) > 15:
        parts.append(f"  ... and {len(code_files) - 15} more files")

    return "\n".join(parts)
