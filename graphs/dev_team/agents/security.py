"""
Security Agent
==============

Responsible for:
  - Static security analysis of generated code (SAST)
  - Detection of hardcoded secrets, injection vectors, insecure patterns
  - Dependency vulnerability assessment
  - (Future) Runtime security checks on deployed infrastructure

Two modes:
  1. ``security_static_review`` — after Developer, before QA
  2. ``security_runtime_check`` — after DevOps (Wave 2+)

LangGraph node function: ``security_agent(state, config=None) -> dict``

The agent populates ``state["security_review"]`` with::

    {
        "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
        "critical": ["issue 1", ...],
        "warnings": ["issue 1", ...],
        "info": ["recommendation 1", ...],
        "summary": "Human-readable summary",
    }
"""

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts, create_prompt_template
from ..state import DevTeamState

logger = structlog.get_logger()


class SecurityAgent(BaseAgent):
    """Security Engineer agent for code review and vulnerability detection."""

    def __init__(self):
        prompts = load_prompts("security")
        llm = get_llm_with_fallback(role="security", temperature=0.2)
        super().__init__(name="security", llm=llm, prompts=prompts)

    def static_review(self, state: DevTeamState, config=None) -> dict:
        """Perform static security analysis on generated code.

        Analyses code_files for vulnerabilities, secrets, and bad practices.
        Returns structured findings categorised by severity.
        """
        code_files = state.get("code_files", [])
        tech_stack = state.get("tech_stack", [])
        task = state.get("task", "")

        logger.info(
            "security.static_review.start",
            files=len(code_files),
            tech_stack=tech_stack,
        )

        if not code_files:
            logger.warning("security.static_review.no_code")
            return {
                "security_review": {
                    "risk_level": "LOW",
                    "critical": [],
                    "warnings": [],
                    "info": [],
                    "summary": "No code files to review.",
                },
                "current_agent": "security",
                "messages": [AIMessage(
                    content="Security review skipped: no code files provided.",
                    name="security",
                )],
            }

        # Format code files for the prompt
        code_files_str = "\n\n".join(
            f"### {f['path']}\n```{f.get('language', '')}\n{f['content']}\n```"
            for f in code_files
        )

        # Extract dependency info from code files
        dependencies_str = self._extract_dependencies(code_files)

        # Build and invoke chain
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["security_static_review"],
        )
        chain = prompt | self.llm

        response = self._invoke_chain(chain, {
            "task": task,
            "tech_stack": ", ".join(tech_stack) if tech_stack else "Not specified",
            "code_files": code_files_str,
            "dependencies": dependencies_str or "No dependency files found",
        }, config=config)

        content = response.content

        # Parse structured findings from LLM response
        review = self._parse_security_review(content)

        logger.info(
            "security.static_review.done",
            risk_level=review["risk_level"],
            critical=len(review["critical"]),
            warnings=len(review["warnings"]),
            info=len(review["info"]),
        )

        return {
            "security_review": review,
            "current_agent": "security",
            "messages": [AIMessage(content=content, name="security")],
        }

    def runtime_check(self, state: DevTeamState, config=None) -> dict:
        """Check deployment configuration for security issues.

        Analyses infra_files (Dockerfile, docker-compose, CI/CD) for
        runtime security concerns.  Used after DevOps agent (Wave 2+).
        """
        infra_files = state.get("infra_files", [])
        task = state.get("task", "")

        logger.info("security.runtime_check.start", infra_files=len(infra_files))

        if not infra_files:
            logger.warning("security.runtime_check.no_infra")
            return {
                "security_review": {
                    "risk_level": "LOW",
                    "critical": [],
                    "warnings": [],
                    "info": [],
                    "summary": "No infrastructure files to review.",
                },
                "current_agent": "security",
                "messages": [AIMessage(
                    content="Security runtime check skipped: no infrastructure files.",
                    name="security",
                )],
            }

        infra_str = "\n\n".join(
            f"### {f.get('path', 'unknown')}\n```\n{f.get('content', '')}\n```"
            for f in infra_files
        )

        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["security_runtime_check"],
        )
        chain = prompt | self.llm

        response = self._invoke_chain(chain, {
            "task": task,
            "infra_files": infra_str,
        }, config=config)

        content = response.content
        review = self._parse_security_review(content)

        logger.info(
            "security.runtime_check.done",
            risk_level=review["risk_level"],
            critical=len(review["critical"]),
            warnings=len(review["warnings"]),
        )

        return {
            "security_review": review,
            "current_agent": "security",
            "messages": [AIMessage(content=content, name="security")],
        }

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_security_review(content: str) -> dict:
        """Parse LLM response into structured security review.

        Extracts findings by severity level from the markdown-formatted response.
        """
        review = {
            "risk_level": "LOW",
            "critical": [],
            "warnings": [],
            "info": [],
            "summary": "",
        }

        lines = content.split("\n")
        current_section = None

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            # Detect risk level
            if "overall risk level" in lower or "risk level" in lower:
                if "critical" in lower:
                    review["risk_level"] = "CRITICAL"
                elif "high" in lower:
                    review["risk_level"] = "HIGH"
                elif "medium" in lower:
                    review["risk_level"] = "MEDIUM"
                else:
                    review["risk_level"] = "LOW"

            # Detect section headers
            if "critical" in lower and ("#" in stripped or "**" in stripped):
                current_section = "critical"
                continue
            elif "warning" in lower and ("#" in stripped or "**" in stripped):
                current_section = "warnings"
                continue
            elif "informational" in lower and ("#" in stripped or "**" in stripped):
                current_section = "info"
                continue
            elif "info" in lower and ("#" in stripped or "**" in stripped) and "informational" not in lower:
                # Avoid matching "information" in other contexts
                if lower.startswith("##") or lower.startswith("**info"):
                    current_section = "info"
                    continue
            elif stripped.startswith("##") or stripped.startswith("**"):
                # Other section headers — reset section
                if current_section in ("critical", "warnings", "info"):
                    current_section = None

            # Collect findings (bullet points)
            if current_section and stripped.startswith("- "):
                finding = stripped[2:].strip()
                if finding and finding.lower() not in ("none found", "none", "n/a"):
                    review[current_section].append(finding)

            # Detect summary
            if "summary" in lower and "#" in stripped:
                current_section = "summary_section"
                continue
            if current_section == "summary_section" and stripped:
                review["summary"] = stripped

        # Auto-generate summary if not found
        if not review["summary"]:
            total = len(review["critical"]) + len(review["warnings"]) + len(review["info"])
            review["summary"] = (
                f"Security review: {review['risk_level']} risk. "
                f"{len(review['critical'])} critical, "
                f"{len(review['warnings'])} warnings, "
                f"{len(review['info'])} info."
            )

        return review

    @staticmethod
    def _extract_dependencies(code_files: list) -> str:
        """Extract dependency file contents from code_files.

        Looks for requirements.txt, package.json, go.mod, Cargo.toml, etc.
        """
        dep_files = []
        dep_filenames = {
            "requirements.txt", "pyproject.toml", "setup.py",
            "package.json", "package-lock.json", "yarn.lock",
            "go.mod", "go.sum",
            "Cargo.toml", "Cargo.lock",
            "Gemfile", "Gemfile.lock",
        }

        for f in code_files:
            filename = f.get("path", "").split("/")[-1]
            if filename in dep_filenames:
                dep_files.append(f"### {f['path']}\n```\n{f['content']}\n```")

        return "\n\n".join(dep_files) if dep_files else ""


# ------------------------------------------------------------------
# Singleton + LangGraph node function
# ------------------------------------------------------------------

_security_agent = None


def get_security_agent() -> SecurityAgent:
    """Get or create the Security agent instance."""
    global _security_agent
    if _security_agent is None:
        _security_agent = SecurityAgent()
    return _security_agent


def security_agent(state: DevTeamState, config=None) -> dict:
    """Security agent node function for LangGraph.

    Performs static security review by default.
    The graph routing determines when to call this node.
    """
    import time as _time
    t0 = _time.monotonic()
    logger.info("node.security.enter")

    agent = get_security_agent()
    result = agent.static_review(state, config=config)

    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("node.security.exit", elapsed_ms=round(elapsed_ms))

    return result
