"""
Business Analyst Agent

Responsible for requirements gathering and user story creation.
"""

from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm, load_prompts, create_prompt_template
from ..state import DevTeamState, UserStory


class AnalystAgent(BaseAgent):
    """Business Analyst agent for requirements and user stories."""
    
    def __init__(self):
        prompts = load_prompts("analyst")
        llm = get_llm(role="analyst", temperature=0.7)
        super().__init__(name="analyst", llm=llm, prompts=prompts)
    
    def gather_requirements(self, state: DevTeamState) -> dict:
        """
        Analyze the task and extract requirements.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["requirements_gathering"]
        )
        
        chain = prompt | self.llm
        
        response = chain.invoke({
            "task": state["task"],
            "context": state.get("context", "No additional context provided"),
        })
        
        # Parse requirements from response
        # In a real implementation, this would be more sophisticated
        content = response.content
        
        # Check if clarification is needed
        needs_clarification = "clarification" in content.lower() and "?" in content
        
        if needs_clarification:
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
        
        return {
            "messages": [AIMessage(content=content, name="analyst")],
            "requirements": requirements if requirements else [state["task"]],
            "current_agent": "analyst",
            "next_agent": "architect",
            "needs_clarification": False,
        }
    
    def process_clarification(self, state: DevTeamState) -> dict:
        """
        Process user's clarification response and continue.
        """
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
        
        response = chain.invoke({
            "task": state["task"],
            "context": enhanced_context,
        })
        
        content = response.content
        
        # Extract requirements
        requirements = []
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                requirements.append(line[2:])
        
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


def analyst_agent(state: DevTeamState) -> dict:
    """
    Analyst agent node function for LangGraph.
    """
    agent = get_analyst_agent()
    
    # If we have a clarification response, process it
    if state.get("clarification_response"):
        return agent.process_clarification(state)
    
    # Otherwise, gather requirements
    return agent.gather_requirements(state)
