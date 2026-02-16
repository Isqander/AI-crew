"""
Tests for Visual QA Phase 1 — Scripted E2E
===========================================

Covers:
  - Sandbox models: browser fields in request/response, ScreenshotOutput
  - Sandbox executor: image selection, screenshot collection, browser log parsing
  - Browser runner: template generation, framework detection
  - QA Agent: has_ui(), test_ui(), _generate_browser_test(), _analyse_browser_results(),
              _extract_code_block(), _parse_browser_verdict(), _parse_defects(), merge_results()
  - QA node function: qa_agent() with browser testing integration
  - State: browser_test_results field
"""

from __future__ import annotations

from unittest.mock import Mock, MagicMock, patch

import pytest


# ==================================================================
# 1. Sandbox Models — Browser Fields
# ==================================================================


class TestSandboxBrowserModels:
    """Test that browser fields are correctly defined in sandbox models."""

    def test_request_browser_fields_defaults(self):
        """Browser fields should have sensible defaults."""
        from sandbox.models import SandboxExecuteRequest

        req = SandboxExecuteRequest(
            language="python",
            code_files=[{"path": "main.py", "content": "print('hi')"}],
            commands=["python main.py"],
        )
        assert req.browser is False
        assert req.collect_screenshots is False
        assert req.app_start_command is None
        assert req.app_ready_timeout == 30

    def test_request_browser_mode_enabled(self):
        """Browser fields can be set explicitly."""
        from sandbox.models import SandboxExecuteRequest

        req = SandboxExecuteRequest(
            language="python",
            code_files=[{"path": "test.py", "content": "pass"}],
            commands=["pytest test.py"],
            browser=True,
            collect_screenshots=True,
            app_start_command="npm run dev",
            app_ready_timeout=60,
        )
        assert req.browser is True
        assert req.collect_screenshots is True
        assert req.app_start_command == "npm run dev"
        assert req.app_ready_timeout == 60

    def test_response_browser_fields_defaults(self):
        """Response should have empty browser fields by default."""
        from sandbox.models import SandboxExecuteResponse

        resp = SandboxExecuteResponse()
        assert resp.screenshots == []
        assert resp.browser_console == ""
        assert resp.network_errors == []

    def test_response_with_screenshots(self):
        """Response can contain screenshot data."""
        from sandbox.models import SandboxExecuteResponse, ScreenshotOutput

        resp = SandboxExecuteResponse(
            stdout="ok",
            exit_code=0,
            screenshots=[
                ScreenshotOutput(name="homepage.png", base64="aGVsbG8="),
                ScreenshotOutput(name="login.png", base64="d29ybGQ="),
            ],
            browser_console="warning: deprecated API",
            network_errors=["GET http://localhost:3000/api/missing 404"],
        )
        assert len(resp.screenshots) == 2
        assert resp.screenshots[0].name == "homepage.png"
        assert resp.browser_console == "warning: deprecated API"
        assert len(resp.network_errors) == 1

    def test_screenshot_output_model(self):
        """ScreenshotOutput should have name and base64 fields."""
        from sandbox.models import ScreenshotOutput

        s = ScreenshotOutput(name="test.png", base64="abc123")
        assert s.name == "test.png"
        assert s.base64 == "abc123"


# ==================================================================
# 2. Sandbox Executor — Browser Mode
# ==================================================================


