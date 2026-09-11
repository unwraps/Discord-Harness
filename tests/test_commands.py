import pytest
from unittest.mock import MagicMock
import discord
from cogs.commands import CommandsCog
from harness.config import ConfigManager
from harness.memory import MemoryManager
from skills.manager import SkillManager


from harness.models import ModelCatalog


@pytest.mark.asyncio
async def test_model_autocomplete(tmp_path):
    config_mgr = ConfigManager(db_path=tmp_path / "test_ac.db")
    await config_mgr.init_db()

    # Add custom provider
    await config_mgr.add_custom_provider(name="opencode", base_url="https://api.opencode.ai/v1")

    model_catalog = ModelCatalog(config_manager=config_mgr)
    # Refresh to pick up custom provider
    await model_catalog.refresh_models()

    cog = CommandsCog(
        bot=MagicMock(),
        config_manager=config_mgr,
        memory_manager=MemoryManager(),
        skill_manager=SkillManager(),
        model_catalog=model_catalog,
    )

    mock_interaction = MagicMock(spec=discord.Interaction)

    # 1. Empty query -> returns default list including custom provider
    choices_empty = await cog.model_autocomplete(mock_interaction, "")
    assert len(choices_empty) <= 25
    assert any("opencode" in c.value for c in choices_empty)
    assert any("deepseek" in c.value for c in choices_empty)

    # 2. Substring query "r1"
    choices_r1 = await cog.model_autocomplete(mock_interaction, "r1")
    assert len(choices_r1) > 0
    assert all("r1" in c.value.lower() or "r1" in c.name.lower() for c in choices_r1)

    # 3. Novel custom model not in list
    choices_custom = await cog.model_autocomplete(mock_interaction, "my-fine-tuned-model")
    assert choices_custom[0].value == "my-fine-tuned-model"
    assert "Custom:" in choices_custom[0].name
