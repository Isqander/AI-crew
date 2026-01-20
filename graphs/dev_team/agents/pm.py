"""
Project Manager Agent

Responsible for task decomposition, coordination, and progress tracking.
"""

from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseAgent, get_llm, load_prompts, create_prompt_template
from ..state import DevTeamState


class ProjectManagerAgent(BaseAgent):
    """Project Manager agent for task coordination."""
    
    def __init__(self):
        prompts = load_prompts("pm")
        llm = get_llm(provider="openai", model="gpt-4o", temperature=0.7)
        super().__init__(name="pm", llm=llm, prompts=prompts)
    
    def decompose_task(self, state: DevTeamState) -> dict:
        """
        Decompose the incoming task into subtasks.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["task_decomposition"]
        )
        
        chain = prompt | self.llm
        
        response = chain.invoke({
            "task": state["task"],
            "context": state.get("context", "No additional context provided"),
        })
        
        return {
            "messages": [AIMessage(content=response.content, name="pm")],
            "current_agent": "pm",
            "next_agent": "analyst",
        }
    
    def check_progress(self, state: DevTeamState) -> dict:
        """
        Check the progress of the current task.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["progress_check"]
        )
        
        chain = prompt | self.llm
        
        response = chain.invoke({
            "task": state["task"],
            "requirements_status": "Complete" if state.get("requirements") else "Pending",
            "architecture_status": "Complete" if state.get("architecture") else "Pending",
            "implementation_status": "Complete" if state.get("code_files") else "Pending",
            "qa_status": "Complete" if state.get("review_comments") else "Pending",
        })
        
        return {
            "messages": [AIMessage(content=response.content, name="pm")],
        }
    
    def final_review(self, state: DevTeamState) -> dict:
        """
        Conduct final review before completion.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["final_review"]
        )
        
        chain = prompt | self.llm
        
        response = chain.invoke({
            "task": state["task"],
            "code_files_count": len(state.get("code_files", [])),
            "tests_status": "Passed" if not state.get("issues_found") else "Issues found",
            "docs_status": "Included" if state.get("implementation_notes") else "Missing",
        })
        
        return {
            "messages": [AIMessage(content=response.content, name="pm")],
            "summary": response.content,
        }


# Create singleton instance
_pm_agent = None


def get_pm_agent() -> ProjectManagerAgent:
    """Get or create the PM agent instance."""
    global _pm_agent
    if _pm_agent is None:
        _pm_agent = ProjectManagerAgent()
    return _pm_agent


def pm_agent(state: DevTeamState) -> dict:
    """
    PM agent node function for LangGraph.
    
    Determines what action to take based on current state.
    """
    agent = get_pm_agent()
    
    # Initial task - decompose
    if not state.get("requirements"):
        return agent.decompose_task(state)
    
    # All done - final review
    if state.get("code_files") and not state.get("issues_found"):
        return agent.final_review(state)
    
    # Check progress
    return agent.check_progress(state)
