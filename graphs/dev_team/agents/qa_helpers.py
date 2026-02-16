"""
QA Helpers — shared static parsing utilities.

Used by qa_sandbox, qa_browser, and qa_exploration submodules.
"""

from __future__ import annotations

import json
import re

try:
    import yaml as _yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — optional dependency
    _yaml = None


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


# HTML markers — if 2+ are found in a non-UI file, it contains embedded HTML
# (common in FastAPI, Flask apps that return HTMLResponse inline).
_HTML_MARKERS = ("<html", "<form", "<input", "<button", "<div ", "<!doctype")


def _has_embedded_html(content: str) -> bool:
    """Detect HTML content embedded in a non-UI file (e.g. Python)."""
    lower = content.lower()
    return sum(1 for m in _HTML_MARKERS if m in lower) >= 2


_QA_HINTS_FILENAMES = (".qa-hints.yaml", ".qa-hints.yml", "qa-hints.yaml", "qa-hints.yml")


def extract_qa_hints(code_files: list[dict]) -> dict | None:
    """Extract the QA hints contract from code_files (if present).

    The Developer agent may generate a ``.qa-hints.yaml`` file that
    contains explicit selectors and test flows for the QA agent.

    Returns the parsed dict, or ``None`` if no hints file exists or
    parsing fails.
    """
    for f in code_files:
        path = (f.get("path") or "").lower()
        basename = path.rsplit("/", 1)[-1]
        if basename not in _QA_HINTS_FILENAMES:
            continue

        content = f.get("content", "")
        if not content.strip():
            continue

        # Try YAML parser first (preferred)
        if _yaml is not None:
            try:
                obj = _yaml.safe_load(content)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

        # Fallback: try JSON (LLM may output JSON instead of YAML)
        try:
            obj = json.loads(content)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def format_qa_hints_for_prompt(hints: dict) -> str:
    """Format QA hints into a human-readable text block for the LLM prompt.

    Produces a compact summary of selectors and test flows that helps
    the LLM build an accurate exploration plan.
    """
    if not hints:
        return ""

    parts: list[str] = []

    # --- Selectors ---
    selectors = hints.get("selectors")
    if isinstance(selectors, dict) and selectors:
        parts.append("## Available UI Selectors (from Developer):")
        for name, info in selectors.items():
            if isinstance(info, dict):
                css = info.get("css", "")
                el_type = info.get("type", "")
                text = info.get("text", "")
                placeholder = info.get("placeholder", "")
                note = info.get("note", "")
                item_css = info.get("item_css", "")

                desc = f"  - {name}: css=\"{css}\""
                if el_type:
                    desc += f"  type={el_type}"
                if text:
                    desc += f'  text="{text}"'
                if placeholder:
                    desc += f'  placeholder="{placeholder}"'
                if item_css:
                    desc += f"  item_css=\"{item_css}\""
                if note:
                    desc += f"  ({note})"
                parts.append(desc)
            else:
                parts.append(f"  - {name}: {info}")

    # --- Test flows ---
    test_flows = hints.get("test_flows")
    if isinstance(test_flows, dict) and test_flows:
        parts.append("")
        parts.append("## Suggested Test Flows (from Developer):")
        for flow_name, steps in test_flows.items():
            parts.append(f"  {flow_name}:")
            if isinstance(steps, list):
                for step in steps:
                    if isinstance(step, dict):
                        action = step.get("action", "?")
                        target = step.get("target", "")
                        value = step.get("value", "")
                        desc = f"    - {action}"
                        if target:
                            desc += f" → {target}"
                        if value:
                            desc += f' = "{value}"'
                        parts.append(desc)

    return "\n".join(parts)


def summarize_code_files(code_files: list[dict]) -> str:
    """Build a compact summary of code files for the LLM prompt.

    For UI files (HTML, CSS, JS) the full content is included so the
    LLM can see actual DOM selectors, class names, and element IDs.

    Also detects HTML content embedded in non-UI files (e.g. FastAPI /
    Flask Python files with inline HTML templates) and includes those
    in full so the LLM can see actual placeholder text, button labels,
    IDs, and other DOM attributes needed for accurate selector generation.
    """
    if not code_files:
        return "(no code files)"

    ui_extensions = (".html", ".css", ".js", ".jsx", ".tsx", ".vue", ".svelte")
    max_full_content = 4000
    max_preview = 500

    parts: list[str] = []
    for f in code_files[:15]:
        path = f.get("path", "unknown")
        content = f.get("content", "")
        lines = len(content.split("\n"))

        is_ui_file = any(path.lower().endswith(ext) for ext in ui_extensions)

        # Detect HTML embedded in Python/other files (FastAPI, Flask)
        if not is_ui_file:
            is_ui_file = _has_embedded_html(content)

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
