"""
Safe Webpage Content Fetcher Skill.
Extracts clean, readable text from public URLs with SSRF & security protections.
"""

from __future__ import annotations
import ipaddress
import logging
import re
import socket
import urllib.parse
from typing import Tuple
import httpx
from lxml import html

from skills.base import skill

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DISALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "169.254.169.254",
    "metadata.google.internal",
}


def _is_safe_url(url: str) -> Tuple[bool, str]:
    """Validate that the URL uses HTTP/HTTPS and does not target private or local networks."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported protocol '{parsed.scheme}'. Only 'http' and 'https' are allowed."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL does not contain a valid hostname."

    if hostname in DISALLOWED_HOSTS:
        return False, f"Access to '{hostname}' is blocked for security reasons."

    # Check for direct IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, "Access to private or local network addresses is blocked."
    except ValueError:
        # Hostname is a domain name: check resolved IP to prevent SSRF via DNS rebinding
        try:
            resolved_ip_str = socket.gethostbyname(hostname)
            resolved_ip = ipaddress.ip_address(resolved_ip_str)
            if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local or resolved_ip.is_reserved:
                return False, f"Domain '{hostname}' resolves to private IP ({resolved_ip_str}) which is blocked."
        except Exception:
            pass

    return True, ""


def _clean_html(raw_html: str, max_chars: int = 4000) -> str:
    """Parse HTML and extract readable text without scripts, styles, or navigation clutter."""
    try:
        tree = html.fromstring(raw_html)
        # Remove noisy tags: script, style, nav, footer, noscript, svg, header
        for tag in tree.xpath("//script | //style | //nav | //footer | //noscript | //svg | //header"):
            tag.drop_tree()

        # Get title
        title_nodes = tree.xpath("//title/text()")
        title = title_nodes[0].strip() if title_nodes else ""

        # Extract text content
        text = tree.text_content()
        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        result = f"Title: {title}\n\n{text}" if title else text
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n\n[Content truncated at {max_chars} characters...]"
        return result
    except Exception:
        # Fallback to regex cleaning if HTML parsing fails
        clean = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) > max_chars:
            clean = clean[:max_chars] + "..."
        return clean


@skill(
    name="fetch_webpage",
    description="Fetch and read the text content of a public URL (e.g. articles, blogs, documentation, forum posts).",
    enabled_by_default=True,
)
async def fetch_webpage(url: str) -> str:
    """
    Fetch and read a public webpage by URL.

    Args:
        url: The full HTTP or HTTPS URL to read.
    """
    is_safe, error_msg = _is_safe_url(url)
    if not is_safe:
        return f"Security Error: {error_msg}"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=False) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"HTTP {resp.status_code} Error: Unable to fetch page ({resp.reason_phrase})"

            content_type = resp.headers.get("content-type", "").lower()
            if "json" in content_type:
                text = resp.text[:3000]
                return f"JSON Content:\n{text}"

            if "text" not in content_type and "html" not in content_type and "xml" not in content_type:
                return f"Unsupported content type '{content_type}'. Only web pages, JSON, and text are supported."

            clean_text = _clean_html(resp.text)
            if not clean_text or len(clean_text) < 30:
                return "The webpage returned minimal text (it may require JavaScript execution to render)."

            return clean_text

    except httpx.TimeoutException:
        return "Error: Request timed out while fetching the webpage (server took >10s to respond)."
    except httpx.RequestError as e:
        return f"Error fetching webpage: {type(e).__name__}: {str(e)}"
    except Exception as e:
        return f"Unexpected error reading webpage: {str(e)}"
