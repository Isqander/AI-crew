#!/usr/bin/env python3
"""
Verification script for Sandbox Infrastructure (Module 3.7) and CI/CD Integration (Module 3.8).

Usage:
  # Full verification (requires Docker services running):
  python scripts/verify_sandbox_ci.py

  # Only graph/routing checks (no Docker needed):
  python scripts/verify_sandbox_ci.py --no-docker

  # Only sandbox checks:
  python scripts/verify_sandbox_ci.py --only sandbox

  # Only CI checks:
  python scripts/verify_sandbox_ci.py --only ci

  # With real GitHub repo (requires GITHUB_TOKEN):
  python scripts/verify_sandbox_ci.py --github-repo owner/repo --github-branch main

Prerequisites:
  docker compose up -d sandbox sandbox-postgres
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


class VerificationRunner:
    """Collects and reports check results."""

    def __init__(self):
        self.results: list[CheckResult] = []
        self._section = ""

    def section(self, name: str):
        self._section = name
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")

    def check(self, name: str, passed: bool, message: str, duration_ms: float = 0, **details):
        full_name = f"[{self._section}] {name}" if self._section else name
        result = CheckResult(full_name, passed, message, duration_ms, details)
        self.results.append(result)
        icon = "PASS" if passed else "FAIL"
        dur = f" ({duration_ms:.0f}ms)" if duration_ms > 0 else ""
        print(f"  [{icon}] {name}{dur}")
        if not passed:
            print(f"         {message}")
        if details:
            for k, v in details.items():
                val = str(v)[:200]
                print(f"         {k}: {val}")

    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print(f"\n{'='*60}")
        print(f"  SUMMARY: {passed}/{total} passed, {failed} failed")
        print(f"{'='*60}")

        if failed > 0:
            print("\n  Failed checks:")
            for r in self.results:
                if not r.passed:
                    print(f"    - {r.name}: {r.message}")

        return failed == 0


# ---------------------------------------------------------------------------
# 1. SANDBOX INFRASTRUCTURE CHECKS (Module 3.7)
# ---------------------------------------------------------------------------

def check_sandbox_health(runner: VerificationRunner, sandbox_url: str):
    """Check sandbox service health endpoint."""
    import httpx

    t0 = time.monotonic()
    try:
        resp = httpx.get(f"{sandbox_url}/health", timeout=10.0)
        dur = (time.monotonic() - t0) * 1000
        data = resp.json()
        runner.check(
            "Sandbox /health",
            resp.status_code == 200 and data.get("docker_available", False),
            f"status={data.get('status')}, docker={data.get('docker_available')}",
            duration_ms=dur,
            response=data,
        )
    except Exception as e:
        dur = (time.monotonic() - t0) * 1000
        runner.check("Sandbox /health", False, str(e), duration_ms=dur)


def check_sandbox_basic_execution(runner: VerificationRunner, sandbox_url: str):
    """Run a simple Python script in sandbox (no postgres)."""
    import httpx

    payload = {
        "language": "python",
        "code_files": [{"path": "hello.py", "content": "print('Hello from sandbox!')"}],
        "commands": ["python hello.py"],
        "timeout": 30,
    }

    t0 = time.monotonic()
    try:
        resp = httpx.post(f"{sandbox_url}/execute", json=payload, timeout=60.0)
        dur = (time.monotonic() - t0) * 1000
        data = resp.json()
        ok = data.get("exit_code") == 0 and "Hello from sandbox!" in data.get("stdout", "")
        runner.check(
            "Basic sandbox execution",
            ok,
            f"exit_code={data.get('exit_code')}, stdout={data.get('stdout', '')[:100]}",
            duration_ms=dur,
        )
    except Exception as e:
        dur = (time.monotonic() - t0) * 1000
        runner.check("Basic sandbox execution", False, str(e), duration_ms=dur)


def check_sandbox_postgres_connectivity(runner: VerificationRunner, sandbox_url: str):
    """Run Python code with enable_postgres=True that connects to PostgreSQL."""
    import httpx

    # This code will be executed INSIDE the sandbox container.
    # It uses DATABASE_URL injected by the executor when enable_postgres=True.
    test_code = """
import os
import sys
import json

results = {"steps": [], "success": False}

# 1. Check DATABASE_URL is set
db_url = os.environ.get("DATABASE_URL", "")
results["steps"].append({
    "name": "DATABASE_URL present",
    "ok": bool(db_url),
    "value": db_url[:50] + "..." if len(db_url) > 50 else db_url
})

