"""
DevOps Agent
============

Responsible for:
  - Generating production infrastructure files (Dockerfile, docker-compose, CI/CD)
  - Setting up Traefik reverse proxy labels for automatic HTTPS
  - Configuring GitHub Actions deployment workflow
  - Determining deploy URL (nip.io domain)

Runs AFTER code is reviewed and approved, BEFORE git_commit.

LangGraph node function: ``devops_agent(state, config=None) -> dict``

The agent populates:
  - ``state["infra_files"]`` — list of {path, content} dicts
  - ``state["deploy_url"]`` — expected deployment URL
"""

import json
import os
import re

import structlog
from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm_with_fallback, load_prompts
from .schemas import DevOpsResponse, InfraFileOutput
from ..state import DevTeamState
from ..language_policy import choose_user_text, resolve_user_language
from common.utils import format_code_files

logger = structlog.get_logger()

# Default deploy VPS IP (overridden by DEPLOY_VPS_IP env var)
DEFAULT_DEPLOY_IP = "31.59.58.143"


def _sanitize_app_name(task: str) -> str:
    """Derive a URL-safe app name from the task description.

    Takes the first few meaningful words, lowercases, replaces spaces with
    hyphens, strips non-alphanumeric chars.

    >>> _sanitize_app_name("Build a TODO app with React")
    'build-a-todo-app'
    """
    words = re.sub(r"[^a-zA-Z0-9\s-]", "", task).strip().split()[:5]
    name = "-".join(words).lower()
    # Remove leading/trailing hyphens
    name = name.strip("-")
    return name or "app"


def _build_deploy_url(app_name: str) -> str:
    """Build deployment URL using hybrid strategy.

    If ``DEPLOY_DOMAIN`` is set → ``https://{app}.{domain}``
    Otherwise → ``https://{app}.{ip}.nip.io``
    """
    custom_domain = os.getenv("DEPLOY_DOMAIN", "").strip()
    if custom_domain:
        return f"https://{app_name}.{custom_domain}"
    deploy_ip = os.getenv("DEPLOY_VPS_IP", DEFAULT_DEPLOY_IP)
    return f"https://{app_name}.{deploy_ip}.nip.io"


def _get_deploy_repo_info(app_name: str) -> tuple[str, str]:
    """Return (deploy_repo, deploy_branch) for the single-repo strategy.

    Reads ``DEPLOY_SINGLE_REPO`` env var.  Branch is ``project/{app_name}``.
    Returns empty strings if deploy repo is not configured.
    """
    repo = os.getenv("DEPLOY_SINGLE_REPO", "").strip()
    if not repo:
        return "", ""
    branch = f"project/{app_name}"
    return repo, branch


