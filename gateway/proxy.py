"""
Aegra Proxy
===========

Transparent reverse-proxy from Gateway to Aegra for all Agent-Protocol
endpoints (threads, runs, assistants, store).

Two modes:
  * ``proxy_to_aegra``         — regular REST (request → response)
  * ``proxy_stream_to_aegra``  — SSE streaming (``text/event-stream``)
"""

from __future__ import annotations

import time

import structlog
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from gateway.config import settings

logger = structlog.get_logger()

# Long timeout for LLM streaming calls
_CLIENT_TIMEOUT = httpx.Timeout(timeout=600.0, connect=30.0)


def _aegra_url(path: str) -> str:
    """Build full Aegra URL from a request path."""
    return f"{settings.aegra_url}{path}"


async def proxy_to_aegra(request: Request) -> JSONResponse:
    """Proxy a regular REST request to Aegra and return the JSON response."""
    path = request.url.path
    method = request.method
    body = await request.body()
    params = dict(request.query_params)
    body_len = len(body) if body else 0

    logger.info("proxy.request", method=method, path=path, body_bytes=body_len,
                params=params if params else None)

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT) as client:
        try:
            resp = await client.request(
                method=method,
                url=_aegra_url(path),
                content=body,
                params=params,
                headers={"Content-Type": "application/json"},
            )
        except httpx.ConnectError as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error("proxy.connect_error", path=path, error=str(exc),
                         elapsed_ms=round(elapsed_ms))
            return JSONResponse({"error": "Aegra unavailable"}, status_code=502)
        except httpx.ReadTimeout as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error("proxy.read_timeout", path=path, error=str(exc),
                         elapsed_ms=round(elapsed_ms))
            return JSONResponse({"error": "Aegra timeout"}, status_code=504)

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info("proxy.response", path=path, status=resp.status_code,
                elapsed_ms=round(elapsed_ms),
                response_bytes=len(resp.content) if resp.content else 0)

    # Log errors from Aegra at warning level
    if resp.status_code >= 400:
        try:
            error_body = resp.json()
        except Exception:
            error_body = resp.text[:500]
        logger.warning("proxy.aegra_error", path=path, status=resp.status_code,
                       error=error_body)

    return JSONResponse(content=resp.json(), status_code=resp.status_code)


async def proxy_stream_to_aegra(request: Request) -> StreamingResponse:
    """Proxy an SSE streaming request to Aegra.

    Chunks are forwarded as-is to the client.
    """
    path = request.url.path
    body = await request.body()

    logger.info("proxy.stream_start", path=path, body_bytes=len(body) if body else 0)

    client = httpx.AsyncClient(timeout=_CLIENT_TIMEOUT)

    async def _stream():
        t0 = time.monotonic()
        chunks_count = 0
        total_bytes = 0
        try:
            async with client.stream(
                "POST",
                _aegra_url(path),
                content=body,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status_code >= 400:
                    logger.warning("proxy.stream_aegra_error", path=path,
                                   status=resp.status_code)
                async for chunk in resp.aiter_bytes():
                    chunks_count += 1
                    total_bytes += len(chunk)
                    yield chunk
        except httpx.ConnectError as exc:
            logger.error("proxy.stream_error", path=path, error=str(exc))
            yield f"data: {{\"error\": \"Aegra unavailable: {exc}\"}}\n\n".encode()
        except httpx.ReadTimeout as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error("proxy.stream_timeout", path=path, error=str(exc),
                         elapsed_ms=round(elapsed_ms))
            yield f"data: {{\"error\": \"Aegra timeout: {exc}\"}}\n\n".encode()
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            await client.aclose()
            logger.info("proxy.stream_end", path=path, chunks=chunks_count,
                        total_bytes=total_bytes, elapsed_ms=round(elapsed_ms))

    return StreamingResponse(_stream(), media_type="text/event-stream")
