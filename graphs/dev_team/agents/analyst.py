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

from .base import BaseAgent, get_llm, load_prompts, create_prompt_template
from ..state import DevTeamState, UserStory

logger = structlog.get_logger()


class AnalystAgent(BaseAgent):
    """Business Analyst agent for requirements and user stories."""
    
    def __init__(self):
        prompts = load_prompts("analyst")
        llm = get_llm(role="analyst", temperature=0.7)
        super().__init__(name="analyst", llm=llm, prompts=prompts)
    
    def gather_requirements(self, state: DevTeamState, config=None) -> dict:
        """
        Analyze the task and extract requirements.
        """
        logger.info("analyst.gather_requirements", task_len=len(state.get("task", "")))
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["requirements_gathering"]
        )
        
        chain = prompt | self.llm
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "context": state.get("context", "No additional context provided"),
        }, config=config)
        
        # Parse requirements from response
        # In a real implementation, this would be more sophisticated
        content = response.content
        
        # Check if clarification is needed
        needs_clarification = "clarification" in content.lower() and "?" in content
        
        if needs_clarification:
            logger.info("analyst.clarification_requested")
            # Extract the question for clarification
            return {
                "messages": [AIMessage(content=content, name="analyst")],
                "current_agent": "analyst",
                "needs_clarification": True,
                "clarification_question": content,
                "clarification_context": "Requirements gathering phase",
            }
        
        # Extract requirements (simplified parsing)
        requirements = []
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                requirements.append(line[2:])
        
        logger.debug("analyst.requirements_gathered", count=len(requirements))
        return {
            "messages": [AIMessage(content=content, name="analyst")],
            "requirements": requirements if requirements else [state["task"]],
            "current_agent": "analyst",
            "next_agent": "architect",
            "needs_clarification": False,
        }
    
    def process_clarification(self, state: DevTeamState, config=None) -> dict:
        """
        Process user's clarification response and continue.
        """
        logger.info("analyst.process_clarification")
        clarification = state.get("clarification_response", "")
        
        # Re-analyze with clarification
        enhanced_context = f"""
        Original context: {state.get('context', 'None')}
        
        User clarification: {clarification}
        """
        
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["requirements_gathering"]
        )
        
        chain = prompt | self.llm
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "context": enhanced_context,
        }, config=config)
        
        content = response.content
        
        # Extract requirements
        requirements = []
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                requirements.append(line[2:])
        
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