class TestExecutorBrowserMode:
    """Test executor's browser-specific logic."""

    def test_browser_image_selection(self):
        """When browser=True, executor should use BROWSER_IMAGE."""
        from sandbox.executor import get_image_for_language, BROWSER_IMAGE

        # Standard image for python
        assert get_image_for_language("python") == "python:3.11-slim"
        # BROWSER_IMAGE is a module-level constant
        assert BROWSER_IMAGE == "aicrew-sandbox-browser:latest"

    def test_collect_browser_logs_console(self):
        """_collect_browser_logs extracts [console] lines."""
        from sandbox.executor import SandboxExecutor

        stdout = (
            "[runner] App started\n"
            "[console] info: App loaded\n"
            "[console] warning: deprecated function\n"
            "[runner] Tests finished\n"
        )
        console, errors = SandboxExecutor._collect_browser_logs(stdout, "")
        assert "info: App loaded" in console
        assert "warning: deprecated function" in console
        assert len(errors) == 0

    def test_collect_browser_logs_network_errors(self):
        """_collect_browser_logs extracts [network-error] lines."""
        from sandbox.executor import SandboxExecutor

        stdout = "[network-error] GET http://localhost:3000/api 500\n"
        stderr = "[network-error] POST http://localhost:3000/submit 404\n"
        console, errors = SandboxExecutor._collect_browser_logs(stdout, stderr)
        assert len(errors) == 2
        assert "500" in errors[0]
        assert "404" in errors[1]

    def test_collect_browser_logs_empty(self):
        """No tagged lines → empty results."""
        from sandbox.executor import SandboxExecutor

        console, errors = SandboxExecutor._collect_browser_logs("plain output", "")
        assert console == ""
        assert errors == []

    def test_execute_passes_browser_params(self):
        """execute() should pass browser params to container creation."""
        from sandbox.executor import SandboxExecutor, BROWSER_IMAGE

        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_client.containers.create.return_value = mock_container
        mock_container.exec_run.return_value = MagicMock(
            exit_code=0, output=(b"ok", b"")
        )

        executor = SandboxExecutor(docker_client=mock_client)

        result = executor.execute(
            language="python",
            code_files=[{"path": "test.py", "content": "pass"}],
            commands=["python test.py"],
            browser=True,
            collect_screenshots=True,
            memory_limit="256m",  # should be auto-upgraded to 512m
        )

        # Should use BROWSER_IMAGE
        create_call = mock_client.containers.create.call_args
        assert create_call.kwargs["image"] == BROWSER_IMAGE
        # Should auto-upgrade memory for browser
        assert create_call.kwargs["mem_limit"] == "512m"
        # Should use named network (not none) for browser
        assert create_call.kwargs["network_mode"] != "none"
        # Result should have browser fields
        assert "screenshots" in result
        assert "browser_console" in result
        assert "network_errors" in result


# ==================================================================
# 3. Browser Runner — Template Generation
# ==================================================================


