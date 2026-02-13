"""Gateway API client for Telegram Bot.

Handles authentication (register / login), automatic token refresh,
and proxied calls to the Gateway API.
"""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()


class GatewayClient:
    """Async HTTP client for the AI-crew Gateway."""

    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url.rstrip("/")
        self.token: str | None = None
        self._email: str | None = None
        self._password: str | None = None
        self.client = httpx.AsyncClient(timeout=300)

    # ────────────────── Auth ──────────────────

    async def ensure_authenticated(self, email: str, password: str) -> str:
        """Register (if needed) then login.  Stores credentials for re-auth."""
        self._email = email
        self._password = password

        # Try login first
        try:
            return await self.login(email, password)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 422):
                # 401 — wrong password / user doesn't exist
                # 422 — validation error (e.g. email format) — try register anyway
                logger.info(
                    "gateway.login_failed_trying_register",
                    email=email,
                    status=exc.response.status_code,
                )
            else:
                raise

        # User doesn't exist — register
        try:
            resp = await self.client.post(
                f"{self.gateway_url}/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "display_name": "Telegram Bot",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data["access_token"]
            logger.info("gateway.registered_bot_account", email=email)
            return self.token
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                # Email exists but password is wrong — re-try login
                logger.warning("gateway.register_conflict", email=email)
                return await self.login(email, password)
            raise

    async def login(self, email: str, password: str) -> str:
        """Login to Gateway and store the JWT token."""
        self._email = email
        self._password = password
        resp = await self.client.post(
            f"{self.gateway_url}/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        logger.info("gateway.login", email=email)
        return self.token

    async def _re_login(self) -> None:
        """Re-authenticate using stored credentials (token expired)."""
        if self._email and self._password:
            logger.info("gateway.re_login", email=self._email)
            try:
                await self.login(self._email, self._password)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 422:
                    # Validation error — try full re-registration flow
                    logger.warning(
                        "gateway.re_login_validation_error",
                        email=self._email,
                        status=exc.response.status_code,
                    )
                    await self.ensure_authenticated(self._email, self._password)
                else:
                    raise
        else:
            logger.error("gateway.re_login_no_credentials")

    # ────────────────── Helpers ──────────────────

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make a request with automatic re-login on 401."""
        url = f"{self.gateway_url}{path}"
        resp = await self.client.request(method, url, headers=self._headers(), **kwargs)

        if resp.status_code == 401 and self._email:
            # Token expired — re-login and retry
            await self._re_login()
            resp = await self.client.request(method, url, headers=self._headers(), **kwargs)

        resp.raise_for_status()
        return resp

    # ────────────────── API Methods ──────────────────

    async def get_graph_list(self) -> list[dict]:
        """Get available graphs via GET /graph/list."""
        resp = await self._request("GET", "/graph/list")
        data = resp.json()
        return data.get("graphs", [])

    async def create_run(self, task: str, **kwargs) -> dict:
        """Create a new task run via POST /api/run."""
        resp = await self._request(
            "POST", "/api/run",
            json={"task": task, **kwargs},
        )
        logger.info("gateway.run_created", task_len=len(task))
        return resp.json()

    async def get_thread_state(self, thread_id: str) -> dict:
        """Get current thread state."""
        resp = await self._request("GET", f"/threads/{thread_id}/state")
        return resp.json()

    async def send_clarification(self, thread_id: str, response_text: str) -> dict:
        """Send HITL clarification response."""
        resp = await self._request(
            "POST", f"/threads/{thread_id}/state",
            json={
                "values": {
                    "clarification_response": response_text,
                    "needs_clarification": False,
                },
                "command": {"update": True},
            },
        )
        logger.info("gateway.clarification_sent", thread_id=thread_id)
        return resp.json()

    async def close(self) -> None:
        await self.client.aclose()
