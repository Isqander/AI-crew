"""
Base Agent Configuration

Provides base utilities and LLM configuration for all agents.
"""

import logging
import os
import yaml
from pathlib import Path
from typing import Optional, Dict

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI  # Used for OpenAI-compatible API

logger = logging.getLogger(__name__)


# ===========================================
# LLM Configuration
# ===========================================

DEFAULT_TEMPERATURE = 0.7
CODE_TEMPERATURE = 0.2  # Lower temperature for code generation

# Default API endpoint
DEFAULT_LLM_API_URL = "https://clipapi4me.31.59.58.143.nip.io/v1"

# Default models for each agent role
DEFAULT_MODELS = {
    "default": "gemini-claude-sonnet-4-5-thinking",
    "pm": "gemini-claude-sonnet-4-5-thinking",
    "analyst": "gemini-claude-sonnet-4-5-thinking", 
    "architect": "gemini-claude-opus-4-5-thinking",
    "developer": "glm-4.7",
    "qa": "glm-4.7",
}

# Available models (for reference)
AVAILABLE_MODELS = [
    "gemini-claude-opus-4-5-thinking",
    "gemini-claude-sonnet-4-5-thinking",
    "gemini-3-pro-high",
    "gemini-3-flash-preview",
    "glm-4.7",
]


def get_llm_endpoint(endpoint_name: str = "default") -> Dict[str, str]:
    """
    Get LLM endpoint configuration by name.
    
    Supports multiple endpoints via environment variables:
    - LLM_API_URL, LLM_API_KEY - default endpoint
    - LLM_<NAME>_URL, LLM_<NAME>_KEY - named endpoints
    
    Args:
        endpoint_name: Name of the endpoint ("default" or custom name)
        
    Returns:
        Dict with "url" and "api_key"
    """
    if endpoint_name == "default":
        url = os.getenv("LLM_API_URL", DEFAULT_LLM_API_URL)
        api_key = os.getenv("LLM_API_KEY", "")
    else:
        # Named endpoint: LLM_BACKUP_URL, LLM_BACKUP_KEY
        env_prefix = f"LLM_{endpoint_name.upper()}"
        url = os.getenv(f"{env_prefix}_URL", DEFAULT_LLM_API_URL)
        api_key = os.getenv(f"{env_prefix}_KEY", "")
    
    logger.debug(
        "LLM endpoint resolved: name=%s url=%s api_key_set=%s",
        endpoint_name,
        url,
        bool(api_key),
    )
    return {"url": url, "api_key": api_key}


def get_model_for_role(role: str) -> str:
    """
    Get the model name for a specific agent role.
    
    Checks environment variable first (LLM_MODEL_<ROLE>),
    falls back to DEFAULT_MODELS.
    
    Args:
        role: Agent role (pm, analyst, architect, developer, qa)
        
    Returns:
        Model name
    """
    # Check environment variable first: LLM_MODEL_PM, LLM_MODEL_DEVELOPER, etc.
    env_var = f"LLM_MODEL_{role.upper()}"
    env_model = os.getenv(env_var)
    
    if env_model:
        logger.debug("Model selected from env: role=%s model=%s", role, env_model)
        return env_model
    
    # Check default model override
    default_override = os.getenv("LLM_DEFAULT_MODEL")
    if default_override and role not in DEFAULT_MODELS:
        logger.debug("Model selected from default override: role=%s model=%s", role, default_override)
        return default_override

    selected = DEFAULT_MODELS.get(role, DEFAULT_MODELS["default"])
    logger.debug("Model selected from defaults: role=%s model=%s", role, selected)
    return selected


def get_llm(
    role: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = DEFAULT_TEMPERATURE,
    endpoint: str = "default",
) -> BaseChatModel:
    """
    Get a configured LLM instance via OpenAI-compatible API.
    
    All models are accessed through a unified proxy API that supports
    OpenAI-compatible endpoints.
    
    Args:
        role: Agent role for automatic model selection (pm, analyst, etc.)
        model: Explicit model name (overrides role-based selection)
        temperature: Sampling temperature
        endpoint: Endpoint name for multi-endpoint setups
        
    Returns:
        Configured LLM instance
        
    Example:
        # Automatic model selection based on role
        llm = get_llm(role="architect")
        
        # Explicit model
        llm = get_llm(model="claude-opus-4-5-thinking")
        
        # Using alternative endpoint
        llm = get_llm(role="developer", endpoint="backup")
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
    
    logger.info(
        "Initializing LLM: role=%s model=%s temp=%.2f endpoint=%s",
        role or "none",
        selected_model,
        temperature,
        endpoint,
    )
    return ChatOpenAI(
        model=selected_model,
        temperature=temperature,
        api_key=endpoint_config["api_key"],
        base_url=endpoint_config["url"],
    )


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
    logger.debug("Prompts loaded: agent=%s keys=%s", agent_name, list(prompts.keys()))
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
        logger.info("Agent initialized: name=%s", self.name)
    
    def invoke(self, state: dict) -> dict:
        """
        Invoke the agent with the current state.
        Override in subclasses.
        """
        raise NotImplementedError