class TestBrowserRunner:
    """Test browser_runner.py template generation."""

    def test_build_runner_script_default(self):
        """build_runner_script produces a valid Python script."""
        from dev_team.tools.browser_runner import build_runner_script

        script = build_runner_script(
            app_command="npm run dev",
            app_port=3000,
            app_ready_timeout=30,
            install_command="npm install",
        )
        assert "npm run dev" in script
        assert "APP_PORT = 3000" in script
        assert "npm install" in script
        assert "def main()" in script
        assert "wait_for_port" in script

    def test_build_runner_script_empty_command(self):
        """Empty app_command produces script with empty string."""
        from dev_team.tools.browser_runner import build_runner_script

        script = build_runner_script()
        assert "APP_COMMAND = ''" in script
        assert "APP_PORT = 3000" in script

    def test_detect_framework_defaults_react(self):
        """React projects should use vite defaults."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        defaults = detect_framework_defaults(["React", "TypeScript"])
        assert "npm install" in defaults["install"]
        assert defaults["port"] == 5173

    def test_detect_framework_defaults_nextjs(self):
        """Next.js projects should use next dev."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        defaults = detect_framework_defaults(["Next.js", "React"])
        assert defaults["port"] == 3000
        assert "next" in defaults["start"].lower()

    def test_detect_framework_defaults_flask(self):
        """Flask projects should use Python."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        defaults = detect_framework_defaults(["Flask", "Python"])
        assert "pip install" in defaults["install"]
        assert defaults["port"] == 5000

    def test_detect_framework_defaults_unknown(self):
        """Unknown stack falls back to npm."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        defaults = detect_framework_defaults(["UnknownFramework"])
        assert defaults["port"] == 3000

    def test_detect_framework_defaults_html(self):
        """Plain HTML uses Python http.server."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        defaults = detect_framework_defaults(["HTML", "CSS"])
        assert "http.server" in defaults["start"]
        assert defaults["port"] == 8080

    # --- Code-content detection (Pass 2) ---

    def test_detect_fastapi_from_code_content(self):
        """FastAPI detected from Python file imports, even with generic tech_stack."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "main.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n"},
        ]
        defaults = detect_framework_defaults(["HTML", "CSS", "JavaScript"], code_files=code_files)
        assert defaults["port"] == 8000
        assert "uvicorn" in defaults["start"]
        assert "main:app" in defaults["start"]
        assert "pip install fastapi" in defaults["install"]

    def test_detect_fastapi_with_requirements(self):
        """FastAPI with requirements.txt uses pip install -r."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "app.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n"},
            {"path": "requirements.txt", "content": "fastapi\nuvicorn\n"},
        ]
        defaults = detect_framework_defaults(["Python"], code_files=code_files)
        assert "pip install -r requirements.txt" in defaults["install"]
        # app.py → default uvicorn app:app
        assert "app:app" in defaults["start"]

    def test_detect_flask_from_code_content(self):
        """Flask detected from Python file imports."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "server.py", "content": "from flask import Flask\napp = Flask(__name__)\n"},
        ]
        defaults = detect_framework_defaults(["HTML", "JavaScript"], code_files=code_files)
        assert defaults["port"] == 5000
        assert "server.py" in defaults["start"]
        assert "pip install flask" in defaults["install"]

    def test_detect_express_from_code_content(self):
        """Express.js detected from JS file requires."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "server.js", "content": 'const express = require("express");\nconst app = express();\n'},
        ]
        defaults = detect_framework_defaults(["JavaScript"], code_files=code_files)
        assert defaults["port"] == 3000
        assert "npm" in defaults["start"]

    def test_detect_react_from_package_json(self):
        """React detected from package.json dependencies."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "package.json", "content": '{"dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"}}'},
        ]
        defaults = detect_framework_defaults(["HTML", "CSS", "JavaScript"], code_files=code_files)
        assert defaults["port"] == 5173  # vite/react default

    def test_code_content_overrides_generic_html(self):
        """Code content detection takes priority over generic html tech_stack match."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "main.py", "content": "import fastapi\napp = fastapi.FastAPI()\n"},
            {"path": "index.html", "content": "<html><body>Hello</body></html>"},
        ]
        # tech_stack says html/css, but code has FastAPI → must detect FastAPI
        defaults = detect_framework_defaults(["html", "css", "javascript"], code_files=code_files)
        assert defaults["port"] == 8000
        assert "uvicorn" in defaults["start"]

    def test_detect_fastapi_in_subdirectory(self):
        """FastAPI file in subdirectory generates correct uvicorn module path."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "backend/main.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n"},
            {"path": "requirements.txt", "content": "fastapi\nuvicorn\n"},
        ]
        defaults = detect_framework_defaults(["html", "css"], code_files=code_files)
        assert defaults["port"] == 8000
        # Must use dotted module path: backend.main:app
        assert "backend.main:app" in defaults["start"]
        assert "uvicorn" in defaults["start"]

    def test_detect_flask_in_subdirectory(self):
        """Flask file in subdirectory uses full path for python command."""
        from dev_team.tools.browser_runner import detect_framework_defaults

        code_files = [
            {"path": "src/server.py", "content": "from flask import Flask\napp = Flask(__name__)\n"},
        ]
        defaults = detect_framework_defaults(["Python"], code_files=code_files)
        assert defaults["port"] == 5000
        assert "python src/server.py" in defaults["start"]


# ==================================================================
# 4. QA Agent — has_ui()
# ==================================================================


