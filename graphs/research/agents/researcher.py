"""
Researcher Agent
================

Responsible for:
  - Searching the web for relevant information
  - Fetching and reading source pages
  - Synthesizing findings into a structured report

LangGraph node function: ``researcher_agent(state, config=None) -> dict``
"""

import re

import structlog
from langchain_core.messages import AIMessage

from dev_team.agents.base import BaseAgent, get_llm, create_prompt_template
from dev_team.tools.web import web_search, fetch_url

logger = structlog.get_logger()

# ─────── Prompt loading (from local prompts dir) ───────

_PROMPTS = None


def _load_prompts() -> dict:
    """Load researcher prompts from YAML file."""
    global _PROMPTS
    if _PROMPTS is not None:
        return _PROMPTS

    import yaml
    from pathlib import Path

    prompt_file = Path(__file__).parent.parent / "prompts" / "researcher.yaml"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompt_file}")

    with open(prompt_file, "r", encoding="utf-8") as f:
        _PROMPTS = yaml.safe_load(f)
    logger.debug("researcher.prompts_loaded", keys=list(_PROMPTS.keys()))
    return _PROMPTS


# ─────── Research helpers ──────────────────────────────

def _extract_urls_from_search(search_text: str, max_urls: int = 5) -> list[str]:
    """Extract URLs from search results text."""
    url_pattern = r'https?://[^\s\n)>]+'
    urls = re.findall(url_pattern, search_text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique[:max_urls]


def _do_search(task: str) -> str:
    """Execute web search for the task."""
    try:
        result = web_search.invoke({"query": task, "max_results": 5})
        logger.info("researcher.search_done", results_len=len(result))
        return result
    except Exception as exc:
        logger.error("researcher.search_failed", error=str(exc))
        return f"Search failed: {exc}"


def _fetch_top_urls(search_results: str, max_fetch: int = 3) -> str:
    """Fetch content from top URLs found in search results."""
    urls = _extract_urls_from_search(search_results, max_urls=max_fetch)
    if not urls:
        return "No URLs to fetch."

    contents = []
    for url in urls:
        try:
            content = fetch_url.invoke({"url": url})
            if content and not content.startswith("Failed"):
                # Truncate each page to keep total context manageable
                truncated = content[:3000]
                contents.append(f"### Source: {url}\n{truncated}")
                logger.debug("researcher.url_fetched", url=url, size=len(content))
        except Exception as exc:
            logger.warning("researcher.url_fetch_failed", url=url, error=str(exc))

    return "\n\n".join(contents) if contents else "Could not fetch any URLs."


# ─────── Agent class ──────────────────────────────────


class ResearcherAgent(BaseAgent):
    """Researcher agent: search, fetch, synthesize."""

    def __init__(self):
        prompts = _load_prompts()
        llm = get_llm(role="researcher", temperature=0.5)
        super().__init__(name="researcher", llm=llm, prompts=prompts)

    def research(self, state: dict, config=None) -> dict:
        """Execute the full research pipeline: search → fetch → synthesize."""
        task = state.get("task", "")
        context = state.get("context", "No additional context")
        logger.info("researcher.start", task_len=len(task))

        # 1. Search the web
        search_results = _do_search(task)

        # 2. Fetch top URLs for deeper content
        fetched_content = _fetch_top_urls(search_results)

        # 3. Synthesize with LLM
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["synthesize"],
        )
        chain = prompt | self.llm

        response = self._invoke_chain(chain, {
            "task": task,
            "context": context,
            "search_results": search_results[:8000],  # Limit context size
            "fetched_content": fetched_content[:8000],
        }, config=config)

        report = response.content

        # 4. Extract sources
        sources = []
        urls = _extract_urls_from_search(search_results, max_urls=10)
        for url in urls:
            sources.append({
                "title": url.split("/")[-1][:50] or url[:50],
                "url": url,
                "snippet": "",
            })

        logger.info("researcher.done", report_len=len(report), sources=len(sources))
        return {
            "messages": [AIMessage(content=report, name="researcher")],
            "search_results": search_results,
            "fetched_content": fetched_content,
            "sources": sources,
            "report": report,
            "summary": report[:1000],
            "current_agent": "complete",
        }


# ─────── Singleton + node function ────────────────────

_researcher = None


def get_researcher_agent() -> ResearcherAgent:
    """Get or create the Researcher agent instance."""
    global _researcher
    if _researcher is None:
        _researcher = ResearcherAgent()
    return _researcher


def researcher_agent(state: dict, config=None) -> dict:
    """Researcher agent node function for LangGraph."""
    agent = get_researcher_agent()
    return agent.research(state, config=config)