# 2. Check PG* env vars
for var in ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"]:
    val = os.environ.get(var, "")
    results["steps"].append({
        "name": f"{var} present",
        "ok": bool(val),
        "value": val if var != "PGPASSWORD" else "***"
    })

# 3. Try to connect via psycopg2
try:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary", "-q"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import psycopg2
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Create test table
    cur.execute("DROP TABLE IF EXISTS _verify_sandbox_test")
    cur.execute(\"\"\"
        CREATE TABLE _verify_sandbox_test (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    \"\"\")
    conn.commit()
    results["steps"].append({"name": "CREATE TABLE", "ok": True})

    # Insert
    cur.execute("INSERT INTO _verify_sandbox_test (name) VALUES (%s) RETURNING id", ("test_row",))
    row_id = cur.fetchone()[0]
    conn.commit()
    results["steps"].append({"name": "INSERT", "ok": True, "row_id": row_id})

    # Select
    cur.execute("SELECT id, name FROM _verify_sandbox_test WHERE id = %s", (row_id,))
    row = cur.fetchone()
    results["steps"].append({"name": "SELECT", "ok": row is not None and row[1] == "test_row"})

    # Cleanup
    cur.execute("DROP TABLE _verify_sandbox_test")
    conn.commit()
    results["steps"].append({"name": "DROP TABLE (cleanup)", "ok": True})

    cur.close()
    conn.close()
    results["steps"].append({"name": "Connection close", "ok": True})
    results["success"] = True

except Exception as e:
    results["steps"].append({"name": "PostgreSQL connection", "ok": False, "error": str(e)})

print("VERIFY_RESULT:" + json.dumps(results))
"""

    payload = {
        "language": "python",
        "code_files": [{"path": "pg_test.py", "content": test_code}],
        "commands": ["python pg_test.py"],
        "timeout": 60,
        "enable_postgres": True,
    }

    t0 = time.monotonic()
    try:
        resp = httpx.post(f"{sandbox_url}/execute", json=payload, timeout=120.0)
        dur = (time.monotonic() - t0) * 1000
        data = resp.json()

        stdout = data.get("stdout", "")
        # Parse structured result
        verify_result = None
        for line in stdout.split("\n"):
            if line.startswith("VERIFY_RESULT:"):
                verify_result = json.loads(line[len("VERIFY_RESULT:"):])
                break

        if verify_result:
            all_ok = verify_result.get("success", False)
            steps = verify_result.get("steps", [])

            # Report each step
            for step in steps:
                runner.check(
                    f"PG: {step['name']}",
                    step.get("ok", False),
                    step.get("error", "") or step.get("value", "ok"),
                    duration_ms=0,
                )

            runner.check(
                "PostgreSQL E2E (overall)",
                all_ok,
                "All PostgreSQL operations succeeded" if all_ok else "Some steps failed",
                duration_ms=dur,
            )
        else:
            runner.check(
                "PostgreSQL E2E (overall)",
                False,
                f"Could not parse result. exit_code={data.get('exit_code')}, stderr={data.get('stderr', '')[:300]}",
                duration_ms=dur,
            )

    except Exception as e:
        dur = (time.monotonic() - t0) * 1000
        runner.check("PostgreSQL E2E (overall)", False, str(e), duration_ms=dur)


def check_sandbox_network_always_on(runner: VerificationRunner, sandbox_url: str):
    """Verify that sandbox containers always have network access (can reach sandbox-postgres)."""
    import httpx

    test_code = """
import socket
import json

result = {"network_available": False}
try:
    addr = socket.gethostbyname("sandbox-postgres")
    result["network_available"] = True
    result["resolved_to"] = addr
except Exception as e:
    result["error"] = str(e)[:200]

print("VERIFY_RESULT:" + json.dumps(result))
"""

    # No explicit enable_network — network should be on by default
    payload = {
        "language": "python",
        "code_files": [{"path": "net_test.py", "content": test_code}],
        "commands": ["python net_test.py"],
        "timeout": 20,
    }

    t0 = time.monotonic()
    try:
        resp = httpx.post(f"{sandbox_url}/execute", json=payload, timeout=60.0)
        dur = (time.monotonic() - t0) * 1000
        data = resp.json()
        stdout = data.get("stdout", "")

        verify_result = None
        for line in stdout.split("\n"):
            if line.startswith("VERIFY_RESULT:"):
                verify_result = json.loads(line[len("VERIFY_RESULT:"):])
                break

        if verify_result:
            avail = verify_result.get("network_available", False)
            runner.check(
                "Network always on (sandbox-postgres reachable)",
                avail,
                f"Resolved sandbox-postgres to {verify_result.get('resolved_to', '?')}" if avail else verify_result.get("error", "failed"),
                duration_ms=dur,
            )
        else:
            runner.check(
                "Network always on",
                False,
                f"Could not parse result. exit_code={data.get('exit_code')}",
                duration_ms=dur,
            )
    except Exception as e:
        dur = (time.monotonic() - t0) * 1000
        runner.check("Network always on", False, str(e), duration_ms=dur)


# ---------------------------------------------------------------------------
# 2. CI/CD INTEGRATION CHECKS (Module 3.8)
# ---------------------------------------------------------------------------

def check_ci_graph_routing(runner: VerificationRunner):
    """Verify route_after_ci logic with various states."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphs"))

    try:
        from dev_team.graph import route_after_ci

        test_cases = [
            ({"ci_status": "success"}, "pm_final"),
            ({"ci_status": "failure"}, "developer"),
            ({"ci_status": "error"}, "developer"),
            ({"ci_status": "timeout"}, "developer"),
            ({"ci_status": "cancelled"}, "developer"),
            ({"ci_status": "skipped"}, "pm_final"),
            ({"ci_status": "not_found"}, "pm_final"),
            ({}, "pm_final"),  # no ci_status -> empty string -> developer? Actually...
        ]

        all_ok = True
        for state, expected in test_cases:
            actual = route_after_ci(state)
            ok = actual == expected
            if not ok:
                all_ok = False
                runner.check(
                    f"route_after_ci({state})",
                    False,
                    f"Expected '{expected}', got '{actual}'",
                )

        if all_ok:
            runner.check(
                "route_after_ci (all cases)",
                True,
                f"All {len(test_cases)} routing cases correct",
            )

    except Exception as e:
        runner.check("route_after_ci", False, str(e))


