"""
QA Agent (Orchestrator)
========================

Coordinates three testing phases:
  - Phase 0: Sandbox testing (unit / integration / syntax)
  - Phase 1: Browser E2E testing (Playwright scripted tests)
  - Phase 2: Guided Exploration (batch exploration plan)

The heavy lifting is delegated to submodules:
  - :mod:`qa_sandbox`     — code testing in isolated sandbox
  - :mod:`qa_browser`     — Playwright E2E testing
  - :mod:`qa_exploration`  — guided exploration testing
  - :mod:`qa_helpers`      — shared parsing utilities

LangGraph node function: ``qa_agent(state, config=None) -> dict``

Note:
  The *code review* role (checking correctness, style, etc.) is handled
  by the **Reviewer** agent.  The QA agent focuses on *runtime* testing.
"""

from __future__ import annotations

import os

import structlog

from .base import BaseAgent, get_llm_with_fallback, load_prompts
from ..state import DevTeamState
from ..tools.sandbox import SandboxClient, get_sandbox_client

# Submodule imports
from .qa_sandbox import run_sandbox_tests, detect_language, build_commands, make_skip_result
from .qa_browser import has_ui, run_browser_tests
from .qa_exploration import run_exploration_tests, make_explore_skip_result
from .qa_helpers import (
    parse_verdict,
    parse_issues,
    parse_defects,
    extract_code_block,
    extract_json,
    summarize_code_files,
)

logger = structlog.get_logger()

# Feature flags
USE_BROWSER_TESTING = os.getenv("USE_BROWSER_TESTING", "true").lower() in ("true", "1", "yes")
USE_BROWSER_EXPLORATION = os.getenv("USE_BROWSER_EXPLORATION", "false").lower() in ("true", "1", "yes")


class QAAgent(BaseAgent):
    """QA agent that tests code using the Sandbox service.

    Delegates actual testing to submodule functions:
      - :func:`qa_sandbox.run_sandbox_tests`
      - :func:`qa_browser.run_browser_tests`
      - :func:`qa_exploration.run_exploration_tests`
    """

    def __init__(self, sandbox_client: SandboxClient | None = None):
        prompts = load_prompts("qa")
        llm = get_llm_with_fallback(role="qa", temperature=0.2)
        super().__init__(name="qa", llm=llm, prompts=prompts)
        self._sandbox = sandbox_client

    @property
    def sandbox(self) -> SandboxClient:
        if self._sandbox is None:
            self._sandbox = get_sandbox_client()
        return self._sandbox

    # ------------------------------------------------------------------
    # Public methods (delegate to submodules)
    # ------------------------------------------------------------------

    def test_code(self, state: DevTeamState, config=None) -> dict:
        """Run code in sandbox and analyse the results."""
        return run_sandbox_tests(self, state, config)

    @staticmethod
    def has_ui(state: DevTeamState) -> bool:
        """Determine if the project has a UI component."""
        return has_ui(state)

    def test_ui(self, state: DevTeamState, config=None) -> dict:
        """Generate and run Playwright E2E tests for UI projects."""
        return run_browser_tests(self, state, config)

    def test_explore(self, state: DevTeamState, config=None) -> dict:
        """Generate and run a batch exploration plan for UI projects."""
        return run_exploration_tests(self, state, config)

    # ------------------------------------------------------------------
    # Backward-compatible static wrappers (used by tests)
    # Delegate to submodule functions.
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_language(code_files: list[dict]) -> str:
        return detect_language(code_files)

    @staticmethod
    def _build_commands(language: str, code_files: list[dict]) -> list[str]:
        return build_commands(language, code_files)

    @staticmethod
    def _make_skip_result(reason: str) -> dict:
        return make_skip_result(reason)

    @staticmethod
    def _make_explore_skip_result(reason: str) -> dict:
        return make_explore_skip_result(reason)

    @staticmethod
    def _parse_verdict(content: str, fallback_exit_code: int = -1) -> bool:
        return parse_verdict(content, fallback_exit_code)

    @staticmethod
    def _parse_issues(content: str) -> list[str]:
        return parse_issues(content)

    @staticmethod
    def _parse_defects(content: str) -> list[dict]:
        return parse_defects(content)

    @staticmethod
    def _extract_code_block(content: str) -> str:
        return extract_code_block(content)

    @staticmethod
    def _extract_json(content: str) -> dict | None:
        return extract_json(content)

    @staticmethod
    def _summarize_code_files(code_files: list[dict]) -> str:
        return summarize_code_files(code_files)

    def _generate_exploration_plan(self, state: DevTeamState, config=None) -> dict | None:
        from .qa_exploration import _generate_exploration_plan
        return _generate_exploration_plan(self, state, config)

    def _analyse_exploration(self, state_or_task: DevTeamState | str, report: dict, sandbox_result: dict, config=None) -> dict:
        from .qa_exploration import _analyse_exploration
        state: DevTeamState | dict
        if isinstance(state_or_task, str):
            state = {"task": state_or_task}
        else:
            state = state_or_task
        return _analyse_exploration(self, state, report, sandbox_result, config)

    def _generate_browser_test(self, state: DevTeamState, config=None) -> str:
        from .qa_browser import _generate_browser_test
        return _generate_browser_test(self, state, config)

    def _analyse_browser_results(self, state_or_task: DevTeamState | str, sandbox_result: dict, config=None) -> dict:
        from .qa_browser import _analyse_browser_results
        state: DevTeamState | dict
        if isinstance(state_or_task, str):
            state = {"task": state_or_task}
        else:
            state = state_or_task
        return _analyse_browser_results(self, state, sandbox_result, config)

    # ------------------------------------------------------------------
    # Merge results
    # ------------------------------------------------------------------

    def merge_results(self, code_result: dict, browser_result: dict) -> dict:
        """Merge code test results with browser test results.

        If browser tests fail, the overall verdict is FAIL and
        ``next_agent`` is set to ``"developer"`` for fixes.
        """
        merged = {**code_result}

        merged["browser_test_results"] = browser_result.get("browser_test_results")

        all_issues = (
            code_result.get("issues_found", [])
            + browser_result.get("issues_found", [])
        )
        merged["issues_found"] = all_issues

        code_approved = code_result.get("test_results", {}).get("approved", True)
        browser_status = (
            browser_result.get("browser_test_results", {}).get("test_status", "pass")
        )
        browser_approved = browser_status == "pass"

        if not browser_approved and code_approved:
            merged["test_results"] = {**code_result.get("test_results", {})}
            merged["test_results"]["approved"] = False
            merged["test_results"]["browser_failed"] = True
            merged["next_agent"] = "developer"

        return merged


