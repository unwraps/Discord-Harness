import base64
import pytest
from unittest.mock import AsyncMock, MagicMock
from harness.memory import ConversationSession
from cogs.chat import extract_message_images


def test_session_multimodal_message():
    session = ConversationSession(channel_id=123)
    images = [
        "data:image/png;base64,samplebase64data",
        "https://example.com/photo.jpg",
    ]
    session.add_user_message("What is this?", images=images)
    msgs = session.get_messages()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert len(content) == 3
    assert content[0] == {"type": "text", "text": "What is this?"}
    assert content[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,samplebase64data"}}
    assert content[2] == {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}}


@pytest.mark.asyncio
async def test_extract_message_images_attachment():
    mock_attachment = MagicMock()
    mock_attachment.filename = "screenshot.png"
    mock_attachment.content_type = "image/png"
    mock_attachment.size = 100
    mock_attachment.url = "https://cdn.discordapp.com/attachments/123/screenshot.png"
    mock_attachment.read = AsyncMock(return_value=b"fake_image_bytes")

    mock_msg = MagicMock()
    mock_msg.attachments = [mock_attachment]
    mock_msg.reference = None
    mock_msg.content = "Look at this error"

    images = await extract_message_images(mock_msg)
    assert len(images) == 1
    assert images[0].startswith("data:image/png;base64,")
    decoded = base64.b64decode(images[0].split(",")[1])
    assert decoded == b"fake_image_bytes"


@pytest.mark.asyncio
async def test_extract_message_images_text_url():
    mock_msg = MagicMock()
    mock_msg.attachments = []
    mock_msg.reference = None
    mock_msg.content = "Check out https://example.com/cat.jpg for reference"

    images = await extract_message_images(mock_msg)
    assert len(images) == 1
    assert images[0] == "https://example.com/cat.jpg"
