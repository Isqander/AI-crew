"""
Exploration Runner — Batch Playwright Exploration
===================================================

Python script template that runs **inside** the sandbox browser container
for Phase 2 (Guided Exploration) of Visual QA.

Unlike the ``browser_runner`` (Phase 1) which executes pytest-playwright
tests, this runner reads a JSON exploration plan and executes each step
sequentially through the Playwright Sync API.

Flow inside the sandbox container:

  1. Install project dependencies
  2. Start the web application in the background
  3. Wait until the app is listening
  4. Load ``exploration_plan.json``
  5. Execute each step (navigate, click, fill, type, select, scroll, hover, wait)
  6. Collect per-step results (screenshots, console, network errors, timing)
  7. Output a structured ``exploration_report`` as JSON to stdout

The template uses ``.format()``-style placeholders that the QA agent
fills in before sending to the sandbox.

See also: ``VISUAL_QA_PLAN.md §4``
"""

from __future__ import annotations

import json
import re

# ---------------------------------------------------------------------------
# Template — the QA agent substitutes these via str.format()
# ---------------------------------------------------------------------------

EXPLORATION_RUNNER_TEMPLATE = '''\
#!/usr/bin/env python3
"""Exploration runner — batch Playwright exploration inside sandbox container.

Reads exploration_plan.json and executes each step through Playwright,
collecting screenshots, console logs, and network errors along the way.
Outputs a structured JSON report to stdout.
"""
import json
import os
import socket
import subprocess
import sys
import time
import traceback

# === Configuration (substituted by QA agent) ===
APP_COMMAND = {app_command!r}
APP_PORT = {app_port}
APP_READY_TIMEOUT = {app_ready_timeout}
INSTALL_COMMAND = {install_command!r}
MAX_STEP_TIMEOUT = {max_step_timeout}  # seconds per step
STOP_ON_ERROR = {stop_on_error!r}       # stop execution on first step failure

SCREENSHOT_DIR = "/screenshots"
PLAN_FILE = "exploration_plan.json"


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


def execute_step(page, step: dict, console_buf: list, network_buf: list) -> dict:
    """Execute a single exploration step and return the step report.

    Supported actions: navigate, click, fill_form, type, select,
    scroll, hover, wait, screenshot_only.

    Each step may have:
      - ``assertions``: list of human-readable assertions (logged, not enforced)
      - ``screenshot``: bool — take a screenshot after this step
      - ``wait_after``: seconds to wait after the action
      - ``selector``: CSS/text selector for interactive actions
      - ``url``: URL for navigate action
      - ``fields``: list of {{selector, value}} for fill_form action
      - ``value``: text value for type/select actions
      - ``direction``: "down"/"up" for scroll action (default: "down")
    """
    step_id = step.get("id", "unknown")
    action = step.get("action", "screenshot_only")
    description = step.get("description", "")

    # Snapshot console/network state before step
    console_before = len(console_buf)
    network_before = len(network_buf)

    step_start = time.time()
    error_msg = None
    screenshot_path = None

    try:
        if action == "navigate":
            url = step.get("url", "/")
            nav_base = step.get("_base_url", f"http://localhost:{{APP_PORT}}")
            if url.startswith("/"):
                url = nav_base.rstrip("/") + url
            page.goto(url, wait_until="domcontentloaded", timeout=MAX_STEP_TIMEOUT * 1000)

        elif action == "click":
            selector = step.get("selector", "")
            if selector:
                loc = _resolve_locator(page, selector)
                try:
                    loc.click(timeout=MAX_STEP_TIMEOUT * 1000)
                except Exception as _ce:
                    if "Timeout" not in type(_ce).__name__:
                        raise
                    _btns = page.locator(
                        "button:visible,input[type='submit']:visible,"
                        "[role='button']:visible"
                    )
                    if _btns.count() == 1:
                        _btns.first.click(timeout=5000)
                        print("[exploration]   Fallback: '" + selector + "' not found, clicked only visible button", file=sys.stderr)
                    else:
                        raise
            else:
                error_msg = "click action requires a selector"

        elif action == "fill_form":
            fields = step.get("fields", [])
            for field in fields:
                sel = field.get("selector", "")
                val = field.get("value", "")
                if sel and val is not None:
                    loc = _resolve_locator(page, sel, for_fill=True)
                    try:
                        loc.fill(str(val), timeout=MAX_STEP_TIMEOUT * 1000)
                    except Exception as _fe:
                        if "Timeout" not in type(_fe).__name__:
                            raise
                        _fb = page.locator(
                            "input:visible:not([type='checkbox']):not([type='radio'])"
                            ":not([type='hidden']):not([type='file']),textarea:visible"
                        ).first
                        _fb.fill(str(val), timeout=5000)
                        print("[exploration]   Fallback: '" + sel + "' not found, used visible text input", file=sys.stderr)

        elif action == "type":
            selector = step.get("selector", "")
            value = step.get("value", "")
            if selector:
                loc = _resolve_locator(page, selector, for_fill=True)
                try:
                    loc.fill(str(value), timeout=MAX_STEP_TIMEOUT * 1000)
                except Exception as _te:
                    if "Timeout" not in type(_te).__name__:
                        raise
                    _fb = page.locator(
                        "input:visible:not([type='checkbox']):not([type='radio'])"
                        ":not([type='hidden']):not([type='file']),textarea:visible"
                    ).first
                    _fb.fill(str(value), timeout=5000)
                    print("[exploration]   Fallback: '" + selector + "' not found, used visible text input", file=sys.stderr)
            else:
                error_msg = "type action requires a selector"

        elif action == "select":
            selector = step.get("selector", "")
            value = step.get("value", "")
            if selector:
                loc = _resolve_locator(page, selector)
                loc.select_option(value, timeout=MAX_STEP_TIMEOUT * 1000)
            else:
                error_msg = "select action requires a selector"

        elif action == "hover":
            selector = step.get("selector", "")
            if selector:
                loc = _resolve_locator(page, selector)
                loc.hover(timeout=MAX_STEP_TIMEOUT * 1000)
            else:
                error_msg = "hover action requires a selector"

        elif action == "scroll":
            direction = step.get("direction", "down")
            amount = step.get("amount", 500)
            delta = amount if direction == "down" else -amount
            page.mouse.wheel(0, delta)

        elif action == "wait":
            wait_time = step.get("duration", 2)
            page.wait_for_timeout(int(wait_time * 1000))

        elif action == "screenshot_only":
            pass  # Screenshot is taken below if step.screenshot is True

        else:
            error_msg = f"Unknown action: {{action}}"

    except Exception as exc:
        err_text = type(exc).__name__ + ": " + str(exc)[:500]
        if "Timeout" in type(exc).__name__:
            inv = _page_element_inventory(page)
            err_text += " [visible elements: " + inv + "]"
        error_msg = err_text

    # Optional wait after action
    wait_after = step.get("wait_after", 0)
    if wait_after and not error_msg:
        page.wait_for_timeout(int(wait_after * 1000))

    # Take screenshot if requested
    if step.get("screenshot", False) or error_msg:
        try:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            safe_id = step_id.replace("/", "_").replace(" ", "_")
            screenshot_path = f"{{SCREENSHOT_DIR}}/{{safe_id}}.png"
            page.screenshot(path=screenshot_path, full_page=False)
        except Exception as ss_err:
            print(f"[exploration] WARNING: screenshot failed for {{step_id}}: {{ss_err}}", file=sys.stderr)
            screenshot_path = None

    # Capture new console and network messages since this step started
    new_console = console_buf[console_before:]
    new_network = network_buf[network_before:]

    step_duration_ms = int((time.time() - step_start) * 1000)

    # Build step report
    step_report = {{
        "id": step_id,
        "description": description,
        "action": action,
        "status": "error" if error_msg else "success",
        "error": error_msg,
        "screenshot": screenshot_path,
        "console_messages": list(new_console),
        "network_errors": list(new_network),
        "current_url": page.url,
        "page_title": page.title(),
        "duration_ms": step_duration_ms,
        "assertions": step.get("assertions", []),
    }}

    status_icon = "FAIL" if error_msg else "OK"
    print(f"[exploration] [{{status_icon}}] {{step_id}}: {{description}} ({{step_duration_ms}}ms)")
    if error_msg:
        print(f"[exploration]   Error: {{error_msg}}", file=sys.stderr)

    return step_report


def _normalize_selector(selector: str) -> str:
    """Normalize common LLM-generated selector mistakes into valid CSS/Playwright.

    LLMs often produce selectors like ``id=foo`` or ``class=bar`` by analogy
    with ``text=...`` / ``placeholder=...``.  These are NOT valid Playwright
    selector engines and must be converted to CSS equivalents.

    Conversions:
      - ``id=foo``       → ``#foo``
      - ``class=foo``    → ``.foo``
      - ``name=foo``     → ``[name='foo']``  (HTML attribute)
      - ``type=foo``     → ``[type='foo']``  (HTML attribute)
      - ``data-testid=x`` → treated as ``testid=x`` (handled later by _resolve_locator)
    """
    sel = selector.strip()

    # id=value → #value
    if sel.startswith("id="):
        return "#" + sel[3:].strip()

    # class=value → .value  (also handle "class=foo bar" → ".foo.bar")
    if sel.startswith("class="):
        classes = sel[6:].strip().split()
        return "." + ".".join(classes)

    # name=value → [name='value']  (HTML attribute, NOT Playwright engine)
    if sel.startswith("name="):
        return "[name='" + sel[5:].strip() + "']"

    # type=value → [type='value']
    if sel.startswith("type="):
        return "[type='" + sel[5:].strip() + "']"

    # data-testid=value → testid=value  (Playwright semantic alias)
    if sel.startswith("data-testid="):
        return "testid=" + sel[12:].strip()

    return sel


def _resolve_locator(page, selector: str, *, for_fill: bool = False):
    """Resolve a selector string to a Playwright locator.

    First normalizes common LLM mistakes (``id=``, ``class=``), then
    dispatches to the appropriate Playwright API:

      - ``text=...``     → page.get_by_text(...)
      - ``role=button[name=Submit]`` → page.get_by_role("button", name="Submit")
      - ``placeholder=...`` → page.get_by_placeholder(...)
      - ``label=...``    → page.get_by_label(...)
      - ``testid=...``   → page.get_by_test_id(...)
      - Everything else  → page.locator(selector)  (CSS / XPath)

    When *for_fill* is True (fill_form / type actions), the function
    proactively checks whether the locator matches more than one element.
    If so, it narrows the match to text-like inputs (excluding checkboxes,
    radios, hidden fields, and file inputs) to prevent Playwright strict
    mode violations.
    """
    sel = _normalize_selector(selector)

    if sel.startswith("text="):
        return page.get_by_text(sel[5:])
    if sel.startswith("placeholder="):
        return page.get_by_placeholder(sel[12:])
    if sel.startswith("label="):
        return page.get_by_label(sel[6:])
    if sel.startswith("testid="):
        return page.get_by_test_id(sel[7:])
    if sel.startswith("role="):
        # Parse role=button[name=Submit]
        role_match = __import__("re").match(r"role=(\\w+)(?:\\[name=(.+?)\\])?", sel)
        if role_match:
            role_name = role_match.group(1)
            name = role_match.group(2)
            if name:
                return page.get_by_role(role_name, name=name)
            return page.get_by_role(role_name)

    loc = page.locator(sel)

    # Strict mode protection for fill/type actions — if the locator
    # matches multiple elements, try to narrow to fillable inputs.
    if for_fill:
        try:
            cnt = loc.count()
            if cnt > 1:
                narrowed = page.locator(
                    sel + ":not([type='checkbox']):not([type='radio'])"
                    ":not([type='hidden']):not([type='file'])"
                )
                nc = narrowed.count()
                if nc == 1:
                    return narrowed
                if nc > 1:
                    return narrowed.first
                # Narrowing eliminated all matches — use first of original
                return loc.first
        except Exception:
            pass

    return loc


def _page_element_inventory(page):
    """Inventory of visible interactive elements for timeout diagnostics."""
    parts = []
    for tag in ("input", "button", "textarea", "a"):
        try:
            els = page.locator(tag + ":visible")
            n = els.count()
            if n > 0:
                descs = []
                for i in range(min(n, 3)):
                    el = els.nth(i)
                    d = tag
                    for attr in ("type", "id", "placeholder"):
                        v = el.get_attribute(attr)
                        if v:
                            d += "[" + attr + "=" + v + "]"
                    if tag in ("button", "a"):
                        t = (el.text_content() or "")[:20].strip()
                        if t:
                            d += "[text=" + t + "]"
                    descs.append(d)
                parts.append(str(n) + "x " + ", ".join(descs))
        except Exception:
            pass
    return "; ".join(parts) or "(none)"


def main() -> None:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # ── 1. Install dependencies ─────────────────────────────────────
    if INSTALL_COMMAND:
        print(f"[exploration] Installing dependencies: {{INSTALL_COMMAND}}")
        result = subprocess.run(
            INSTALL_COMMAND, shell=True,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"[exploration] WARNING: Install exited with {{result.returncode}}")
            if result.stderr:
                print(result.stderr[:2000], file=sys.stderr)

    # ── 2. Start the application in the background ──────────────────
    app_proc = None
    if APP_COMMAND:
        print(f"[exploration] Starting app: {{APP_COMMAND}}")
        app_proc = subprocess.Popen(
            APP_COMMAND, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        print(f"[exploration] App started (PID {{app_proc.pid}})")

    # ── 3. Wait for the app to be ready ─────────────────────────────
    if APP_PORT:
        print(f"[exploration] Waiting for port {{APP_PORT}} (timeout={{APP_READY_TIMEOUT}}s)...")
        if not wait_for_port(APP_PORT, APP_READY_TIMEOUT):
            app_error = "Application did not start in time"
            print(f"[exploration] ERROR: {{app_error}}", file=sys.stderr)
            app_stderr_text = ""
            if app_proc:
                app_proc.terminate()
                try:
                    out, err = app_proc.communicate(timeout=5)
                    if out:
                        print(f"[exploration] App stdout: {{out.decode(errors='replace')[:3000]}}")
                    if err:
                        app_stderr_text = err.decode(errors="replace")[:3000]
                        print(f"[exploration] App stderr: {{app_stderr_text}}", file=sys.stderr)
                except subprocess.TimeoutExpired:
                    app_proc.kill()
            # Generate a failure report so QA can still analyse what went wrong
            failure_report = {{
                "plan_name": "Unknown",
                "base_url": f"http://localhost:{{APP_PORT}}",
                "total_steps": 0,
                "executed_steps": 0,
                "successful_steps": 0,
                "failed_steps": 0,
                "screenshots_collected": 0,
                "total_duration_seconds": 0,
                "steps": [],
                "all_console_messages": [],
                "all_network_errors": [],
                "startup_error": f"{{app_error}}: {{app_stderr_text[:1000]}}",
            }}
            # Try to read plan name from exploration_plan.json
            try:
                if os.path.exists(PLAN_FILE):
                    with open(PLAN_FILE, "r") as f:
                        plan_data = json.load(f)
                    failure_report["plan_name"] = plan_data.get("name", "Unknown")
                    failure_report["total_steps"] = len(plan_data.get("steps", []))
            except Exception:
                pass
            print("===EXPLORATION_REPORT_START===")
            print(json.dumps(failure_report, indent=2, ensure_ascii=False))
            print("===EXPLORATION_REPORT_END===")
            sys.exit(1)
        print(f"[exploration] App ready on port {{APP_PORT}}")

    # ── 4. Load exploration plan ────────────────────────────────────
    if not os.path.exists(PLAN_FILE):
        print(f"[exploration] ERROR: {{PLAN_FILE}} not found", file=sys.stderr)
        sys.exit(1)

    with open(PLAN_FILE, "r") as f:
        plan = json.load(f)

    plan_name = plan.get("name", "Unnamed Exploration")
    steps = plan.get("steps", [])
    # base_url is ALWAYS derived from APP_PORT (set by QA agent from
    # detect_framework_defaults).  The LLM-generated plan may contain a
    # wrong base_url — we ignore it.
    base_url = f"http://localhost:{{APP_PORT}}"

    print(f"[exploration] Plan: {{plan_name}} ({{len(steps)}} steps, base_url={{base_url}})")

    # ── 5. Execute steps with Playwright ────────────────────────────
    from playwright.sync_api import sync_playwright

    exploration_start = time.time()
    report_steps = []
    all_console = []
    all_network = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={{"width": 1280, "height": 720}},
            user_agent="AI-crew-ExplorationRunner/1.0",
        )
        page = context.new_page()

        # Attach console and network listeners
        page.on("console", lambda msg: all_console.append(f"{{msg.type}}: {{msg.text}}"))
        page.on("requestfailed", lambda req: all_network.append(
            f"{{req.method}} {{req.url}} {{req.failure}}"
        ))

        for step in steps:
            # Inject base_url into each step for navigate resolution
            step["_base_url"] = base_url

            step_report = execute_step(page, step, all_console, all_network)
            report_steps.append(step_report)

            # Stop on error if configured
            if STOP_ON_ERROR and step_report["status"] == "error":
                print(f"[exploration] Stopping: STOP_ON_ERROR is set and step {{step['id']}} failed")
                break

        browser.close()

    total_duration = time.time() - exploration_start

    # ── 6. Build and output report ──────────────────────────────────
    successful = sum(1 for s in report_steps if s["status"] == "success")
    failed = sum(1 for s in report_steps if s["status"] == "error")
    screenshots_collected = sum(1 for s in report_steps if s.get("screenshot"))

    report = {{
        "plan_name": plan_name,
        "base_url": base_url,
        "total_steps": len(steps),
        "executed_steps": len(report_steps),
        "successful_steps": successful,
        "failed_steps": failed,
        "screenshots_collected": screenshots_collected,
        "total_duration_seconds": round(total_duration, 2),
        "steps": report_steps,
        "all_console_messages": all_console,
        "all_network_errors": all_network,
    }}

    # Output the report as delimited JSON (easy to parse from stdout)
    print("===EXPLORATION_REPORT_START===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("===EXPLORATION_REPORT_END===")

    print(f"[exploration] Done: {{successful}}/{{len(report_steps)}} steps OK, "
          f"{{screenshots_collected}} screenshots, {{total_duration:.1f}}s total")

    # ── 7. Cleanup ──────────────────────────────────────────────────
    if app_proc:
        print("[exploration] Stopping app...")
        app_proc.terminate()
        try:
            app_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            app_proc.kill()

    # Exit with 0 if all steps passed, 1 if any failed
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_exploration_runner(
    app_command: str | None = None,
    app_port: int = 3000,
    app_ready_timeout: int = 30,
    install_command: str | None = None,
    max_step_timeout: int = 15,
    stop_on_error: bool = False,
) -> str:
    """Fill the exploration runner template with concrete values.

    Parameters
    ----------
    app_command:
        Shell command to start the web application.
    app_port:
        Port the application listens on.
    app_ready_timeout:
        Seconds to wait for the port to become available.
    install_command:
        Dependency install command (e.g. ``"npm install"``).
    max_step_timeout:
        Max seconds for a single Playwright step (action + wait).
    stop_on_error:
        If True, stop the exploration on the first step failure.

    Returns
    -------
    str
        Complete Python script ready to be written as
        ``exploration_runner.py`` inside the sandbox container.
    """
    return EXPLORATION_RUNNER_TEMPLATE.format(
        app_command=app_command or "",
        app_port=app_port,
        app_ready_timeout=app_ready_timeout,
        install_command=install_command or "",
        max_step_timeout=max_step_timeout,
        stop_on_error=stop_on_error,
    )


# ---------------------------------------------------------------------------
# Selector Normalization (host-side, before sending to sandbox)
# ---------------------------------------------------------------------------

# Prefixes that are NOT valid Playwright selector engines but LLMs
# commonly generate by analogy with ``text=`` / ``placeholder=``.
_INVALID_ENGINE_PREFIXES = {
    "id=": lambda v: "#" + v,
    "class=": lambda v: "." + ".".join(v.split()),
    "name=": lambda v: f"[name='{v}']",
    "type=": lambda v: f"[type='{v}']",
    "data-testid=": lambda v: "testid=" + v,
}


def normalize_selector(selector: str) -> str:
    """Normalize a single selector string.

    Converts common LLM mistakes into valid CSS / Playwright selectors:

      - ``id=foo``        → ``#foo``
      - ``class=foo``     → ``.foo``
      - ``class=foo bar`` → ``.foo.bar``
      - ``name=foo``      → ``[name='foo']``
      - ``type=submit``   → ``[type='submit']``
      - ``data-testid=x`` → ``testid=x``

    Valid selectors (``text=``, ``placeholder=``, ``label=``, ``testid=``,
    ``role=``, CSS, XPath) pass through unchanged.
    """
    sel = selector.strip()
    for prefix, transform in _INVALID_ENGINE_PREFIXES.items():
        if sel.startswith(prefix):
            return transform(sel[len(prefix):].strip())
    return sel


def qualify_for_fill(selector: str) -> str:
    """Qualify bare tag selectors that are ambiguous in fill/type contexts.

    A bare ``input`` selector often matches multiple elements after DOM changes
    (e.g. text input + checkbox), causing Playwright strict mode violations.

    Conversions:
      - ``input`` → ``input:not([type='checkbox']):not([type='radio']):not([type='hidden']):not([type='file'])``
      - Other selectors pass through unchanged.
    """
    sel = selector.strip()
    if sel.lower() == "input":
        return (
            "input:not([type='checkbox']):not([type='radio'])"
            ":not([type='hidden']):not([type='file'])"
        )
    return sel


def normalize_plan_selectors(plan: dict) -> int:
    """Normalize all selectors in an exploration plan **in-place**.

    Applies two transformations:
      1. ``normalize_selector`` — fix invalid engine prefixes (``id=``, ``class=``, etc.)
      2. ``qualify_for_fill`` — qualify bare tag selectors in fill/type contexts

    Returns the number of selectors that were changed.
    """
    fixed = 0
    for step in plan.get("steps", []):
        action = step.get("action", "")
        is_fill = action in ("type", "fill_form")

        # Direct selector
        sel = step.get("selector")
        if sel:
            new_sel = normalize_selector(sel)
            if is_fill:
                new_sel = qualify_for_fill(new_sel)
            if new_sel != sel:
                step["selector"] = new_sel
                fixed += 1

        # fill_form fields (always fill context)
        for field in step.get("fields", []):
            sel = field.get("selector")
            if sel:
                new_sel = normalize_selector(sel)
                new_sel = qualify_for_fill(new_sel)
                if new_sel != sel:
                    field["selector"] = new_sel
                    fixed += 1
    return fixed


# ---------------------------------------------------------------------------
# Exploration Plan Validation
# ---------------------------------------------------------------------------

# Supported action types for exploration steps
VALID_ACTIONS = frozenset({
    "navigate", "click", "fill_form", "type", "select",
    "scroll", "hover", "wait", "screenshot_only",
})


def validate_exploration_plan(plan: dict) -> list[str]:
    """Validate an exploration plan dict.

    Returns a list of error strings.  Empty list means valid.

    Checks:
      - ``steps`` is a non-empty list
      - Each step has ``id``, ``action``
      - ``action`` is one of the supported types
      - ``navigate`` steps have ``url``
      - ``click`` / ``type`` / ``select`` / ``hover`` steps have ``selector``
      - ``fill_form`` steps have ``fields`` list
    """
    errors: list[str] = []

    if not isinstance(plan, dict):
        return ["Plan must be a JSON object"]

    steps = plan.get("steps")
    if not steps or not isinstance(steps, list):
        errors.append("Plan must have a non-empty 'steps' list")
        return errors

    seen_ids: set[str] = set()
    for i, step in enumerate(steps):
        prefix = f"Step {i}"

        if not isinstance(step, dict):
            errors.append(f"{prefix}: must be a JSON object")
            continue

        step_id = step.get("id")
        if not step_id:
            errors.append(f"{prefix}: missing 'id'")
        else:
            prefix = f"Step '{step_id}'"
            if step_id in seen_ids:
                errors.append(f"{prefix}: duplicate id")
            seen_ids.add(step_id)

        action = step.get("action")
        if not action:
            errors.append(f"{prefix}: missing 'action'")
        elif action not in VALID_ACTIONS:
            errors.append(f"{prefix}: unknown action '{action}' "
                          f"(valid: {', '.join(sorted(VALID_ACTIONS))})")
        else:
            # Action-specific checks
            if action == "navigate" and not step.get("url"):
                errors.append(f"{prefix}: 'navigate' action requires 'url'")
            if action in ("click", "type", "select", "hover") and not step.get("selector"):
                errors.append(f"{prefix}: '{action}' action requires 'selector'")
            if action == "fill_form":
                fields = step.get("fields")
                if not fields or not isinstance(fields, list):
                    errors.append(f"{prefix}: 'fill_form' action requires 'fields' list")
                else:
                    for j, field in enumerate(fields):
                        if not field.get("selector"):
                            errors.append(f"{prefix}: field {j} missing 'selector'")

    return errors


def extract_exploration_report(stdout: str) -> dict | None:
    """Extract the exploration report JSON from sandbox stdout.

    The runner outputs the report between delimiters:
    ``===EXPLORATION_REPORT_START===`` and ``===EXPLORATION_REPORT_END===``.

    Returns the parsed dict, or ``None`` if not found / invalid.
    """
    match = re.search(
        r"===EXPLORATION_REPORT_START===\s*(.*?)\s*===EXPLORATION_REPORT_END===",
        stdout,
        re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
