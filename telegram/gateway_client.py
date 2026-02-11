"""Gateway API client for Telegram Bot."""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()


class GatewayClient:
    """Async HTTP client for the AI-crew Gateway."""

    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url.rstrip("/")
        self.token: str | None = None
        self.client = httpx.AsyncClient(timeout=300)

    async def login(self, email: str, password: str) -> str:
        """Login to Gateway and store the JWT token."""
        resp = await self.client.post(
            f"{self.gateway_url}/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        logger.info("gateway.login", email=email)
        return self.token

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def create_run(self, task: str, **kwargs) -> dict:
        """Create a new task run via POST /api/run."""
        resp = await self.client.post(
            f"{self.gateway_url}/api/run",
            json={"task": task, **kwargs},
            headers=self._headers(),
        )
        resp.raise_for_status()
        logger.info("gateway.run_created", task_len=len(task))
        return resp.json()

    async def get_thread_state(self, thread_id: str) -> dict:
        """Get current thread state."""
        resp = await self.client.get(
            f"{self.gateway_url}/threads/{thread_id}/state",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def send_clarification(self, thread_id: str, response_text: str) -> dict:
        """Send HITL clarification response."""
        resp = await self.client.post(
            f"{self.gateway_url}/threads/{thread_id}/state",
            json={
                "values": {
                    "clarification_response": response_text,
                    "needs_clarification": False,
                },
                "command": {"update": True},
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        logger.info("gateway.clarification_sent", thread_id=thread_id)
        return resp.json()

    async def close(self) -> None:
        await self.client.aclose()