class DevOpsAgent(BaseAgent):
    """DevOps Engineer agent for infrastructure generation."""

    def __init__(self):
        prompts = load_prompts("devops")
        llm = get_llm_with_fallback(role="devops", temperature=0.3)
        super().__init__(name="devops", llm=llm, prompts=prompts)

    def generate_infra(self, state: DevTeamState, config=None) -> dict:
        """Generate infrastructure files for deployment.

        Analyses the code, tech stack, and architecture to produce:
        - Dockerfile (multi-stage, optimised)
        - docker-compose.prod.yml (with Traefik labels)
        - .github/workflows/deploy.yml (CI/CD pipeline)

        Returns state update with ``infra_files``, ``deploy_url``,
        and a summary message.
        """
        code_files = state.get("code_files", [])
        tech_stack = state.get("tech_stack", [])
        architecture = state.get("architecture", {})
        task = state.get("task", "")
        requirements = state.get("requirements", [])

        logger.info(
            "devops.generate_infra.start",
            files=len(code_files),
            tech_stack=tech_stack,
        )

        app_name = _sanitize_app_name(task)
        deploy_ip = os.getenv("DEPLOY_VPS_IP", DEFAULT_DEPLOY_IP)

        if not code_files:
            logger.warning("devops.generate_infra.no_code")
            return {
                "infra_files": [],
                "deploy_url": "",
                "current_agent": "devops",
                "messages": [AIMessage(
                    content=choose_user_text(
                        state,
                        en="DevOps: no code files to generate infrastructure for.",
                        ru="DevOps: нет файлов кода для генерации инфраструктуры.",
                    ),
                    name="devops",
                )],
            }

        code_files_str = format_code_files(code_files)
        arch_str = json.dumps(architecture, indent=2, default=str) if architecture else "Not specified"
        requirements_str = "\n".join(f"- {r}" for r in requirements) if requirements else "Not specified"

        # Build deploy URL using hybrid strategy (nip.io or custom domain)
        deploy_url = _build_deploy_url(app_name)
        deploy_repo, deploy_branch = _get_deploy_repo_info(app_name)

        # Build and invoke chain
        prompt = self.create_prompt(
            state,
            self.prompts["generate_infra"],
        )
        chain = prompt | self.llm

        response = self._invoke_chain(chain, {
            "task": task,
            "tech_stack": ", ".join(tech_stack) if tech_stack else "Not specified",
            "architecture": arch_str,
            "code_files": code_files_str,
            "requirements": requirements_str,
            "deploy_ip": deploy_ip,
            "app_name": app_name,
        }, config=config)

        content = response.content

        # Parse structured response
        parsed = self._parse_devops_response(content, app_name, deploy_ip)

        # Override deploy_url with our hybrid-computed URL (more reliable than LLM output)
        parsed.deploy_url = deploy_url

        logger.info(
            "devops.generate_infra.done",
            infra_files=len(parsed.infra_files),
            deploy_url=deploy_url,
            deploy_repo=deploy_repo or "(not configured)",
            deploy_branch=deploy_branch or "(not configured)",
            env_vars=len(parsed.env_vars_needed),
        )

        # Convert infra_files to list of dicts for state
        infra_files_dicts = [
            {"path": f.path, "content": f.content}
            for f in parsed.infra_files
        ]

        if resolve_user_language(state) == "ru":
            summary_parts = [
                f"Сгенерировано инфраструктурных файлов: {len(parsed.infra_files)}",
                *[f"  - {f.path}" for f in parsed.infra_files],
            ]
        else:
            summary_parts = [
                f"Generated {len(parsed.infra_files)} infrastructure file(s):",
                *[f"  - {f.path}" for f in parsed.infra_files],
            ]
        if deploy_url:
            summary_parts.append(
                choose_user_text(
                    state,
                    en=f"Deploy URL: {deploy_url}",
                    ru=f"URL деплоя: {deploy_url}",
                )
            )
        if deploy_repo:
            summary_parts.append(
                choose_user_text(
                    state,
                    en=f"Deploy repo: {deploy_repo} (branch: {deploy_branch})",
                    ru=f"Репозиторий деплоя: {deploy_repo} (ветка: {deploy_branch})",
                )
            )
        if parsed.env_vars_needed:
            summary_parts.append(
                choose_user_text(
                    state,
                    en=f"Required env vars: {', '.join(parsed.env_vars_needed)}",
                    ru=f"Обязательные переменные окружения: {', '.join(parsed.env_vars_needed)}",
                )
            )
        if parsed.notes:
            summary_parts.append(
                choose_user_text(
                    state,
                    en=f"Notes: {parsed.notes}",
                    ru=f"Примечания: {parsed.notes}",
                )
            )

        summary = "\n".join(summary_parts)

        result = {
            "infra_files": infra_files_dicts,
            "deploy_url": deploy_url,
            "current_agent": "devops",
            "messages": [AIMessage(content=summary, name="devops")],
        }
        # Set deploy repo/branch if configured (single-repo strategy)
        if deploy_repo:
            result["deploy_repo"] = deploy_repo
            result["deploy_branch"] = deploy_branch
            result["deploy_status"] = "pending"

        return result

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_devops_response(
        self, content: str, app_name: str, deploy_ip: str
    ) -> DevOpsResponse:
        """Parse the LLM response into a DevOpsResponse.

        Tries JSON extraction first, falls back to code-block parsing.
        """
        # Try direct JSON parse
        try:
            data = self._extract_json(content)
            if data and "infra_files" in data:
                return DevOpsResponse(**data)
        except Exception:
            pass

        # Try structured output via _invoke_structured pattern
        try:
            data = self._extract_json(content)
            if data:
                return DevOpsResponse(**data)
        except Exception:
            pass

        # Fallback: extract code blocks as individual files
        logger.warning("devops.parse.fallback_to_code_blocks")
        return self._parse_code_blocks(content, app_name, deploy_ip)

    @staticmethod
    def _extract_json(content: str) -> dict | None:
        """Extract JSON from content (with or without markdown fences)."""
        # Try stripping markdown fences
        json_match = re.search(
            r'```(?:json)?\s*\n(.*?)\n```',
            content,
            re.DOTALL,
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try raw JSON
        brace_start = content.find("{")
        if brace_start >= 0:
            # Find matching closing brace
            depth = 0
            for i in range(brace_start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(content[brace_start:i + 1])
                        except json.JSONDecodeError:
                            break
        return None

    @staticmethod
    def _parse_code_blocks(
        content: str, app_name: str, deploy_ip: str
    ) -> DevOpsResponse:
        """Fallback parser: extract fenced code blocks as infra files.

        Looks for patterns like:
            ### Dockerfile
            ```dockerfile
            FROM python:3.12-slim
            ...
            ```
        """
        files: list[InfraFileOutput] = []

        # Pattern: header followed by code block
        pattern = re.compile(
            r'###?\s*(?:\d+\.\s*)?'             # header marker
            r'([^\n]+)\n'                        # file name / description
            r'```[a-zA-Z]*\s*\n'                 # opening fence
            r'(.*?)\n```',                       # content
            re.DOTALL,
        )

        for m in pattern.finditer(content):
            header = m.group(1).strip()
            block_content = m.group(2).strip()

            # Determine file path from header
            path = _header_to_filepath(header)
            if path and block_content:
                files.append(InfraFileOutput(path=path, content=block_content))

        deploy_url = f"https://{app_name}.{deploy_ip}.nip.io"
        return DevOpsResponse(
            infra_files=files,
            deploy_url=deploy_url,
            env_vars_needed=[],
            notes="Parsed from code blocks (non-JSON response).",
        )


def _header_to_filepath(header: str) -> str | None:
    """Map a section header to an infrastructure file path.

    Examples:
        "Dockerfile"             -> "Dockerfile"
        "docker-compose.prod.yml" -> "docker-compose.prod.yml"
        "GitHub Actions deploy"   -> ".github/workflows/deploy.yml"
        "deploy.yml"             -> ".github/workflows/deploy.yml"
    """
    h = header.lower().strip().strip("`").strip("*")

    if "dockerfile" in h:
        return "Dockerfile"
    if "docker-compose" in h or "docker_compose" in h or "docker compose" in h:
        if "prod" in h:
            return "docker-compose.prod.yml"
        return "docker-compose.yml"
    if "deploy" in h and ("workflow" in h or "action" in h or "github" in h or "yml" in h or "yaml" in h):
        return ".github/workflows/deploy.yml"
    if "pre-commit" in h or "precommit" in h:
        return ".pre-commit-config.yaml"
    if "nginx" in h:
        return "nginx.conf"
    if "traefik" in h:
        return "traefik.yml"

    # If it looks like a file path already
    if "/" in h or "." in h:
        return h

    return None


# ------------------------------------------------------------------
# Singleton + LangGraph node function
# ------------------------------------------------------------------

_devops_agent = None


def get_devops_agent() -> DevOpsAgent:
    """Get or create the DevOps agent instance."""
    global _devops_agent
    if _devops_agent is None:
        _devops_agent = DevOpsAgent()
    return _devops_agent


def devops_agent(state: DevTeamState, config=None) -> dict:
    """DevOps agent node function for LangGraph.

    Generates infrastructure files for deployment.
    Called after code review is approved, before git_commit.
    """
    import time as _time
    t0 = _time.monotonic()
    logger.info("node.devops.enter")

    agent = get_devops_agent()
    result = agent.generate_infra(state, config=config)

    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("node.devops.exit", elapsed_ms=round(elapsed_ms))

    return result