class TestQAAgentHasUI:
    """Test QAAgent.has_ui() UI detection."""

    def test_has_ui_react_in_tech_stack(self):
        """Detect UI from tech_stack containing 'React'."""
        from dev_team.agents.qa import QAAgent

        state = {"tech_stack": ["React", "Node.js", "PostgreSQL"]}
        assert QAAgent.has_ui(state) is True

    def test_has_ui_vue_in_tech_stack(self):
        from dev_team.agents.qa import QAAgent

        state = {"tech_stack": ["Vue", "Express"]}
        assert QAAgent.has_ui(state) is True

    def test_has_ui_html_in_tech_stack(self):
        from dev_team.agents.qa import QAAgent

        state = {"tech_stack": ["HTML", "CSS", "JavaScript"]}
        assert QAAgent.has_ui(state) is True

    def test_has_ui_no_ui_backend_only(self):
        """Backend-only projects should return False."""
        from dev_team.agents.qa import QAAgent

        state = {"tech_stack": ["Python", "FastAPI", "PostgreSQL"]}
        assert QAAgent.has_ui(state) is False

    def test_has_ui_empty_tech_stack_with_tsx_files(self):
        """Detect UI from .tsx file extensions."""
        from dev_team.agents.qa import QAAgent

        state = {
            "tech_stack": [],
            "code_files": [
                {"path": "src/App.tsx", "content": "export default function App() {}"},
            ],
        }
        assert QAAgent.has_ui(state) is True

    def test_has_ui_html_file(self):
        """Detect UI from .html file."""
        from dev_team.agents.qa import QAAgent

        state = {
            "tech_stack": [],
            "code_files": [{"path": "index.html", "content": "<html></html>"}],
        }
        assert QAAgent.has_ui(state) is True

    def test_has_ui_no_code_files(self):
        """No tech stack and no code files → False."""
        from dev_team.agents.qa import QAAgent

        state = {"tech_stack": [], "code_files": []}
        assert QAAgent.has_ui(state) is False

    def test_has_ui_python_only_files(self):
        """Only .py files → no UI."""
        from dev_team.agents.qa import QAAgent

        state = {
            "tech_stack": [],
            "code_files": [{"path": "main.py", "content": "print('hi')"}],
        }
        assert QAAgent.has_ui(state) is False

    def test_has_ui_tailwind_keyword(self):
        """Tailwind in tech_stack → UI."""
        from dev_team.agents.qa import QAAgent

        state = {"tech_stack": ["Tailwind", "TypeScript"]}
        assert QAAgent.has_ui(state) is True

    def test_has_ui_nextjs_variant(self):
        """'Next.js' should be detected."""
        from dev_team.agents.qa import QAAgent

        state = {"tech_stack": ["Next.js"]}
        assert QAAgent.has_ui(state) is True


# ==================================================================
# 5. QA Agent — _extract_code_block()
# ==================================================================


class TestExtractCodeBlock:
    """Test QAAgent._extract_code_block."""

    def test_extract_python_block(self):
        from dev_team.agents.qa import QAAgent

        content = '''Here is the test:

```python
import pytest

def test_home(page):
    page.goto("/")
    assert page.title()
```

That's the test.'''

        result = QAAgent._extract_code_block(content)
        assert "import pytest" in result
        assert "def test_home" in result

    def test_extract_plain_block(self):
        from dev_team.agents.qa import QAAgent

        content = '''```
def test_something():
    pass
```'''
        result = QAAgent._extract_code_block(content)
        assert "def test_something" in result

    def test_extract_no_block_but_code(self):
        """If no fences but looks like code, return it."""
        from dev_team.agents.qa import QAAgent

        content = "import pytest\n\ndef test_page(page):\n    page.goto('/')"
        result = QAAgent._extract_code_block(content)
        assert "import pytest" in result

    def test_extract_no_code(self):
        """Plain text without code → empty string."""
        from dev_team.agents.qa import QAAgent

        content = "Sorry, I can't generate a test for this project."
        result = QAAgent._extract_code_block(content)
        assert result == ""


# ==================================================================
# 6. QA Agent — _parse_browser_verdict() and _parse_defects()
# ==================================================================


