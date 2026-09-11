"""
Slash Commands Cog: Configuration commands for models, keys, custom providers,
system prompts, memory reset, and modular skills.
"""

from __future__ import annotations
import logging
from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from harness.config import ConfigManager, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT
from harness.memory import MemoryManager
from harness.models import ModelCatalog
from skills.manager import SkillManager

import aiosqlite

logger = logging.getLogger(__name__)

PROVIDERS = [
    "openrouter",
    "deepseek",
    "openai",
    "anthropic",
    "gemini",
    "groq",
    "mistral",
    "custom",
]


class CommandsCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        config_manager: ConfigManager,
        memory_manager: MemoryManager,
        skill_manager: SkillManager,
        model_catalog: ModelCatalog,
    ):
        self.bot = bot
        self.config = config_manager
        self.memory = memory_manager
        self.skills = skill_manager
        self.model_catalog = model_catalog

    # --- /model command with live API autocomplete ---

    @app_commands.command(
        name="model",
        description="Switch active LLM model with live API autocomplete or view current model",
    )
    @app_commands.describe(model_name="Select from live autocomplete or type any custom model identifier")
    async def model_cmd(
        self, interaction: discord.Interaction, model_name: Optional[str] = None
    ) -> None:
        if model_name:
            clean_model = model_name.strip()
            # If user types bare deepseek-chat or deepseek-reasoner, auto-prefix with deepseek/
            if clean_model.lower().startswith("deepseek-") and not (
                clean_model.lower().startswith("deepseek/") or clean_model.lower().startswith("openrouter/")
            ):
                clean_model = f"deepseek/{clean_model}"
            await self.config.set_channel_config(channel_id=interaction.channel_id, model=clean_model)
            await interaction.response.send_message(
                f"✅ Active model updated to: `{clean_model}` for this channel/thread."
            )
        else:
            cfg = await self.config.get_channel_config(interaction.channel_id)
            total_models = len(self.model_catalog.models)
            embed = discord.Embed(
                title="🤖 Model Settings",
                description=(
                    f"Current active model: `{cfg.model}`\n\n"
                    f"✨ **{total_models} live models** fetched from your connected providers.\n"
                    f"Type `/model <name>` to search with live autocomplete!"
                ),
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="🧠 Top Reasoning / Thinking Models",
                value="`deepseek/deepseek-reasoner`\n`openrouter/deepseek/deepseek-r1`\n`claude-3-7-sonnet-20250219`\n`o3-mini`",
                inline=False,
            )
            embed.add_field(
                name="⚡ Top Fast & Versatile Models",
                value="`deepseek/deepseek-chat`\n`gpt-4o` | `gpt-4o-mini`\n`gemini/gemini-2.0-flash`\n`claude-3-5-sonnet-20241022`",
                inline=False,
            )
            embed.add_field(
                name="🔄 Refresh Live Models",
                value="Run `/models_refresh` anytime to pull the newest models from OpenRouter/DeepSeek/Ollama.",
                inline=False,
            )
            await interaction.response.send_message(embed=embed)

    @model_cmd.autocomplete("model_name")
    async def model_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        # Search live models catalog fetched from provider APIs
        matches = self.model_catalog.search(current, limit=25)
        choices = [app_commands.Choice(name=m, value=m) for m in matches]

        # If user types something not in catalog, offer custom option at top
        clean_current = current.strip()
        if clean_current and not any(c.value.lower() == clean_current.lower() for c in choices):
            choices.insert(
                0,
                app_commands.Choice(name=f"Custom: {clean_current}", value=clean_current),
            )

        return choices[:25]

    @app_commands.command(
        name="setmodel",
        description="Switch active LLM model (same as /model <name>)",
    )
    @app_commands.describe(model_name="Select from live autocomplete or type any custom model identifier")
    async def setmodel_cmd(
        self, interaction: discord.Interaction, model_name: str
    ) -> None:
        await self.model_cmd(interaction, model_name=model_name)

    @setmodel_cmd.autocomplete("model_name")
    async def setmodel_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return await self.model_autocomplete(interaction, current)


    @app_commands.command(name="models_refresh", description="Refresh live models list from all connected provider APIs")
    async def models_refresh_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        count = await self.model_catalog.refresh_models()
        await interaction.followup.send(
            f"🔄 Refreshed live model catalog! **{count} models** currently available in autocomplete.",
            ephemeral=True,
        )

    @app_commands.command(name="models", description="Browse popular models and supported providers")
    async def models_list_cmd(self, interaction: discord.Interaction) -> None:
        cfg = await self.config.get_channel_config(interaction.channel_id)
        total_models = len(self.model_catalog.models)
        embed = discord.Embed(
            title="🤖 Popular & Supported Models",
            description=f"Current channel model: `{cfg.model}`\n(Catalog has **{total_models} live models** available via `/model`)",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="DeepSeek",
            value="`deepseek/deepseek-chat`\n`deepseek/deepseek-reasoner`",
            inline=False,
        )
        embed.add_field(
            name="OpenRouter (Universal Gateway)",
            value="`openrouter/deepseek/deepseek-r1`\n`openrouter/deepseek/deepseek-chat`\n`openrouter/anthropic/claude-3.7-sonnet`\n`openrouter/openai/gpt-4o`",
            inline=False,
        )
        embed.add_field(
            name="Anthropic & OpenAI",
            value="`claude-3-7-sonnet-20250219`\n`gpt-4o` | `gpt-4o-mini` | `o3-mini`",
            inline=False,
        )
        embed.add_field(
            name="Google Gemini",
            value="`gemini/gemini-2.0-flash`\n`gemini/gemini-2.0-pro-exp-02-05`",
            inline=False,
        )
        embed.add_field(
            name="Local / Ollama",
            value="`ollama/deepseek-r1`\n`ollama/llama3.3` | `ollama/qwen2.5`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    # --- /key group ---
    key_group = app_commands.Group(name="key", description="Manage personal or custom API keys securely")

    @key_group.command(name="set", description="Set custom API key (Private, ephemeral)")
    @app_commands.describe(
        provider="Provider name (openrouter, deepseek, openai, anthropic, gemini, etc.)",
        api_key="Your API key",
        scope="Set key for just yourself or for this channel",
    )
    @app_commands.choices(
        provider=[app_commands.Choice(name=p, value=p) for p in PROVIDERS],
        scope=[
            app_commands.Choice(name="Personal (Your user ID across all chats)", value="user"),
            app_commands.Choice(name="Channel (Only this channel)", value="channel"),
        ],
    )
    async def key_set(
        self,
        interaction: discord.Interaction,
        provider: app_commands.Choice[str],
        api_key: str,
        scope: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        chosen_scope = scope.value if scope else "user"
        scope_id = interaction.user.id if chosen_scope == "user" else interaction.channel_id

        await self.config.set_api_key(
            scope=chosen_scope,
            scope_id=scope_id,
            provider=provider.value,
            api_key=api_key,
        )

        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        await interaction.response.send_message(
            f"🔒 API Key saved for provider **{provider.value}** ({chosen_scope} scope): `{masked}`\n"
            f"*(This message is private to you and never logged in channel history)*",
            ephemeral=True,
        )

    @key_group.command(name="clear", description="Remove custom API key")
    @app_commands.describe(
        provider="Provider name",
        scope="Personal or channel",
    )
    @app_commands.choices(
        provider=[app_commands.Choice(name=p, value=p) for p in PROVIDERS],
        scope=[
            app_commands.Choice(name="Personal", value="user"),
            app_commands.Choice(name="Channel", value="channel"),
        ],
    )
    async def key_clear(
        self,
        interaction: discord.Interaction,
        provider: app_commands.Choice[str],
        scope: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        chosen_scope = scope.value if scope else "user"
        scope_id = interaction.user.id if chosen_scope == "user" else interaction.channel_id

        deleted = await self.config.delete_api_key(chosen_scope, scope_id, provider.value)
        if deleted:
            await interaction.response.send_message(
                f"🗑️ Cleared custom API key for **{provider.value}** ({chosen_scope} scope).",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"ℹ️ No custom key was found for **{provider.value}** ({chosen_scope} scope).",
                ephemeral=True,
            )

    # --- /provider group ---
    provider_group = app_commands.Group(name="provider", description="Add custom OpenAI-compatible endpoints")

    @provider_group.command(
        name="add",
        description="Register a custom provider endpoint (e.g. OpenCode, LM Studio, vLLM, Ollama)",
    )
    @app_commands.describe(
        name="Unique provider prefix (e.g. opencode or mylocal)",
        base_url="Endpoint URL (e.g. https://api.opencode.ai/v1 or http://localhost:11434/v1)",
        api_key="Optional API key for this endpoint",
    )
    async def provider_add(
        self,
        interaction: discord.Interaction,
        name: str,
        base_url: str,
        api_key: Optional[str] = None,
    ) -> None:
        clean_name = name.strip().lower()
        await self.config.add_custom_provider(clean_name, base_url, api_key)
        await interaction.response.send_message(
            f"🔌 Registered custom provider: **{clean_name}**\n"
            f"• Base URL: `{base_url}`\n"
            f"• To use: `/model set model_name:{clean_name}/<model>` (e.g. `{clean_name}/deepseek-coder`)",
            ephemeral=True,
        )

    # --- /system group ---
    system_group = app_commands.Group(name="system", description="Customize system prompt / persona")

    @system_group.command(name="set", description="Set custom system prompt for this channel/thread")
    @app_commands.describe(prompt="System instructions / persona")
    async def system_set(self, interaction: discord.Interaction, prompt: str) -> None:
        await self.config.set_channel_config(channel_id=interaction.channel_id, system_prompt=prompt)
        await interaction.response.send_message(
            f"🎭 System prompt updated for this channel:\n> {prompt[:200]}..."
        )

    @system_group.command(name="reset", description="Reset system prompt to default")
    async def system_reset(self, interaction: discord.Interaction) -> None:
        await self.config.set_channel_config(
            channel_id=interaction.channel_id, system_prompt=DEFAULT_SYSTEM_PROMPT
        )
        await interaction.response.send_message("🔄 System prompt reset to default.")

    # --- /skills group ---
    skills_group = app_commands.Group(name="skills", description="Manage modular skills / tools")

    @skills_group.command(name="list", description="List all available skills and their status")
    async def skills_list(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🧩 Modular Skills Registry",
            description="Tools that the LLM can autonomously invoke to solve queries.",
            color=discord.Color.green(),
        )
        if not self.skills.skills:
            embed.description = "No skills are currently loaded."
        else:
            for name, skill_obj in self.skills.skills.items():
                is_enabled = self.skills.is_skill_enabled(name, interaction.channel_id)
                status_icon = "🟢 Active" if is_enabled else "🔴 Disabled"
                embed.add_field(
                    name=f"{name} ({status_icon})",
                    value=skill_obj.description[:150],
                    inline=False,
                )
        await interaction.response.send_message(embed=embed)

    @skills_group.command(name="toggle", description="Toggle a skill on/off for this channel")
    @app_commands.describe(skill_name="Name of the skill to toggle")
    async def skills_toggle(self, interaction: discord.Interaction, skill_name: str) -> None:
        name = skill_name.strip()
        if name not in self.skills.skills:
            await interaction.response.send_message(
                f"❌ Skill `{name}` does not exist. Use `/skills list` to see available skills.",
                ephemeral=True,
            )
            return

        is_now_enabled = self.skills.toggle_skill_for_channel(interaction.channel_id, name)
        status = "enabled 🟢" if is_now_enabled else "disabled 🔴"
        await interaction.response.send_message(
            f"Skill `{name}` is now **{status}** for this channel/thread."
        )

    @skills_toggle.autocomplete("skill_name")
    async def skill_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        choices = [
            app_commands.Choice(name=name, value=name)
            for name in self.skills.skills.keys()
            if current.lower() in name.lower()
        ]
        return choices[:25]

    @skills_group.command(name="reload", description="Hot-reload skill modules from disk")
    async def skills_reload(self, interaction: discord.Interaction) -> None:
        reloaded_count = self.skills.reload_all()
        await interaction.response.send_message(
            f"🔄 Reloaded {reloaded_count} skills from `skills/modules/`."
        )

    # --- /thinking group ---
    thinking_group = app_commands.Group(name="thinking", description="Configure reasoning / thinking token display")

    @thinking_group.command(name="set", description="Choose how thinking tokens (DeepSeek R1, Claude, o1) are shown")
    @app_commands.describe(mode="Display mode for thinking process")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Collapsible Button (Click to toggle 🧠 View/Hide Thinking) - Recommended", value="button"),
            app_commands.Choice(name="Spoiler (Click to reveal with ||...||)", value="spoiler"),
            app_commands.Choice(name="Visible (Quoted text block)", value="visible"),
            app_commands.Choice(name="Hide (Do not display thinking)", value="hide"),
        ]
    )
    async def thinking_set(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        await self.config.set_channel_config(
            channel_id=interaction.channel_id, thinking_mode=mode.value
        )
        await interaction.response.send_message(
            f"💭 Thinking display mode set to: **{mode.name}** for this channel/thread."
        )

    # --- /profile group ---
    profile_group = app_commands.Group(name="profile", description="Manage personal description/bio for the AI to remember")

    @profile_group.command(name="set", description="Tell the AI about yourself (e.g. background, coding style, preferences)")
    @app_commands.describe(bio="Description or custom info about yourself")
    async def profile_set(self, interaction: discord.Interaction, bio: str) -> None:
        await self.config.set_user_bio(interaction.user.id, bio)
        await interaction.response.send_message(
            f"👤 Profile bio saved for **{interaction.user.display_name}**!\n> {bio[:300]}\n"
            f"*(The bot will now remember this about you in every conversation!)*",
            ephemeral=True,
        )

    @profile_group.command(name="view", description="View your saved profile info")
    async def profile_view(self, interaction: discord.Interaction) -> None:
        bio = await self.config.get_user_bio(interaction.user.id)
        if bio:
            await interaction.response.send_message(
                f"👤 **Your Saved Profile**:\n> {bio}",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ℹ️ You don't have a profile set yet. Use `/profile set <bio>` to set one!",
                ephemeral=True,
            )

    @profile_group.command(name="clear", description="Clear your saved profile info")
    async def profile_clear(self, interaction: discord.Interaction) -> None:
        deleted = await self.config.clear_user_bio(interaction.user.id)
        if deleted:
            await interaction.response.send_message("🗑️ Your profile bio has been cleared.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ No saved profile was found.", ephemeral=True)

    # --- /clear & /config top-level commands ---

    @app_commands.command(name="clear", description="Clear conversation memory for this channel/thread")
    async def clear_memory(self, interaction: discord.Interaction) -> None:
        self.memory.clear_session(interaction.channel_id)
        await interaction.response.send_message("🧹 Conversation memory cleared for this channel/thread.")

    @app_commands.command(name="config", description="View current settings for this channel/thread")
    async def view_config(self, interaction: discord.Interaction) -> None:
        cfg = await self.config.get_channel_config(interaction.channel_id)
        embed = discord.Embed(
            title="⚙️ Current Channel Configuration",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Model", value=f"`{cfg.model}`", inline=False)
        embed.add_field(name="Temperature", value=f"`{cfg.temperature}`", inline=True)
        embed.add_field(name="Thinking Display", value=f"`{cfg.thinking_mode}`", inline=True)
        active_tools = [
            name
            for name in self.skills.skills
            if self.skills.is_skill_enabled(name, interaction.channel_id)
        ]
        embed.add_field(
            name="Enabled Skills",
            value=", ".join([f"`{t}`" for t in active_tools]) or "None",
            inline=False,
        )
        embed.add_field(
            name="System Prompt",
            value=f"```{cfg.system_prompt[:300]}```",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


async def setup_commands(
    bot: commands.Bot,
    config_manager: ConfigManager,
    memory_manager: MemoryManager,
    skill_manager: SkillManager,
    model_catalog: ModelCatalog,
) -> None:
    await bot.add_cog(CommandsCog(bot, config_manager, memory_manager, skill_manager, model_catalog))
