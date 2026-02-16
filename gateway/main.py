"""
AI-crew Gateway
===============

FastAPI application — the single external API entry point.

Responsibilities:
  * JWT authentication (register / login / refresh / me)
  * Reverse-proxy to Aegra (REST + SSE streaming)
  * Own endpoints: graph list, topology, config, ``/api/run``
  * Health check
"""

from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Aegra graph modules use ``from dev_team.*`` imports (not ``graphs.dev_team.*``).
# Add ``graphs/`` to sys.path so these imports work when gateway loads
# graph topology via importlib.
_GRAPHS_DIR = str(Path(__file__).parent.parent / "graphs")
if _GRAPHS_DIR not in sys.path:
    sys.path.insert(0, _GRAPHS_DIR)

import httpx
import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gateway.auth import (
    get_current_user,
    login,
    refresh_token,
    register,
)
from gateway.config import settings
from gateway.database import close_db, init_db
from gateway.models import (
    AuthResponse,
    RefreshRequest,
    TokenPair,
    User,
    UserCreate,
    UserLogin,
)
from gateway.proxy import proxy_stream_to_aegra, proxy_to_aegra
from gateway.endpoints.graph import router as graph_router
from gateway.endpoints.run import router as run_router

logger = structlog.get_logger()


# ────────────────────── Lifespan ──────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("gateway.startup", aegra_url=settings.aegra_url,
                cors_origins=settings.cors_origins)
    await init_db()
    logger.info("gateway.db_ready")
    yield
    await close_db()
    logger.info("gateway.shutdown")


# ────────────────────── App ───────────────────────────────────

app = FastAPI(
    title="AI-crew Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sub-routers
app.include_router(graph_router)
app.include_router(run_router)


# ────────────────────── Request Logging Middleware ─────────────


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request with timing (skip /health for noise reduction)."""
    path = request.url.path
    # Skip health checks to reduce noise
    if path == "/health":
        return await call_next(request)

    method = request.method
    t0 = time.monotonic()
    logger.info("http.request", method=method, path=path,
                client=request.client.host if request.client else "unknown")

    response = await call_next(request)

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info("http.response", method=method, path=path,
                status=response.status_code, elapsed_ms=round(elapsed_ms))
    return response


# ────────────────────── Auth Endpoints ────────────────────────


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
async def route_register(data: UserCreate):
    return await register(data)


@app.post("/auth/login", response_model=AuthResponse)
async def route_login(data: UserLogin):
    return await login(data)


@app.post("/auth/refresh", response_model=TokenPair)
async def route_refresh(data: RefreshRequest):
    return await refresh_token(data)


@app.get("/auth/me", response_model=User)
async def route_me(user: User = Depends(get_current_user)):
    return user


# ────────────────────── Health ────────────────────────────────


@app.get("/health")
async def health():
    """Health check — no auth required."""
    aegra_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.aegra_url}/health")
            aegra_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok",
        "aegra": "ok" if aegra_ok else "error",
    }


# ────────────────────── Aegra Proxy ───────────────────────────


@app.api_route(
    "/threads",
    methods=["GET", "POST"],
)
async def proxy_threads_root(request: Request, _user: User = Depends(get_current_user)):
    """Handle bare /threads (no trailing slash) — avoids 307 redirect."""
    return await proxy_to_aegra(request)


@app.api_route(
    "/threads/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_threads(request: Request, _user: User = Depends(get_current_user)):
    # SSE streaming endpoint
    if request.url.path.endswith("/runs/stream"):
        return await proxy_stream_to_aegra(request)
    return await proxy_to_aegra(request)


@app.api_route(
    "/assistants/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_assistants(request: Request, _user: User = Depends(get_current_user)):
    return await proxy_to_aegra(request)


@app.api_route(
    "/store/{path:path}",
    methods=["GET", "POST", "PUT"],
)
async def proxy_store(request: Request, _user: User = Depends(get_current_user)):
    return await proxy_to_aegra(request)