class TestParseBrowserResults:
    """Test browser-specific parsing methods."""

    def test_parse_browser_verdict_pass(self):
        from dev_team.agents.qa import QAAgent

        content = "## Verdict: PASS\nAll tests passed."
        assert QAAgent._parse_verdict(content, 0) is True

    def test_parse_browser_verdict_fail(self):
        from dev_team.agents.qa import QAAgent

        content = "## Verdict: FAIL\nHomepage does not render."
        assert QAAgent._parse_verdict(content, 1) is False

    def test_parse_browser_verdict_fallback_exit_code(self):
        from dev_team.agents.qa import QAAgent

        content = "Analysis complete."  # no explicit verdict
        assert QAAgent._parse_verdict(content, 0) is True
        assert QAAgent._parse_verdict(content, 1) is False

    def test_parse_defects_visual(self):
        from dev_team.agents.qa import QAAgent

        content = """## Verdict: FAIL

## Visual Issues
- Button is partially hidden on mobile viewport
- Color contrast too low on header

## Functional Issues
- Form submit does not redirect to success page

## Console/Network Issues
- None
"""
        defects = QAAgent._parse_defects(content)
        assert len(defects) == 3
        assert defects[0]["severity"] == "medium"  # visual
        assert defects[2]["severity"] == "high"  # functional

    def test_parse_defects_none(self):
        from dev_team.agents.qa import QAAgent

        content = """## Verdict: PASS
## Visual Issues
- None
## Functional Issues
- None
"""
        defects = QAAgent._parse_defects(content)
        assert defects == []


# ==================================================================
# 7. QA Agent — merge_results()
# ==================================================================


class TestMergeResults:
    """Test QAAgent.merge_results()."""

    @pytest.fixture
    def agent(self):
        """Create a QAAgent with mocked dependencies."""
        with patch("dev_team.agents.qa.get_llm_with_fallback") as mock_llm, \
             patch("dev_team.agents.qa.load_prompts") as mock_prompts:
            mock_prompts.return_value = {
                "system": "QA agent",
                "analyse_sandbox": "...",
                "generate_browser_test": "...",
                "analyse_browser_results": "...",
            }
            mock_llm.return_value = Mock()
            from dev_team.agents.qa import QAAgent
            return QAAgent(sandbox_client=Mock())

    def test_merge_both_pass(self, agent):
        """Both code and browser pass → overall pass."""
        code_result = {
            "test_results": {"approved": True},
            "issues_found": [],
            "next_agent": "git_commit",
        }
        browser_result = {
            "browser_test_results": {"test_status": "pass", "screenshots": []},
            "issues_found": [],
        }
        merged = agent.merge_results(code_result, browser_result)
        assert merged["test_results"]["approved"] is True
        assert merged["next_agent"] == "git_commit"
        assert merged["browser_test_results"]["test_status"] == "pass"

    def test_merge_code_pass_browser_fail(self, agent):
        """Code passes but browser fails → overall fail."""
        code_result = {
            "test_results": {"approved": True},
            "issues_found": [],
            "next_agent": "git_commit",
        }
        browser_result = {
            "browser_test_results": {"test_status": "fail", "screenshots": []},
            "issues_found": ["Homepage not rendering"],
        }
        merged = agent.merge_results(code_result, browser_result)
        assert merged["test_results"]["approved"] is False
        assert merged["test_results"]["browser_failed"] is True
        assert merged["next_agent"] == "developer"
        assert "Homepage not rendering" in merged["issues_found"]

    def test_merge_both_fail(self, agent):
        """Both fail → already failed from code."""
        code_result = {
            "test_results": {"approved": False},
            "issues_found": ["Syntax error"],
            "next_agent": "developer",
        }
        browser_result = {
            "browser_test_results": {"test_status": "fail", "screenshots": []},
            "issues_found": ["UI broken"],
        }
        merged = agent.merge_results(code_result, browser_result)
        assert merged["test_results"]["approved"] is False
        assert "Syntax error" in merged["issues_found"]
        assert "UI broken" in merged["issues_found"]

    def test_merge_issues_combined(self, agent):
        """Issues from both sources are merged."""
        code_result = {
            "test_results": {"approved": True},
            "issues_found": ["Warning: unused import"],
            "next_agent": "git_commit",
        }
        browser_result = {
            "browser_test_results": {"test_status": "pass"},
            "issues_found": ["Console warning: deprecated API"],
        }
        merged = agent.merge_results(code_result, browser_result)
        assert len(merged["issues_found"]) == 2


# ==================================================================
# 8. QA Agent — test_ui() with mocked sandbox
# ==================================================================


