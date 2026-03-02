"""
Base Agent Configuration
========================

Shared infrastructure for all dev-team agents:

- **LLM factory** (``get_llm``) — creates ChatOpenAI instances routed
  through an OpenAI-compatible proxy, with per-role model selection and
  support for multiple API endpoints.
- **Prompt loader** (``load_prompts``) — reads YAML prompt files from
  ``graphs/dev_team/prompts/``.
- **BaseAgent** — abstract base class every agent inherits from.

Environment variables consumed
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- ``LLM_API_URL`` / ``LLM_API_KEY`` — default endpoint
- ``LLM_<NAME>_URL`` / ``LLM_<NAME>_KEY`` — named endpoints
- ``LLM_MODEL_<ROLE>`` — per-agent model override
- ``LLM_DEFAULT_MODEL`` — global model fallback
"""

import os
import yaml
from pathlib import Path
from string import Template
from typing import Optional, Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..language_policy import build_user_language_system_instruction

logger = structlog.get_logger()


# ===========================================
# LLM Configuration
# ===========================================

DEFAULT_TEMPERATURE = 0.7
CODE_TEMPERATURE = 0.2  # Lower temperature for code generation

# Default API endpoint
DEFAULT_LLM_API_URL = "https://clipapi4me.31.59.58.143.nip.io/v1"

# Default models for each agent role (lowest-priority fallback)
DEFAULT_MODELS = {
    "default": "gemini-claude-sonnet-4-5-thinking",
    "pm": "gemini-claude-sonnet-4-5-thinking",
    "analyst": "gemini-claude-sonnet-4-5-thinking",
    "architect": "gemini-claude-opus-4-6-thinking",
    "developer": "gemini-3-pro-preview",
    "reviewer": "gemini-claude-sonnet-4-5-thinking",
    "qa": "gemini-3-pro-preview",
    "security": "gemini-claude-sonnet-4-5-thinking",
    "devops": "gemini-claude-sonnet-4-5-thinking",
    "router": "gemini-3-flash-preview",
    "researcher": "gemini-claude-sonnet-4-5-thinking",
}

# Available models (for reference)
AVAILABLE_MODELS = [
    "gemini-claude-opus-4-6-thinking",
    "gemini-claude-sonnet-4-5-thinking",
    "gemini-3-pro-preview",
    "gemini-3-pro-high",
    "gemini-3-flash-preview",
    "kimi-k2-thinking",
    "iflow-rome-30ba3b",
]


# ===========================================
# agents.yaml loader (cached)
# ===========================================

_agent_config_cache: dict | None = None


def load_agent_config() -> dict:
    """Load ``config/agents.yaml`` with env-var substitution.

    The result is cached for the lifetime of the process.
    Returns a minimal empty structure when the file is missing so that
    call-sites never have to handle ``None``.
    """
    global _agent_config_cache
    if _agent_config_cache is not None:
        return _agent_config_cache

    from common import PROJECT_ROOT
    config_path = PROJECT_ROOT / "config" / "agents.yaml"
    if not config_path.exists():
        logger.warning("config.not_found", path=str(config_path))
        _agent_config_cache = {"defaults": {}, "endpoints": {}, "agents": {}}
        return _agent_config_cache

    raw = config_path.read_text(encoding="utf-8")
    # Substitute ${ENV_VAR} from the environment
    substituted = Template(raw).safe_substitute(os.environ)
    config = yaml.safe_load(substituted) or {}
    _agent_config_cache = config
    logger.debug("config.loaded", path=str(config_path), agents=list(config.get("agents", {}).keys()))
    return _agent_config_cache


def _reset_agent_config_cache() -> None:
    """Reset the cached config (useful in tests)."""
    global _agent_config_cache
    _agent_config_cache = None


# ===========================================
# Endpoint resolution
# ===========================================


