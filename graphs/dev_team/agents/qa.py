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

import os
import re

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts, create_prompt_template
from ..state import DevTeamState
from ..tools.sandbox import SandboxClient, get_sandbox_client
from ..tools.browser_runner import build_runner_script, detect_framework_defaults

logger = structlog.get_logger()

# Feature flags
USE_BROWSER_TESTING = os.getenv("USE_BROWSER_TESTING", "true").lower() in ("true", "1", "yes")

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
    # Visual QA: internal helpers
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
            approved = self._parse_browser_verdict(content, sandbox_result)
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
    def _parse_browser_verdict(content: str, sandbox_result: dict) -> bool:
        """Parse PASS/FAIL from browser analysis LLM response."""
        content_lower = content.lower()
        if "verdict: pass" in content_lower:
            return True
        if "verdict: fail" in content_lower:
            return False
        # Fallback
        return sandbox_result.get("exit_code", -1) == 0

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
        """Build a compact summary of code files for the LLM prompt."""
        if not code_files:
            return "(no code files)"

        parts: list[str] = []
        for f in code_files[:15]:
            path = f.get("path", "unknown")
            content = f.get("content", "")
            lines = len(content.split("\n"))
            # Include first few lines for context
            preview = "\n".join(content.split("\n")[:5])
            parts.append(f"  {path} ({lines} lines):\n    {preview[:200]}")

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
        approved = self._parse_approved(content, sandbox_results)
        issues = self._parse_issues(content)

        return {
            "approved": approved,
            "issues": issues,
            "explanation": content,
        }

    @staticmethod
    def _parse_approved(content: str, sandbox_results: dict) -> bool:
        """Determine approval from LLM response and sandbox exit code."""
        content_lower = content.lower()

        # Explicit verdicts from LLM
        if "verdict: pass" in content_lower or "verdict: approved" in content_lower:
            return True
        if "verdict: fail" in content_lower or "verdict: rejected" in content_lower:
            return False

        # Fallback: exit_code == 0 and no "fail" keywords
        exit_code = sandbox_results.get("exit_code", -1)
        if exit_code == 0 and "fail" not in content_lower:
            return True

        return False

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
        """Build sandbox commands based on language and file structure."""
        lang = language.lower()
        filenames = [f["path"] for f in code_files if f.get("path")]
        commands: list[str] = []

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
                commands.append("npx jest --no-cache 2>&1 || npx vitest run 2>&1 || true")
            elif lang in ("go", "golang"):
                commands.append("go test -v ./... 2>&1 || true")
            elif lang == "rust":
                commands.append("cargo test 2>&1 || true")
            else:
                # Fallback: detect runner from test file extensions
                js_tests = [f for f in test_files if f.endswith((".js", ".ts", ".mjs"))]
                py_tests = [f for f in test_files if f.endswith(".py")]
                if js_tests:
                    commands.append("npx jest --no-cache 2>&1 || npx vitest run 2>&1 || true")
                elif py_tests:
                    commands.append("python -m pytest -v --tb=short 2>&1 || true")
                else:
                    # HTML/CSS projects: validate files exist
                    html_files = [f for f in filenames if f.endswith(".html")]
                    if html_files:
                        commands.append(f"cat {html_files[0]} | head -5 && echo 'HTML files present'")
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
                commands.append(f"node --check {target} 2>&1")
            elif lang in ("typescript", "ts"):
                commands.append(f"npx tsc --noEmit {target} 2>&1 || true")
            elif lang in ("go", "golang"):
                commands.append("go build ./... 2>&1")
            elif lang == "rust":
                commands.append("rustc --edition 2021 -o /dev/null " + target + " 2>&1 || true")
            else:
                commands.append(f"cat {target}")

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

    Runs code tests (always), then browser E2E tests (if the project
    has a UI component and ``USE_BROWSER_TESTING`` is enabled).
    """
    agent = get_qa_agent()

    # Phase 0: Unit / Integration / Syntax tests
    logger.debug("qa.route", action="test_code")
    code_result = agent.test_code(state, config=config)

    # Phase 1: Browser E2E tests (Visual QA)
    if USE_BROWSER_TESTING and agent.has_ui(state):
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
        else:
            logger.debug("qa.route", action="skip_test_ui", reason="no_ui")

    return code_result
