"""
QA Agent (Sandbox Testing + Visual QA)
========================================

Responsible for:
  - Running generated code in an isolated sandbox
  - Executing tests (pytest, jest, etc.)
  - Verifying that code compiles / runs without errors
  - Analysing sandbox output with LLM and deciding pass/fail
  - **Visual QA (Phase 1):** Generating and running Playwright E2E tests
    for UI projects, collecting screenshots, analysing visual results

The QA agent delegates execution to the :mod:`sandbox` service and
uses an LLM to interpret the results.

LangGraph node function: ``qa_agent(state, config=None) -> dict``

Note:
  The *code review* role (checking correctness, style, etc.) is handled
  by the **Reviewer** agent.  The QA agent focuses on *runtime* testing.
"""

from __future__ import annotations

import json
import os
import re

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts, create_prompt_template
from ..state import DevTeamState
from ..tools.sandbox import SandboxClient, get_sandbox_client
from ..tools.browser_runner import build_runner_script, detect_framework_defaults
from ..tools.exploration_runner import (
    build_exploration_runner,
    validate_exploration_plan,
    extract_exploration_report,
)

logger = structlog.get_logger()

# Feature flags
USE_BROWSER_TESTING = os.getenv("USE_BROWSER_TESTING", "true").lower() in ("true", "1", "yes")
USE_BROWSER_EXPLORATION = os.getenv("USE_BROWSER_EXPLORATION", "false").lower() in ("true", "1", "yes")

# Limits for exploration
EXPLORATION_MAX_STEPS = int(os.getenv("BROWSER_EXPLORATION_MAX_STEPS", "30"))
EXPLORATION_MAX_SCREENSHOTS = int(os.getenv("BROWSER_MAX_SCREENSHOTS", "20"))

# UI framework indicators (lowercase)
UI_INDICATORS: set[str] = {
    "react", "vue", "angular", "svelte", "next.js", "nuxt",
    "nextjs", "gatsby", "vite", "html", "css", "tailwind",
    "bootstrap", "frontend", "web", "ui", "next", "remix",
    "solid", "solidjs", "astro", "qwik", "preact",
}


