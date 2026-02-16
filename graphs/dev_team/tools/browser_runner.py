"""
Browser Test Runner — Template
================================

Python script template that runs **inside** the sandbox browser container.

The QA agent includes this runner along with a Playwright test file
in ``code_files``.  The runner:

  1. Installs project dependencies (``npm install`` / ``pip install``)
  2. Starts the web application in the background
  3. Waits until the app is listening on the expected port
  4. Runs Playwright tests via ``pytest``
  5. Collects screenshots into ``/screenshots/``
  6. Outputs structured results to stdout

The template uses ``.format()``-style placeholders that the QA agent
fills in before sending to the sandbox.

See also: ``VISUAL_QA_PLAN.md §3.2``
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Template constants — the QA agent substitutes these via str.format()
# ---------------------------------------------------------------------------

BROWSER_RUNNER_TEMPLATE = '''\
#!/usr/bin/env python3
"""Browser test runner — executes inside sandbox container."""
import subprocess
import time
import sys
import json
import os
import socket

# === Configuration (substituted by QA agent) ===
APP_COMMAND = {app_command!r}
APP_PORT = {app_port}
APP_READY_TIMEOUT = {app_ready_timeout}
TEST_TIMEOUT = {test_timeout}
INSTALL_COMMAND = {install_command!r}
BASE_URL = f"http://localhost:{{APP_PORT}}"

SCREENSHOT_DIR = "/screenshots"


def wait_for_port(port: int, timeout: int = 30) -> bool:
    """Wait until the application is listening on *port*."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def main() -> None:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # ── 1. Install dependencies ──────────────────────────────────
    if INSTALL_COMMAND:
        print(f"[runner] Installing dependencies: {{INSTALL_COMMAND}}")
        result = subprocess.run(
            INSTALL_COMMAND, shell=True,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"[runner] WARNING: Install exited with {{result.returncode}}")
            if result.stderr:
                print(result.stderr[:2000], file=sys.stderr)

    # ── 2. Start the application in the background ───────────────
    app_proc = None
    if APP_COMMAND:
        print(f"[runner] Starting app: {{APP_COMMAND}}")
        app_proc = subprocess.Popen(
            APP_COMMAND, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        print(f"[runner] App started (PID {{app_proc.pid}})")

    # ── 3. Wait for the app to be ready ──────────────────────────
    if APP_PORT:
        print(f"[runner] Waiting for port {{APP_PORT}} (timeout={{APP_READY_TIMEOUT}}s)...")
        if not wait_for_port(APP_PORT, APP_READY_TIMEOUT):
            print("[runner] ERROR: Application did not start in time", file=sys.stderr)
            # Dump app logs for debugging
            if app_proc:
                app_proc.terminate()
                try:
                    out, err = app_proc.communicate(timeout=5)
                    if out:
                        print(f"[runner] App stdout: {{out.decode(errors='replace')[:3000]}}")
                    if err:
                        print(f"[runner] App stderr: {{err.decode(errors='replace')[:3000]}}", file=sys.stderr)
                except subprocess.TimeoutExpired:
                    app_proc.kill()
            sys.exit(1)
        print(f"[runner] App ready on port {{APP_PORT}}")

    # ── 4. Run Playwright tests ──────────────────────────────────
    print("[runner] Running Playwright tests...")
    test_result = subprocess.run(
        [
            "python", "-m", "pytest",
            "playwright_test.py",
            "-v",
            "--tb=short",
        ],
        capture_output=True, text=True,
        timeout=TEST_TIMEOUT,
        env={{
            **os.environ,
            "BASE_URL": BASE_URL,
            "SCREENSHOT_DIR": SCREENSHOT_DIR,
        }},
    )

    # Print test output
    print(test_result.stdout)
    if test_result.stderr:
        print(test_result.stderr, file=sys.stderr)

    # ── 5. Cleanup ───────────────────────────────────────────────
    if app_proc:
        print("[runner] Stopping app...")
        app_proc.terminate()
        try:
            app_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            app_proc.kill()

    # ── 6. Summary ───────────────────────────────────────────────
    # Count screenshots
    screenshots = [
        f for f in os.listdir(SCREENSHOT_DIR)
        if f.endswith(".png")
    ] if os.path.isdir(SCREENSHOT_DIR) else []

    print(f"[runner] Tests finished. Exit code: {{test_result.returncode}}")
    print(f"[runner] Screenshots collected: {{len(screenshots)}}")

    sys.exit(test_result.returncode)


if __name__ == "__main__":
    main()
'''


def build_runner_script(
    app_command: str | None = None,
    app_port: int = 3000,
    app_ready_timeout: int = 30,
    install_command: str | None = None,
    test_timeout: int = 180,
) -> str:
    """Fill the runner template with concrete values.

    Parameters
    ----------
    app_command:
        Shell command to start the web application (e.g. ``"npm run dev"``).
    app_port:
        Port the application listens on.
    app_ready_timeout:
        Seconds to wait for the port to become available.
    install_command:
        Dependency install command (e.g. ``"npm install"``).
    test_timeout:
        Max seconds for the pytest subprocess (should be less than
        the overall sandbox timeout to allow cleanup).

    Returns
    -------
    str
        Complete Python script ready to be written as ``browser_runner.py``
        inside the sandbox container.
    """
    return BROWSER_RUNNER_TEMPLATE.format(
        app_command=app_command or "",
        app_port=app_port,
        app_ready_timeout=app_ready_timeout,
        install_command=install_command or "",
        test_timeout=test_timeout,
    )


# ---------------------------------------------------------------------------
# Tech-stack → defaults mapping
# ---------------------------------------------------------------------------

# Common app start commands and ports by framework
FRAMEWORK_DEFAULTS: dict[str, dict] = {
    # Node.js frameworks
    "react": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "vite": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "next": {"install": "npm install", "start": "npx next dev", "port": 3000},
    "nextjs": {"install": "npm install", "start": "npx next dev", "port": 3000},
    "vue": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "nuxt": {"install": "npm install", "start": "npx nuxi dev", "port": 3000},
    "angular": {"install": "npm install", "start": "npx ng serve --host 0.0.0.0", "port": 4200},
    "svelte": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "gatsby": {"install": "npm install", "start": "npx gatsby develop -H 0.0.0.0", "port": 8000},
    "express": {"install": "npm install", "start": "npm start", "port": 3000},
    "node": {"install": "npm install", "start": "npm start", "port": 3000},
    # Python frameworks
    "flask": {"install": "pip install -r requirements.txt -q", "start": "python app.py", "port": 5000},
    "fastapi": {"install": "pip install -r requirements.txt -q", "start": "uvicorn app:app --host 0.0.0.0 --port 8000", "port": 8000},
    "django": {"install": "pip install -r requirements.txt -q", "start": "python manage.py runserver 0.0.0.0:8000", "port": 8000},
    # Static (lowest priority — matched only in fallback pass)
    "html": {"install": "", "start": "python -m http.server 8080", "port": 8080},
}


# Python frameworks whose start command depends on actual file paths
# and must be refined through code analysis (Pass 2b).
_PYTHON_FRAMEWORKS = {"fastapi", "flask", "django"}

# Regex to detect the ASGI/WSGI app variable name.
# Matches:  app = FastAPI()  /  application = FastAPI(...)  /  server=FastAPI()
import re as _re
_FASTAPI_VAR_RE = _re.compile(r"(\w+)\s*=\s*(?:fastapi\.)?FastAPI\s*\(")
_FLASK_VAR_RE = _re.compile(r"(\w+)\s*=\s*(?:flask\.)?Flask\s*\(")


def detect_framework_defaults(
    tech_stack: list[str],
    code_files: list[dict] | None = None,
) -> dict:
    """Detect install/start/port defaults from the tech stack and code files.

    Returns a dict with keys ``install``, ``start``, ``port``.

    Detection strategy:
      1. Check tech_stack for specific frameworks (skip generic html/css).
         For Python frameworks (FastAPI, Flask, Django), defer to Pass 2b
         if code_files are available, so the actual file paths are used.
      2. Analyse code_files contents:
         a. package.json dependencies → specific Node.js framework
         b. Python file imports → FastAPI / Flask / Django (with real paths)
         c. JS/TS file imports → Express etc.
      3. Fall back to generic html/css match from tech_stack
      4. Default: Node.js (npm start on port 3000)
    """
    generic_keys = {"html", "css"}

    def _normalize(tech: str) -> str:
        return tech.lower().replace(".", "").replace(".js", "").strip()

    # Pass 1: specific frameworks (skip html/css).
    # For Python frameworks, remember the match but defer to Pass 2b
    # to detect actual file paths (e.g. app/main.py → uvicorn app.main:app).
    deferred_python_default: dict | None = None

    for tech in tech_stack:
        key = _normalize(tech)
        if key in generic_keys:
            continue
        if key in FRAMEWORK_DEFAULTS:
            if key in _PYTHON_FRAMEWORKS and code_files:
                deferred_python_default = FRAMEWORK_DEFAULTS[key]
                continue  # defer to Pass 2b
            return FRAMEWORK_DEFAULTS[key]
        # Partial match
        tech_lower = tech.lower()
        for fk, fv in FRAMEWORK_DEFAULTS.items():
            if fk in tech_lower:
                if fk in _PYTHON_FRAMEWORKS and code_files:
                    deferred_python_default = fv
                    break  # defer to Pass 2b
                return fv

    # Pass 2: detect from code_files
    if code_files:
        # 2a: package.json → Node.js project (check deps for specific framework)
        for f in code_files:
            if f.get("path", "").endswith("package.json"):
                content = f.get("content", "")
                content_lower = content.lower()
                for fw in ("react", "vue", "next", "nuxt", "angular", "svelte", "gatsby", "express", "vite"):
                    if f'"{fw}' in content_lower:
                        if fw in FRAMEWORK_DEFAULTS:
                            return FRAMEWORK_DEFAULTS[fw]
                # Generic Node.js
                return FRAMEWORK_DEFAULTS["node"]

        # 2b: Scan Python file contents for framework imports
        _py_framework_patterns = {
            "fastapi": ["from fastapi", "import fastapi", "FastAPI("],
            "flask": ["from flask", "import flask", "Flask("],
            "django": ["from django", "import django", "django.conf"],
        }
        for f in code_files:
            path = f.get("path", "")
            if not path.endswith(".py"):
                continue
            content = f.get("content", "")
            for fw, patterns in _py_framework_patterns.items():
                if any(p in content for p in patterns):
                    defaults = FRAMEWORK_DEFAULTS[fw].copy()
                    norm_path = path.replace("\\", "/")

                    if fw == "fastapi":
                        module = norm_path.removesuffix(".py").replace("/", ".")
                        # Detect app variable name (default: "app")
                        var_match = _FASTAPI_VAR_RE.search(content)
                        var_name = var_match.group(1) if var_match else "app"
                        defaults["start"] = (
                            f"uvicorn {module}:{var_name} --host 0.0.0.0 --port {defaults['port']}"
                        )
                    elif fw == "flask":
                        defaults["start"] = f"python {norm_path}"
                    # Check if requirements.txt exists; if not, install inline
                    has_requirements = any(
                        cf.get("path", "").endswith("requirements.txt")
                        for cf in code_files
                    )
                    if not has_requirements:
                        if fw == "fastapi":
                            defaults["install"] = "pip install fastapi uvicorn -q"
                        elif fw == "flask":
                            defaults["install"] = "pip install flask -q"
                        elif fw == "django":
                            defaults["install"] = "pip install django -q"
                    return defaults

        # 2c: Scan JS/TS file contents for framework requires/imports
        _js_framework_patterns = {
            "express": ["require('express')", 'require("express")', "from 'express'", 'from "express"'],
        }
        for f in code_files:
            path = f.get("path", "")
            if not any(path.endswith(ext) for ext in (".js", ".ts", ".mjs")):
                continue
            content = f.get("content", "")
            for fw, patterns in _js_framework_patterns.items():
                if any(p in content for p in patterns):
                    return FRAMEWORK_DEFAULTS[fw]

    # Pass 2 didn't find anything — use deferred Python default if available
    if deferred_python_default:
        return deferred_python_default

    # Pass 3: generic match (html)
    for tech in tech_stack:
        key = _normalize(tech)
        if key in FRAMEWORK_DEFAULTS:
            return FRAMEWORK_DEFAULTS[key]

    # Default: assume Node.js/npm project
    return {"install": "npm install", "start": "npm start", "port": 3000}