def check_ci_check_node_skip(runner: VerificationRunner):
    """Verify ci_check_node skips when no repo/branch in state."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphs"))

    try:
        from dev_team.graph import ci_check_node

        # No repo/branch -> should return skipped
        result = ci_check_node({})
        ok = result.get("ci_status") == "skipped"
        runner.check(
            "ci_check_node (no repo/branch -> skip)",
            ok,
            f"ci_status={result.get('ci_status')}, ci_log={result.get('ci_log', '')[:100]}",
        )

    except Exception as e:
        runner.check("ci_check_node (skip)", False, str(e))


def check_ci_graph_structure_without_ci(runner: VerificationRunner):
    """Verify graph structure when USE_CI_INTEGRATION=false."""
    # We check that the compiled graph has certain nodes
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphs"))

    try:
        # Current module-level graph is compiled with current env
        # USE_CI_INTEGRATION defaults to "false"
        from dev_team import graph as graph_module

        use_ci = os.getenv("USE_CI_INTEGRATION", "false").lower() in ("true", "1", "yes")

        compiled_graph = graph_module.graph
        node_names = set(compiled_graph.nodes.keys()) if hasattr(compiled_graph, 'nodes') else set()

        if not use_ci:
            has_ci = "ci_check" in node_names
            runner.check(
                "Graph structure (CI disabled)",
                not has_ci,
                "ci_check node correctly absent" if not has_ci else "ci_check should NOT be in graph!",
                nodes=sorted(node_names),
            )
        else:
            has_ci = "ci_check" in node_names
            runner.check(
                "Graph structure (CI enabled)",
                has_ci,
                "ci_check node correctly present" if has_ci else "ci_check MISSING from graph!",
                nodes=sorted(node_names),
            )

    except Exception as e:
        runner.check("Graph structure", False, str(e))


def check_ci_client_import(runner: VerificationRunner):
    """Verify GitHubActionsClient can be imported."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphs"))

    try:
        from dev_team.tools.github_actions import GitHubActionsClient, github_actions_tools
        runner.check(
            "GitHubActionsClient import",
            True,
            f"Imported successfully. Tools: {[t.name for t in github_actions_tools]}",
        )
    except Exception as e:
        runner.check("GitHubActionsClient import", False, str(e))


