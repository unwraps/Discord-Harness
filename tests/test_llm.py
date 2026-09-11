from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from harness.config import ConfigManager
from harness.llm import LLMEngine
from harness.memory import ConversationSession
from skills.manager import SkillManager
from skills.modules.calculator import calculate


class MockFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.function = MockFunction(name, arguments)


class MockMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class MockChoice:
    def __init__(self, message):
        self.message = message


class MockResponse:
    def __init__(self, message):
        self.choices = [MockChoice(message)]


@pytest.mark.asyncio
async def test_llm_tool_calling_loop(tmp_path):
    config_mgr = ConfigManager(db_path=tmp_path / "test.db")
    await config_mgr.init_db()

    skill_mgr = SkillManager()
    skill_mgr.register(calculate)

    engine = LLMEngine(config_manager=config_mgr, skill_manager=skill_mgr)
    session = ConversationSession(channel_id=42)
    session.add_user_message("What is 25 * 4?")

    # Step 1: model returns tool call for calculate
    resp_step1 = MockResponse(
        MockMessage(
            content=None,
            tool_calls=[MockToolCall("call_123", "calculator", '{"expression": "25 * 4"}')],
        )
    )
    # Step 2: model returns final text after getting tool result
    resp_step2 = MockResponse(
        MockMessage(content="25 * 4 is 100.", tool_calls=None)
    )

    statuses = []

    async def on_status(s: str):
        statuses.append(s)

    with patch("harness.llm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.side_effect = [resp_step1, resp_step2]

        final_answer = await engine.generate_response(
            session=session,
            channel_id=42,
            on_status=on_status,
        )

        assert final_answer == "25 * 4 is 100."
        assert mock_acompletion.call_count == 2
        assert any("calculator" in s for s in statuses)

        # Check that session history now has: user -> assistant (tool call) -> tool (100) -> assistant (final)
        messages = session.get_messages()
        # [0] is system prompt, [1] is user, [2] is assistant tool call, [3] is tool output, [4] is assistant final
        assert len(messages) >= 4
        tool_results = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_results) == 1
        assert tool_results[0]["content"] == "100"


@pytest.mark.asyncio
async def test_llm_reasoning_tokens(tmp_path):
    config_mgr = ConfigManager(db_path=tmp_path / "test_reasoning.db")
    await config_mgr.init_db()
    # Default thinking mode is spoiler
    await config_mgr.set_channel_config(channel_id=99, thinking_mode="spoiler")

    skill_mgr = SkillManager()
    engine = LLMEngine(config_manager=config_mgr, skill_manager=skill_mgr)
    session = ConversationSession(channel_id=99)
    session.add_user_message("Solve this puzzle.")

    msg = MockMessage(content="The solution is 7.")
    msg.reasoning_content = "First I analyzed the clues and concluded 7."
    resp = MockResponse(msg)

    with patch("harness.llm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = resp

        output = await engine.generate_response(session=session, channel_id=99)
        assert "||First I analyzed the clues and concluded 7.||" in output
        assert "The solution is 7." in output
