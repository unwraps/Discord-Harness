"""Tests for TTS text sanitizing/chunking (no network; synthesize not exercised)."""

from harness.tts import chunk_for_speech, sanitize_for_speech


def test_sanitize_strips_markdown_and_urls():
    text = "Hello **world**! Check https://example.com and `code()` plus ```python\nx=1\n```"
    clean = sanitize_for_speech(text)
    assert "https://example.com" not in clean
    assert "**" not in clean
    assert "```" not in clean
    assert "Hello" in clean and "world" in clean


def test_sanitize_drops_thinking_and_media_tags():
    text = "<!--THINKING_BLOCK-->\nsecret\n<!--THINKING_END-->\nHi\nATTACH_MEDIA: https://x/y.gif"
    clean = sanitize_for_speech(text)
    assert "secret" not in clean
    assert "ATTACH_MEDIA" not in clean
    assert "Hi" in clean


def test_sanitize_truncates_long_text():
    long_text = "Hello world. " * 200
    clean = sanitize_for_speech(long_text, limit=100)
    assert len(clean) <= 105  # limit + room for ellipsis


def test_chunk_splits_long_text():
    long_text = "First sentence. " + "Another sentence here. " * 100
    chunks = chunk_for_speech(long_text, max_chars=100)
    assert len(chunks) > 1
    assert all(len(c) <= 110 for c in chunks)


def test_chunk_empty_returns_empty():
    assert chunk_for_speech("   ") == []
    assert sanitize_for_speech("") == ""
