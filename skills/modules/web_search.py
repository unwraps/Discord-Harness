"""
Universal DuckDuckGo Web Search Skill.
Searches the entire open web across all topics: funny content, memes, jokes,
weird news, Reddit discussions, pop culture, entertainment, tech, and current events.
"""

from __future__ import annotations
import asyncio
import logging
import os
import urllib.parse
from typing import Any, Dict, List
import httpx
from lxml import html

from skills.base import skill

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _search_ddg_library(query: str, max_results: int = 4, search_type: str = "all") -> List[Dict[str, str]]:
    """Search using ddgs library across all web content."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results: List[Dict[str, str]] = []

        with DDGS(timeout=8) as ddgs:
            # 1. Primary: Search entire open web (memes, jokes, blogs, forums, news, general sites)
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", "Web Result"),
                    "body": r.get("body", ""),
                    "url": r.get("href") or r.get("url", ""),
                })

            # 2. If search_type is explicitly 'news' and few results were found, augment with news
            if search_type == "news" and len(results) < max_results:
                try:
                    for r in ddgs.news(query, max_results=max_results - len(results)):
                        results.append({
                            "title": f"[News] {r.get('title', '')}",
                            "body": r.get("body", "") or r.get("excerpt", ""),
                            "url": r.get("url") or r.get("href", ""),
                        })
                except Exception:
                    pass

        return results
    except Exception as e:
        logger.debug(f"DDGS library search exception: {e}")
        return []


async def _search_ddg_direct_html(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """Direct DuckDuckGo HTML search fallback (no cookies or tokens needed)."""
    results: List[Dict[str, str]] = []
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        async with httpx.AsyncClient(timeout=7.0, headers=headers) as client:
            resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            if resp.status_code == 200:
                tree = html.fromstring(resp.text)
                bodies = tree.xpath('//div[contains(@class, "result__body")]')
                for b in bodies[:max_results]:
                    link_nodes = b.xpath('.//a[contains(@class, "result__a")]')
                    snippet_nodes = b.xpath('.//a[contains(@class, "result__snippet")]')
                    if link_nodes:
                        title = link_nodes[0].text_content().strip()
                        raw_href = link_nodes[0].get("href", "")
                        parsed = urllib.parse.urlparse(raw_href)
                        qs = urllib.parse.parse_qs(parsed.query)
                        final_url = qs.get("uddg", [raw_href])[0]
                        desc = snippet_nodes[0].text_content().strip() if snippet_nodes else ""
                        results.append({"title": title, "body": desc, "url": final_url})
    except Exception as e:
        logger.debug(f"Direct DuckDuckGo HTML search error: {e}")
    return results


async def _search_wikipedia(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Wikipedia search fallback for facts, people, entities, and general knowledge."""
    results: List[Dict[str, str]] = []
    try:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "utf8": 1,
            "srlimit": max_results,
        }
        headers = {"User-Agent": "DiscordLLMHarness/1.0 (bot@example.com)"}
        async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                for s in data.get("query", {}).get("search", []):
                    title = s.get("title", "")
                    raw_snippet = s.get("snippet", "")
                    clean_snippet = (
                        raw_snippet.replace('<span class="searchmatch">', "")
                        .replace("</span>", "")
                        .replace("&quot;", '"')
                    )
                    page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    results.append({
                        "title": f"Wikipedia: {title}",
                        "body": clean_snippet,
                        "url": page_url,
                    })
    except Exception as e:
        logger.debug(f"Wikipedia fallback error: {e}")
    return results


async def run_search(query: str, max_results: int = 4, search_type: str = "all") -> str:
    """Core search runner supporting general web, funny content, Reddit, and news."""
    clean_query = query.strip()
    if not clean_query:
        return "Search query is empty."

    # Tailor query based on search type if user or LLM requested specific flavor
    effective_query = clean_query
    if search_type == "funny" and not any(k in clean_query.lower() for k in ("funny", "meme", "joke", "humor", "hilarious")):
        effective_query = f"{clean_query} funny memes jokes"
    elif search_type == "discussions" and not any(k in clean_query.lower() for k in ("reddit", "forum", "discussion")):
        effective_query = f"{clean_query} (site:reddit.com OR discussion)"

    raw_results: List[Dict[str, str]] = []

    # 1. DuckDuckGo Open Web Search
    loop = asyncio.get_running_loop()
    raw_results = await loop.run_in_executor(None, _search_ddg_library, effective_query, max_results, search_type)

    # 2. DuckDuckGo Direct HTML Fallback
    if not raw_results:
        raw_results = await _search_ddg_direct_html(effective_query, max_results=max_results)

    # 3. Wikipedia Fallback
    if not raw_results:
        raw_results = await _search_wikipedia(clean_query, max_results=max_results)

    if not raw_results:
        return f"No search results found for: '{clean_query}'. Try trying alternative or broader keywords."

    formatted = []
    for item in raw_results:
        title = item.get("title", "No title")
        body = item.get("body", "No description available.")
        url = item.get("url", "")
        formatted.append(f"### {title}\n{body}\n**Source**: {url}")

    return "\n\n".join(formatted)


@skill(
    name="duckduckgo_search",
    description="Search the entire web with DuckDuckGo for ANYTHING: general topics, funny memes, jokes, weird news, Reddit discussions, pop culture, entertainment, tech, or current events.",
)
async def duckduckgo_search(query: str, max_results: int = 4, search_type: str = "all") -> str:
    """Execute DuckDuckGo open search across all web topics."""
    return await run_search(query, max_results=max_results, search_type=search_type)


@skill(
    name="web_search",
    description="Universal web search for ANYTHING on the internet: funny content, memes, jokes, community discussions, social media, Reddit, pop culture, entertainment, facts, or news. Use this anytime the user asks for information, funny things, memes, recommendations, or current events.",
)
async def web_search(query: str, max_results: int = 4, search_type: str = "all") -> str:
    """Execute universal web search across all web topics."""
    return await run_search(query, max_results=max_results, search_type=search_type)
