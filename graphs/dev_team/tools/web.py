"""
Web Tools
=========

Internet access tools for agents:

- ``web_search``    — DuckDuckGo search
- ``fetch_url``     — Fetch and extract main text from a web page
- ``download_file`` — Download a text file from URL

All tools are decorated with ``@tool`` and can be bound to LLM agents
via ``llm.bind_tools([web_search, fetch_url])``.
"""

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()

# Maximum text size returned to avoid flooding the LLM context
_MAX_TEXT_CHARS = 10_000
_MAX_FILE_BYTES = 1_000_000  # 1 MB


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo.

    Returns titles, URLs, and snippets for the top results.

    Args:
        query: Search query string.
        max_results: Maximum number of results (default 5).
    """
    from duckduckgo_search import DDGS

    logger.info("tool.web_search", query=query, max_results=max_results)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        logger.error("tool.web_search.error", error=str(exc))
        return f"Search failed: {exc}"

    if not results:
        return "No results found."

    return "\n\n".join(
        f"**{r['title']}**\n{r['href']}\n{r['body']}"
        for r in results
    )


@tool
def fetch_url(url: str) -> str:
    """Fetch a web page and extract its main text content.

    Uses ``trafilatura`` for content extraction.  Falls back to raw
    text (truncated) if extraction fails.

    Args:
        url: Full URL to fetch.
    """
    import httpx
    import trafilatura

    logger.info("tool.fetch_url", url=url)
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        logger.error("tool.fetch_url.error", url=url, error=str(exc))
        return f"Failed to fetch URL: {exc}"

    text = trafilatura.extract(response.text) or response.text[:5000]
    return text[:_MAX_TEXT_CHARS]


@tool
def download_file(url: str) -> str:
    """Download a file from URL and return its content as text.

    Only suitable for text files.  Binary files or files larger than
    1 MB return an error message instead.

    Args:
        url: Full URL to download.
    """
    import httpx

    logger.info("tool.download_file", url=url)
    try:
        response = httpx.get(url, timeout=60, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        logger.error("tool.download_file.error", url=url, error=str(exc))
        return f"Failed to download: {exc}"

    if len(response.content) > _MAX_FILE_BYTES:
        return f"File too large: {len(response.content):,} bytes (limit {_MAX_FILE_BYTES:,})"

    return response.text[:_MAX_TEXT_CHARS]