def get_llm_endpoint(endpoint_name: str = "default") -> dict[str, str]:
    """Get LLM endpoint configuration by name.

    Resolution order:
      1. Environment variables (``LLM_API_URL`` / ``LLM_<NAME>_URL``)
      2. ``config/agents.yaml`` → ``endpoints.<name>``
      3. ``DEFAULT_LLM_API_URL`` hardcoded fallback

    Args:
        endpoint_name: Name of the endpoint ("default" or custom name)

    Returns:
        Dict with "url" and "api_key"
    """
    config = load_agent_config()

    if endpoint_name == "default":
        url = os.getenv("LLM_API_URL") or config.get("endpoints", {}).get("default", {}).get("url") or DEFAULT_LLM_API_URL
        api_key = os.getenv("LLM_API_KEY") or config.get("endpoints", {}).get("default", {}).get("api_key") or ""
    else:
        env_prefix = f"LLM_{endpoint_name.upper()}"
        yaml_ep = config.get("endpoints", {}).get(endpoint_name, {})
        url = os.getenv(f"{env_prefix}_URL") or yaml_ep.get("url") or DEFAULT_LLM_API_URL
        api_key = os.getenv(f"{env_prefix}_KEY") or yaml_ep.get("api_key") or ""

    logger.debug("llm.endpoint_resolved", name=endpoint_name, url=url, api_key_set=bool(api_key))
    return {"url": url, "api_key": api_key}


# ===========================================
# Model resolution
# ===========================================


def get_model_for_role(role: str) -> str:
    """Get the model name for a specific agent role.

    Priority chain (highest to lowest):
      1. ``LLM_MODEL_<ROLE>`` env var
      2. ``agents.<role>.model`` in ``config/agents.yaml``
      3. ``LLM_DEFAULT_MODEL`` env var
      4. ``DEFAULT_MODELS`` hardcoded dict

    Args:
        role: Agent role (pm, analyst, architect, developer, qa, router, ...)

    Returns:
        Model name
    """
    # 1. Per-role env override
    env_model = os.getenv(f"LLM_MODEL_{role.upper()}")
    if env_model:
        logger.debug("model.selected", role=role, model=env_model, source="env")
        return env_model

    # 2. agents.yaml
    config = load_agent_config()
    yaml_model = config.get("agents", {}).get(role, {}).get("model")
    if yaml_model:
        logger.debug("model.selected", role=role, model=yaml_model, source="yaml")
        return yaml_model

    # 3. Global env default
    global_default = os.getenv("LLM_DEFAULT_MODEL")
    if global_default:
        logger.debug("model.selected", role=role, model=global_default, source="env_default")
        return global_default

    # 4. Hardcoded defaults
    selected = DEFAULT_MODELS.get(role, DEFAULT_MODELS["default"])
    logger.debug("model.selected", role=role, model=selected, source="hardcoded")
    return selected


def get_llm(
    role: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = DEFAULT_TEMPERATURE,
    endpoint: str = "default",
) -> BaseChatModel:
    """Get a configured LLM instance via OpenAI-compatible API.

    All models are accessed through a unified proxy API that supports
    OpenAI-compatible endpoints.

    Args:
        role: Agent role for automatic model selection (pm, analyst, etc.)
        model: Explicit model name (overrides role-based selection)
        temperature: Sampling temperature
        endpoint: Endpoint name for multi-endpoint setups

    Returns:
        Configured LLM instance
    """
    # Get endpoint configuration
    endpoint_config = get_llm_endpoint(endpoint)

    # Determine model
    if model:
        selected_model = model
    elif role:
        selected_model = get_model_for_role(role)
    else:
        selected_model = os.getenv("LLM_DEFAULT_MODEL", DEFAULT_MODELS["default"])

    logger.info("llm.init", role=role or "none", model=selected_model, temperature=temperature, endpoint=endpoint)
    return ChatOpenAI(
        model=selected_model,
        temperature=temperature,
        api_key=endpoint_config["api_key"],
        base_url=endpoint_config["url"],
    )


def get_llm_with_fallback(role: str, **kwargs) -> BaseChatModel:
    """Get an LLM with a fallback chain from ``config/agents.yaml``.

    If ``agents.<role>.fallback_model`` is configured, returns
    ``primary.with_fallbacks([fallback])``.  Otherwise returns the
    primary model as-is.

    The fallback chain catches **all** exceptions (including ``TypeError``
    from null ``choices`` responses) and retries with the fallback model.
    """
    primary = get_llm(role=role, **kwargs)

    config = load_agent_config()
    fallback_model = config.get("agents", {}).get(role, {}).get("fallback_model")
    if fallback_model:
        fallback = get_llm(model=fallback_model, **kwargs)
        logger.info("llm.fallback_chain", role=role, fallback=fallback_model)
        return _LoggingFallbackLLM(primary, fallback, role=role)

    return primary


