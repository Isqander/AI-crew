"""
QA Agent (Sandbox Testing)
==========================

Responsible for:
  - Running generated code in an isolated sandbox
  - Executing tests (pytest, jest, etc.)
  - Verifying that code compiles / runs without errors
  - Analysing sandbox output with LLM and deciding pass/fail

The QA agent delegates execution to the :mod:`sandbox` service and
uses an LLM to interpret the results.

LangGraph node function: ``qa_agent(state, config=None) -> dict``

Note:
  The *code review* role (checking correctness, style, etc.) is handled
  by the **Reviewer** agent.  The QA agent focuses on *runtime* testing.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts, create_prompt_template
from ..state import DevTeamState
from ..tools.sandbox import SandboxClient, get_sandbox_client

logger = structlog.get_logger()


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
    """QA agent node function for LangGraph."""
    agent = get_qa_agent()
    logger.debug("qa.route", action="test_code")
    return agent.test_code(state, config=config)
