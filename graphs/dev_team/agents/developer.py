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

from .base import BaseAgent, get_llm, load_prompts, create_prompt_template, CODE_TEMPERATURE
from ..state import DevTeamState, CodeFile

logger = structlog.get_logger()


class DeveloperAgent(BaseAgent):
    """Developer agent for code implementation."""
    
    def __init__(self):
        prompts = load_prompts("developer")
        # Use lower temperature for more deterministic code generation
        llm = get_llm(role="developer", temperature=CODE_TEMPERATURE)
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
    
    def _parse_code_files(self, content: str) -> list[CodeFile]:
        """
        Parse code files from LLM response.
        
        Expected format:
        ```language:path/to/file.ext
        code content
        ```
        """
        files = []
        
        # Pattern to match code blocks with language and optional path
        pattern = r"```(\w+)(?::([^\n]+))?\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        for i, (language, filepath, code) in enumerate(matches):
            # Generate filepath if not provided
            if not filepath:
                ext = self._get_extension(language)
                filepath = f"generated_file_{i + 1}{ext}"
            
            files.append(CodeFile(
                path=filepath.strip(),
                content=code.strip(),
                language=language.lower(),
            ))
        
        return files
    
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
    
    # If there are issues to fix
    if state.get("issues_found"):
        logger.debug("developer.route", action="fix_issues")
        return agent.fix_issues(state, config=config)
    
    # Otherwise, implement
    logger.debug("developer.route", action="implement")
    return agent.implement(state, config=config)