class _LoggingFallbackLLM(BaseChatModel):
    """Wrapper that adds visibility into fallback attempts.

    LangChain's built-in ``with_fallbacks`` works but doesn't log when
    the fallback is tried, making it hard to diagnose production issues.
    This thin wrapper makes the process observable.
    """

    _primary: BaseChatModel
    _fallback: BaseChatModel
    _role: str

    def __init__(self, primary: BaseChatModel, fallback: BaseChatModel, *, role: str = ""):
        """Initialise without calling Pydantic BaseModel validation."""
        # BaseChatModel is a Pydantic model — bypass its __init__
        super().__init__()
        object.__setattr__(self, "_primary", primary)
        object.__setattr__(self, "_fallback", fallback)
        object.__setattr__(self, "_role", role)

    # --- LangChain interface -------------------------------------------------

    @property
    def _llm_type(self) -> str:  # type: ignore[override]
        return "logging_fallback"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """Synchronous generation with fallback."""
        try:
            return self._primary._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            logger.warning(
                "llm.primary_failed",
                role=self._role,
                error=str(exc)[:200],
                error_type=type(exc).__name__,
            )
            logger.info("llm.trying_fallback", role=self._role)
            try:
                result = self._fallback._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
                logger.info("llm.fallback_succeeded", role=self._role)
                return result
            except Exception as fallback_exc:
                logger.error(
                    "llm.fallback_also_failed",
                    role=self._role,
                    error=str(fallback_exc)[:200],
                    error_type=type(fallback_exc).__name__,
                )
                raise

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        """Async generation with fallback."""
        try:
            return await self._primary._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            logger.warning(
                "llm.primary_failed",
                role=self._role,
                error=str(exc)[:200],
                error_type=type(exc).__name__,
            )
            logger.info("llm.trying_fallback", role=self._role)
            try:
                result = await self._fallback._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
                logger.info("llm.fallback_succeeded", role=self._role)
                return result
            except Exception as fallback_exc:
                logger.error(
                    "llm.fallback_also_failed",
                    role=self._role,
                    error=str(fallback_exc)[:200],
                    error_type=type(fallback_exc).__name__,
                )
                raise


# ===========================================
# Retry helper
# ===========================================

# Exception types that should trigger a retry (transient network issues)
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
)

try:
    import httpx
    RETRYABLE_EXCEPTIONS = (*RETRYABLE_EXCEPTIONS, httpx.ConnectError, httpx.ReadTimeout)
except ImportError:
    pass


def invoke_with_retry(
    chain,
    inputs: dict,
    config: dict | None = None,
    max_attempts: int = 3,
):
    """Invoke an LLM chain with exponential-backoff retry.

    Only retries on *transient* errors (network / timeout).
    All other exceptions are re-raised immediately.

    Args:
        chain: LangChain Runnable (prompt | llm).
        inputs: Inputs dict for the chain.
        config: Optional RunnableConfig with callbacks, etc.
        max_attempts: Maximum retry attempts (default 3).

    Returns:
        The chain invocation result.
    """
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        RetryError,
    )

    callbacks = (config or {}).get("callbacks", [])

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        reraise=True,
    )
    def _invoke():
        invoke_config = {"callbacks": callbacks} if callbacks else {}
        return chain.invoke(inputs, config=invoke_config)

    try:
        return _invoke()
    except RetryError:
        logger.error("llm.retry_exhausted", attempts=max_attempts)
        raise


def load_prompts(agent_name: str) -> dict:
    """
    Load prompts from YAML file for an agent.

    Args:
        agent_name: Name of the agent (e.g., "pm", "analyst")

    Returns:
        Dictionary of prompts
    """
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / f"{agent_name}.yaml"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompt_file}")

    with open(prompt_file, "r", encoding="utf-8") as f:
        prompts = yaml.safe_load(f)
    logger.debug("prompts.loaded", agent=agent_name, keys=list(prompts.keys()))
    return prompts


def create_prompt_template(
    system_prompt: str,
    human_template: str,
) -> ChatPromptTemplate:
    """
    Create a chat prompt template.

    Args:
        system_prompt: System message content
        human_template: Human message template with placeholders

    Returns:
        ChatPromptTemplate instance
    """
    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_template),
    ])


