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
        timeout=90,
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
    )


# ---------------------------------------------------------------------------
# Tech-stack → defaults mapping
# ---------------------------------------------------------------------------

# Common app start commands and ports by framework
FRAMEWORK_DEFAULTS: dict[str, dict] = {
    "react": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "vite": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "next": {"install": "npm install", "start": "npx next dev", "port": 3000},
    "nextjs": {"install": "npm install", "start": "npx next dev", "port": 3000},
    "vue": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "nuxt": {"install": "npm install", "start": "npx nuxi dev", "port": 3000},
    "angular": {"install": "npm install", "start": "npx ng serve --host 0.0.0.0", "port": 4200},
    "svelte": {"install": "npm install", "start": "npx vite --host 0.0.0.0", "port": 5173},
    "gatsby": {"install": "npm install", "start": "npx gatsby develop -H 0.0.0.0", "port": 8000},
    "flask": {"install": "pip install -r requirements.txt -q", "start": "python app.py", "port": 5000},
    "fastapi": {"install": "pip install -r requirements.txt -q", "start": "uvicorn app:app --host 0.0.0.0 --port 8000", "port": 8000},
    "django": {"install": "pip install -r requirements.txt -q", "start": "python manage.py runserver 0.0.0.0:8000", "port": 8000},
    "html": {"install": "", "start": "python -m http.server 8080", "port": 8080},
}


def detect_framework_defaults(tech_stack: list[str]) -> dict:
    """Detect install/start/port defaults from the tech stack.

    Returns a dict with keys ``install``, ``start``, ``port``.
    Falls back to generic Node.js defaults.
    """
    for tech in tech_stack:
        key = tech.lower().replace(".", "").replace("js", "").strip()
        if key in FRAMEWORK_DEFAULTS:
            return FRAMEWORK_DEFAULTS[key]
        # Try partial match
        for fk, fv in FRAMEWORK_DEFAULTS.items():
            if fk in tech.lower():
                return fv

    # Default: assume Node.js/npm project
    return {"install": "npm install", "start": "npm start", "port": 3000}
