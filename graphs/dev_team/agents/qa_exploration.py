"""
QA Exploration — Guided Exploration testing (Visual QA Phase 2).

Generates an exploration plan, runs it in the browser sandbox,
and analyses the structured report.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import structlog

from .base import create_prompt_template
from .qa_helpers import (
    parse_verdict,
    parse_issues,
    parse_defects,
    extract_json,
    summarize_code_files,
)
from ..tools.browser_runner import detect_framework_defaults
from ..tools.exploration_runner import (
    build_exploration_runner,
    validate_exploration_plan,
    extract_exploration_report,
)

if TYPE_CHECKING:
    from .qa import QAAgent
    from ..state import DevTeamState

logger = structlog.get_logger()

# Limits for exploration
EXPLORATION_MAX_STEPS = int(os.getenv("BROWSER_EXPLORATION_MAX_STEPS", "30"))
EXPLORATION_MAX_SCREENSHOTS = int(os.getenv("BROWSER_MAX_SCREENSHOTS", "20"))


def _generate_exploration_plan(
    agent: QAAgent,
    state: DevTeamState,
    config=None,
) -> dict | None:
    """Use LLM to generate an exploration plan as a JSON dict.

    Returns the parsed plan dict, or ``None`` on failure.
    """
    prompt = create_prompt_template(
        agent.system_prompt,
        agent.prompts["generate_exploration_plan"],
    )
    chain = prompt | agent.llm

    user_stories = state.get("user_stories", [])
    stories_text = "\n".join(
        f"- {s.get('title', '')}: {s.get('description', '')}"
        for s in user_stories[:5]
    ) if user_stories else "No user stories available"

    tech_stack = state.get("tech_stack", [])
    tech_stack_str = ", ".join(tech_stack) or "Unknown"
    code_structure = summarize_code_files(state.get("code_files", []))

    # Detect default port for the plan template
    code_files = state.get("code_files", [])
    defaults = detect_framework_defaults(tech_stack, code_files=code_files)
    app_port = defaults.get("port", 3000)

    try:
        response = agent._invoke_chain(chain, {
            "task": state.get("task", ""),
            "user_stories": stories_text,
            "tech_stack": tech_stack_str,
            "code_structure": code_structure,
            "app_port": str(app_port),
        }, config=config)

        plan = extract_json(response.content)
        if plan is None:
            logger.warning(
                "qa.generate_exploration_plan.parse_failed",
                content_preview=response.content[:300],
            )
        return plan
    except Exception as exc:
        logger.error("qa.generate_exploration_plan.failed", error=str(exc)[:300])
        return None


def _analyse_exploration(
    agent: QAAgent,
    task: str,
    report: dict,
    sandbox_result: dict,
    config=None,
) -> dict:
    """Use LLM to analyse the exploration report in batch.

    Returns ``{"approved": bool, "issues": list[str], "defects": list[dict]}``.
    """
    prompt = create_prompt_template(
        agent.system_prompt,
        agent.prompts["analyse_exploration"],
    )
    chain = prompt | agent.llm

    # Format step results for the prompt
    step_lines = []
    for s in report.get("steps", [])[:EXPLORATION_MAX_STEPS]:
        status = s.get("status", "unknown")
        icon = "PASS" if status == "success" else "FAIL"
        desc = s.get("description", "")
        step_id = s.get("id", "?")
        error = s.get("error", "")
        url = s.get("current_url", "")
        assertions = ", ".join(s.get("assertions", []))

        line = f"  [{icon}] {step_id}: {desc}"
        if url:
            line += f" (url: {url})"
        if error:
            line += f"\n         Error: {error}"
        if assertions:
            line += f"\n         Planned assertions: {assertions}"
        step_lines.append(line)

    step_results_text = "\n".join(step_lines) or "(no steps executed)"

    console_logs = "\n".join(
        report.get("all_console_messages", [])[:50]
    ) or "(none)"

    network_errors = "\n".join(
        report.get("all_network_errors", [])[:20]
    ) or "(none)"

    try:
        response = agent._invoke_chain(chain, {
            "task": task,
            "plan_name": report.get("plan_name", "Unknown"),
            "total_steps": str(report.get("total_steps", 0)),
            "executed_steps": str(report.get("executed_steps", 0)),
            "successful_steps": str(report.get("successful_steps", 0)),
            "failed_steps": str(report.get("failed_steps", 0)),
            "step_results": step_results_text,
            "console_logs": console_logs,
            "network_errors": network_errors,
            "total_duration": str(report.get("total_duration_seconds", 0)),
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
        logger.error("qa.analyse_exploration.failed", error=str(exc)[:300])
        successful = report.get("successful_steps", 0)
        total = report.get("executed_steps", 1) or 1
        fallback_approved = (successful / total) >= 0.7
        return {
            "approved": fallback_approved,
            "issues": [f"Exploration analysis failed: {exc}"],
            "defects": [],
            "explanation": f"Analysis error: {exc}",
        }


def make_explore_skip_result(reason: str) -> dict:
    """Return a pass-through result when exploration is skipped."""
    return {
        "browser_test_results": {
            "mode": "guided_exploration",
            "test_status": "skip",
            "screenshots": [],
            "console_logs": "",
            "network_errors": [],
            "steps_executed": 0,
            "successful_steps": 0,
            "failed_steps": 0,
            "urls_visited": [],
            "defects_found": [],
            "duration_seconds": 0,
        },
        "issues_found": [reason] if reason else [],
    }


def run_exploration_tests(agent: QAAgent, state: DevTeamState, config=None) -> dict:
    """Generate and run a batch exploration plan for UI projects.

    Returns a dict with ``browser_test_results`` and ``issues_found``.
    """
    code_files = state.get("code_files", [])
    task = state.get("task", "")
    tech_stack = state.get("tech_stack", [])

    logger.info(
        "qa.test_explore.start",
        files=len(code_files),
        tech_stack=tech_stack[:5],
    )

    # ── 1. Generate exploration plan ──
    plan = _generate_exploration_plan(agent, state, config)

    if not plan:
        logger.warning("qa.test_explore.skip", reason="empty_plan")
        return make_explore_skip_result("LLM failed to generate exploration plan")

    # ── 2. Validate plan ──
    validation_errors = validate_exploration_plan(plan)
    if validation_errors:
        logger.warning(
            "qa.test_explore.invalid_plan",
            errors=validation_errors[:5],
        )
        return make_explore_skip_result(
            f"Invalid exploration plan: {'; '.join(validation_errors[:3])}"
        )

    # Enforce step limit
    steps = plan.get("steps", [])
    if len(steps) > EXPLORATION_MAX_STEPS:
        logger.info(
            "qa.test_explore.truncate_steps",
            original=len(steps),
            limit=EXPLORATION_MAX_STEPS,
        )
        plan["steps"] = steps[:EXPLORATION_MAX_STEPS]

    # ── 3. Build runner + prepare sandbox files ──
    sandbox_timeout = 300
    defaults = detect_framework_defaults(tech_stack, code_files=code_files)

    runner_script = build_exploration_runner(
        app_command=defaults["start"],
        app_port=defaults["port"],
        app_ready_timeout=30,
        install_command=defaults["install"],
        max_step_timeout=15,
        stop_on_error=False,
    )

    sandbox_files = [
        {"path": f["path"], "content": f["content"]}
        for f in code_files
        if f.get("path") and f.get("content")
    ]
    sandbox_files.append({
        "path": "exploration_runner.py",
        "content": runner_script,
    })
    sandbox_files.append({
        "path": "exploration_plan.json",
        "content": json.dumps(plan, indent=2, ensure_ascii=False),
    })

    # ── 4. Execute in browser sandbox ──
    logger.info(
        "qa.test_explore.execute",
        sandbox_files=len(sandbox_files),
        plan_steps=len(plan.get("steps", [])),
    )

    sandbox_result = agent.sandbox.execute(
        language="python",
        code_files=sandbox_files,
        commands=["python exploration_runner.py"],
        timeout=sandbox_timeout,
        memory_limit="512m",
        network=False,
        browser=True,
        collect_screenshots=True,
        app_ready_timeout=30,
    )

    explore_exit_code = sandbox_result.get("exit_code")
    logger.info(
        "qa.test_explore.sandbox_done",
        exit_code=explore_exit_code,
        screenshots=len(sandbox_result.get("screenshots", [])),
        duration=sandbox_result.get("duration_seconds"),
    )

    if explore_exit_code != 0:
        stdout_preview = sandbox_result.get("stdout", "")[:2000]
        stderr_preview = sandbox_result.get("stderr", "")[:2000]
        if stdout_preview:
            logger.warning("qa.test_explore.stdout", output=stdout_preview)
        if stderr_preview:
            logger.warning("qa.test_explore.stderr", output=stderr_preview)

    # ── 5. Parse exploration report from stdout ──
    report = extract_exploration_report(sandbox_result.get("stdout", ""))

    if not report:
        logger.warning("qa.test_explore.no_report", reason="report_not_found_in_stdout")
        report = {
            "plan_name": plan.get("name", "Unknown"),
            "total_steps": len(plan.get("steps", [])),
            "executed_steps": 0,
            "successful_steps": 0,
            "failed_steps": 0,
            "steps": [],
            "all_console_messages": [],
            "all_network_errors": [],
            "total_duration_seconds": sandbox_result.get("duration_seconds", 0),
        }

    # ── 6. LLM analyses exploration results ──
    verdict = _analyse_exploration(
        agent=agent,
        task=task,
        report=report,
        sandbox_result=sandbox_result,
        config=config,
    )

    # ── 7. Build result ──
    browser_results = {
        "mode": "guided_exploration",
        "screenshots": [
            {"name": s.get("name", ""), "step": ""}
            for s in sandbox_result.get("screenshots", [])
        ],
        "console_logs": "\n".join(report.get("all_console_messages", []))[:3000],
        "network_errors": report.get("all_network_errors", []),
        "test_status": "pass" if verdict["approved"] else "fail",
        "steps_executed": report.get("executed_steps", 0),
        "successful_steps": report.get("successful_steps", 0),
        "failed_steps": report.get("failed_steps", 0),
        "urls_visited": list({
            s.get("current_url", "")
            for s in report.get("steps", [])
            if s.get("current_url")
        }),
        "defects_found": verdict.get("defects", []),
        "duration_seconds": report.get("total_duration_seconds", 0),
    }

    logger.info(
        "qa.test_explore.verdict",
        approved=verdict["approved"],
        executed=report.get("executed_steps", 0),
        successful=report.get("successful_steps", 0),
        failed=report.get("failed_steps", 0),
        defects=len(verdict.get("defects", [])),
    )

    return {
        "browser_test_results": browser_results,
        "issues_found": verdict.get("issues", []),
    }
