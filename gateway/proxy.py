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

    logger.debug("proxy.request", method=method, path=path)

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
            logger.error("proxy.connect_error", path=path, error=str(exc))
            return JSONResponse({"error": "Aegra unavailable"}, status_code=502)

    logger.debug("proxy.response", path=path, status=resp.status_code)
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


async def proxy_stream_to_aegra(request: Request) -> StreamingResponse:
    """Proxy an SSE streaming request to Aegra.

    Chunks are forwarded as-is to the client.
    """
    path = request.url.path
    body = await request.body()

    logger.debug("proxy.stream_start", path=path)

    client = httpx.AsyncClient(timeout=_CLIENT_TIMEOUT)

    async def _stream():
        try:
            async with client.stream(
                "POST",
                _aegra_url(path),
                content=body,
                headers={"Content-Type": "application/json"},
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.ConnectError as exc:
            logger.error("proxy.stream_error", path=path, error=str(exc))
            yield f"data: {{\"error\": \"Aegra unavailable: {exc}\"}}\n\n".encode()
        finally:
            await client.aclose()
            logger.debug("proxy.stream_end", path=path)

    return StreamingResponse(_stream(), media_type="text/event-stream")
