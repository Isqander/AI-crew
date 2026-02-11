"""
Gateway Authentication
======================

JWT-based authentication: register, login, refresh, and dependency for
protected endpoints.

Passwords are hashed with ``bcrypt``.  Tokens are signed with HS256.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from gateway.config import settings
from gateway.database import get_pool
from gateway.models import (
    AuthResponse,
    RefreshRequest,
    TokenPair,
    User,
    UserCreate,
    UserLogin,
)

logger = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ────────────────────── Password helpers ──────────────────────


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ────────────────────── JWT helpers ───────────────────────────


def _create_token(user_id: str, email: str, token_type: str = "access") -> str:
    ttl = settings.jwt_access_ttl if token_type == "access" else settings.jwt_refresh_ttl
    payload = {
        "sub": user_id,
        "email": email,
        "type": token_type,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT.  Raises ``HTTPException`` on failure."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ────────────────────── Public API ────────────────────────────


async def register(data: UserCreate) -> AuthResponse:
    """Register a new user.  Returns JWT pair + user object."""
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check duplicate
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", data.email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        row = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, display_name)
            VALUES ($1, $2, $3)
            RETURNING id, email, display_name, is_active, created_at
            """,
            data.email,
            _hash_password(data.password),
            data.display_name,
        )

    user = User(
        id=str(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )
    logger.info("auth.register", user_id=user.id, email=user.email)
    return AuthResponse(
        user=user,
        access_token=_create_token(user.id, user.email, "access"),
        refresh_token=_create_token(user.id, user.email, "refresh"),
    )


async def login(data: UserLogin) -> AuthResponse:
    """Authenticate user by email + password."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password_hash, display_name, is_active, created_at FROM users WHERE email = $1",
            data.email,
        )

    if not row or not _verify_password(data.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    user = User(
        id=str(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )
    logger.info("auth.login", user_id=user.id)
    return AuthResponse(
        user=user,
        access_token=_create_token(user.id, user.email, "access"),
        refresh_token=_create_token(user.id, user.email, "refresh"),
    )


async def refresh_token(data: RefreshRequest) -> TokenPair:
    """Issue a new token pair from a valid refresh token."""
    payload = _decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user_id = payload["sub"]
    email = payload["email"]
    logger.info("auth.refresh", user_id=user_id)
    return TokenPair(
        access_token=_create_token(user_id, email, "access"),
        refresh_token=_create_token(user_id, email, "refresh"),
    )


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> User:
    """FastAPI dependency — extract and validate the current user from JWT."""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = _decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, is_active, created_at FROM users WHERE id = $1::uuid",
            payload["sub"],
        )

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return User(
        id=str(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )
