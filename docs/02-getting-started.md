# 02 — Getting Started

## 1. Discord Developer Portal

1. Create an application at https://discord.com/developers/applications → **Bot** → copy token.
2. **Bot → Privileged Gateway Intents** → enable **Message Content Intent** (required to read mention text).
3. **OAuth2 → URL Generator** → scopes: `bot` + `applications.commands`.
4. Bot permissions: `Send Messages`, `Create Public Threads`, `Send Messages in Threads`, `Embed Links`, `Read Message History`, `Attach Files`.
5. Open the generated URL, invite to your server.

## 2. Install

```bash
pip install -r requirements.txt
```

Requires Python 3.10+ (tested 3.11/3.12/3.13). Key deps: `discord.py`, `litellm`, `python-dotenv`, `pydantic`, `aiosqlite`, `ddgs`, `httpx`, `pytest` + `pytest-asyncio`.

## 3. Configure

```bash
cp .env.example .env
```

Minimal `.env`:

```ini
DISCORD_BOT_TOKEN=your_bot_token_here
DEFAULT_MODEL=openrouter/deepseek/deepseek-chat
OPENROUTER_API_KEY=sk-or-v1-...
```

Add whichever providers you use: `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`. Optional tuning: `DEFAULT_SYSTEM_PROMPT`, `MAX_HISTORY_TURNS=20`, `DEFAULT_TEMPERATURE=0.7`, `OLLAMA_API_BASE`, `CUSTOM_API_BASE`/`CUSTOM_API_KEY`.

## 4. Run

```bash
python main.py
```

What happens (`main.py:main`):

1. `load_dotenv()`, validates `DISCORD_BOT_TOKEN`.
2. `ConfigManager.init_db()` creates SQLite tables.
3. `SkillManager.load_modules()` imports `skills/modules/*.py`.
4. `MemoryManager`, `ModelCatalog` (background `refresh_models()` task), `LLMEngine` init.
5. `setup_chat` + `setup_commands` register cogs; `bot.tree.sync()` on `on_ready`; presence set.

## 5. First checks in Discord

- `/config` → see model, temperature, thinking mode, skills.
- `/model` → view catalog embed; `/model model_name:<pick>` → switch.
- Mention the bot: `@Harness hello, what can you do?` → should branch into a thread and reply.
- `/skills list` → confirm tools loaded.
- `/models_refresh` → pull live models if catalog looks stale.
