"""
Reviewer Agent
==============

Responsible for:
  - Reviewing code against task requirements
  - Identifying critical and major issues
  - Verifying that previous issues have been resolved
  - Giving final approval before the code proceeds to QA testing

LangGraph node function: ``reviewer_agent(state, config=None) -> dict``

Note:
  Previously this role was named "QA".  It was renamed to "Reviewer"
  to better reflect its actual responsibility (code review, not testing).
  The new QA agent handles sandbox-based testing.
"""

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts
from .schemas import ReviewerResponse, ReviewerVerifyResponse
from ..state import DevTeamState
from common.utils import format_code_files

logger = structlog.get_logger()


class ReviewerAgent(BaseAgent):
    """Reviewer agent for code review and approval."""

    def __init__(self):
        prompts = load_prompts("reviewer")
        llm = get_llm_with_fallback(role="reviewer", temperature=0.3)
        super().__init__(name="reviewer", llm=llm, prompts=prompts)

    @staticmethod
    def _parse_review_fallback(content: str) -> ReviewerResponse:
        """Legacy string parser for review results."""
        issues_found: list[str] = []
        review_comments: list[str] = []
        approved = False
        for line in content.split("\n"):
            line_lower = line.lower()
            if "critical" in line_lower or "major" in line_lower:
                issues_found.append(line.strip())
            if "approved" in line_lower and "not" not in line_lower:
                approved = True
            if line.strip().startswith("- "):
                review_comments.append(line.strip()[2:])
        return ReviewerResponse(
            approved=approved, issues_found=issues_found,
            review_comments=review_comments)

    @staticmethod
    def _parse_verify_fallback(content: str) -> ReviewerVerifyResponse:
        """Legacy string parser for fix verification."""
        all_fixed = "fixed" in content.lower() and "not fixed" not in content.lower()
        return ReviewerVerifyResponse(all_fixed=all_fixed)

    def review_code(self, state: DevTeamState, config=None) -> dict:
        """
        Review the implemented code.
        """
        logger.info("reviewer.review_code", code_files=len(state.get("code_files", [])))
        prompt = self.create_prompt(
            state,
            self.prompts["code_review"]
        )

        chain = prompt | self.llm

        code_files = state.get("code_files", [])
        requirements = state.get("requirements", [])
        lint_warnings = state.get("lint_warnings", [])

        code_files_str = format_code_files(code_files)
        lint_warnings_str = "\n".join(f"- {w}" for w in lint_warnings[:30]) if lint_warnings else "None"

        response = self._invoke_chain(chain, {
            "task": state["task"],
            "requirements": "\n".join(f"- {r}" for r in requirements),
            "code_files": code_files_str,
            "lint_warnings": lint_warnings_str,
        }, config=config)

        content = response.content

        parsed = self._parse_review_fallback(content)

        # Try structured output
        try:
            parsed = self._invoke_structured(
                prompt, {
                    "task": state["task"],
                    "requirements": "\n".join(f"- {r}" for r in requirements),
                    "code_files": code_files_str,
                    "lint_warnings": lint_warnings_str,
                }, ReviewerResponse,
                config=config,
                fallback_parser=self._parse_review_fallback,
            )
        except Exception:
            pass

        issues_found = parsed.issues_found
        review_comments = parsed.review_comments
        approved = parsed.approved

        # Determine next step
        if issues_found:
            next_agent = "developer"  # Send back for fixes
        elif approved:
            next_agent = "qa"  # Proceed to QA sandbox testing
        else:
            next_agent = "pm"  # Final review

        # Increment Dev↔Reviewer iteration counter when issues are found
        review_iter = state.get("review_iteration_count", 0)
        if issues_found:
            review_iter += 1

        logger.debug(
            "reviewer.review_code.done",
            approved=approved,
            issues=len(issues_found),
            next_agent=next_agent,
            review_iter=review_iter,
        )
        return {
            "messages": [AIMessage(content=content, name="reviewer")],
            "review_comments": review_comments,
            "issues_found": issues_found,
            "test_results": {
                "reviewed": True,
                "approved": approved,
                "issues_count": len(issues_found),
            },
            "current_agent": "reviewer",
            "next_agent": next_agent,
            "review_iteration_count": review_iter,
        }

    def verify_fixes(self, state: DevTeamState, config=None) -> dict:
        """
        Verify that previous issues have been fixed.
        """
        logger.info("reviewer.verify_fixes")
        prompt = self.create_prompt(
            state,
            self.prompts["verify_fixes"]
        )

        chain = prompt | self.llm

        code_files = state.get("code_files", [])
        code_files_str = format_code_files(code_files)

        # Previous issues (stored before clearing)
        previous_issues = state.get("_previous_issues", [])

        response = self._invoke_chain(chain, {
            "original_issues": "\n".join(f"- {i}" for i in previous_issues),
            "updated_code": code_files_str,
        }, config=config)

        content = response.content

        parsed = self._parse_verify_fallback(content)
        all_fixed = parsed.all_fixed

        logger.debug("reviewer.verify_fixes.done", all_fixed=all_fixed)
        return {
            "messages": [AIMessage(content=content, name="reviewer")],
            "issues_found": [] if all_fixed else state.get("issues_found", []),
            "current_agent": "reviewer",
            "next_agent": "qa" if all_fixed else "developer",
        }

    def final_approval(self, state: DevTeamState, config=None) -> dict:
        """
        Give final approval for deployment.
        """
        logger.info("reviewer.final_approval")
        prompt = self.create_prompt(
            state,
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
            "messages": [AIMessage(content=response.content, name="reviewer")],
            "test_results": {
                **state.get("test_results", {}),
                "final_approval": True,
            },
        }


# Create singleton instance
_reviewer_agent = None


def get_reviewer_agent() -> ReviewerAgent:
    """Get or create the Reviewer agent instance."""
    global _reviewer_agent
    if _reviewer_agent is None:
        _reviewer_agent = ReviewerAgent()
    return _reviewer_agent


def reviewer_agent(state: DevTeamState, config=None) -> dict:
    """
    Reviewer agent node function for LangGraph.
    """
    agent = get_reviewer_agent()

    # Review the code
    logger.debug("reviewer.route", action="review_code")
    return agent.review_code(state, config=config)
