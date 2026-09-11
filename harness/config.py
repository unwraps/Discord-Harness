"""
Configuration and Credential Management for Discord LLM Harness.
Handles environment variables, SQLite persistence for per-channel/user settings,
custom API keys, and arbitrary OpenAI-compatible provider endpoints.
"""

from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass
import aiosqlite
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "harness.db"

# Fallback defaults
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openrouter/deepseek/deepseek-chat")
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT",
    "You are a versatile, intelligent AI assistant inside a Discord server. You have access to specialized tools called skills. Be concise, direct, helpful, and use markdown formatting naturally. When asked for GIFs or images, use the search_gif or search_image skills and place the direct image/gif URL on its own line so Discord embeds it.",
)
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
# Default per-user daily token cap (total tokens). 0 = unlimited unless overridden per user.
try:
    DEFAULT_DAILY_TOKEN_LIMIT = int(os.getenv("DEFAULT_DAILY_TOKEN_LIMIT", "0"))
except ValueError:
    DEFAULT_DAILY_TOKEN_LIMIT = 0
if DEFAULT_DAILY_TOKEN_LIMIT < 0:
    DEFAULT_DAILY_TOKEN_LIMIT = 0


def _utc_today() -> str:
    """Current UTC day as YYYY-MM-DD (token limits reset at UTC midnight)."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class ChannelConfig:
    channel_id: int
    model: str
    system_prompt: str
    temperature: float
    thinking_mode: str = "button"  # 'button' (collapsible), 'spoiler', 'visible', or 'hide'


class ConfigManager:
    """Manages database storage for custom keys, providers, and channel overrides."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self) -> None:
        """Initialize SQLite database tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channel_configs (
                    channel_id INTEGER PRIMARY KEY,
                    model TEXT,
                    system_prompt TEXT,
                    temperature REAL,
                    thinking_mode TEXT DEFAULT 'spoiler'
                )
            """)
            # Migration check: add thinking_mode column if table already exists without it
            try:
                await db.execute("ALTER TABLE channel_configs ADD COLUMN thinking_mode TEXT DEFAULT 'spoiler'")
            except Exception:
                pass  # Column already exists

            await db.execute("""
                CREATE TABLE IF NOT EXISTS custom_keys (
                    scope TEXT,        -- 'user' or 'channel' or 'guild'
                    scope_id INTEGER,
                    provider TEXT,     -- e.g. 'openrouter', 'deepseek', 'openai'
                    api_key TEXT,
                    PRIMARY KEY (scope, scope_id, provider)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS custom_providers (
                    name TEXT PRIMARY KEY,   -- e.g. 'opencode', 'local_vllm'
                    base_url TEXT NOT NULL,
                    api_key TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id INTEGER PRIMARY KEY,
                    bio TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_token_limits (
                    user_id INTEGER PRIMARY KEY,
                    daily_limit INTEGER NOT NULL DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_token_usage (
                    user_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, day)
                )
            """)
            await db.commit()
        logger.info(f"Initialized database schema at {self.db_path}")

    # --- User Profiles / Bio ---

    async def set_user_bio(self, user_id: int, bio: str) -> None:
        """Set custom description or bio for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_profiles (user_id, bio)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET bio=excluded.bio
                """,
                (user_id, bio.strip()),
            )
            await db.commit()

    async def get_user_bio(self, user_id: int) -> Optional[str]:
        """Fetch custom description or bio for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT bio FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return row[0]
        return None

    async def clear_user_bio(self, user_id: int) -> bool:
        """Clear custom description or bio for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            res = await db.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
            await db.commit()
            return res.rowcount > 0

    # --- Per-User Daily Token Limits ---

    async def set_user_token_limit(self, user_id: int, daily_limit: int) -> None:
        """Set a per-user daily token cap. 0 (or negative) means unlimited."""
        limit = max(0, int(daily_limit))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_token_limits (user_id, daily_limit)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET daily_limit=excluded.daily_limit
                """,
                (user_id, limit),
            )
            await db.commit()

    async def clear_user_token_limit(self, user_id: int) -> bool:
        """Remove a per-user override (falls back to DEFAULT_DAILY_TOKEN_LIMIT)."""
        async with aiosqlite.connect(self.db_path) as db:
            res = await db.execute("DELETE FROM user_token_limits WHERE user_id = ?", (user_id,))
            await db.commit()
            return res.rowcount > 0

    async def get_user_token_limit(self, user_id: int) -> int:
        """Effective daily token cap for a user. 0 = unlimited."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT daily_limit FROM user_token_limits WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0] is not None:
                    return max(0, int(row[0]))
        return DEFAULT_DAILY_TOKEN_LIMIT

    async def add_token_usage(
        self,
        user_id: int,
        prompt_tokens: int,
        completion_tokens: int,
        day: Optional[str] = None,
    ) -> None:
        """Accumulate token usage for a user on a UTC day."""
        day = day or _utc_today()
        prompt_tokens = max(0, int(prompt_tokens or 0))
        completion_tokens = max(0, int(completion_tokens or 0))
        if prompt_tokens == 0 and completion_tokens == 0:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_token_usage (user_id, day, prompt_tokens, completion_tokens)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, day) DO UPDATE SET
                    prompt_tokens=user_token_usage.prompt_tokens+excluded.prompt_tokens,
                    completion_tokens=user_token_usage.completion_tokens+excluded.completion_tokens
                """,
                (user_id, day, prompt_tokens, completion_tokens),
            )
            await db.commit()

    async def get_token_usage(
        self, user_id: int, day: Optional[str] = None
    ) -> Dict[str, int]:
        """Token usage for a user on a UTC day (defaults to today)."""
        day = day or _utc_today()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT prompt_tokens, completion_tokens FROM user_token_usage "
                "WHERE user_id = ? AND day = ?",
                (user_id, day),
            ) as cursor:
                row = await cursor.fetchone()
                prompt = int(row[0]) if row else 0
                completion = int(row[1]) if row else 0
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}

    async def check_daily_limit(self, user_id: int) -> Optional[str]:
        """
        Return a user-facing refusal message if the user exhausted today's
        token budget, else None. 0 limit = unlimited.
        """
        limit = await self.get_user_token_limit(user_id)
        if limit <= 0:
            return None
        usage = await self.get_token_usage(user_id)
        used = usage["total_tokens"]
        if used >= limit:
            return (
                f"⚠️ **Daily token limit reached** — you've used "
                f"`{used:,}` / `{limit:,}` tokens today. "
                f"Limits reset at UTC midnight. Ask a server admin to raise your cap."
            )
        return None

    # --- Channel Configs ---

    async def get_channel_config(self, channel_id: int) -> ChannelConfig:
        """Get settings for a channel/thread or return defaults."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT model, system_prompt, temperature, thinking_mode FROM channel_configs WHERE channel_id = ?",
                (channel_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return ChannelConfig(
                        channel_id=channel_id,
                        model=row[0] or DEFAULT_MODEL,
                        system_prompt=row[1] or DEFAULT_SYSTEM_PROMPT,
                        temperature=row[2] if row[2] is not None else DEFAULT_TEMPERATURE,
                        thinking_mode=row[3] or "button",
                    )
        return ChannelConfig(
            channel_id=channel_id,
            model=DEFAULT_MODEL,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=DEFAULT_TEMPERATURE,
            thinking_mode="button",
        )

    async def set_channel_config(
        self,
        channel_id: int,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        thinking_mode: Optional[str] = None,
    ) -> ChannelConfig:
        """Update or insert channel configuration."""
        current = await self.get_channel_config(channel_id)
        new_model = model if model is not None else current.model
        new_prompt = system_prompt if system_prompt is not None else current.system_prompt
        new_temp = temperature if temperature is not None else current.temperature
        new_thinking = thinking_mode if thinking_mode is not None else current.thinking_mode

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO channel_configs (channel_id, model, system_prompt, temperature, thinking_mode)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    model=excluded.model,
                    system_prompt=excluded.system_prompt,
                    temperature=excluded.temperature,
                    thinking_mode=excluded.thinking_mode
                """,
                (channel_id, new_model, new_prompt, new_temp, new_thinking),
            )
            await db.commit()
        return ChannelConfig(channel_id, new_model, new_prompt, new_temp, new_thinking)

    # --- Custom API Keys ---

    async def set_api_key(self, scope: str, scope_id: int, provider: str, api_key: str) -> None:
        """Store an API key for a specific user, channel, or guild."""
        provider_clean = provider.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO custom_keys (scope, scope_id, provider, api_key)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope, scope_id, provider) DO UPDATE SET
                    api_key=excluded.api_key
                """,
                (scope, scope_id, provider_clean, api_key.strip()),
            )
            await db.commit()

    async def get_api_key(self, scope: str, scope_id: int, provider: str) -> Optional[str]:
        """Fetch a custom API key for a scope."""
        provider_clean = provider.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT api_key FROM custom_keys WHERE scope = ? AND scope_id = ? AND provider = ?",
                (scope, scope_id, provider_clean),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
        return None

    async def delete_api_key(self, scope: str, scope_id: int, provider: str) -> bool:
        """Delete a custom API key."""
        provider_clean = provider.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            res = await db.execute(
                "DELETE FROM custom_keys WHERE scope = ? AND scope_id = ? AND provider = ?",
                (scope, scope_id, provider_clean),
            )
            await db.commit()
            return res.rowcount > 0

    # --- Custom Providers (e.g. OpenCode, vLLM, local endpoints) ---

    async def add_custom_provider(self, name: str, base_url: str, api_key: Optional[str] = None) -> None:
        """Register an arbitrary OpenAI-compatible provider endpoint."""
        clean_name = name.strip().lower()
        clean_url = base_url.strip().rstrip("/")
        clean_key = api_key.strip() if api_key else ""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO custom_providers (name, base_url, api_key)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    base_url=excluded.base_url,
                    api_key=excluded.api_key
                """,
                (clean_name, clean_url, clean_key),
            )
            await db.commit()

    async def get_custom_provider(self, name: str) -> Optional[Tuple[str, Optional[str]]]:
        """Get (base_url, api_key) for a custom provider."""
        clean_name = name.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT base_url, api_key FROM custom_providers WHERE name = ?",
                (clean_name,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return (row[0], row[1] if row[1] else None)
        return None

    # --- Credential Resolution ---

    async def resolve_credentials(
        self,
        model: str,
        user_id: Optional[int] = None,
        channel_id: Optional[int] = None,
    ) -> Dict[str, Optional[str]]:
        """
        Dynamically determine api_key and api_base for the given model.
        Precedence:
        1. Custom Provider table match (if model starts with provider_name/...)
        2. User-specific custom key
        3. Channel-specific custom key
        4. Environment variables (.env)
        """
        model_lower = model.lower()
        provider = "openai"

        if "/" in model_lower:
            prefix, _ = model_lower.split("/", 1)
            # Check if prefix matches a custom provider
            custom_prov = await self.get_custom_provider(prefix)
            if custom_prov:
                base_url, custom_key = custom_prov
                return {
                    "api_base": base_url,
                    "api_key": custom_key or os.getenv("CUSTOM_API_KEY") or "none",
                }
            provider = prefix
        elif model_lower.startswith("gpt-") or model_lower.startswith("o1") or model_lower.startswith("o3"):
            provider = "openai"
        elif model_lower.startswith("claude"):
            provider = "anthropic"
        elif model_lower.startswith("deepseek"):
            provider = "deepseek"
        elif model_lower.startswith("gemini"):
            provider = "gemini"

        # 1. User key
        if user_id:
            user_key = await self.get_api_key("user", user_id, provider)
            if user_key:
                return {"api_key": user_key, "api_base": None}

        # 2. Channel key
        if channel_id:
            ch_key = await self.get_api_key("channel", channel_id, provider)
            if ch_key:
                return {"api_key": ch_key, "api_base": None}

        # 3. Environment variable fallback
        env_map = {
            "openrouter": os.getenv("OPENROUTER_API_KEY"),
            "deepseek": os.getenv("DEEPSEEK_API_KEY"),
            "openai": os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "gemini": os.getenv("GEMINI_API_KEY"),
            "groq": os.getenv("GROQ_API_KEY"),
            "mistral": os.getenv("MISTRAL_API_KEY"),
            "custom": os.getenv("CUSTOM_API_KEY"),
        }

        api_key = env_map.get(provider)
        api_base = os.getenv("CUSTOM_API_BASE") if provider == "custom" else None

        return {"api_key": api_key, "api_base": api_base}
