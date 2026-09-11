from harness.formatter import split_message, StreamThrottle
import time


def test_split_message_short():
    msg = "Hello, world!"
    chunks = split_message(msg, limit=100)
    assert chunks == ["Hello, world!"]


def test_split_message_long_plain():
    long_msg = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
    chunks = split_message(long_msg, limit=15)
    assert len(chunks) > 1
    # Check that recombined lines have all parts
    recombined = "\n".join(chunks)
    for line in ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5"]:
        assert line in recombined


def test_split_message_with_codeblock():
    code = (
        "Here is some python code:\n"
        "```python\n"
        "def hello():\n"
        "    print('Hello World')\n"
        "    return 42\n"
        "```\n"
        "End of message."
    )
    # Force split inside the code block
    chunks = split_message(code, limit=40)
    assert len(chunks) >= 2

    # Verify first chunk was closed with ```
    assert chunks[0].endswith("```")
    # Verify second chunk was opened with ```python
    assert chunks[1].startswith("```python")


def test_stream_throttle():
    throttle = StreamThrottle(min_interval_sec=0.1)
    assert throttle.should_update() is True
    assert throttle.should_update() is False
    time.sleep(0.12)
    assert throttle.should_update() is True


def test_format_with_thinking_spoiler():
    from harness.formatter import format_with_thinking
    content = "The answer is 42."
    reasoning = "Step 1: calculate 6 * 7 = 42."
    formatted = format_with_thinking(content, reasoning=reasoning, mode="spoiler")
    assert "||Step 1: calculate 6 * 7 = 42.||" in formatted
    assert "The answer is 42." in formatted


def test_format_with_thinking_visible():
    from harness.formatter import format_with_thinking
    content = "The answer is 42."
    reasoning = "Thought 1\nThought 2"
    formatted = format_with_thinking(content, reasoning=reasoning, mode="visible")
    assert "> Thought 1" in formatted
    assert "> Thought 2" in formatted
    assert "The answer is 42." in formatted


def test_format_with_thinking_inline_think_tags():
    from harness.formatter import format_with_thinking
    raw_content = "<think>Let me ponder this.</think>Done thinking!"
    formatted = format_with_thinking(raw_content, reasoning=None, mode="spoiler")
    assert "||Let me ponder this.||" in formatted
    assert "Done thinking!" in formatted
    assert "<think>" not in formatted

    # Test hide mode
    hidden = format_with_thinking(raw_content, reasoning=None, mode="hide")
    assert hidden == "Done thinking!"

    # Test button / collapsible mode
    button_mode = format_with_thinking(raw_content, reasoning=None, mode="button")
    assert "<!--THINKING_BLOCK-->" in button_mode
    assert "Let me ponder this." in button_mode
    assert "<!--THINKING_END-->" in button_mode
    assert "Done thinking!" in button_mode