class TestQAAgentTestUI:
    """Test QAAgent.test_ui() end-to-end with mocks."""

    @pytest.fixture
    def agent(self):
        """Create a QAAgent with mocked LLM and sandbox."""
        with patch("dev_team.agents.qa.get_llm_with_fallback") as mock_get_llm, \
             patch("dev_team.agents.qa.load_prompts") as mock_load_prompts:
            mock_load_prompts.return_value = {
                "system": "You are a QA agent.",
                "analyse_sandbox": "Analyse: {task} {files} {exit_code} {tests_passed} {stdout} {stderr}",
                "generate_browser_test": "Generate: {task} {user_stories} {tech_stack} {code_structure}",
                "analyse_browser_results": "Analyse browser: {task} {exit_code} {stdout} {stderr} {console_logs} {network_errors}",
            }
            mock_llm = Mock()
            mock_get_llm.return_value = mock_llm
            from dev_team.agents.qa import QAAgent
            mock_sandbox = Mock()
            agent = QAAgent(sandbox_client=mock_sandbox)
            agent._llm = mock_llm
            return agent

    def test_test_ui_happy_path(self, agent):
        """test_ui generates test, executes, analyses, returns results."""
        state = {
            "task": "Create a React dashboard",
            "tech_stack": ["React", "TypeScript"],
            "code_files": [{"path": "src/App.tsx", "content": "export default () => <div>App</div>"}],
            "user_stories": [{"title": "Dashboard", "description": "User sees dashboard"}],
        }

        # Mock LLM: generate test script
        mock_generate_response = Mock()
        mock_generate_response.content = '''```python
import pytest
def test_homepage(page):
    page.goto("/")
    assert page.title()
```'''

        # Mock LLM: analyse results
        mock_analyse_response = Mock()
        mock_analyse_response.content = """## Verdict: PASS
## UI Summary
Dashboard renders correctly.
## Visual Issues
- None
## Functional Issues
- None
## Console/Network Issues
- None
## Recommendations
- None
"""

        agent.llm.invoke = Mock(side_effect=[mock_generate_response, mock_analyse_response])
        # Make _invoke_chain use the side_effect
        call_count = [0]
        def fake_invoke_chain(chain, inputs, config=None):
            result = [mock_generate_response, mock_analyse_response][call_count[0]]
            call_count[0] += 1
            return result
        agent._invoke_chain = fake_invoke_chain

        # Mock sandbox execution
        agent.sandbox.execute.return_value = {
            "stdout": "PASSED test_homepage",
            "stderr": "",
            "exit_code": 0,
            "duration_seconds": 15.0,
            "screenshots": [{"name": "homepage.png", "base64": "abc"}],
            "browser_console": "",
            "network_errors": [],
        }

        result = agent.test_ui(state)

        assert "browser_test_results" in result
        assert result["browser_test_results"]["test_status"] == "pass"
        assert result["browser_test_results"]["mode"] == "scripted_e2e"
        assert len(result["issues_found"]) == 0

        # Verify sandbox was called with browser=True
        agent.sandbox.execute.assert_called_once()
        call_kwargs = agent.sandbox.execute.call_args
        assert call_kwargs.kwargs.get("browser") is True or call_kwargs[1].get("browser") is True

    def test_test_ui_empty_test_script(self, agent):
        """If LLM fails to generate a test, test_ui returns skip."""
        state = {
            "task": "Build a widget",
            "tech_stack": ["React"],
            "code_files": [],
            "user_stories": [],
        }

        # Mock LLM: empty response
        mock_response = Mock()
        mock_response.content = "I cannot generate a test."
        agent._invoke_chain = Mock(return_value=mock_response)

        result = agent.test_ui(state)
        assert result["browser_test_results"]["test_status"] == "skip"

    def test_test_ui_sandbox_failure(self, agent):
        """If sandbox fails, analysis should reflect the failure."""
        state = {
            "task": "Create a Vue app",
            "tech_stack": ["Vue"],
            "code_files": [{"path": "src/App.vue", "content": "<template></template>"}],
            "user_stories": [],
        }

        # Mock: generate test
        mock_gen = Mock()
        mock_gen.content = '```python\ndef test_app(page):\n    page.goto("/")\n```'

        # Mock: analyse (fail verdict)
        mock_analyse = Mock()
        mock_analyse.content = "## Verdict: FAIL\n## UI Summary\nApp crashed.\n## Visual Issues\n- None\n## Functional Issues\n- App did not start"

        call_count = [0]
        def fake_invoke(chain, inputs, config=None):
            result = [mock_gen, mock_analyse][call_count[0]]
            call_count[0] += 1
            return result
        agent._invoke_chain = fake_invoke

        agent.sandbox.execute.return_value = {
            "stdout": "ERROR: app failed to start",
            "stderr": "Error: EADDRINUSE",
            "exit_code": 1,
            "duration_seconds": 5.0,
            "screenshots": [],
            "browser_console": "",
            "network_errors": [],
        }

        result = agent.test_ui(state)
        assert result["browser_test_results"]["test_status"] == "fail"


