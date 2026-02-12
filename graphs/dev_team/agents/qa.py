"""
QA Engineer Agent
=================

Responsible for:
  - Reviewing code against task requirements
  - Identifying critical and major issues
  - Verifying that previous issues have been resolved
  - Giving final approval before the code is committed

LangGraph node function: ``qa_agent(state, config=None) -> dict``
"""

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts, create_prompt_template
from ..state import DevTeamState

logger = structlog.get_logger()


class QAAgent(BaseAgent):
    """QA Engineer agent for code review and testing."""
    
    def __init__(self):
        prompts = load_prompts("qa")
        llm = get_llm_with_fallback(role="qa", temperature=0.3)
        super().__init__(name="qa", llm=llm, prompts=prompts)
    
    def review_code(self, state: DevTeamState, config=None) -> dict:
        """
        Review the implemented code.
        """
        logger.info("qa.review_code", code_files=len(state.get("code_files", [])))
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["code_review"]
        )
        
        chain = prompt | self.llm
        
        code_files = state.get("code_files", [])
        requirements = state.get("requirements", [])
        
        # Format code files for review
        code_files_str = "\n\n".join([
            f"### {f['path']}\n```{f['language']}\n{f['content']}\n```"
            for f in code_files
        ])
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "requirements": "\n".join(f"- {r}" for r in requirements),
            "code_files": code_files_str if code_files_str else "No code files provided",
        }, config=config)
        
        content = response.content
        
        # Parse review results
        issues_found = []
        review_comments = []
        approved = False
        
        # Simple parsing (in production, use structured output)
        lines = content.split("\n")
        for line in lines:
            line_lower = line.lower()
            if "critical" in line_lower or "major" in line_lower:
                issues_found.append(line.strip())
            if "approved" in line_lower and "not" not in line_lower:
                approved = True
            if line.strip().startswith("- "):
                review_comments.append(line.strip()[2:])
        
        # Determine next step
        if issues_found:
            next_agent = "developer"  # Send back for fixes
        elif approved:
            next_agent = "git_commit"  # Ready for commit
        else:
            next_agent = "pm"  # Final review
        
        # Increment Dev↔QA iteration counter when issues are found
        qa_iter = state.get("qa_iteration_count", 0)
        if issues_found:
            qa_iter += 1

        logger.debug(
            "qa.review_code.done",
            approved=approved,
            issues=len(issues_found),
            next_agent=next_agent,
            qa_iter=qa_iter,
        )
        return {
            "messages": [AIMessage(content=content, name="qa")],
            "review_comments": review_comments,
            "issues_found": issues_found,
            "test_results": {
                "reviewed": True,
                "approved": approved,
                "issues_count": len(issues_found),
            },
            "current_agent": "qa",
            "next_agent": next_agent,
            "qa_iteration_count": qa_iter,
        }
    
    def verify_fixes(self, state: DevTeamState, config=None) -> dict:
        """
        Verify that previous issues have been fixed.
        """
        logger.info("qa.verify_fixes")
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["verify_fixes"]
        )
        
        chain = prompt | self.llm
        
        code_files = state.get("code_files", [])
        
        # Format code files
        code_files_str = "\n\n".join([
            f"### {f['path']}\n```{f['language']}\n{f['content']}\n```"
            for f in code_files
        ])
        
        # Previous issues (stored before clearing)
        previous_issues = state.get("_previous_issues", [])
        
        response = self._invoke_chain(chain, {
            "original_issues": "\n".join(f"- {i}" for i in previous_issues),
            "updated_code": code_files_str,
        }, config=config)
        
        content = response.content
        
        # Check if all issues are fixed
        all_fixed = "fixed" in content.lower() and "not fixed" not in content.lower()
        
        logger.debug("qa.verify_fixes.done", all_fixed=all_fixed)
        return {
            "messages": [AIMessage(content=content, name="qa")],
            "issues_found": [] if all_fixed else state.get("issues_found", []),
            "current_agent": "qa",
            "next_agent": "git_commit" if all_fixed else "developer",
        }
    
    def final_approval(self, state: DevTeamState, config=None) -> dict:
        """
        Give final approval for deployment.
        """
        logger.info("qa.final_approval")
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["final_approval"]
        )
        
        chain = prompt | self.llm
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "requirements_status": "Met" if state.get("requirements") else "Unknown",
            "code_quality": "Reviewed" if state.get("review_comments") else "Not reviewed",
            "test_results": str(state.get("test_results", {})),
            "notes": state.get("implementation_notes", ""),
        }, config=config)
        
        return {
            "messages": [AIMessage(content=response.content, name="qa")],
            "test_results": {
                **state.get("test_results", {}),
                "final_approval": True,
            },
        }


# Create singleton instance
_qa_agent = None


def get_qa_agent() -> QAAgent:
    """Get or create the QA agent instance."""
    global _qa_agent
    if _qa_agent is None:
        _qa_agent = QAAgent()
    return _qa_agent


def qa_agent(state: DevTeamState, config=None) -> dict:
    """
    QA agent node function for LangGraph.
    """
    agent = get_qa_agent()
    
    # Review the code
    logger.debug("qa.route", action="review_code")
    return agent.review_code(state, config=config)
