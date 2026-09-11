"""
GIF and Image Search Skills for Discord.
Enables the bot to find animated GIFs and images on the web
and return direct links that embed and display natively in Discord chat.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Optional

from skills.base import skill

logger = logging.getLogger(__name__)


def _fetch_ddg_images(query: str, max_results: int = 4) -> List[Dict[str, Any]]:
    """Synchronous worker to fetch images/gifs using ddgs."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            return list(ddgs.images(query, max_results=max_results))
    except Exception as e:
        logger.error(f"DDGS image search error for '{query}': {e}")
        return []


@skill(
    name="search_gif",
    description="Search for animated GIFs. Returns multiple numbered GIF options (titles & URLs) so you can pick the best match or request a specific index.",
    enabled_by_default=True,
)
async def search_gif(query: str, index: int = 1) -> str:
    """
    Search for an animated GIF.

    Args:
        query: Search term for the GIF (e.g. 'cat dancing', 'facepalm', 'celebration', 'mind blown').
        index: Which result number to pick by default (1-based, default 1). Use 2, 3, etc. if user wants another or different result.
    """
    clean_q = query.strip()
    search_term = clean_q if "gif" in clean_q.lower() else f"{clean_q} gif"

    results = await asyncio.to_thread(_fetch_ddg_images, search_term, max_results=8)

    if not results:
        # Retry with simpler query
        results = await asyncio.to_thread(_fetch_ddg_images, f"{clean_q} animated gif", max_results=6)

    if not results:
        return f"No GIFs found for '{query}'. Try a different keyword."

    # Filter/prioritize genuine gif URLs or known gif domains
    gif_candidates = []
    for r in results:
        img_url = r.get("image", "")
        if (
            img_url.lower().endswith(".gif")
            or "tenor.com" in img_url.lower()
            or "giphy.com" in img_url.lower()
            or "gif" in img_url.lower()
        ):
            gif_candidates.append(r)

    candidates = gif_candidates if gif_candidates else results

    # Select candidate based on index (1-based)
    chosen_idx = max(1, min(index, len(candidates))) - 1
    selected = candidates[chosen_idx]
    primary_url = selected.get("image", "")

    # Format all candidate options for the LLM to inspect and choose from
    options_text = []
    for i, c in enumerate(candidates[:5], 1):
        t = c.get("title", f"GIF #{i}")
        u = c.get("image", "")
        marker = " (SELECTED)" if (i - 1) == chosen_idx else ""
        options_text.append(f"[{i}] {t}{marker}\n    URL: {u}")

    return (
        f"ATTACH_MEDIA: {primary_url}\n"
        f"Found {len(candidates)} GIF option(s) for '{query}':\n\n"
        + "\n\n".join(options_text)
        + f"\n\n[Default Selected: Option {chosen_idx + 1} ({primary_url})]\n"
        f"Note to Assistant: You can pick any of the above options by including that option's URL in your reply. "
        f"The bot will automatically download and attach the chosen GIF file directly to the Discord chat."
    )


@skill(
    name="search_image",
    description="Search the web for photos, illustrations, artwork, wallpapers, or diagrams. Returns multiple numbered image options so you can pick the best match or request a specific index.",
    enabled_by_default=True,
)
async def search_image(query: str, index: int = 1) -> str:
    """
    Search for a photo or image.

    Args:
        query: Description or name of the image (e.g. 'red panda', 'cyberpunk city skyline', 'James Webb telescope nebula').
        index: Which result number to pick by default (1-based, default 1). Use 2, 3, etc. if user wants another or different result.
    """
    clean_q = query.strip()
    results = await asyncio.to_thread(_fetch_ddg_images, clean_q, max_results=6)

    if not results:
        return f"No images found for '{query}'. Try different keywords."

    # Select candidate based on index (1-based)
    chosen_idx = max(1, min(index, len(results))) - 1
    selected = results[chosen_idx]
    primary_url = selected.get("image", "")

    # Format candidate options for the LLM
    options_text = []
    for i, c in enumerate(results[:5], 1):
        t = c.get("title", f"Image #{i}")
        u = c.get("image", "")
        marker = " (SELECTED)" if (i - 1) == chosen_idx else ""
        options_text.append(f"[{i}] {t}{marker}\n    URL: {u}")

    return (
        f"ATTACH_MEDIA: {primary_url}\n"
        f"Found {len(results)} image option(s) for '{query}':\n\n"
        + "\n\n".join(options_text)
        + f"\n\n[Default Selected: Option {chosen_idx + 1} ({primary_url})]\n"
        f"Note to Assistant: You can pick any of the above options by including that option's URL in your reply. "
        f"The bot will automatically download and attach the chosen image file directly to the Discord chat."
    )
