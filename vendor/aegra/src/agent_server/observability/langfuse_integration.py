from typing import Any

import structlog

from src.agent_server.settings import settings

from .base import ObservabilityProvider

logger = structlog.getLogger(__name__)


def _check_langfuse_connectivity() -> None:
    """Best-effort connectivity check for Langfuse.

    Logs a warning if the Langfuse host is unreachable.
    Does NOT block startup.
    """
    import os

    host = os.environ.get("LANGFUSE_HOST", "")
    if not host:
        return

    try:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{host}/api/public/health")
            if resp.status_code == 200:
                logger.info("langfuse.connectivity_ok", host=host)
            else:
                logger.warning(
                    "langfuse.connectivity_warning",
                    host=host,
                    status=resp.status_code,
                )
    except Exception as e:
        logger.warning(
            "langfuse.connectivity_error",
            host=host,
            error=str(e)[:200],
        )


class LangfuseProvider(ObservabilityProvider):
    """Langfuse observability provider."""

    def get_callbacks(self) -> list[Any]:
        """Return Langfuse callbacks."""
        import os

        callbacks = []
        if self.is_enabled():
            host = os.environ.get("LANGFUSE_HOST", "(not set)")
            public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
            secret_set = bool(os.environ.get("LANGFUSE_SECRET_KEY"))

            logger.info(
                "langfuse.init_attempt",
                host=host,
                public_key_prefix=public_key[:12] + "..." if len(public_key) > 12 else public_key,
                secret_key_set=secret_set,
            )

            try:
                from langfuse.langchain import CallbackHandler

                # Handler is now stateless, metadata will be passed in config
                handler = CallbackHandler()
                callbacks.append(handler)
                logger.info(
                    "langfuse.handler_created",
                    host=host,
                )
                # Best-effort connectivity check (non-blocking diagnostic)
                _check_langfuse_connectivity()
            except ImportError:
                logger.warning(
                    "langfuse.not_installed",
                    hint="LANGFUSE_LOGGING is true, but 'langfuse' is not installed. "
                    "Please run 'pip install langfuse' to enable tracing.",
                )
            except Exception as e:
                logger.error(
                    "langfuse.init_failed",
                    error=str(e),
                    host=host,
                )
        else:
            logger.debug("langfuse.disabled")

        return callbacks

    def get_metadata(
        self, run_id: str, thread_id: str, user_identity: str | None = None
    ) -> dict[str, Any]:
        """Return Langfuse-specific metadata."""
        metadata: dict[str, Any] = {
            "langfuse_session_id": thread_id,
        }

        if user_identity:
            metadata["langfuse_user_id"] = user_identity
            metadata["langfuse_tags"] = [
                "aegra_run",
                f"run:{run_id}",
                f"thread:{thread_id}",
                f"user:{user_identity}",
            ]
        else:
            metadata["langfuse_tags"] = [
                "aegra_run",
                f"run:{run_id}",
                f"thread:{thread_id}",
            ]

        return metadata

    def is_enabled(self) -> bool:
        """Check if Langfuse is enabled."""
        return settings.langfuse.LANGFUSE_LOGGING


# Create and register the Langfuse provider
_langfuse_provider = LangfuseProvider()


def get_tracing_callbacks() -> list[Any]:
    """
    Backward compatibility function - delegates to the new observability system.
    """
    from .base import get_observability_manager

    # Register the Langfuse provider unconditionally; registration should be idempotent
    manager = get_observability_manager()
    manager.register_provider(_langfuse_provider)

    return manager.get_all_callbacks()
