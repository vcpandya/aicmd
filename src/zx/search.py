"""Web search providers for enriching AI context.

Supports Jina AI Search and Google Custom Search API.
"""

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str


@dataclass
class SearchResponse:
    """Aggregated search response."""
    query: str
    results: list[SearchResult]
    raw_context: str  # Pre-formatted context string for LLM consumption

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0


def _get_search_config() -> dict:
    """Resolve search provider and API key from config and env vars."""
    from .config import ZxConfig

    config = ZxConfig.load()
    provider = config.search_provider

    if not provider:
        return {"provider": "", "api_key": "", "cx": ""}

    if provider == "jina":
        api_key = os.environ.get("JINA_API_KEY", "").strip()
        if not api_key:
            api_key = config.provider_keys.get("jina", "")
        return {"provider": "jina", "api_key": api_key, "cx": ""}

    if provider == "google":
        api_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
        if not api_key:
            api_key = config.provider_keys.get("google_search", "")
        cx = os.environ.get("GOOGLE_SEARCH_CX", "").strip()
        if not cx:
            cx = config.provider_keys.get("google_search_cx", "")
        return {"provider": "google", "api_key": api_key, "cx": cx}

    return {"provider": "", "api_key": "", "cx": ""}


def search_jina(query: str, api_key: str, max_results: int = 5) -> SearchResponse:
    """Search using Jina AI Search API (s.jina.ai)."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://s.jina.ai/{encoded_query}"

    headers = {
        "Accept": "application/json",
        "X-Retain-Images": "none",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return SearchResponse(query=query, results=[], raw_context=f"Search failed: {e}")

    results = []
    raw_lines = []

    items = data.get("data", [])[:max_results]
    for item in items:
        title = item.get("title", "")
        link = item.get("url", "")
        snippet = item.get("description", "") or item.get("content", "")[:300]

        results.append(SearchResult(title=title, url=link, snippet=snippet))
        raw_lines.append(f"- {title}\n  {snippet[:200]}")

    raw_context = f"Web search results for '{query}':\n" + "\n".join(raw_lines) if raw_lines else ""
    return SearchResponse(query=query, results=results, raw_context=raw_context)


def search_google(query: str, api_key: str, cx: str, max_results: int = 5) -> SearchResponse:
    """Search using Google Custom Search JSON API."""
    if not api_key or not cx:
        return SearchResponse(
            query=query, results=[],
            raw_context="Google Search not configured (missing API key or CX).",
        )

    params = urllib.parse.urlencode({
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(max_results, 10),
    })
    url = f"https://www.googleapis.com/customsearch/v1?{params}"

    req = urllib.request.Request(url, headers={"Accept": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return SearchResponse(query=query, results=[], raw_context=f"Search failed: {e}")

    results = []
    raw_lines = []

    for item in data.get("items", [])[:max_results]:
        title = item.get("title", "")
        link = item.get("link", "")
        snippet = item.get("snippet", "")

        results.append(SearchResult(title=title, url=link, snippet=snippet))
        raw_lines.append(f"- {title}\n  {snippet[:200]}")

    raw_context = f"Web search results for '{query}':\n" + "\n".join(raw_lines) if raw_lines else ""
    return SearchResponse(query=query, results=results, raw_context=raw_context)


def web_search(query: str, max_results: int = 5) -> SearchResponse:
    """Run a web search using the configured provider.

    Automatically resolves provider and credentials from config/env.
    Returns empty SearchResponse if no provider is configured.
    """
    cfg = _get_search_config()

    if not cfg["provider"]:
        return SearchResponse(query=query, results=[], raw_context="")

    if not cfg["api_key"]:
        return SearchResponse(
            query=query, results=[],
            raw_context=f"Search provider '{cfg['provider']}' configured but no API key found.",
        )

    if cfg["provider"] == "jina":
        return search_jina(query, cfg["api_key"], max_results)
    elif cfg["provider"] == "google":
        return search_google(query, cfg["api_key"], cfg["cx"], max_results)

    return SearchResponse(query=query, results=[], raw_context="")


def is_search_available() -> bool:
    """Check if a search provider is configured and has credentials."""
    cfg = _get_search_config()
    return bool(cfg["provider"] and cfg["api_key"])


# ── Heuristics for when to search ─────────────────────────────────────────────

_SEARCH_KEYWORDS = {
    "latest", "newest", "recent", "today",
    "recommended", "tutorial",
    "download", "release",
    "documentation", "docs", "library",
    "troubleshoot", "workaround",
    "alternative", "compare", "versus",
    "official", "guide",
}


def should_search(prompt: str) -> bool:
    """Heuristic: would this prompt benefit from web search context?

    Returns True if the prompt seems to ask about external/current information
    that the LLM might not have or might be outdated on.
    """
    lower = prompt.lower()
    words = set(lower.split())

    # Check for search-worthy single keywords
    if words & _SEARCH_KEYWORDS:
        return True

    # Check for multi-word phrases
    search_phrases = [
        "how to", "how do", "best way", "what is the latest",
        "is there a", "where can i", "what version",
        "latest version", "current version",
    ]
    for phrase in search_phrases:
        if phrase in lower:
            return True

    return False


def build_search_query(prompt: str) -> str:
    """Extract a good search query from a user prompt.

    Strips shell/command-specific language and focuses on the informational need.
    """
    # Remove common command prefixes
    noise = [
        "please", "can you", "i want to", "i need to", "help me",
        "run a command to", "write a command", "give me",
    ]
    query = prompt.lower()
    for word in noise:
        query = query.replace(word, "")

    return query.strip()
