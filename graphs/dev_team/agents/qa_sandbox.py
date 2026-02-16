"""
QA Sandbox — code testing in isolated sandbox.

Handles language detection, command building, sandbox execution,
and LLM-based analysis of results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from langchain_core.messages import AIMessage

from .base import create_prompt_template
from .qa_helpers import parse_verdict, parse_issues

if TYPE_CHECKING:
    from .qa import QAAgent
    from ..state import DevTeamState

logger = structlog.get_logger()


def detect_language(code_files: list[dict]) -> str:
    """Detect the primary language from code files."""
    lang_counts: dict[str, int] = {}
    for f in code_files:
        lang = f.get("language", "").lower()
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    if not lang_counts:
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


def build_commands(language: str, code_files: list[dict]) -> list[str]:
    """Build sandbox commands based on language and file structure.

    For JS/TS projects: npm-based test runners (jest, vitest) are only
    attempted when ``package.json`` is present, because the sandbox runs
    with ``network=False`` and cannot download packages on the fly.
    """
    lang = language.lower()
    filenames = [f["path"].lstrip("/") for f in code_files if f.get("path")]
    commands: list[str] = []

    has_package_json = any(f.endswith("package.json") for f in filenames)

    # Reusable command fragments
    jest_or_vitest = (
        "npm install --ignore-scripts 2>/dev/null; "
        "npx jest --no-cache 2>&1 || npx vitest run 2>&1 || true"
    )

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
        if lang in ("python", "python3"):
            commands.append("python -m pytest -v --tb=short 2>&1 || true")
        elif lang in ("javascript", "js", "node", "typescript", "ts"):
            if has_package_json:
                commands.append(jest_or_vitest)
            else:
                js_files = [f for f in filenames if f.endswith((".js", ".mjs"))]
                for jf in js_files[:3]:
                    commands.append(node_check(jf))
                if not js_files:
                    commands.append(
                        "echo 'JS test files found but no package.json — "
                        "skipping (browser tests will cover UI)'"
                    )
        elif lang in ("go", "golang"):
            commands.append("go test -v ./... 2>&1 || true")
        elif lang == "rust":
            commands.append("cargo test 2>&1 || true")
        else:
            js_tests = [f for f in test_files if f.endswith((".js", ".ts", ".mjs"))]
            py_tests = [f for f in test_files if f.endswith(".py")]
            if js_tests and has_package_json:
                commands.append(jest_or_vitest)
            elif js_tests:
                for jf in js_tests[:3]:
                    commands.append(node_check(jf))
            elif py_tests:
                commands.append("python -m pytest -v --tb=short 2>&1 || true")
            else:
                html_files = [f for f in filenames if f.endswith(".html")]
                if html_files:
                    commands.append(
                        "echo 'Static HTML project — browser tests will validate UI' "
                        "&& ls -la *.html *.css *.js 2>/dev/null || true"
                    )
                else:
                    commands.append("ls -la")
    else:
        main_files = [f for f in filenames if "main" in f.lower()]
        target = main_files[0] if main_files else filenames[0] if filenames else "main.py"

        if lang in ("python", "python3"):
            commands.append(
                f"python -c \"import py_compile; py_compile.compile('{target}', doraise=True)\" 2>&1"
            )
        elif lang in ("javascript", "js", "node"):
            commands.append(node_check(target))
        elif lang in ("typescript", "ts"):
            commands.append(f"npx tsc --noEmit {target} 2>&1 || true")
        elif lang in ("go", "golang"):
            commands.append("go build ./... 2>&1")
        elif lang == "rust":
            commands.append(f"rustc --edition 2021 -o /dev/null {target} 2>&1 || true")
        elif lang in ("html", "css"):
            js_files = [f for f in filenames if f.endswith((".js", ".mjs"))]
            if js_files:
                for jf in js_files[:3]:
                    commands.append(node_check(jf))
            else:
                commands.append(
                    "echo 'Static HTML project — browser tests will validate UI' && ls -la"
                )

    if not commands:
        commands.append("echo 'No runnable commands detected' && ls -la")

    return commands


def make_skip_result(reason: str) -> dict:
    """Return a pass-through result when there is nothing to test."""
    return {
        "messages": [AIMessage(content=f"QA skipped: {reason}", name="qa")],
        "sandbox_results": None,
        "test_results": {"approved": True, "skipped": True},
        "issues_found": [],
        "current_agent": "qa",
        "next_agent": "git_commit",
    }


def _analyse_results(
    agent: QAAgent,
    task: str,
    code_files: list[dict],
    sandbox_results: dict,
    config=None,
) -> dict:
    """Use LLM to interpret sandbox output and decide pass/fail."""
    prompt = create_prompt_template(
        agent.system_prompt,
        agent.prompts["analyse_sandbox"],
    )
    chain = prompt | agent.llm

    files_summary = ", ".join(f["path"] for f in code_files[:20])
    stdout = sandbox_results.get("stdout", "")[:4000]
    stderr = sandbox_results.get("stderr", "")[:4000]

    response = agent._invoke_chain(chain, {
        "task": task,
        "files": files_summary,
        "exit_code": str(sandbox_results.get("exit_code", -1)),
        "stdout": stdout or "(empty)",
        "stderr": stderr or "(empty)",
        "tests_passed": str(sandbox_results.get("tests_passed", "unknown")),
    }, config=config)

    content = response.content
    approved = parse_verdict(content, sandbox_results.get("exit_code", -1))
    issues = parse_issues(content)

    return {
        "approved": approved,
        "issues": issues,
        "explanation": content,
    }


def run_sandbox_tests(agent: QAAgent, state: DevTeamState, config=None) -> dict:
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
        return make_skip_result("No code files to test.")

    language = detect_language(code_files)
    commands = build_commands(language, code_files)

    logger.info(
        "qa.test_code.execute",
        language=language,
        files=len(code_files),
        commands=commands,
    )

    # ── Run in sandbox ──
    sandbox_files = [
        {"path": f["path"], "content": f["content"]}
        for f in code_files
        if f.get("path") and f.get("content")
    ]

    sandbox_result = agent.sandbox.execute(
        language=language,
        code_files=sandbox_files,
        commands=commands,
        timeout=120,
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

    if sandbox_results["exit_code"] != 0:
        stdout_preview = sandbox_results["stdout"][:2000]
        stderr_preview = sandbox_results["stderr"][:2000]
        if stdout_preview:
            logger.warning("qa.test_code.stdout", output=stdout_preview)
        if stderr_preview:
            logger.warning("qa.test_code.stderr", output=stderr_preview)

    # ── LLM analyses results ──
    verdict = _analyse_results(
        agent=agent,
        task=task,
        code_files=code_files,
        sandbox_results=sandbox_results,
        config=config,
    )

    approved = verdict["approved"]
    issues = verdict["issues"]
    next_agent = "git_commit" if approved else "developer"

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
