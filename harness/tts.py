"""
Text-to-Speech Engine for Discord Voice output.

Uses Microsoft Edge TTS (free, no API key) via the `edge-tts` package.
Provides speech-friendly sanitizing so LLM markdown/code/URLs don't get read aloud.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")

# Curated voice choices surfaced in the /voice voice autocomplete.
CURATED_VOICES = [
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
    "en-IN-NeerjaNeural",
    "en-IN-NeerjaExpressiveNeural",
    "en-IN-PrabhatNeural",
]

# Hard cap per utterance so a single TTS request stays fast and conversational.
MAX_SPEECH_CHARS = 1000
# Chunk size when splitting long replies into queued utterances.
CHUNK_SIZE = 900


def sanitize_for_speech(text: str, limit: int = MAX_SPEECH_CHARS) -> str:
    """Strip markdown/code/URLs down to plain speakable text, truncated to `limit`."""
    if not text:
        return ""

    clean = text

    # Drop collapsible thinking sentinels and inline <think> blocks (never read aloud)
    clean = re.sub(r"<!--THINKING_BLOCK-->.*?<!--THINKING_END-->", "", clean, flags=re.DOTALL)
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL)

    # Drop technical media tags and markdown image syntax
    clean = re.sub(r"ATTACH_MEDIA:\s*https?://\S+", "", clean)
    clean = re.sub(r"!\[.*?\]\(.*?\)", "", clean)

    # Code fences -> placeholder (don't read code aloud verbatim)
    clean = re.sub(r"```.*?```", " code snippet. ", clean, flags=re.DOTALL)
    clean = re.sub(r"`([^`]*)`", r"\1", clean)

    # Links [label](url) -> label
    clean = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", clean)

    # Strip markdown/quote/spoiler formatting, keep the words
    clean = clean.replace("**", "").replace("__", "")
    clean = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", clean)  # headings
    clean = re.sub(r"(?m)^\s*>\s?", "", clean)  # blockquotes
    clean = re.sub(r"\|\|", "", clean)  # spoilers
    clean = re.sub(r"(^|\s)[*_~]{1,2}(\S)", r"\1\2", clean)
    clean = re.sub(r"(\S)[*_~]{1,2}($|\s)", r"\1\2", clean)

    # Bare URLs and Discord mentions are noise when spoken
    clean = re.sub(r"https?://\S+", "", clean)
    clean = re.sub(r"<@!?\d+>", "", clean)
    clean = re.sub(r"<@&\d+>", "", clean)
    clean = re.sub(r"<#\d+>", "", clean)
    clean = re.sub(r":\w+:", "", clean)  # :emoji:

    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()

    if len(clean) > limit:
        # Prefer cutting at a sentence boundary so speech doesn't end mid-word
        cut = clean[:limit]
        boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        if boundary > limit // 2:
            clean = cut[: boundary + 1].strip()
        else:
            clean = cut.strip() + "…"

    return clean


def chunk_for_speech(text: str, max_chars: int = CHUNK_SIZE) -> List[str]:
    """Split speakable text into sentence-aligned chunks of at most `max_chars`."""
    clean = sanitize_for_speech(text, limit=100_000)
    if not clean:
        return []
    if len(clean) <= max_chars:
        return [clean]

    sentences = re.split(r"(?<=[.!?])\s+", clean)
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            # A single pathological sentence longer than max_chars gets hard-cut
            while len(sentence) > max_chars:
                chunks.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            current = sentence
    if current:
        chunks.append(current)
    return chunks


class TTSEngine:
    """Synthesize speech via Edge TTS into temp MP3 files."""

    def __init__(self, default_voice: str = DEFAULT_VOICE, tmp_dir: Path | None = None):
        self.default_voice = default_voice
        self.tmp_dir = tmp_dir or Path(tempfile.gettempdir()) / "discord-harness-tts"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, text: str, voice: str | None = None) -> Path:
        """
        Synthesize `text` to an MP3 file. Returns the file path.
        Caller is responsible for deleting the file after playback.
        """
        try:
            import edge_tts  # lazy import so unit tests don't require the package
        except ImportError as e:
            raise RuntimeError(
                "edge-tts is not installed. Run: pip install edge-tts"
            ) from e

        speakable = sanitize_for_speech(text)
        if not speakable:
            raise ValueError("Nothing speakable after sanitizing text.")

        chosen_voice = (voice or self.default_voice).strip()

        fd, tmp_path = tempfile.mkstemp(suffix=".mp3", dir=str(self.tmp_dir))
        os.close(fd)
        out_path = Path(tmp_path)

        communicate = edge_tts.Communicate(speakable, chosen_voice)
        await communicate.save(str(out_path))
        logger.info(f"Synthesized {len(speakable)} chars with voice {chosen_voice} -> {out_path}")
        return out_path