# ==================================================================
# 9. QA Node Function — Integration with Browser Testing
# ==================================================================


class TestQANodeWithBrowser:
    """Test the qa_agent node function with browser testing."""

    def test_qa_node_skips_browser_when_no_ui(self):
        """qa_agent should NOT call test_ui for backend-only projects."""
        with patch("dev_team.agents.qa.get_qa_agent") as mock_get, \
             patch("dev_team.agents.qa.USE_BROWSER_TESTING", True):
            mock_agent = Mock()
            mock_agent.has_ui.return_value = False
            mock_agent.test_code.return_value = {
                "test_results": {"approved": True},
                "issues_found": [],
                "next_agent": "git_commit",
            }
            mock_get.return_value = mock_agent

            from dev_team.agents.qa import qa_agent
            result = qa_agent({"tech_stack": ["Python", "FastAPI"], "code_files": []})

            mock_agent.test_code.assert_called_once()
            mock_agent.test_ui.assert_not_called()

    def test_qa_node_calls_browser_for_ui_project(self):
        """qa_agent should call test_ui for UI projects."""
        with patch("dev_team.agents.qa.get_qa_agent") as mock_get, \
             patch("dev_team.agents.qa.USE_BROWSER_TESTING", True):
            mock_agent = Mock()
            mock_agent.has_ui.return_value = True
            code_result = {
                "test_results": {"approved": True},
                "issues_found": [],
                "next_agent": "git_commit",
            }
            browser_result = {
                "browser_test_results": {"test_status": "pass"},
                "issues_found": [],
            }
            mock_agent.test_code.return_value = code_result
            mock_agent.test_ui.return_value = browser_result
            mock_agent.merge_results.return_value = {
                **code_result,
                "browser_test_results": browser_result["browser_test_results"],
            }
            mock_get.return_value = mock_agent

            from dev_team.agents.qa import qa_agent
            result = qa_agent({"tech_stack": ["React"], "code_files": []})

            mock_agent.test_code.assert_called_once()
            mock_agent.test_ui.assert_called_once()
            mock_agent.merge_results.assert_called_once()

    def test_qa_node_skips_browser_when_disabled(self):
        """qa_agent should skip browser testing when USE_BROWSER_TESTING=false."""
        with patch("dev_team.agents.qa.get_qa_agent") as mock_get, \
             patch("dev_team.agents.qa.USE_BROWSER_TESTING", False):
            mock_agent = Mock()
            mock_agent.has_ui.return_value = True
            mock_agent.test_code.return_value = {
                "test_results": {"approved": True},
                "next_agent": "git_commit",
            }
            mock_get.return_value = mock_agent

            from dev_team.agents.qa import qa_agent
            result = qa_agent({"tech_stack": ["React"], "code_files": []})

            mock_agent.test_ui.assert_not_called()

    def test_qa_node_browser_error_doesnt_crash(self):
        """If test_ui raises an exception, qa_agent should still return code results."""
        with patch("dev_team.agents.qa.get_qa_agent") as mock_get, \
             patch("dev_team.agents.qa.USE_BROWSER_TESTING", True):
            mock_agent = Mock()
            mock_agent.has_ui.return_value = True
            code_result = {
                "test_results": {"approved": True},
                "issues_found": [],
                "next_agent": "git_commit",
            }
            mock_agent.test_code.return_value = code_result
            mock_agent.test_ui.side_effect = Exception("Playwright crashed")
            mock_get.return_value = mock_agent

            from dev_team.agents.qa import qa_agent
            result = qa_agent({"tech_stack": ["React"], "code_files": []})

            # Should still return code result, not crash
            assert result["test_results"]["approved"] is True