def check_ci_state_fields(runner: VerificationRunner):
    """Verify CI fields exist in DevTeamState."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphs"))

    try:
        from dev_team.state import DevTeamState
        import typing

        hints = typing.get_type_hints(DevTeamState, include_extras=True)
        ci_fields = ["ci_status", "ci_log", "ci_run_id", "ci_run_url"]

        missing = [f for f in ci_fields if f not in hints]
        ok = len(missing) == 0
        runner.check(
            "DevTeamState CI fields",
            ok,
            "All CI fields present" if ok else f"Missing: {missing}",
            fields=ci_fields,
        )
    except Exception as e:
        runner.check("DevTeamState CI fields", False, str(e))


def check_ci_developer_prompt(runner: VerificationRunner):
    """Verify developer.yaml has fix_ci prompt with placeholders."""
    import yaml

    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "graphs", "dev_team", "prompts", "developer.yaml"
    )

    try:
        with open(prompt_path) as f:
            prompts = yaml.safe_load(f)

        has_fix_ci = "fix_ci" in prompts
        fix_ci = prompts.get("fix_ci", "")
        has_ci_status = "{ci_status}" in fix_ci
        has_ci_log = "{ci_log}" in fix_ci

        runner.check(
            "developer.yaml: fix_ci prompt",
            has_fix_ci and has_ci_status and has_ci_log,
            f"fix_ci={'present' if has_fix_ci else 'MISSING'}, "
            f"{{ci_status}}={'found' if has_ci_status else 'MISSING'}, "
            f"{{ci_log}}={'found' if has_ci_log else 'MISSING'}",
        )

        # Also check system prompt mentions CI
        system_prompt = prompts.get("system", "")
        mentions_ci = "ci" in system_prompt.lower() or "CI/CD" in system_prompt
        runner.check(
            "developer.yaml: system mentions CI",
            mentions_ci,
            "System prompt references CI/CD" if mentions_ci else "No CI mention in system prompt",
        )

    except Exception as e:
        runner.check("developer.yaml prompts", False, str(e))


def check_ci_manifest(runner: VerificationRunner):
    """Verify manifest.yaml declares ci_integration feature."""
    import yaml

    manifest_path = os.path.join(
        os.path.dirname(__file__), "..", "graphs", "dev_team", "manifest.yaml"
    )

    try:
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        features = manifest.get("features", [])
        has_feature = "ci_integration" in features
        runner.check(
            "manifest.yaml: ci_integration feature",
            has_feature,
            "Feature declared" if has_feature else "MISSING from features list",
        )

        params = manifest.get("parameters", {})
        has_param = "use_ci_integration" in params
        runner.check(
            "manifest.yaml: use_ci_integration param",
            has_param,
            f"Value: {params.get('use_ci_integration')}" if has_param else "MISSING",
        )

    except Exception as e:
        runner.check("manifest.yaml", False, str(e))


def check_ci_github_live(runner: VerificationRunner, repo: str, branch: str):
    """Live check: query GitHub Actions API for a real repo/branch."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphs"))

    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        runner.check("GitHub Actions live check", False, "GITHUB_TOKEN not set, skipping")
        return

    try:
        from dev_team.tools.github_actions import GitHubActionsClient

        t0 = time.monotonic()
        client = GitHubActionsClient(token=token)
        result = client.get_latest_workflow_run(repo, branch)
        dur = (time.monotonic() - t0) * 1000

        run_id = result.get("run_id")
        if run_id:
            runner.check(
                f"GitHub Actions: latest run for {repo}@{branch}",
                True,
                f"run_id={run_id}, status={result.get('status')}, conclusion={result.get('conclusion')}",
                duration_ms=dur,
            )
        else:
            runner.check(
                f"GitHub Actions: latest run for {repo}@{branch}",
                True,  # Not a failure — just no runs
                "No workflow runs found (this is OK if no CI configured)",
                duration_ms=dur,
            )

    except Exception as e:
        runner.check("GitHub Actions live check", False, str(e))


# ---------------------------------------------------------------------------
# 3. DOCKER COMPOSE CHECKS
# ---------------------------------------------------------------------------

