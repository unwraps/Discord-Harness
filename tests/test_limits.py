"""Tests for per-user daily token limits (storage + LLM enforcement)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from harness.config import ConfigManager
from harness.llm import LLMEngine
from harness.memory import ConversationSession
from skills.manager import SkillManager


async def _make_config(tmp_path):
    cfg = ConfigManager(db_path=tmp_path / "limits.db")
    await cfg.init_db()
    return cfg


@pytest.mark.asyncio
async def test_limit_defaults_to_unlimited(tmp_path):
    config = await _make_config(tmp_path)
    assert await config.get_user_token_limit(123) == 0
    assert await config.check_daily_limit(123) is None


@pytest.mark.asyncio
async def test_set_get_clear_limit(tmp_path):
    config = await _make_config(tmp_path)
    await config.set_user_token_limit(123, 5000)
    assert await config.get_user_token_limit(123) == 5000
    assert await config.clear_user_token_limit(123) is True
    assert await config.get_user_token_limit(123) == 0
    assert await config.clear_user_token_limit(123) is False


@pytest.mark.asyncio
async def test_negative_limit_means_unlimited(tmp_path):
    config = await _make_config(tmp_path)
    await config.set_user_token_limit(123, -10)
    assert await config.get_user_token_limit(123) == 0


@pytest.mark.asyncio
async def test_usage_accumulates_per_day(tmp_path):
    config = await _make_config(tmp_path)
    await config.add_token_usage(7, 100, 50)
    await config.add_token_usage(7, 25, 25)
    usage = await config.get_token_usage(7)
    assert usage == {"prompt_tokens": 125, "completion_tokens": 75, "total_tokens": 200}


@pytest.mark.asyncio
async def test_usage_isolated_by_user_and_day(tmp_path):
    config = await _make_config(tmp_path)
    await config.add_token_usage(7, 100, 0)
    await config.add_token_usage(8, 100, 0)
    await config.add_token_usage(7, 100, 0, day="2000-01-01")
    assert (await config.get_token_usage(7))["total_tokens"] == 100
    assert (await config.get_token_usage(8))["total_tokens"] == 100
    assert (await config.get_token_usage(7, day="2000-01-01"))["total_tokens"] == 100
    assert (await config.get_token_usage(9))["total_tokens"] == 0


@pytest.mark.asyncio
async def test_check_daily_limit_refusal(tmp_path):
    config = await _make_config(tmp_path)
    await config.set_user_token_limit(7, 100)
    await config.add_token_usage(7, 60, 39)
    assert await config.check_daily_limit(7) is None  # 99 < 100
    await config.add_token_usage(7, 1, 0)
    refusal = await config.check_daily_limit(7)
    assert refusal is not None and "Daily token limit reached" in refusal


def _fake_response(prompt=10, completion=5, content="hello"):
    msg = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=msg)
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.mark.asyncio
async def test_engine_refuses_without_calling_llm(tmp_path):
    config = await _make_config(tmp_path)
    await config.set_user_token_limit(7, 50)
    await config.add_token_usage(7, 50, 0)
    engine = LLMEngine(config_manager=config, skill_manager=SkillManager())
    session = ConversationSession(channel_id=1)
    session.add_user_message("hi")

    with patch("harness.llm.acompletion", new=AsyncMock()) as mock_complete:
        result = await engine.generate_response(session, user_id=7, channel_id=1)
    mock_complete.assert_not_called()
    assert "Daily token limit reached" in result


@pytest.mark.asyncio
async def test_engine_records_usage_on_success(tmp_path):
    config = await _make_config(tmp_path)
    engine = LLMEngine(config_manager=config, skill_manager=SkillManager())
    session = ConversationSession(channel_id=1)
    session.add_user_message("hi")

    with patch("harness.llm.acompletion", new=AsyncMock(return_value=_fake_response(30, 12))):
        result = await engine.generate_response(session, user_id=7, channel_id=1)
    assert result == "hello"
    usage = await config.get_token_usage(7)
    assert usage["total_tokens"] == 42


@pytest.mark.asyncio
async def test_engine_records_dict_style_usage(tmp_path):
    config = await _make_config(tmp_path)
    engine = LLMEngine(config_manager=config, skill_manager=SkillManager())
    session = ConversationSession(channel_id=1)
    session.add_user_message("hi")
    resp = _fake_response(content="hi")
    resp.usage = {"prompt_tokens": 3, "completion_tokens": 4}

    with patch("harness.llm.acompletion", new=AsyncMock(return_value=resp)):
        await engine.generate_response(session, user_id=7, channel_id=1)
    assert (await config.get_token_usage(7))["total_tokens"] == 7
