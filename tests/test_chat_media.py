import pytest
from cogs.chat import extract_media_url


def test_extract_media_url_from_tool_message():
    session_messages = [
        {"role": "user", "content": "send a dancing cat gif"},
        {
            "role": "tool",
            "content": "ATTACH_MEDIA: https://media.tenor.com/5BYK-WS0__gAAAAM/cool-fun.gif\nFound GIF: Dancing Cat",
        },
    ]
    url = extract_media_url(session_messages, "Here is a cat dancing for you!")
    assert url == "https://media.tenor.com/5BYK-WS0__gAAAAM/cool-fun.gif"


def test_extract_media_url_from_response_text():
    session_messages = [
        {"role": "user", "content": "send a gif"},
    ]
    response_text = "Check out this: https://example.com/dance.gif"
    url = extract_media_url(session_messages, response_text)
    assert url == "https://example.com/dance.gif"


def test_extract_media_url_none():
    session_messages = [
        {"role": "user", "content": "hello"},
    ]
    url = extract_media_url(session_messages, "Hello! How can I help you today?")
    assert url is None


def test_extract_media_url_model_can_pick_other_result():
    # Tool output gave option 1 as default
    session_messages = [
        {"role": "user", "content": "send another gif of triple h"},
        {
            "role": "tool",
            "content": (
                "ATTACH_MEDIA: https://tenor.com/option1.gif\n"
                "[1] Triple H entrance 1: https://tenor.com/option1.gif\n"
                "[2] Triple H entrance 2: https://tenor.com/option2.gif\n"
            ),
        },
    ]
    # But model explicitly chose Option 2!
    response_text = "Here is another great entrance for you! https://tenor.com/option2.gif"
    url = extract_media_url(session_messages, response_text)
    assert url == "https://tenor.com/option2.gif"


def test_thinking_toggle_view():
    from cogs.chat import ThinkingToggleView
    view = ThinkingToggleView(main_text="The answer is 42", reasoning_text="Thinking step 1")
    assert view.main_text == "The answer is 42"
    assert view.reasoning_text == "Thinking step 1"
    assert view.is_expanded is False
    assert len(view.children) == 1
    assert view.children[0].label == "View Thought Process"


