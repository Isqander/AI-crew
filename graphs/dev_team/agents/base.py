"""
Base Agent Configuration

Provides base utilities and LLM configuration for all agents.
"""

import os
import yaml
from pathlib import Path
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


# LLM Configuration
DEFAULT_TEMPERATURE = 0.7
CODE_TEMPERATURE = 0.2  # Lower temperature for code generation


def get_llm(
    provider: str = "openai",
    model: Optional[str] = None,
    temperature: float = DEFAULT_TEMPERATURE,
) -> BaseChatModel:
    """
    Get a configured LLM instance.
    
    Args:
        provider: LLM provider ("openai", "anthropic")
        model: Specific model name (optional)
        temperature: Sampling temperature
        
    Returns:
        Configured LLM instance
    """
    if provider == "openai":
        return ChatOpenAI(
            model=model or "gpt-4o",
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model=model or "claude-3-5-sonnet-20241022",
            temperature=temperature,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


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
        return yaml.safe_load(f)


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
    
    def invoke(self, state: dict) -> dict:
        """
        Invoke the agent with the current state.
        Override in subclasses.
        """
        raise NotImplementedError
