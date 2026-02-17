"""
Deploy Pipeline Helpers
=======================

Utility functions used by the deploy graph nodes:
  - ``verify_deploy_health``  — HTTP health check against the deployed app
  - ``wait_for_deploy_ci``    — wait for GitHub Actions CI+deploy to complete

These are *platform-level* helpers (no LLM calls, no token spend).
"""

from __future__ import annotations

import time

import httpx
import structlog

logger = structlog.get_logger()


def verify_deploy_health(
    deploy_url: str,
    *,
    max_retries: int = 8,
    initial_delay: float = 10.0,
    backoff_factor: float = 1.5,
    timeout: float = 10.0,
) -> dict:
    """Check that a deployed application is reachable.

    Tries the deploy URL with exponential backoff to give the
    application time to start up after GitHub Actions deploys it.

    Args:
        deploy_url: Full URL (e.g. ``https://todo-app.deploy.mysite.ru``)
        max_retries: Maximum number of health-check attempts.
        initial_delay: Seconds before the first check.
        backoff_factor: Multiplier for subsequent waits.
        timeout: HTTP request timeout in seconds.

    Returns:
        Dict with keys ``healthy`` (bool), ``status_code`` (int | None),
        ``attempts`` (int), ``url`` (str), ``error`` (str | None).
    """
    if not deploy_url:
        return {
            "healthy": False,
            "status_code": None,
            "attempts": 0,
            "url": deploy_url,
            "error": "No deploy URL provided",
        }

    # Try common health-check paths
    health_paths = ["/health", "/api/health", "/healthz", "/"]

    delay = initial_delay
    last_error: str | None = None
    last_status: int | None = None

    for attempt in range(1, max_retries + 1):
        logger.info("deploy_health.attempt",
                     attempt=attempt, max=max_retries,
                     url=deploy_url, delay=round(delay, 1))
        time.sleep(delay)

        for path in health_paths:
            url = deploy_url.rstrip("/") + path
            try:
                with httpx.Client(
                    timeout=timeout,
                    verify=False,  # nip.io certs may not be ready yet
                    follow_redirects=True,
                ) as client:
                    resp = client.get(url)

                last_status = resp.status_code
                if resp.status_code < 500:
                    logger.info("deploy_health.success",
                                url=url, status=resp.status_code,
                                attempt=attempt)
                    return {
                        "healthy": True,
                        "status_code": resp.status_code,
                        "attempts": attempt,
                        "url": url,
                        "error": None,
                    }
            except httpx.ConnectError as exc:
                last_error = f"Connection refused: {exc}"
            except httpx.TimeoutException:
                last_error = f"Timeout after {timeout}s"
            except Exception as exc:
                last_error = str(exc)[:200]

        delay = min(delay * backoff_factor, 60.0)

    logger.warning("deploy_health.failed",
                    url=deploy_url, attempts=max_retries,
                    last_status=last_status, last_error=last_error)

    return {
        "healthy": False,
        "status_code": last_status,
        "attempts": max_retries,
        "url": deploy_url,
        "error": last_error,
    }