class BaseAgent:
    """Base class for all agents."""

    def __init__(
        self,
        name: str,
        llm: BaseChatModel,
        prompts: dict,
    ):
        self.name = name
        self.llm = llm
        self.prompts = prompts
        self.system_prompt = prompts.get("system", "")
        logger.info("agent.initialized", agent=self.name)

    def create_prompt(self, state: dict[str, Any], human_template: str) -> ChatPromptTemplate:
        """Create a prompt with dynamic user-language policy injected."""
        system_prompt = self.system_prompt
        language_policy = build_user_language_system_instruction(state)
        if language_policy:
            system_prompt = f"{system_prompt}\n\n{language_policy}"
        return create_prompt_template(system_prompt, human_template)

    # ------------------------------------------------------------------
    # Langfuse / callback helpers  (Wave 1 — module 2.4)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_callbacks(config) -> list:
        """Extract callbacks from a LangGraph ``RunnableConfig``.

        LangGraph automatically passes the config to node functions when
        they declare a ``config`` parameter.  Langfuse installs its
        callback handler there so that every LLM call is traced.
        """
        if config and "callbacks" in config:
            return config["callbacks"]
        return []

    def _invoke_chain(self, chain, inputs: dict, config=None):
        """Invoke *chain* with retry + Langfuse callbacks.

        A thin wrapper that ensures:
          * ``invoke_with_retry`` provides exponential backoff;
          * Langfuse callbacks from the LangGraph config are forwarded
            to the underlying LLM call.
        """
        import time as _time
        t0 = _time.monotonic()
        logger.info("agent.llm_call_start", agent=self.name,
                     input_keys=list(inputs.keys()))
        try:
            result = invoke_with_retry(chain, inputs, config=config)
            elapsed_ms = (_time.monotonic() - t0) * 1000
            # Log response size for visibility
            content_len = len(result.content) if hasattr(result, 'content') else 0
            logger.info("agent.llm_call_done", agent=self.name,
                         elapsed_ms=round(elapsed_ms),
                         response_chars=content_len)
            return result
        except Exception as exc:
            elapsed_ms = (_time.monotonic() - t0) * 1000
            logger.error("agent.llm_call_failed", agent=self.name,
                          elapsed_ms=round(elapsed_ms),
                          error=str(exc)[:300])
            raise

    def _invoke_structured(self, prompt, inputs: dict, schema, config=None,
                            fallback_parser=None):
        """Invoke LLM with structured output, falling back to string parsing.

        Tries ``llm.with_structured_output(schema)`` first.  If the
        model doesn't support it or parsing fails, falls back to the
        legacy string-based ``fallback_parser``.

        Args:
            prompt: ChatPromptTemplate to use.
            inputs: Template variables.
            schema: Pydantic model class for the expected output.
            config: Optional LangGraph RunnableConfig.
            fallback_parser: ``Callable[[str], schema]`` that parses
                raw LLM text into the schema.  Required for models
                that don't support tool calling.

        Returns:
            An instance of *schema*.
        """
        import time as _time
        from pydantic import BaseModel

        t0 = _time.monotonic()
        logger.info("agent.structured_call_start", agent=self.name,
                     schema=schema.__name__,
                     input_keys=list(inputs.keys()))

        # --- Try structured output first ---
        try:
            structured_llm = self.llm.with_structured_output(schema)
            chain = prompt | structured_llm
            result = invoke_with_retry(chain, inputs, config=config)
            if isinstance(result, BaseModel):
                elapsed_ms = (_time.monotonic() - t0) * 1000
                logger.info("agent.structured_call_done", agent=self.name,
                             mode="structured", elapsed_ms=round(elapsed_ms))
                return result
        except (NotImplementedError, TypeError, Exception) as exc:
            logger.debug("agent.structured_fallback", agent=self.name,
                          reason=str(exc)[:200])

        # --- Fallback to plain text + parser ---
        chain = prompt | self.llm
        raw = invoke_with_retry(chain, inputs, config=config)
        content = raw.content if hasattr(raw, "content") else str(raw)
        elapsed_ms = (_time.monotonic() - t0) * 1000

        if fallback_parser:
            parsed = fallback_parser(content)
            logger.info("agent.structured_call_done", agent=self.name,
                         mode="fallback_parser", elapsed_ms=round(elapsed_ms))
            return parsed

        logger.warning("agent.structured_no_parser", agent=self.name,
                        schema=schema.__name__)
        return schema()

    # ------------------------------------------------------------------

    def invoke(self, state: dict, config=None) -> dict:
        """Invoke the agent with the current state.

        Override in subclasses.  The *config* parameter carries the
        LangGraph ``RunnableConfig`` (including Langfuse callbacks).
        """
        raise NotImplementedError
