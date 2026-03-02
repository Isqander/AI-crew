"""
Software Architect Agent
=========================

Responsible for:
  - Designing system architecture based on requirements
  - Choosing a technology stack
  - Creating implementation specs for the Developer
  - Reviewing QA escalations (after repeated Dev↔QA failures)

LangGraph node function: ``architect_agent(state, config=None) -> dict``
"""

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts
from .schemas import ArchitectDesignResponse, ArchitectReviewResponse
from ..state import DevTeamState
from common.utils import format_code_files

logger = structlog.get_logger()


class ArchitectAgent(BaseAgent):
    """Software Architect agent for system design."""
    
    def __init__(self):
        prompts = load_prompts("architect")
        llm = get_llm_with_fallback(role="architect", temperature=0.7)
        super().__init__(name="architect", llm=llm, prompts=prompts)
    
    @staticmethod
    def _parse_design_fallback(content: str) -> ArchitectDesignResponse:
        """Legacy parser: extract tech stack from free-form text."""
        tech_stack: list[str] = []
        lower = content.lower()
        for tech, kw in [("Python", "python"), ("React", "react"),
                         ("TypeScript", "typescript"), ("FastAPI", "fastapi"),
                         ("PostgreSQL", "postgresql"), ("PostgreSQL", "postgres")]:
            if kw in lower and tech not in tech_stack:
                tech_stack.append(tech)
        return ArchitectDesignResponse(design=content, tech_stack=tech_stack)

    @staticmethod
    def _parse_review_fallback(content: str) -> ArchitectReviewResponse:
        """Legacy parser: extract verdict and critical issues."""
        approved = "approve_with_notes" in content.lower()
        critical_issues: list[str] = []
        in_critical = False
        for line in content.split("\n"):
            if "critical issues" in line.lower() and "must fix" in line.lower():
                in_critical = True
                continue
            if in_critical and line.strip().startswith("- "):
                issue = line.strip()[2:].strip()
                if issue.lower() != "none":
                    critical_issues.append(issue)
            if in_critical and line.strip().startswith("##"):
                in_critical = False
        return ArchitectReviewResponse(approved=approved, critical_issues=critical_issues)

    def design_architecture(self, state: DevTeamState, config=None) -> dict:
        """
        Design the system architecture based on requirements.
        """
        logger.info("architect.design_architecture")
        prompt = self.create_prompt(
            state,
            self.prompts["architecture_design"]
        )
        
        chain = prompt | self.llm
        
        requirements = state.get("requirements", [])
        user_stories = state.get("user_stories", [])
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "requirements": "\n".join(f"- {r}" for r in requirements),
            "user_stories": "\n".join(str(s) for s in user_stories) if user_stories else "None provided",
        }, config=config)
        
        content = response.content

        parsed = self._parse_design_fallback(content)

        # Try structured output
        try:
            parsed = self._invoke_structured(
                prompt, {
                    "task": state["task"],
                    "requirements": "\n".join(f"- {r}" for r in requirements),
                    "user_stories": "\n".join(str(s) for s in user_stories) if user_stories else "None provided",
                }, ArchitectDesignResponse,
                config=config,
                fallback_parser=self._parse_design_fallback,
            )
        except Exception:
            pass

        tech_stack = parsed.tech_stack

        logger.debug("architect.design_done", tech_stack=tech_stack or ["Python"])
        return {
            "messages": [AIMessage(content=content, name="architect")],
            "architecture": {"design": content},
            "tech_stack": tech_stack if tech_stack else ["Python"],
            "current_agent": "architect",
            "next_agent": "developer",
            "needs_clarification": False,
        }
    
    def review_qa_escalation(self, state: DevTeamState, config=None) -> dict:
        """
        Review QA issues after repeated Dev↔QA cycles.
        Decide which issues are truly critical vs cosmetic/acceptable.
        """
        logger.info("architect.review_qa_escalation", review_iter=state.get("review_iteration_count", 0))
        prompt = self.create_prompt(
            state,
            self.prompts["qa_escalation"]
        )

        chain = prompt | self.llm

        code_files = state.get("code_files", [])
        code_files_str = format_code_files(code_files)

        response = self._invoke_chain(chain, {
            "task": state["task"],
            "iteration_count": state.get("review_iteration_count", 0),
            "issues": "\n".join(
                f"- {i}" for i in state.get("issues_found", [])
            ) or "None",
            "review_comments": "\n".join(
                f"- {c}" for c in state.get("review_comments", [])
            ) or "None",
            "code_files": code_files_str,
        }, config=config)

        content = response.content

        parsed = self._parse_review_fallback(content)

        if parsed.approved:
            logger.info("architect.escalation_verdict", verdict="approve_with_notes")
            return {
                "messages": [AIMessage(content=content, name="architect")],
                "issues_found": [],
                "test_results": {
                    **state.get("test_results", {}),
                    "approved": True,
                    "architect_waived": True,
                },
                "current_agent": "architect",
                "next_agent": "git_commit",
                "review_iteration_count": 0,
                "architect_escalated": True,
            }
        else:
            logger.info("architect.escalation_verdict", verdict="fix_required")
            critical_issues = parsed.critical_issues

            return {
                "messages": [AIMessage(content=content, name="architect")],
                "issues_found": critical_issues if critical_issues else state.get("issues_found", []),
                "current_agent": "architect",
                "next_agent": "developer",
                "review_iteration_count": 0,
                "architect_escalated": True,
            }

    def create_implementation_spec(self, state: DevTeamState, config=None) -> dict:
        """
        Create detailed implementation specification for developers.
        """
        logger.info("architect.create_implementation_spec")
        prompt = self.create_prompt(
            state,
            self.prompts["implementation_spec"]
        )
        
        chain = prompt | self.llm
        
        architecture = state.get("architecture", {})
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "architecture": architecture.get("design", "Not specified"),
            "file_structure": "To be determined based on architecture",
            "code_guidelines": "Follow best practices for the chosen stack",
            "important_notes": "Ensure code is well-documented and tested",
        }, config=config)
        
        logger.debug("architect.create_implementation_spec.done")
        return {
            "messages": [AIMessage(content=response.content, name="architect")],
            "architecture": {
                **architecture,
                "implementation_spec": response.content,
            },
        }


# Create singleton instance
_architect_agent = None


def get_architect_agent() -> ArchitectAgent:
    """Get or create the Architect agent instance."""
    global _architect_agent
    if _architect_agent is None:
        _architect_agent = ArchitectAgent()
    return _architect_agent


def architect_agent(state: DevTeamState, config=None) -> dict:
    """
    Architect agent node function for LangGraph.
    """
    agent = get_architect_agent()
    
    # If clarification response received, continue with design
    if state.get("clarification_response"):
        # Process approval and continue
        logger.debug("architect.route", action="design_architecture", reason="clarification")
        return agent.design_architecture(state, config=config)
    
    # Design architecture
    logger.debug("architect.route", action="design_architecture")
    return agent.design_architecture(state, config=config)