def check_docker_compose_services(runner: VerificationRunner):
    """Verify required services are defined in docker-compose.yml."""
    import yaml

    compose_path = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")

    try:
        with open(compose_path) as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})

        # Check sandbox-postgres
        has_sp = "sandbox-postgres" in services
        runner.check(
            "docker-compose: sandbox-postgres service",
            has_sp,
            "Service defined" if has_sp else "MISSING",
        )

        if has_sp:
            sp = services["sandbox-postgres"]
            has_hc = "healthcheck" in sp
            runner.check(
                "docker-compose: sandbox-postgres healthcheck",
                has_hc,
                "Healthcheck configured" if has_hc else "No healthcheck!",
            )

            has_vol = any("sandbox_postgres_data" in str(v) for v in sp.get("volumes", []))
            runner.check(
                "docker-compose: sandbox-postgres volume",
                has_vol,
                "Persistent volume configured" if has_vol else "No persistent volume!",
            )

        # Check sandbox depends on sandbox-postgres
        sandbox = services.get("sandbox", {})
        deps = sandbox.get("depends_on", {})
        depends_on_pg = "sandbox-postgres" in deps
        runner.check(
            "docker-compose: sandbox depends_on sandbox-postgres",
            depends_on_pg,
            "Dependency configured" if depends_on_pg else "MISSING dependency!",
        )

        # Check sandbox env vars include PG config
        sandbox_env = sandbox.get("environment", {})
        pg_env_keys = ["SANDBOX_PG_HOST", "SANDBOX_PG_PORT", "SANDBOX_PG_USER",
                       "SANDBOX_PG_PASSWORD", "SANDBOX_PG_DB", "SANDBOX_NETWORK"]
        missing_env = [k for k in pg_env_keys if k not in sandbox_env]
        runner.check(
            "docker-compose: sandbox PG env vars",
            len(missing_env) == 0,
            "All PG env vars present" if not missing_env else f"Missing: {missing_env}",
        )

        # Check volumes section
        volumes = compose.get("volumes", {})
        has_sp_vol = "sandbox_postgres_data" in volumes
        runner.check(
            "docker-compose: sandbox_postgres_data volume",
            has_sp_vol,
            "Volume declared" if has_sp_vol else "MISSING from volumes section",
        )

    except Exception as e:
        runner.check("docker-compose.yml", False, str(e))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Verify Sandbox (3.7) and CI/CD (3.8) integration")
    parser.add_argument("--sandbox-url", default=os.getenv("SANDBOX_URL", "http://localhost:8002"),
                        help="Sandbox service URL")
    parser.add_argument("--no-docker", action="store_true",
                        help="Skip checks that require running Docker services")
    parser.add_argument("--only", choices=["sandbox", "ci", "compose"],
                        help="Run only a specific group of checks")
    parser.add_argument("--github-repo", default="",
                        help="GitHub repo (owner/name) for live CI check")
    parser.add_argument("--github-branch", default="main",
                        help="Branch for live CI check")
    args = parser.parse_args()

    runner = VerificationRunner()

    print()
    print("AI-crew Sandbox & CI/CD Verification")
    print(f"Sandbox URL: {args.sandbox_url}")
    print(f"Docker checks: {'disabled' if args.no_docker else 'enabled'}")
    if args.only:
        print(f"Running only: {args.only}")

    # --- Docker Compose checks ---
    if args.only in (None, "compose"):
        runner.section("Docker Compose Configuration")
        check_docker_compose_services(runner)

    # --- Sandbox Infrastructure (Module 3.7) ---
    if args.only in (None, "sandbox"):
        runner.section("Sandbox Infrastructure (Module 3.7)")

        if not args.no_docker:
            check_sandbox_health(runner, args.sandbox_url)
            check_sandbox_basic_execution(runner, args.sandbox_url)
            check_sandbox_network_always_on(runner, args.sandbox_url)
            check_sandbox_postgres_connectivity(runner, args.sandbox_url)
        else:
            print("  (skipped — --no-docker)")

    # --- CI/CD Integration (Module 3.8) ---
    if args.only in (None, "ci"):
        runner.section("CI/CD Integration (Module 3.8) — Static Checks")
        check_ci_client_import(runner)
        check_ci_state_fields(runner)
        check_ci_developer_prompt(runner)
        check_ci_manifest(runner)
        check_ci_graph_routing(runner)
        check_ci_check_node_skip(runner)
        check_ci_graph_structure_without_ci(runner)

        if args.github_repo:
            runner.section("CI/CD Integration — Live GitHub Check")
            check_ci_github_live(runner, args.github_repo, args.github_branch)

    # --- Summary ---
    all_passed = runner.summary()

    # Write JSON report
    report_path = os.path.join(os.path.dirname(__file__), "..", "verify_report.json")
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sandbox_url": args.sandbox_url,
        "docker_checks": not args.no_docker,
        "total": len(runner.results),
        "passed": sum(1 for r in runner.results if r.passed),
        "failed": sum(1 for r in runner.results if not r.passed),
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "duration_ms": r.duration_ms,
                "details": {k: str(v)[:500] for k, v in r.details.items()},
            }
            for r in runner.results
        ],
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Report saved: {report_path}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
