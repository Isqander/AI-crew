"""
Project Manager (PM) Agent
===========================

Responsible for:
  - Decomposing incoming tasks into subtasks
  - Tracking overall progress across the pipeline
  - Conducting the final review before completion

LangGraph node function: ``pm_agent(state) -> dict``
"""

import structlog
from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts, create_prompt_template
from ..state import DevTeamState

logger = structlog.get_logger()


class ProjectManagerAgent(BaseAgent):
    """Project Manager agent for task coordination."""
    
    def __init__(self):
        prompts = load_prompts("pm")
        llm = get_llm_with_fallback(role="pm", temperature=0.7)
        super().__init__(name="pm", llm=llm, prompts=prompts)
    
    def decompose_task(self, state: DevTeamState, config=None) -> dict:
        """
        Decompose the incoming task into subtasks.
        """
        logger.info("pm.decompose_task", task_len=len(state.get("task", "")))
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["task_decomposition"]
        )
        
        chain = prompt | self.llm
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "context": state.get("context", "No additional context provided"),
        }, config=config)
        logger.debug("pm.decompose_task.done")
        return {
            "messages": [AIMessage(content=response.content, name="pm")],
            "current_agent": "pm",
            "next_agent": "analyst",
        }
    
    def check_progress(self, state: DevTeamState, config=None) -> dict:
        """
        Check the progress of the current task.
        """
        logger.info("pm.check_progress")
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["progress_check"]
        )
        
        chain = prompt | self.llm
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "requirements_status": "Complete" if state.get("requirements") else "Pending",
            "architecture_status": "Complete" if state.get("architecture") else "Pending",
            "implementation_status": "Complete" if state.get("code_files") else "Pending",
            "qa_status": "Complete" if state.get("review_comments") else "Pending",
        }, config=config)
        logger.debug("pm.check_progress.done")
        return {
            "messages": [AIMessage(content=response.content, name="pm")],
        }
    
    def final_review(self, state: DevTeamState, config=None) -> dict:
        """
        Conduct final review before completion.

        Includes deploy_url and pr_url in the summary if available.
        """
        logger.info("pm.final_review", code_files=len(state.get("code_files", [])))
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["final_review"]
        )
        
        chain = prompt | self.llm
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "code_files_count": len(state.get("code_files", [])),
            "tests_status": "Passed" if not state.get("issues_found") else "Issues found",
            "docs_status": "Included" if state.get("implementation_notes") else "Missing",
        }, config=config)
        logger.debug("pm.final_review.done")

        # Build enriched summary with deployment info
        summary_parts = [response.content]
        pr_url = state.get("pr_url")
        deploy_url = state.get("deploy_url")
        if pr_url:
            summary_parts.append(f"\nPR: {pr_url}")
        if deploy_url:
            summary_parts.append(f"Deploy URL: {deploy_url}")
        summary = "\n".join(summary_parts)

        return {
            "messages": [AIMessage(content=summary, name="pm")],
            "summary": summary,
        }


# Create singleton instance
_pm_agent = None


def get_pm_agent() -> ProjectManagerAgent:
    """Get or create the PM agent instance."""
    global _pm_agent
    if _pm_agent is None:
        _pm_agent = ProjectManagerAgent()
    return _pm_agent


def pm_agent(state: DevTeamState, config=None) -> dict:
    """PM agent node function for LangGraph.

    LangGraph automatically passes ``config`` when the function
    declares it.  This carries Langfuse callbacks, thread metadata, etc.
    """
    agent = get_pm_agent()

    # Initial task - decompose
    if not state.get("requirements"):
        logger.debug("pm.route", action="decompose_task")
        return agent.decompose_task(state, config=config)

    # All done - final review
    if state.get("code_files") and not state.get("issues_found"):
        logger.debug("pm.route", action="final_review")
        return agent.final_review(state, config=config)

    # Check progress
    logger.debug("pm.route", action="check_progress")
    return agent.check_progress(state, config=config)
