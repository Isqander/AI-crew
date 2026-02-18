"""
Developer Agent
===============

Responsible for:
  - Implementing code based on the Architect's specification
  - Fixing issues reported by QA
  - Parsing code blocks from LLM output into ``CodeFile`` structures

LangGraph node function: ``developer_agent(state) -> dict``
"""

import re

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts, create_prompt_template, CODE_TEMPERATURE
from ..state import DevTeamState, CodeFile
from common.utils import format_code_files

logger = structlog.get_logger()


class DeveloperAgent(BaseAgent):
    """Developer agent for code implementation."""
    
    def __init__(self):
        prompts = load_prompts("developer")
        # Use lower temperature for more deterministic code generation
        llm = get_llm_with_fallback(role="developer", temperature=CODE_TEMPERATURE)
        super().__init__(name="developer", llm=llm, prompts=prompts)
    
    def implement(self, state: DevTeamState, config=None) -> dict:
        """
        Implement code based on architecture specification.
        """
        logger.info("developer.implement")
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["implementation"]
        )
        
        chain = prompt | self.llm
        
        architecture = state.get("architecture", {})
        
        response = self._invoke_chain(chain, {
            "task": state["task"],
            "architecture": architecture.get("design", "Not specified"),
            "implementation_spec": architecture.get("implementation_spec", "Follow best practices"),
        }, config=config)
        
        content = response.content
        
        # Parse code files from response
        code_files = self._parse_code_files(content)
        logger.debug("developer.implement.done", code_files=len(code_files))
        
        return {
            "messages": [AIMessage(content=content, name="developer")],
            "code_files": code_files,
            "implementation_notes": f"Implemented {len(code_files)} file(s)",
            "current_agent": "developer",
            "next_agent": "qa",
        }
    
    def fix_issues(self, state: DevTeamState, config=None) -> dict:
        """
        Fix issues found by QA.
        """
        logger.info("developer.fix_issues", issues=len(state.get("issues_found", [])))
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["fix_issues"]
        )
        
        chain = prompt | self.llm
        
        issues = state.get("issues_found", [])
        review_comments = state.get("review_comments", [])
        
        response = self._invoke_chain(chain, {
            "task": state.get("task", ""),
            "architecture": state.get("architecture", {}),
            "current_code": format_code_files(state.get("code_files", [])),
            "issues": "\n".join(f"- {i}" for i in issues),
            "review_comments": "\n".join(f"- {c}" for c in review_comments),
        }, config=config)
        
        content = response.content
        
        # Parse updated code files
        code_files = self._parse_code_files(content)
        logger.debug("developer.fix_issues.done", code_files=len(code_files))
        
        # Merge with existing files (update or add)
        existing_files = {f["path"]: f for f in state.get("code_files", [])}
        for new_file in code_files:
            existing_files[new_file["path"]] = new_file
        
        return {
            "messages": [AIMessage(content=content, name="developer")],
            "code_files": list(existing_files.values()),
            "issues_found": [],  # Clear issues after fixing
            "current_agent": "developer",
            "next_agent": "qa",
        }

    def fix_ci(self, state: DevTeamState, config=None) -> dict:
        """Fix CI/CD pipeline failures."""
        ci_log = state.get("ci_log", "")
        ci_status = state.get("ci_status", "")
        logger.info("developer.fix_ci", ci_status=ci_status)

        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["fix_ci"]
        )
        chain = prompt | self.llm

        response = self._invoke_chain(chain, {
            "ci_status": ci_status,
            "ci_log": ci_log or "(no CI output)",
        }, config=config)

        content = response.content
        code_files = self._parse_code_files(content)
        logger.debug("developer.fix_ci.done", code_files=len(code_files))

        existing_files = {f["path"]: f for f in state.get("code_files", [])}
        for new_file in code_files:
            existing_files[new_file["path"]] = new_file

        return {
            "messages": [AIMessage(content=content, name="developer")],
            "code_files": list(existing_files.values()),
            "ci_status": "",  # Clear CI status after attempting fix
            "current_agent": "developer",
        }

    def fix_lint(self, state: DevTeamState, config=None) -> dict:
        """Fix lint issues found by the lint_check node."""
        lint_log = state.get("lint_log", "")
        lint_iter = state.get("lint_iteration_count", 0)
        logger.info("developer.fix_lint", lint_iteration=lint_iter)

        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["fix_lint"]
        )
        chain = prompt | self.llm

        response = self._invoke_chain(chain, {
            "lint_status": state.get("lint_status", "issues"),
            "lint_log": lint_log or "(no lint output)",
        }, config=config)

        content = response.content
        code_files = self._parse_code_files(content)
        logger.debug("developer.fix_lint.done", code_files=len(code_files))

        existing_files = {f["path"]: f for f in state.get("code_files", [])}
        for new_file in code_files:
            existing_files[new_file["path"]] = new_file

        return {
            "messages": [AIMessage(content=content, name="developer")],
            "code_files": list(existing_files.values()),
            "current_agent": "developer",
        }
    
    def _parse_code_files(self, content: str) -> list[CodeFile]:
        """
        Parse code files from LLM response.
        
        Expected format:
        ```language:path/to/file.ext
        code content
        ```
        """
        files = []
        skipped_unnamed = 0
        
        # Pattern to match code blocks with language and optional path
        pattern = r"```(\w+)(?::([^\n]+))?\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        for language, filepath, code in matches:
            # Enforce explicit filepath to avoid garbage generated_file_* artifacts.
            if not filepath:
                skipped_unnamed += 1
                continue
            normalized_path = self._normalize_path(filepath)
            if not normalized_path:
                continue
            
            files.append(CodeFile(
                path=normalized_path,
                content=code.strip(),
                language=language.lower(),
            ))

        if skipped_unnamed:
            logger.warning("developer.parse_code_files.skipped_unnamed_blocks", count=skipped_unnamed)
        
        return files

    @staticmethod
    def _normalize_path(filepath: str) -> str:
        """Normalize paths for repository-safe relative file references."""
        path = filepath.strip().replace("\\", "/")
        while path.startswith("/"):
            path = path[1:]
        path = re.sub(r"/{2,}", "/", path)
        if not path or path.startswith("../") or "/../" in path:
            return ""
        return path
    
    def _get_extension(self, language: str) -> str:
        """Get file extension for a language."""
        extensions = {
            "python": ".py",
            "py": ".py",
            "javascript": ".js",
            "js": ".js",
            "typescript": ".ts",
            "ts": ".ts",
            "tsx": ".tsx",
            "jsx": ".jsx",
            "html": ".html",
            "css": ".css",
            "json": ".json",
            "yaml": ".yaml",
            "yml": ".yml",
            "sql": ".sql",
            "bash": ".sh",
            "shell": ".sh",
            "markdown": ".md",
            "md": ".md",
        }
        return extensions.get(language.lower(), ".txt")


# Create singleton instance
_developer_agent = None


def get_developer_agent() -> DeveloperAgent:
    """Get or create the Developer agent instance."""
    global _developer_agent
    if _developer_agent is None:
        _developer_agent = DeveloperAgent()
    return _developer_agent


def developer_agent(state: DevTeamState, config=None) -> dict:
    """
    Developer agent node function for LangGraph.
    """
    agent = get_developer_agent()

    # If lint issues need fixing (from lint_check node)
    lint_status = state.get("lint_status", "")
    if lint_status == "issues":
        logger.debug("developer.route", action="fix_lint")
        return agent.fix_lint(state, config=config)

    # If CI failed — fix CI issues
    ci_status = state.get("ci_status", "")
    if ci_status in ("failure", "error"):
        logger.debug("developer.route", action="fix_ci")
        return agent.fix_ci(state, config=config)

    # If there are issues to fix (from Reviewer/QA)
    if state.get("issues_found"):
        logger.debug("developer.route", action="fix_issues")
        return agent.fix_issues(state, config=config)
    
    # Otherwise, implement
    logger.debug("developer.route", action="implement")
    return agent.implement(state, config=config)
