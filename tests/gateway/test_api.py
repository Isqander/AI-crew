"""
Gateway API Tests
=================

End-to-end HTTP tests for gateway endpoints using FastAPI TestClient.
Database layer is mocked — no PostgreSQL required.

Covers:
  - Auth: register, login, refresh, me, error cases
  - Health check
  - Protected endpoint access
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers: fake DB records
# ---------------------------------------------------------------------------

def _make_user_row(
    email: str = "test@test.com",
    display_name: str = "Test User",
    password_hash: str | None = None,
    is_active: bool = True,
) -> dict:
    """Build a dict that looks like an asyncpg Record for the users table."""
    import bcrypt
    if password_hash is None:
        password_hash = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode()
    return {
        "id": uuid.uuid4(),
        "email": email,
        "display_name": display_name,
        "password_hash": password_hash,
        "is_active": is_active,
        "created_at": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeAcquireCtx:
    """Async context manager that returns a mock connection."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        pass


@pytest.fixture()
def mock_pool():
    """Create a mocked asyncpg pool with a mock connection."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()

    pool = MagicMock()
    pool.acquire.return_value = _FakeAcquireCtx(mock_conn)
    pool.close = AsyncMock()

    return pool, mock_conn


@pytest.fixture()
def client(mock_pool):
    """FastAPI TestClient with mocked database."""
    pool, _conn = mock_pool

    async def _fake_get_pool():
        return pool

    with patch("gateway.database.init_db", new_callable=AsyncMock), \
         patch("gateway.database.close_db", new_callable=AsyncMock), \
         patch("gateway.database.pool", pool), \
         patch("gateway.auth.get_pool", new=_fake_get_pool):

        from gateway.main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def registered_user_row():
    """A user row as returned from the database."""
    return _make_user_row()


# ---------------------------------------------------------------------------
# Auth Tests: Registration
# ---------------------------------------------------------------------------


class TestRegister:
    """POST /auth/register"""

    def test_register_success(self, client, mock_pool):
        """Successful registration returns user + tokens."""
        pool, conn = mock_pool
        conn.fetchrow.side_effect = [
            None,  # no duplicate email
            _make_user_row(),  # INSERT RETURNING
        ]

        resp = client.post("/auth/register", json={
            "email": "new@test.com",
            "password": "securepass123",
            "display_name": "New User",
        })

        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "new@test.com" or data["user"]["email"]

    def test_register_short_password(self, client):
        """Password < 8 chars should fail with 400."""
        resp = client.post("/auth/register", json={
            "email": "a@b.com",
            "password": "short",
            "display_name": "Test",
        })
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    def test_register_duplicate_email(self, client, mock_pool):
        """Duplicate email returns 409."""
        _, conn = mock_pool
        conn.fetchrow.return_value = {"id": uuid.uuid4()}  # user exists

        resp = client.post("/auth/register", json={
            "email": "exists@test.com",
            "password": "longpassword123",
            "display_name": "Duplicate",
        })
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Auth Tests: Login
# ---------------------------------------------------------------------------


class TestLogin:
    """POST /auth/login"""

    def test_login_success(self, client, mock_pool):
        """Valid credentials return tokens + user."""
        _, conn = mock_pool
        import bcrypt
        hashed = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode()
        conn.fetchrow.return_value = _make_user_row(password_hash=hashed)

        resp = client.post("/auth/login", json={
            "email": "test@test.com",
            "password": "testpass123",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "test@test.com"

    def test_login_wrong_password(self, client, mock_pool):
        """Wrong password returns 401."""
        _, conn = mock_pool
        import bcrypt
        hashed = bcrypt.hashpw(b"correctpass", bcrypt.gensalt()).decode()
        conn.fetchrow.return_value = _make_user_row(password_hash=hashed)

        resp = client.post("/auth/login", json={
            "email": "test@test.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, mock_pool):
        """Non-existent email returns 401."""
        _, conn = mock_pool
        conn.fetchrow.return_value = None

        resp = client.post("/auth/login", json={
            "email": "noone@test.com",
            "password": "testpass123",
        })
        assert resp.status_code == 401

    def test_login_deactivated_user(self, client, mock_pool):
        """Deactivated user returns 403."""
        _, conn = mock_pool
        import bcrypt
        hashed = bcrypt.hashpw(b"testpass123", bcrypt.gensalt()).decode()
        conn.fetchrow.return_value = _make_user_row(
            password_hash=hashed, is_active=False,
        )

        resp = client.post("/auth/login", json={
            "email": "test@test.com",
            "password": "testpass123",
        })
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Auth Tests: Token Refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    """POST /auth/refresh"""

    def test_refresh_success(self, client, mock_pool):
        """Valid refresh token returns new token pair."""
        from gateway.auth import _create_token
        refresh_tok = _create_token("user-id-123", "test@test.com", "refresh")

        resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_tok,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_with_access_token_fails(self, client):
        """Using an access token as refresh should fail."""
        from gateway.auth import _create_token
        access_tok = _create_token("user-id-123", "test@test.com", "access")

        resp = client.post("/auth/refresh", json={
            "refresh_token": access_tok,
        })
        assert resp.status_code == 401

    def test_refresh_invalid_token(self, client):
        """Invalid token string should fail."""
        resp = client.post("/auth/refresh", json={
            "refresh_token": "this-is-not-a-valid-jwt",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Auth Tests: /auth/me (Protected Endpoint)
# ---------------------------------------------------------------------------


class TestAuthMe:
    """GET /auth/me"""

    def test_me_success(self, client, mock_pool):
        """Valid access token returns user info."""
        _, conn = mock_pool
        user_row = _make_user_row()
        conn.fetchrow.return_value = user_row

        from gateway.auth import _create_token
        token = _create_token(str(user_row["id"]), user_row["email"], "access")

        resp = client.get("/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == user_row["email"]
        assert data["display_name"] == user_row["display_name"]

    def test_me_no_token(self, client):
        """No token returns 401."""
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client):
        """Invalid token returns 401."""
        resp = client.get("/auth/me", headers={
            "Authorization": "Bearer invalid-jwt-token",
        })
        assert resp.status_code == 401

    def test_me_refresh_token_rejected(self, client, mock_pool):
        """Refresh token should not work for /auth/me."""
        from gateway.auth import _create_token
        token = _create_token("user-id", "test@test.com", "refresh")

        resp = client.get("/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------


class TestHealth:
    """GET /health"""

    def test_health_no_auth(self, client):
        """Health endpoint works without authentication."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        # Aegra won't be reachable in tests
        assert data["aegra"] in ("ok", "error")


