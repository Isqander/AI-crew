"""
QA Browser — Playwright E2E testing (Visual QA Phase 1).

Generates Playwright tests from user stories and code,
runs them in the browser sandbox, and analyses the results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from .base import create_prompt_template
from .qa_helpers import (
    parse_verdict,
    parse_issues,
    parse_defects,
    extract_code_block,
    summarize_code_files,
    extract_qa_hints,
    format_qa_hints_for_prompt,
)
from ..tools.browser_runner import build_runner_script, detect_framework_defaults

if TYPE_CHECKING:
    from .qa import QAAgent
    from ..state import DevTeamState

logger = structlog.get_logger()

# UI framework indicators (lowercase)
UI_INDICATORS: set[str] = {
    "react", "vue", "angular", "svelte", "next.js", "nuxt",
    "nextjs", "gatsby", "vite", "html", "css", "tailwind",
    "bootstrap", "frontend", "web", "ui", "next", "remix",
    "solid", "solidjs", "astro", "qwik", "preact",
}


def has_ui(state: DevTeamState) -> bool:
    """Determine if the project has a UI component.

    Checks ``tech_stack`` and ``code_files`` for indicators of
    a frontend / web UI project.
    """
    tech_stack = state.get("tech_stack", [])
    for tech in tech_stack:
        if tech.lower().replace(".", "").replace("js", "").strip() in UI_INDICATORS:
            return True
        for indicator in UI_INDICATORS:
            if indicator in tech.lower():
                return True

    ui_extensions = (".html", ".jsx", ".tsx", ".vue", ".svelte", ".astro")
    for f in state.get("code_files", []):
        path = f.get("path", "").lower()
        if any(path.endswith(ext) for ext in ui_extensions):
            return True

    return False


def _generate_browser_test(agent: QAAgent, state: DevTeamState, config=None) -> str:
    """Use LLM to generate a Playwright test script.

    Returns a Python source string (pytest-playwright style), or
    empty string on failure.
    """
    prompt = create_prompt_template(
        agent.system_prompt,
        agent.prompts["generate_browser_test"],
    )
    chain = prompt | agent.llm

    user_stories = state.get("user_stories", [])
    stories_text = "\n".join(
        f"- {s.get('title', '')}: {s.get('description', '')}"
        for s in user_stories[:5]
    ) if user_stories else "No user stories available"

    tech_stack = ", ".join(state.get("tech_stack", [])) or "Unknown"
    code_files = state.get("code_files", [])
    code_structure = summarize_code_files(code_files)

    # Extract QA hints (UI Test Contract)
    qa_hints = extract_qa_hints(code_files)
    qa_hints_text = format_qa_hints_for_prompt(qa_hints) if qa_hints else ""
    if qa_hints:
        logger.info("qa.generate_browser_test.qa_hints_found",
                     selectors=len(qa_hints.get("selectors", {})))

    try:
        response = agent._invoke_chain(chain, {
            "task": state.get("task", ""),
            "user_stories": stories_text,
            "tech_stack": tech_stack,
            "code_structure": code_structure,
            "qa_hints": qa_hints_text,
        }, config=config)

        return extract_code_block(response.content)
    except Exception as exc:
        logger.error("qa.generate_browser_test.failed", error=str(exc)[:300])
        return ""


def _analyse_browser_results(
    agent: QAAgent,
    task: str,
    sandbox_result: dict,
    config=None,
) -> dict:
    """Use LLM to interpret browser test output and screenshots.

    Returns ``{"approved": bool, "issues": list[str], "defects": list[dict]}``.
    """
    prompt = create_prompt_template(
        agent.system_prompt,
        agent.prompts["analyse_browser_results"],
    )
    chain = prompt | agent.llm

    stdout = sandbox_result.get("stdout", "")[:4000]
    stderr = sandbox_result.get("stderr", "")[:4000]
    console_logs = sandbox_result.get("browser_console", "")[:2000]
    network_errors = sandbox_result.get("network_errors", [])

    try:
        response = agent._invoke_chain(chain, {
            "task": task,
            "exit_code": str(sandbox_result.get("exit_code", -1)),
            "stdout": stdout or "(empty)",
            "stderr": stderr or "(empty)",
            "console_logs": console_logs or "(none)",
            "network_errors": ", ".join(network_errors[:10]) or "(none)",
        }, config=config)

        content = response.content
        approved = parse_verdict(content, sandbox_result.get("exit_code", -1))
        issues = parse_issues(content)
        defects = parse_defects(content)

        return {
            "approved": approved,
            "issues": issues,
            "defects": defects,
            "explanation": content,
        }
    except Exception as exc:
        logger.error("qa.analyse_browser_results.failed", error=str(exc)[:300])
        return {
            "approved": sandbox_result.get("exit_code", -1) == 0,
            "issues": [f"Browser analysis failed: {exc}"],
            "defects": [],
            "explanation": f"Analysis error: {exc}",
        }


def run_browser_tests(agent: QAAgent, state: DevTeamState, config=None) -> dict:
    """Generate and run Playwright E2E tests for UI projects.

    Returns a dict with ``browser_test_results`` and ``issues_found``.
    """
    code_files = state.get("code_files", [])
    task = state.get("task", "")
    tech_stack = state.get("tech_stack", [])

    logger.info(
        "qa.test_ui.start",
        files=len(code_files),
        tech_stack=tech_stack[:5],
    )

    # ── 1. Generate Playwright test script ──
    test_script = _generate_browser_test(agent, state, config)

    if not test_script:
        logger.warning("qa.test_ui.skip", reason="empty_test_script")
        return {
            "browser_test_results": {
                "mode": "scripted_e2e",
                "test_status": "skip",
                "screenshots": [],
                "console_logs": "",
                "network_errors": [],
                "defects_found": [],
                "duration_seconds": 0,
            },
            "issues_found": [],
        }

    # ── 2. Detect framework and build runner script ──
    sandbox_timeout = 240
    defaults = detect_framework_defaults(tech_stack, code_files=code_files)
    runner_script = build_runner_script(
        app_command=defaults["start"],
        app_port=defaults["port"],
        app_ready_timeout=30,
        install_command=defaults["install"],
        test_timeout=sandbox_timeout - 50,
    )

    # ── 3. Prepare files for sandbox ──
    sandbox_files = [
        {"path": f["path"], "content": f["content"]}
        for f in code_files
        if f.get("path") and f.get("content")
    ]
    sandbox_files.append({"path": "browser_runner.py", "content": runner_script})
    sandbox_files.append({"path": "playwright_test.py", "content": test_script})

    # ── 4. Execute in browser sandbox ──
    logger.info("qa.test_ui.execute", sandbox_files=len(sandbox_files))

    sandbox_result = agent.sandbox.execute(
        language="python",
        code_files=sandbox_files,
        commands=["python browser_runner.py"],
        timeout=sandbox_timeout,
        memory_limit="512m",
        network=False,
        browser=True,
        collect_screenshots=True,
        app_ready_timeout=30,
    )

    ui_exit_code = sandbox_result.get("exit_code")
    logger.info(
        "qa.test_ui.sandbox_done",
        exit_code=ui_exit_code,
        screenshots=len(sandbox_result.get("screenshots", [])),
        duration=sandbox_result.get("duration_seconds"),
    )

    if ui_exit_code != 0:
        stdout_preview = sandbox_result.get("stdout", "")[:2000]
        stderr_preview = sandbox_result.get("stderr", "")[:2000]
        if stdout_preview:
            logger.warning("qa.test_ui.stdout", output=stdout_preview)
        if stderr_preview:
            logger.warning("qa.test_ui.stderr", output=stderr_preview)

    # ── 5. LLM analyses browser results ──
    verdict = _analyse_browser_results(
        agent=agent,
        task=task,
        sandbox_result=sandbox_result,
        config=config,
    )

    browser_results = {
        "mode": "scripted_e2e",
        "screenshots": [
            {"name": s.get("name", ""), "step": ""}
            for s in sandbox_result.get("screenshots", [])
        ],
        "console_logs": sandbox_result.get("browser_console", ""),
        "network_errors": sandbox_result.get("network_errors", []),
        "test_status": "pass" if verdict["approved"] else "fail",
        "defects_found": verdict.get("defects", []),
        "duration_seconds": sandbox_result.get("duration_seconds", 0),
    }

    logger.info(
        "qa.test_ui.verdict",
        approved=verdict["approved"],
        defects=len(verdict.get("defects", [])),
        issues=len(verdict.get("issues", [])),
    )

    return {
        "browser_test_results": browser_results,
        "issues_found": verdict.get("issues", []),
    }
