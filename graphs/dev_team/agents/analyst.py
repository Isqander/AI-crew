"""
Business Analyst Agent
======================

Responsible for:
  - Analysing the task description and extracting requirements
  - Creating user stories with acceptance criteria
  - Requesting clarification from the user when the task is ambiguous

LangGraph node function: ``analyst_agent(state, config=None) -> dict``
"""

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts
from .schemas import AnalystResponse
from ..state import DevTeamState, UserStory

logger = structlog.get_logger()


class AnalystAgent(BaseAgent):
    """Business Analyst agent for requirements and user stories."""
    
    def __init__(self):
        prompts = load_prompts("analyst")
        llm = get_llm_with_fallback(role="analyst", temperature=0.7)
        super().__init__(name="analyst", llm=llm, prompts=prompts)
    
    @staticmethod
    def _parse_analyst_fallback(content: str) -> AnalystResponse:
        """Legacy string parser for models without structured output."""
        needs_clarification = "clarification" in content.lower() and "?" in content
        requirements: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                requirements.append(stripped[2:])
        return AnalystResponse(
            needs_clarification=needs_clarification,
            clarification_question=content if needs_clarification else None,
            requirements=requirements,
        )

    def gather_requirements(self, state: DevTeamState, config=None) -> dict:
        """Analyze the task and extract requirements."""
        logger.info("analyst.gather_requirements", task_len=len(state.get("task", "")))
        prompt = self.create_prompt(
            state,
            self.prompts["requirements_gathering"]
        )

        inputs = {
            "task": state["task"],
            "context": state.get("context", "No additional context provided"),
        }

        # Also get raw text for the chat message
        chain = prompt | self.llm
        raw_response = self._invoke_chain(chain, inputs, config=config)
        content = raw_response.content

        parsed = self._parse_analyst_fallback(content)

        # Try structured output (best-effort upgrade)
        try:
            structured = self._invoke_structured(
                prompt, inputs, AnalystResponse,
                config=config,
                fallback_parser=self._parse_analyst_fallback,
            )
            parsed = structured
        except Exception:
            pass

        if parsed.needs_clarification:
            logger.info("analyst.clarification_requested")
            return {
                "messages": [AIMessage(content=content, name="analyst")],
                "current_agent": "analyst",
                "needs_clarification": True,
                "clarification_question": parsed.clarification_question or content,
                "clarification_context": "Requirements gathering phase",
            }

        requirements = parsed.requirements
        logger.debug("analyst.requirements_gathered", count=len(requirements))
        return {
            "messages": [AIMessage(content=content, name="analyst")],
            "requirements": requirements if requirements else [state["task"]],
            "current_agent": "analyst",
            "next_agent": "architect",
            "needs_clarification": False,
        }
    
    def process_clarification(self, state: DevTeamState, config=None) -> dict:
        """Process user's clarification response and continue."""
        logger.info("analyst.process_clarification")
        clarification = state.get("clarification_response", "")

        enhanced_context = (
            f"Original context: {state.get('context', 'None')}\n\n"
            f"User clarification: {clarification}"
        )

        prompt = self.create_prompt(
            state,
            self.prompts["requirements_gathering"]
        )

        inputs = {"task": state["task"], "context": enhanced_context}

        chain = prompt | self.llm
        response = self._invoke_chain(chain, inputs, config=config)
        content = response.content

        parsed = self._parse_analyst_fallback(content)

        requirements = parsed.requirements
        logger.debug("analyst.clarified_requirements", count=len(requirements))
        return {
            "messages": [AIMessage(content=content, name="analyst")],
            "requirements": requirements if requirements else [state["task"]],
            "current_agent": "analyst",
            "next_agent": "architect",
            "needs_clarification": False,
            "clarification_response": None,
        }


# Create singleton instance
_analyst_agent = None


def get_analyst_agent() -> AnalystAgent:
    """Get or create the Analyst agent instance."""
    global _analyst_agent
    if _analyst_agent is None:
        _analyst_agent = AnalystAgent()
    return _analyst_agent


def analyst_agent(state: DevTeamState, config=None) -> dict:
    """
    Analyst agent node function for LangGraph.
    """
    agent = get_analyst_agent()
    
    # If we have a clarification response, process it
    if state.get("clarification_response"):
        logger.debug("analyst.route", action="process_clarification")
        return agent.process_clarification(state, config=config)
    
    # Otherwise, gather requirements
    logger.debug("analyst.route", action="gather_requirements")
    return agent.gather_requirements(state, config=config)