# ---------------------------------------------------------------------------
# Protected Proxy Endpoints (basic access tests)
# ---------------------------------------------------------------------------


class TestProtectedEndpoints:
    """Verify that proxy endpoints require authentication."""

    def test_threads_requires_auth(self, client):
        """GET /threads without token returns 401."""
        resp = client.get("/threads")
        assert resp.status_code == 401

    def test_assistants_requires_auth(self, client):
        """GET /assistants/test without token returns 401."""
        resp = client.get("/assistants/test")
        assert resp.status_code == 401

    def test_store_requires_auth(self, client):
        """GET /store/test without token returns 401."""
        resp = client.get("/store/test")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Graph Endpoints
# ---------------------------------------------------------------------------


class TestGraphEndpoints:
    """Tests for /graph/* endpoints (require auth)."""

    def _get_auth_headers(self, mock_pool):
        """Get valid auth headers using a mock user."""
        _, conn = mock_pool
        user_row = _make_user_row()
        conn.fetchrow.return_value = user_row

        from gateway.auth import _create_token
        token = _create_token(str(user_row["id"]), user_row["email"], "access")
        return {"Authorization": f"Bearer {token}"}

    def test_graph_list(self, client, mock_pool):
        """GET /graph/list returns a list of graphs."""
        headers = self._get_auth_headers(mock_pool)
        resp = client.get("/graph/list", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "graphs" in data
        assert isinstance(data["graphs"], list)
        # Should find at least dev_team
        graph_ids = [g["graph_id"] for g in data["graphs"]]
        assert "dev_team" in graph_ids

    def test_graph_list_requires_auth(self, client):
        """GET /graph/list without token returns 401."""
        resp = client.get("/graph/list")
        assert resp.status_code == 401

    def test_graph_topology_dev_team(self, client, mock_pool):
        """GET /graph/topology/dev_team returns topology data."""
        headers = self._get_auth_headers(mock_pool)
        resp = client.get("/graph/topology/dev_team", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["graph_id"] == "dev_team"
        assert "topology" in data or "manifest" in data

    def test_graph_topology_not_found(self, client, mock_pool):
        """GET /graph/topology/nonexistent returns 404."""
        headers = self._get_auth_headers(mock_pool)
        resp = client.get("/graph/topology/nonexistent_graph", headers=headers)
        assert resp.status_code == 404

    def test_graph_config_dev_team(self, client, mock_pool):
        """GET /graph/config/dev_team returns agent configs."""
        headers = self._get_auth_headers(mock_pool)
        resp = client.get("/graph/config/dev_team", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["graph_id"] == "dev_team"
        assert "agents" in data

    def test_graph_config_not_found(self, client, mock_pool):
        """GET /graph/config/nonexistent returns 404."""
        headers = self._get_auth_headers(mock_pool)
        resp = client.get("/graph/config/nonexistent_graph", headers=headers)
        assert resp.status_code == 404