# ==================================================================
# 10. State — browser_test_results field
# ==================================================================


class TestStateBrowserField:
    """Test that DevTeamState accepts browser_test_results."""

    def test_create_state_without_browser_results(self):
        """State should work without browser_test_results."""
        from dev_team.state import create_initial_state

        state = create_initial_state(task="Build a landing page")
        # browser_test_results is NotRequired, so it's not in the state
        assert "browser_test_results" not in state

    def test_state_accepts_browser_results(self):
        """State should accept browser_test_results when provided."""
        from dev_team.state import DevTeamState

        # Should not raise
        state_dict: dict = {
            "task": "Build app",
            "requirements": [],
            "user_stories": [],
            "architecture": {},
            "tech_stack": ["React"],
            "architecture_decisions": [],
            "code_files": [],
            "implementation_notes": "",
            "review_comments": [],
            "test_results": {},
            "issues_found": [],
            "summary": "",
            "messages": [],
            "current_agent": "qa",
            "needs_clarification": False,
            "review_iteration_count": 0,
            "architect_escalated": False,
            "retry_count": 0,
            "browser_test_results": {
                "mode": "scripted_e2e",
                "test_status": "pass",
                "screenshots": [],
            },
        }
        # TypedDict doesn't enforce at runtime, but this confirms the field exists
        assert "browser_test_results" in state_dict


# ==================================================================
# 11. SandboxClient — Browser Fields
# ==================================================================


class TestSandboxClientBrowser:
    """Test that SandboxClient passes browser fields correctly."""

    def test_execute_sends_browser_fields(self):
        """SandboxClient.execute should include browser fields in payload."""
        from dev_team.tools.sandbox import SandboxClient

        with patch("dev_team.tools.sandbox.httpx.Client") as MockClient:
            mock_response = Mock()
            mock_response.json.return_value = {
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
                "duration_seconds": 1.0,
                "screenshots": [{"name": "test.png", "base64": "abc"}],
                "browser_console": "loaded",
                "network_errors": [],
            }
            mock_response.raise_for_status = Mock()
            mock_http = Mock()
            mock_http.post.return_value = mock_response
            mock_http.__enter__ = Mock(return_value=mock_http)
            mock_http.__exit__ = Mock(return_value=False)
            MockClient.return_value = mock_http

            client = SandboxClient(base_url="http://test:8002")
            result = client.execute(
                language="python",
                code_files=[{"path": "test.py", "content": "pass"}],
                commands=["pytest"],
                browser=True,
                collect_screenshots=True,
                app_start_command="npm run dev",
                app_ready_timeout=30,
            )

            # Check payload
            call_args = mock_http.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["browser"] is True
            assert payload["collect_screenshots"] is True
            assert payload["app_start_command"] == "npm run dev"

            # Check result
            assert len(result["screenshots"]) == 1
            assert result["browser_console"] == "loaded"

    def test_execute_no_browser_fields_when_disabled(self):
        """When browser=False, browser fields should not be in payload."""
        from dev_team.tools.sandbox import SandboxClient

        with patch("dev_team.tools.sandbox.httpx.Client") as MockClient:
            mock_response = Mock()
            mock_response.json.return_value = {
                "stdout": "ok", "stderr": "", "exit_code": 0,
                "duration_seconds": 1.0,
            }
            mock_response.raise_for_status = Mock()
            mock_http = Mock()
            mock_http.post.return_value = mock_response
            mock_http.__enter__ = Mock(return_value=mock_http)
            mock_http.__exit__ = Mock(return_value=False)
            MockClient.return_value = mock_http

            client = SandboxClient(base_url="http://test:8002")
            client.execute(
                language="python",
                code_files=[{"path": "test.py", "content": "pass"}],
                commands=["pytest"],
            )

            call_args = mock_http.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "browser" not in payload
