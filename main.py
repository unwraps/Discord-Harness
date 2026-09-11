"""
Discord LLM Harness - Bot Main Entrypoint.
Initializes intents, database, skill manager, LLM engine, and registers cogs.
"""

from __future__ import annotations
import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from harness.config import ConfigManager, DISCORD_BOT_TOKEN
from harness.llm import LLMEngine
from harness.memory import MemoryManager
from harness.models import ModelCatalog
from skills.manager import SkillManager
from cogs.chat import setup_chat
from cogs.commands import setup_commands

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("DiscordHarness")


def create_bot() -> commands.Bot:
    """Create and configure the Discord Bot client."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot


async def main() -> None:
    load_dotenv()
    token = DISCORD_BOT_TOKEN or os.getenv("DISCORD_BOT_TOKEN", "")

    if not token or token == "your_discord_bot_token_here":
        logger.error(
            "DISCORD_BOT_TOKEN is not set! Please set it in your .env file before starting the bot."
        )
        sys.exit(1)

    # Initialize Core Subsystems
    config_manager = ConfigManager()
    await config_manager.init_db()

    skill_manager = SkillManager()
    loaded_skills = skill_manager.load_modules()
    logger.info(f"Initialized SkillManager with {loaded_skills} modular skills.")

    memory_manager = MemoryManager()
    model_catalog = ModelCatalog(config_manager=config_manager)
    # Start non-blocking background fetch of live models from provider APIs
    asyncio.create_task(model_catalog.refresh_models())

    llm_engine = LLMEngine(config_manager=config_manager, skill_manager=skill_manager)

    bot = create_bot()

    @bot.event
    async def on_ready() -> None:
        logger.info(f"Log in as {bot.user} (ID: {bot.user.id})")
        # Sync slash commands with Discord
        try:
            synced = await bot.tree.sync()
            logger.info(f"Successfully synced {len(synced)} slash commands globally.")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="mentions & /commands | LLM Harness",
        )
        await bot.change_presence(activity=activity)

    # Load Cogs
    await setup_chat(bot, llm_engine, memory_manager, config_manager, skill_manager)
    await setup_commands(bot, config_manager, memory_manager, skill_manager, model_catalog)

    # Start Bot
    logger.info("Starting Discord LLM Harness Bot...")
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
