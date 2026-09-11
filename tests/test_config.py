import pytest
from pathlib import Path
from harness.config import ConfigManager, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_config_manager(tmp_path: Path):
    db_file = tmp_path / "test_harness.db"
    mgr = ConfigManager(db_path=db_file)
    await mgr.init_db()

    # Test default channel config
    cfg = await mgr.get_channel_config(channel_id=999)
    assert cfg.model == DEFAULT_MODEL
    assert cfg.system_prompt == DEFAULT_SYSTEM_PROMPT

    # Test custom channel config update
    await mgr.set_channel_config(
        channel_id=999,
        model="deepseek/deepseek-chat",
        system_prompt="Custom prompt",
        temperature=0.2,
    )
    cfg2 = await mgr.get_channel_config(channel_id=999)
    assert cfg2.model == "deepseek/deepseek-chat"
    assert cfg2.system_prompt == "Custom prompt"
    assert cfg2.temperature == 0.2

    # Test custom API keys
    await mgr.set_api_key(
        scope="user",
        scope_id=12345,
        provider="openrouter",
        api_key="sk-or-test-1234",
    )
    key = await mgr.get_api_key(scope="user", scope_id=12345, provider="openrouter")
    assert key == "sk-or-test-1234"

    # Test custom provider
    await mgr.add_custom_provider(
        name="opencode",
        base_url="https://api.opencode.ai/v1",
        api_key="opencode-key-xyz",
    )
    prov = await mgr.get_custom_provider("opencode")
    assert prov is not None
    base_url, prov_key = prov
    assert base_url == "https://api.opencode.ai/v1"
    assert prov_key == "opencode-key-xyz"

    # Test credential resolution for custom provider
    creds = await mgr.resolve_credentials(model="opencode/deepseek-coder", user_id=12345)
    assert creds["api_base"] == "https://api.opencode.ai/v1"
    assert creds["api_key"] == "opencode-key-xyz"

    # Test credential resolution for user-configured key
    creds_user = await mgr.resolve_credentials(
        model="openrouter/anthropic/claude-3.5-sonnet", user_id=12345
    )
    assert creds_user["api_key"] == "sk-or-test-1234"

    # Test delete key
    deleted = await mgr.delete_api_key(scope="user", scope_id=12345, provider="openrouter")
    assert deleted is True
    assert await mgr.get_api_key(scope="user", scope_id=12345, provider="openrouter") is None

    # Test user bio
    await mgr.set_user_bio(user_id=12345, bio="Senior Software Engineer")
    bio = await mgr.get_user_bio(user_id=12345)
    assert bio == "Senior Software Engineer"

    cleared = await mgr.clear_user_bio(user_id=12345)
    assert cleared is True
    assert await mgr.get_user_bio(user_id=12345) is None

    # Test direct DeepSeek provider key resolution
    await mgr.set_api_key(scope="user", scope_id=12345, provider="deepseek", api_key="sk-ds-userkey")
    ds_creds = await mgr.resolve_credentials(model="deepseek/deepseek-chat", user_id=12345)
    assert ds_creds["api_key"] == "sk-ds-userkey"

    ds_creds_bare = await mgr.resolve_credentials(model="deepseek-chat", user_id=12345)
    assert ds_creds_bare["api_key"] == "sk-ds-userkey"

    # Test OpenRouter DeepSeek routing
    await mgr.set_api_key(scope="user", scope_id=12345, provider="openrouter", api_key="sk-or-userkey")
    or_ds_creds = await mgr.resolve_credentials(model="openrouter/deepseek/deepseek-chat", user_id=12345)
    assert or_ds_creds["api_key"] == "sk-or-userkey"

