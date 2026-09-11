# 08 — Architecture

## File map

```
main.py                 # create_bot() (message_content+guilds+messages intents, "!" prefix),
                        # main(): dotenv, token guard, ConfigManager.init_db, SkillManager.load_modules,
                        # MemoryManager, ModelCatalog + background refresh_models(),
                        # LLMEngine, setup_chat, setup_commands, on_ready sync + presence, bot.start
cogs/chat.py            # ChatCog.on_message, extract_message_images, download_discord_media,
                        # extract_media_url, ThinkingToggleView
cogs/commands.py        # CommandsCog: /model /setmodel /models_refresh /models,
                        # /key set|clear, /provider add, /system set|reset,
                        # /skills list|toggle|reload, /thinking set,
                        # /profile set|view|clear, /clear, /config
harness/config.py       # BASE_DIR/DATA_DIR/DB_PATH, defaults from env,
                        # ChannelConfig dataclass, ConfigManager (aiosqlite)
harness/llm.py          # LLMEngine.generate_response (tool loop)
harness/memory.py       # ConversationSession, MemoryManager
harness/models.py       # ModelCatalog, FALLBACK_MODELS
harness/formatter.py    # split_message, StreamThrottle, format_with_thinking
skills/base.py          # python_type_to_json_type, Skill, extract_parameter_schema, @skill
skills/manager.py       # SkillManager
skills/modules/         # calculator, web_search, fetch_webpage, media_search, time_notes
tests/                  # test_chat_media, test_commands, test_config, test_fetch_webpage,
                        # test_formatter, test_llm, test_media_search, test_memory,
                        # test_models, test_skills, test_vision
data/                   # harness.db (created at runtime), .gitkeep
```

## Request lifecycle

```
on_message → trigger check → clean + vision + thread + mentions + user_info
  → MemoryManager.get_session().add_user_message
  → LLMEngine.generate_response (config + creds + tools + acompletion loop + SkillManager.execute)
  → format_with_thinking → ThinkingToggleView parse → extract_media_url + download
  → split_message → send (media/view on last chunk)
```

Slash commands bypass chat and mutate `ConfigManager` / `SkillManager` / `MemoryManager` / `ModelCatalog` directly.

## Database schema (`data/harness.db`)

```sql
channel_configs(channel_id INTEGER PK, model TEXT, system_prompt TEXT,
  temperature REAL, thinking_mode TEXT DEFAULT 'spoiler');
-- thinking_mode migration: ALTER TABLE ADD COLUMN if missing

custom_keys(scope TEXT, scope_id INTEGER, provider TEXT, api_key TEXT,
  PRIMARY KEY(scope, scope_id, provider));  -- scope: user|channel|guild

custom_providers(name TEXT PK, base_url TEXT NOT NULL, api_key TEXT);

user_profiles(user_id INTEGER PK, bio TEXT);
```

## Key classes & functions

| Symbol | File | Role |
|---|---|---|
| `create_bot()`, `main()` | `main.py` | Wiring + startup |
| `ChatCog`, `setup_chat()` | `cogs/chat.py` | Message UX |
| `CommandsCog`, `setup_commands()` | `cogs/commands.py` | Config UX |
| `ConfigManager`, `ChannelConfig` | `harness/config.py` | Env + SQLite + credential precedence |
| `LLMEngine` | `harness/llm.py` | Routing + tools |
| `MemoryManager`, `ConversationSession` | `harness/memory.py` | Rolling context + identity headers |
| `ModelCatalog` | `harness/models.py` | Live models + search |
| `split_message`, `format_with_thinking`, `StreamThrottle` | `harness/formatter.py` | Discord output |
| `Skill`, `skill()`, `extract_parameter_schema()` | `skills/base.py` | Tool definition |
| `SkillManager` | `skills/manager.py` | Discovery + gating + exec |

## Dependencies (`requirements.txt`)

`discord.py` (gateway/slash/threads/embeds/views), `litellm` (unified completions + tools), `python-dotenv`, `pydantic` (transitive), `aiosqlite` (async SQLite), `ddgs` (search/images), `httpx` (web fetch/media), `lxml` (HTML parse — used by skills though not pinned), `pytest` + `pytest-asyncio` (suite).
