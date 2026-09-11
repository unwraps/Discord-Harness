"""
Discord Markdown Formatter and Message Splitter.
Ensures responses stay strictly within Discord's 2000-character limit
and properly closes and reopens code fences (```) across chunks.
"""

from __future__ import annotations
import re
import time
from typing import List


def split_message(content: str, limit: int = 1950) -> List[str]:
    """
    Split long markdown content into chunks of at most `limit` characters.
    Properly handles markdown code fences so code blocks remain valid across chunks.
    """
    if len(content) <= limit:
        return [content]

    chunks: List[str] = []
    lines = content.split("\n")
    current_chunk = ""
    in_code_block = False
    code_block_lang = ""

    for line in lines:
        # Check if line toggles a code block
        code_fence_match = re.match(r"^```(\w*)", line.strip())

        # Estimated size if we append this line
        additional_len = len(line) + 1  # line + newline
        closing_fence_len = (len(f"\n```") if in_code_block else 0)

        if len(current_chunk) + additional_len + closing_fence_len > limit:
            # Need to close chunk
            if in_code_block:
                current_chunk += "\n```"
                chunks.append(current_chunk)
                # Re-open code fence in next chunk
                current_chunk = f"```{code_block_lang}\n" + line
            else:
                chunks.append(current_chunk)
                current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line

        # Update code block state
        if code_fence_match:
            if not in_code_block:
                in_code_block = True
                code_block_lang = code_fence_match.group(1)
            else:
                in_code_block = False
                code_block_lang = ""

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


class StreamThrottle:
    """Throttle live message edits to avoid hitting Discord's rate limits."""

    def __init__(self, min_interval_sec: float = 1.2):
        self.min_interval = min_interval_sec
        self.last_update = 0.0

    def should_update(self) -> bool:
        """Check if enough time has elapsed since last edit."""
        now = time.monotonic()
        if now - self.last_update >= self.min_interval:
            self.last_update = now
            return True
        return False


def format_with_thinking(
    content: str,
    reasoning: Optional[str] = None,
    mode: str = "spoiler",
) -> str:
    """
    Format message with reasoning / thinking tokens.
    Modes:
      - 'spoiler': Enclose thinking in Discord ||...|| spoiler tag (click to reveal).
      - 'visible': Format thinking as a clean blockquote.
      - 'hide': Completely omit thinking from Discord message.
    """
    clean_content = content
    extracted_reasoning = reasoning

    # If reasoning not provided directly, check for inline <think>...</think>
    if not extracted_reasoning and clean_content:
        think_match = re.search(r"<think>(.*?)</think>", clean_content, flags=re.DOTALL)
        if think_match:
            extracted_reasoning = think_match.group(1).strip()
            clean_content = re.sub(r"<think>.*?</think>", "", clean_content, flags=re.DOTALL).strip()

    if not extracted_reasoning or mode == "hide":
        return clean_content

    extracted_reasoning = extracted_reasoning.strip()
    if not extracted_reasoning:
        return clean_content

    if mode in ("button", "collapsible"):
        return f"<!--THINKING_BLOCK-->\n{extracted_reasoning}\n<!--THINKING_END-->\n{clean_content}"
    elif mode == "spoiler":
        thinking_block = f"> 💭 **Thinking Process** *(click to reveal)*:\n||{extracted_reasoning}||\n\n"
    elif mode == "visible":
        quoted = "\n".join(f"> {line}" for line in extracted_reasoning.splitlines())
        thinking_block = f"💭 **Thinking Process:**\n{quoted}\n\n"
    else:
        thinking_block = ""

    return thinking_block + clean_content