class QAAgent(BaseAgent):
    """QA agent that tests code using the Sandbox service."""

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
    # Public methods
    # ------------------------------------------------------------------

    def test_code(self, state: DevTeamState, config=None) -> dict:
        """Run code in sandbox and analyse the results.

        Steps:
          1. Detect language from ``code_files``
          2. Build appropriate run / test commands
          3. Execute in sandbox
          4. Feed output to LLM for verdict
          5. Return ``sandbox_results`` + pass/fail decision
        """
        code_files = state.get("code_files", [])
        task = state.get("task", "")

        if not code_files:
            logger.info("qa.test_code.skip", reason="no_code_files")
            return self._make_skip_result("No code files to test.")

        language = self._detect_language(code_files)
        commands = self._build_commands(language, code_files)

        logger.info(
            "qa.test_code.execute",
            language=language,
            files=len(code_files),
            commands=commands,
        )

        # ── Run in sandbox ──────────────────────────────────────────
        sandbox_files = [
            {"path": f["path"], "content": f["content"]}
            for f in code_files
            if f.get("path") and f.get("content")
        ]

        sandbox_result = self.sandbox.execute(
            language=language,
            code_files=sandbox_files,
            commands=commands,
            timeout=120,
            network=False,
        )

        sandbox_results = {
            "stdout": sandbox_result.get("stdout", ""),
            "stderr": sandbox_result.get("stderr", ""),
            "exit_code": sandbox_result.get("exit_code", -1),
            "tests_passed": sandbox_result.get("tests_passed"),
            "duration_seconds": sandbox_result.get("duration_seconds", 0.0),
        }

        logger.info(
            "qa.test_code.sandbox_done",
            exit_code=sandbox_results["exit_code"],
            tests_passed=sandbox_results["tests_passed"],
            duration=sandbox_results["duration_seconds"],
        )

        # Log stdout/stderr on failure for easier debugging
        if sandbox_results["exit_code"] != 0:
            stdout_preview = sandbox_results["stdout"][:2000]
            stderr_preview = sandbox_results["stderr"][:2000]
            if stdout_preview:
                logger.warning("qa.test_code.stdout", output=stdout_preview)
            if stderr_preview:
                logger.warning("qa.test_code.stderr", output=stderr_preview)

        # ── LLM analyses results ────────────────────────────────────
        verdict = self._analyse_results(
            task=task,
            code_files=code_files,
            sandbox_results=sandbox_results,
            config=config,
        )

        approved = verdict["approved"]
        issues = verdict["issues"]

        # Determine next step
        if approved:
            next_agent = "git_commit"
        else:
            next_agent = "developer"

        review_iter = state.get("review_iteration_count", 0)
        if issues:
            review_iter += 1

        logger.info(
            "qa.test_code.verdict",
            approved=approved,
            issues_count=len(issues),
            next_agent=next_agent,
            review_iter=review_iter,
        )

        return {
            "messages": [AIMessage(content=verdict["explanation"], name="qa")],
            "sandbox_results": sandbox_results,
            "issues_found": issues,
            "test_results": {
                "sandbox_exit_code": sandbox_results["exit_code"],
                "tests_passed": sandbox_results["tests_passed"],
                "approved": approved,
            },
            "current_agent": "qa",
            "next_agent": next_agent,
            "review_iteration_count": review_iter,
        }

    # ------------------------------------------------------------------
    # Visual QA: Browser E2E testing (Phase 1)
    # ------------------------------------------------------------------

    @staticmethod
    def has_ui(state: DevTeamState) -> bool:
        """Determine if the project has a UI component.

        Checks ``tech_stack`` and ``code_files`` for indicators of
        a frontend / web UI project.
        """
        # Check tech_stack
        tech_stack = state.get("tech_stack", [])
        for tech in tech_stack:
            if tech.lower().replace(".", "").replace("js", "").strip() in UI_INDICATORS:
                return True
            # Partial match
            for indicator in UI_INDICATORS:
                if indicator in tech.lower():
                    return True

        # Check code_files for UI file extensions
        ui_extensions = (".html", ".jsx", ".tsx", ".vue", ".svelte", ".astro")
        for f in state.get("code_files", []):
            path = f.get("path", "").lower()
            if any(path.endswith(ext) for ext in ui_extensions):
                return True

        return False

    def test_ui(self, state: DevTeamState, config=None) -> dict:
        """Generate and run Playwright E2E tests for UI projects.

        Steps:
          1. LLM generates a Playwright test script from user_stories + code
          2. Build the browser_runner.py with framework-specific defaults
          3. Execute in browser-sandbox (code_files + runner + test)
          4. LLM analyses screenshots + console + test results
          5. Return browser_test_results + verdict

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

        # ── 1. Generate Playwright test script ────────────────────
        test_script = self._generate_browser_test(state, config)

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

        # ── 2. Detect framework and build runner script ───────────
        sandbox_timeout = 240  # Browser tests need more time than unit tests
        defaults = detect_framework_defaults(tech_stack)
        runner_script = build_runner_script(
            app_command=defaults["start"],
            app_port=defaults["port"],
            app_ready_timeout=30,
            install_command=defaults["install"],
            test_timeout=sandbox_timeout - 50,  # Leave buffer for startup + cleanup
        )

        # ── 3. Prepare files for sandbox ──────────────────────────
        sandbox_files = [
            {"path": f["path"], "content": f["content"]}
            for f in code_files
            if f.get("path") and f.get("content")
        ]
        # Add runner and test
        sandbox_files.append({"path": "browser_runner.py", "content": runner_script})
        sandbox_files.append({"path": "playwright_test.py", "content": test_script})

        # ── 4. Execute in browser sandbox ─────────────────────────
        logger.info("qa.test_ui.execute", sandbox_files=len(sandbox_files))

        sandbox_result = self.sandbox.execute(
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

        # Log stdout/stderr on failure for easier debugging
        if ui_exit_code != 0:
            stdout_preview = sandbox_result.get("stdout", "")[:2000]
            stderr_preview = sandbox_result.get("stderr", "")[:2000]
            if stdout_preview:
                logger.warning("qa.test_ui.stdout", output=stdout_preview)
            if stderr_preview:
                logger.warning("qa.test_ui.stderr", output=stderr_preview)

        # ── 5. LLM analyses browser results ──────────────────────
        verdict = self._analyse_browser_results(
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

    def merge_results(self, code_result: dict, browser_result: dict) -> dict:
        """Merge code test results with browser test results.

        If browser tests fail, the overall verdict is FAIL and
        ``next_agent`` is set to ``"developer"`` for fixes.
        """
        merged = {**code_result}

        # Add browser results
        merged["browser_test_results"] = browser_result.get("browser_test_results")

        # Merge issues
        all_issues = (
            code_result.get("issues_found", [])
            + browser_result.get("issues_found", [])
        )
        merged["issues_found"] = all_issues

        # Overall verdict: both must pass
        code_approved = code_result.get("test_results", {}).get("approved", True)
        browser_status = (
            browser_result.get("browser_test_results", {}).get("test_status", "pass")
        )
        browser_approved = browser_status == "pass"

        if not browser_approved and code_approved:
            # Code passed but browser failed → mark as failed
            merged["test_results"] = {**code_result.get("test_results", {})}
            merged["test_results"]["approved"] = False
            merged["test_results"]["browser_failed"] = True
            merged["next_agent"] = "developer"

        return merged

    # ------------------------------------------------------------------
    # Visual QA Phase 2: Guided Exploration (Batch)
    # ------------------------------------------------------------------

    def test_explore(self, state: DevTeamState, config=None) -> dict:
        """Generate and run a batch exploration plan for UI projects.

        This is the Phase 2 mode of Visual QA.  The flow is:

          1. LLM generates a JSON exploration plan (list of steps)
          2. Validate the plan structure
          3. Build the exploration runner script
          4. Execute the full plan in browser-sandbox (one pass)
          5. Parse the structured report from stdout
          6. LLM analyses the report + screenshots in batch
          7. Return exploration results + verdict

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

        # ── 1. Generate exploration plan ───────────────────────────
        plan = self._generate_exploration_plan(state, config)

        if not plan:
            logger.warning("qa.test_explore.skip", reason="empty_plan")
            return self._make_explore_skip_result("LLM failed to generate exploration plan")

        # ── 2. Validate plan ───────────────────────────────────────
        validation_errors = validate_exploration_plan(plan)
        if validation_errors:
            logger.warning(
                "qa.test_explore.invalid_plan",
                errors=validation_errors[:5],
            )
            return self._make_explore_skip_result(
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

        # ── 3. Build runner + prepare sandbox files ────────────────
        sandbox_timeout = 300  # Exploration needs more time
        defaults = detect_framework_defaults(tech_stack)

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

        # ── 4. Execute in browser sandbox ──────────────────────────
        logger.info(
            "qa.test_explore.execute",
            sandbox_files=len(sandbox_files),
            plan_steps=len(plan.get("steps", [])),
        )

        sandbox_result = self.sandbox.execute(
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

        # Log on failure
        if explore_exit_code != 0:
            stdout_preview = sandbox_result.get("stdout", "")[:2000]
            stderr_preview = sandbox_result.get("stderr", "")[:2000]
            if stdout_preview:
                logger.warning("qa.test_explore.stdout", output=stdout_preview)
            if stderr_preview:
                logger.warning("qa.test_explore.stderr", output=stderr_preview)

        # ── 5. Parse exploration report from stdout ────────────────
        report = extract_exploration_report(sandbox_result.get("stdout", ""))

        if not report:
            logger.warning("qa.test_explore.no_report", reason="report_not_found_in_stdout")
            # Fallback: create minimal report from sandbox output
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

        # ── 6. LLM analyses exploration results ───────────────────
        verdict = self._analyse_exploration(
            task=task,
            report=report,
            sandbox_result=sandbox_result,
            config=config,
        )

        # ── 7. Build result ────────────────────────────────────────
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

    def _generate_exploration_plan(self, state: DevTeamState, config=None) -> dict | None:
        """Use LLM to generate an exploration plan as a JSON dict.

        Returns the parsed plan dict, or ``None`` on failure.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["generate_exploration_plan"],
        )
        chain = prompt | self.llm

        user_stories = state.get("user_stories", [])
        stories_text = "\n".join(
            f"- {s.get('title', '')}: {s.get('description', '')}"
            for s in user_stories[:5]
        ) if user_stories else "No user stories available"

        tech_stack = state.get("tech_stack", [])
        tech_stack_str = ", ".join(tech_stack) or "Unknown"
        code_structure = self._summarize_code_files(state.get("code_files", []))

        # Detect default port for the plan template
        defaults = detect_framework_defaults(tech_stack)
        app_port = defaults.get("port", 3000)

        try:
            response = self._invoke_chain(chain, {
                "task": state.get("task", ""),
                "user_stories": stories_text,
                "tech_stack": tech_stack_str,
                "code_structure": code_structure,
                "app_port": str(app_port),
            }, config=config)

            plan = self._extract_json(response.content)
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
        self,
        task: str,
        report: dict,
        sandbox_result: dict,
        config=None,
    ) -> dict:
        """Use LLM to analyse the exploration report in batch.

        Returns ``{"approved": bool, "issues": list[str], "defects": list[dict]}``.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["analyse_exploration"],
        )
        chain = prompt | self.llm

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
            response = self._invoke_chain(chain, {
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
            approved = self._parse_verdict(content, sandbox_result.get("exit_code", -1))
            issues = self._parse_issues(content)
            defects = self._parse_defects(content)

            return {
                "approved": approved,
                "issues": issues,
                "defects": defects,
                "explanation": content,
            }
        except Exception as exc:
            logger.error("qa.analyse_exploration.failed", error=str(exc)[:300])
            # Fallback: if most steps passed, consider it approved
            successful = report.get("successful_steps", 0)
            total = report.get("executed_steps", 1) or 1
            fallback_approved = (successful / total) >= 0.7
            return {
                "approved": fallback_approved,
                "issues": [f"Exploration analysis failed: {exc}"],
                "defects": [],
                "explanation": f"Analysis error: {exc}",
            }

    @staticmethod
    def _extract_json(content: str) -> dict | None:
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
            # Find the matching closing brace
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

    @staticmethod
    def _make_explore_skip_result(reason: str) -> dict:
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

    # ------------------------------------------------------------------
    # Visual QA: internal helpers (shared Phase 1 + Phase 2)
    # ------------------------------------------------------------------

    def _generate_browser_test(self, state: DevTeamState, config=None) -> str:
        """Use LLM to generate a Playwright test script.

        Returns a Python source string (pytest-playwright style), or
        empty string on failure.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["generate_browser_test"],
        )
        chain = prompt | self.llm

        user_stories = state.get("user_stories", [])
        stories_text = "\n".join(
            f"- {s.get('title', '')}: {s.get('description', '')}"
            for s in user_stories[:5]
        ) if user_stories else "No user stories available"

        tech_stack = ", ".join(state.get("tech_stack", [])) or "Unknown"
        code_structure = self._summarize_code_files(state.get("code_files", []))

        try:
            response = self._invoke_chain(chain, {
                "task": state.get("task", ""),
                "user_stories": stories_text,
                "tech_stack": tech_stack,
                "code_structure": code_structure,
            }, config=config)

            return self._extract_code_block(response.content)
        except Exception as exc:
            logger.error("qa.generate_browser_test.failed", error=str(exc)[:300])
            return ""

    def _analyse_browser_results(
        self,
        task: str,
        sandbox_result: dict,
        config=None,
    ) -> dict:
        """Use LLM to interpret browser test output and screenshots.

        Returns ``{"approved": bool, "issues": list[str], "defects": list[dict]}``.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["analyse_browser_results"],
        )
        chain = prompt | self.llm

        stdout = sandbox_result.get("stdout", "")[:4000]
        stderr = sandbox_result.get("stderr", "")[:4000]
        console_logs = sandbox_result.get("browser_console", "")[:2000]
        network_errors = sandbox_result.get("network_errors", [])

        try:
            response = self._invoke_chain(chain, {
                "task": task,
                "exit_code": str(sandbox_result.get("exit_code", -1)),
                "stdout": stdout or "(empty)",
                "stderr": stderr or "(empty)",
                "console_logs": console_logs or "(none)",
                "network_errors": ", ".join(network_errors[:10]) or "(none)",
            }, config=config)

            content = response.content
            approved = self._parse_verdict(content, sandbox_result.get("exit_code", -1))
            issues = self._parse_issues(content)
            defects = self._parse_defects(content)

            return {
                "approved": approved,
                "issues": issues,
                "defects": defects,
                "explanation": content,
            }
        except Exception as exc:
            logger.error("qa.analyse_browser_results.failed", error=str(exc)[:300])
            # Fallback: use exit code
            return {
                "approved": sandbox_result.get("exit_code", -1) == 0,
                "issues": [f"Browser analysis failed: {exc}"],
                "defects": [],
                "explanation": f"Analysis error: {exc}",
            }

    @staticmethod
    def _parse_verdict(content: str, fallback_exit_code: int = -1) -> bool:
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

    @staticmethod
    def _parse_defects(content: str) -> list[dict]:
        """Extract defect descriptions from the ``## Visual Issues``
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

    @staticmethod
    def _extract_code_block(content: str) -> str:
        """Extract the first fenced code block from LLM output.

        Supports ```python ... ``` and ``` ... ``` formats.
        Returns the code without the fences, or empty string if none found.
        """
        # Try to find ```python ... ``` or ``` ... ```
        pattern = r"```(?:python)?\s*\n(.*?)```"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: if the entire response looks like code, return it
        if "import " in content and "def " in content:
            return content.strip()

        return ""

    @staticmethod
    def _summarize_code_files(code_files: list[dict]) -> str:
        """Build a compact summary of code files for the LLM prompt.

        For UI files (HTML, CSS, JS) the full content is included so the
        LLM can see actual DOM selectors, class names, and element IDs
        when generating Playwright tests.
        """
        if not code_files:
            return "(no code files)"

        # File extensions that should be included in full for accurate test generation
        ui_extensions = (".html", ".css", ".js", ".jsx", ".tsx", ".vue", ".svelte")
        # Max chars per file to prevent prompt overflow
        max_full_content = 3000
        max_preview = 500

        parts: list[str] = []
        for f in code_files[:15]:
            path = f.get("path", "unknown")
            content = f.get("content", "")
            lines = len(content.split("\n"))

            is_ui_file = any(path.lower().endswith(ext) for ext in ui_extensions)

            if is_ui_file and len(content) <= max_full_content:
                # Full content for UI files — LLM needs real selectors
                parts.append(f"  {path} ({lines} lines):\n{content}")
            else:
                # Preview for large files or non-UI files
                preview = content[:max_preview]
                if len(content) > max_preview:
                    preview += f"\n    ... [{lines} lines total]"
                parts.append(f"  {path} ({lines} lines):\n    {preview}")

        if len(code_files) > 15:
            parts.append(f"  ... and {len(code_files) - 15} more files")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _analyse_results(
        self,
        task: str,
        code_files: list[dict],
        sandbox_results: dict,
        config=None,
    ) -> dict:
        """Use LLM to interpret sandbox output and decide pass/fail."""
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["analyse_sandbox"],
        )
        chain = prompt | self.llm

        files_summary = ", ".join(f["path"] for f in code_files[:20])
        stdout = sandbox_results.get("stdout", "")[:4000]
        stderr = sandbox_results.get("stderr", "")[:4000]

        response = self._invoke_chain(chain, {
            "task": task,
            "files": files_summary,
            "exit_code": str(sandbox_results.get("exit_code", -1)),
            "stdout": stdout or "(empty)",
            "stderr": stderr or "(empty)",
            "tests_passed": str(sandbox_results.get("tests_passed", "unknown")),
        }, config=config)

        content = response.content

        # Parse LLM verdict
        approved = self._parse_verdict(content, sandbox_results.get("exit_code", -1))
        issues = self._parse_issues(content)

        return {
            "approved": approved,
            "issues": issues,
            "explanation": content,
        }


    @staticmethod
    def _parse_issues(content: str) -> list[str]:
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

    @staticmethod
    def _detect_language(code_files: list[dict]) -> str:
        """Detect the primary language from code files."""
        lang_counts: dict[str, int] = {}
        for f in code_files:
            lang = f.get("language", "").lower()
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

        if not lang_counts:
            # Guess from extensions
            for f in code_files:
                path = f.get("path", "")
                if path.endswith(".py"):
                    return "python"
                if path.endswith((".js", ".ts", ".tsx")):
                    return "javascript"
                if path.endswith(".go"):
                    return "go"
                if path.endswith(".rs"):
                    return "rust"
            return "python"  # default

        return max(lang_counts, key=lang_counts.get)  # type: ignore[arg-type]

    @staticmethod
    def _build_commands(language: str, code_files: list[dict]) -> list[str]:
        """Build sandbox commands based on language and file structure.

        For JS/TS projects: npm-based test runners (jest, vitest) are only
        attempted when ``package.json`` is present, because the sandbox runs
        with ``network=False`` and cannot download packages on the fly.
        """
        lang = language.lower()
        filenames = [f["path"] for f in code_files if f.get("path")]
        commands: list[str] = []

        has_package_json = any(f.endswith("package.json") for f in filenames)

        # Reusable command fragments (avoid duplication)
        jest_or_vitest = "npm install --ignore-scripts 2>/dev/null; npx jest --no-cache 2>&1 || npx vitest run 2>&1 || true"
        def node_check(path: str) -> str:
            return f"node --check {path} 2>&1"

        # Install dependencies if present
        if lang in ("python", "python3"):
            if any(f.endswith("requirements.txt") for f in filenames):
                commands.append("pip install -r requirements.txt -q 2>/dev/null || true")

        # Detect test files
        test_files = [
            f for f in filenames
            if "test" in f.lower() or f.startswith("test_") or f.endswith("_test.py")
        ]

        if test_files:
            # Run tests
            if lang in ("python", "python3"):
                commands.append("python -m pytest -v --tb=short 2>&1 || true")
            elif lang in ("javascript", "js", "node", "typescript", "ts"):
                if has_package_json:
                    commands.append(jest_or_vitest)
                else:
                    # No package.json → no test runner available, do syntax check
                    js_files = [f for f in filenames if f.endswith((".js", ".mjs"))]
                    for jf in js_files[:3]:
                        commands.append(node_check(jf))
                    if not js_files:
                        commands.append("echo 'JS test files found but no package.json — skipping (browser tests will cover UI)'")
            elif lang in ("go", "golang"):
                commands.append("go test -v ./... 2>&1 || true")
            elif lang == "rust":
                commands.append("cargo test 2>&1 || true")
            else:
                # Fallback: detect runner from test file extensions
                js_tests = [f for f in test_files if f.endswith((".js", ".ts", ".mjs"))]
                py_tests = [f for f in test_files if f.endswith(".py")]
                if js_tests and has_package_json:
                    commands.append(jest_or_vitest)
                elif js_tests:
                    # Syntax check only — no runner without package.json
                    for jf in js_tests[:3]:
                        commands.append(node_check(jf))
                elif py_tests:
                    commands.append("python -m pytest -v --tb=short 2>&1 || true")
                else:
                    # HTML/CSS projects: validate main file
                    html_files = [f for f in filenames if f.endswith(".html")]
                    if html_files:
                        commands.append(f"echo 'Static HTML project — browser tests will validate UI' && ls -la *.html *.css *.js 2>/dev/null || true")
                    else:
                        commands.append("ls -la")
        else:
            # No tests — just try to run / compile
            main_files = [f for f in filenames if "main" in f.lower()]
            target = main_files[0] if main_files else filenames[0] if filenames else "main.py"

            if lang in ("python", "python3"):
                # Syntax check + try to run
                commands.append(f"python -c \"import py_compile; py_compile.compile('{target}', doraise=True)\" 2>&1")
            elif lang in ("javascript", "js", "node"):
                commands.append(node_check(target))
            elif lang in ("typescript", "ts"):
                commands.append(f"npx tsc --noEmit {target} 2>&1 || true")
            elif lang in ("go", "golang"):
                commands.append("go build ./... 2>&1")
            elif lang == "rust":
                commands.append("rustc --edition 2021 -o /dev/null " + target + " 2>&1 || true")
            elif lang in ("html", "css"):
                # Static web: syntax check JS files if present
                js_files = [f for f in filenames if f.endswith((".js", ".mjs"))]
                if js_files:
                    for jf in js_files[:3]:
                        commands.append(node_check(jf))
                else:
                    commands.append("echo 'Static HTML project — browser tests will validate UI' && ls -la")

        # Safety net: sandbox API requires at least one command
        if not commands:
            commands.append("echo 'No runnable commands detected' && ls -la")

        return commands

    @staticmethod
    def _make_skip_result(reason: str) -> dict:
        """Return a pass-through result when there is nothing to test."""
        return {
            "messages": [AIMessage(content=f"QA skipped: {reason}", name="qa")],
            "sandbox_results": None,
            "test_results": {"approved": True, "skipped": True},
            "issues_found": [],
            "current_agent": "qa",
            "next_agent": "git_commit",
        }


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

    has_ui = agent.has_ui(state)

    # Phase 1: Browser E2E tests (Visual QA — Scripted)
    if USE_BROWSER_TESTING and has_ui:
        logger.info("qa.route", action="test_ui", reason="ui_detected")
        try:
            browser_result = agent.test_ui(state, config=config)
            code_result = agent.merge_results(code_result, browser_result)
        except Exception as exc:
            logger.error("qa.test_ui.error", error=str(exc)[:300])
            # Don't fail the whole QA on browser test errors
            # — code test results still apply
    else:
        if not USE_BROWSER_TESTING:
            logger.debug("qa.route", action="skip_test_ui", reason="disabled")
        elif not has_ui:
            logger.debug("qa.route", action="skip_test_ui", reason="no_ui")

    # Phase 2: Guided Exploration (Batch)
    if USE_BROWSER_EXPLORATION and has_ui:
        logger.info("qa.route", action="test_explore", reason="exploration_enabled")
        try:
            explore_result = agent.test_explore(state, config=config)
            code_result = agent.merge_results(code_result, explore_result)
        except Exception as exc:
            logger.error("qa.test_explore.error", error=str(exc)[:300])
            # Don't fail the whole QA on exploration errors
    else:
        if not USE_BROWSER_EXPLORATION:
            logger.debug("qa.route", action="skip_test_explore", reason="disabled")
        elif not has_ui:
            logger.debug("qa.route", action="skip_test_explore", reason="no_ui")

    return code_result