# Singleton
_qa_agent: QAAgent | None = None


def get_qa_agent() -> QAAgent:
    """Get or create the QA agent instance."""
    global _qa_agent
    if _qa_agent is None:
        _qa_agent = QAAgent()
    return _qa_agent


def qa_agent(state: DevTeamState, config=None) -> dict:
    """QA agent node function for LangGraph.

    Runs code tests (always), then browser E2E tests (Phase 1), then
    guided exploration (Phase 2) — each when the project has a UI
    component and the corresponding feature flag is enabled.

    Testing pipeline::

        Phase 0: test_code()    — always (unit / integration / syntax)
        Phase 1: test_ui()      — if USE_BROWSER_TESTING and has_ui()
        Phase 2: test_explore() — if USE_BROWSER_EXPLORATION and has_ui()

    All phases feed into ``merge_results()`` for a combined verdict.
    """
    agent = get_qa_agent()

    # Phase 0: Unit / Integration / Syntax tests
    logger.debug("qa.route", action="test_code")
    code_result = agent.test_code(state, config=config)

    ui_detected = agent.has_ui(state)

    # Phase 1: Browser E2E tests (Visual QA — Scripted)
    # Skipped when Phase 2 is enabled — exploration supersedes scripted E2E
    if USE_BROWSER_TESTING and ui_detected and not USE_BROWSER_EXPLORATION:
        logger.info("qa.route", action="test_ui", reason="ui_detected")
        try:
            browser_result = agent.test_ui(state, config=config)
            code_result = agent.merge_results(code_result, browser_result)
        except Exception as exc:
            logger.error("qa.test_ui.error", error=str(exc)[:300])
    else:
        if USE_BROWSER_EXPLORATION and ui_detected:
            logger.debug("qa.route", action="skip_test_ui", reason="superseded_by_exploration")
        elif not USE_BROWSER_TESTING:
            logger.debug("qa.route", action="skip_test_ui", reason="disabled")
        elif not ui_detected:
            logger.debug("qa.route", action="skip_test_ui", reason="no_ui")

    # Phase 2: Guided Exploration (Batch) — supersedes Phase 1
    if USE_BROWSER_EXPLORATION and ui_detected:
        logger.info("qa.route", action="test_explore", reason="exploration_enabled")
        try:
            explore_result = agent.test_explore(state, config=config)
            code_result = agent.merge_results(code_result, explore_result)
        except Exception as exc:
            logger.error("qa.test_explore.error", error=str(exc)[:300])
    else:
        if not USE_BROWSER_EXPLORATION:
            logger.debug("qa.route", action="skip_test_explore", reason="disabled")
        elif not ui_detected:
            logger.debug("qa.route", action="skip_test_explore", reason="no_ui")

    return code_result
