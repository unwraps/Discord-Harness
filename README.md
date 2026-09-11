# 🤖 Discord LLM Harness

A modular, multi-model AI harness bot for Discord built with Python. Connect any LLM (OpenRouter, DeepSeek, OpenAI, Anthropic, Google Gemini, Ollama, OpenCode, or custom self-hosted endpoints) and give them superpowers with dynamic, hot-reloadable custom tools (**Skills**).

---

## ✨ Features

- **🌐 Connect Any Model**:
  - **OpenRouter** (`openrouter/anthropic/claude-3.5-sonnet`, `openrouter/deepseek/deepseek-chat`, etc.)
  - **DeepSeek** (`deepseek/deepseek-chat`, `deepseek/deepseek-reasoner`)
  - **OpenAI & Anthropic** (`gpt-4o`, `gpt-4o-mini`, `claude-3-5-sonnet-20241022`)
  - **Google Gemini** (`gemini/gemini-2.0-flash`)
  - **Local Models** (`ollama/llama3`, `ollama/qwen2.5`, vLLM, LM Studio)
  - **Custom Endpoints** (OpenCode, self-hosted proxies via `/provider add`)

- **🔒 Custom API Key Management**:
  - Central keys configured in `.env`.
  - Or connect custom keys directly in Discord using private ephemeral slash commands (`/key set provider:openrouter api_key:...`). Keys are never logged in channel history.

- **🧩 Plug-and-Play Skills (Modular Tools)**:
  - Drop a Python file with a `@skill` decorator into `skills/modules/`.
  - JSON schema is **automatically extracted** from standard Python type hints and docstrings.
  - LLMs autonomously call skills when needed, inspect results, and return answers.
  - Hot-reload tools without rebooting the bot (`/skills reload`).
  - Toggle tools on or off per channel (`/skills toggle`).

- **🧵 Clean Thread Conversations**:
  - When mentioned in a busy channel, the bot automatically branches into a Discord Thread to keep chats isolated and clean.
  - Per-thread/channel memory with rolling window context management.

- **🧠 Thinking / Reasoning Model Support**:
  - Full native support for **DeepSeek-R1** (`deepseek/deepseek-reasoner` or `openrouter/deepseek/deepseek-r1`), **Claude 3.7 Extended Thinking**, **OpenAI o1/o3-mini**, and local models with `<think>` tags.
  - Automatically captures reasoning tokens and formats them using Discord's spoiler blocks (`||...||` click-to-reveal) so chat remains readable.
  - Custom display modes per channel via `/thinking set <spoiler|visible|hide>`.

- **💬 Discord-Safe Formatting**:
  - Automatically splits messages exceeding Discord's 2000-character limit.
  - Preserves markdown code fences (```` ```python ````) across split messages so code never breaks.

---

## 🚀 Quickstart

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11, 3.12, 3.13)
- A Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))

### 2. Installation
Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials:
```ini
DISCORD_BOT_TOKEN=your_bot_token_here

# Default model used across channels
DEFAULT_MODEL=openrouter/deepseek/deepseek-chat

# Provider keys (configure whichever you want to use)
OPENROUTER_API_KEY=sk-or-v1-...
DEEPSEEK_API_KEY=sk-...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIzaSy...
```

> [!IMPORTANT]
> **Discord Bot Permissions**:
> In the [Discord Developer Portal](https://discord.com/developers/applications):
> 1. Go to your Application -> **Bot**.
> 2. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
> 3. Under **OAuth2 -> URL Generator**, select `bot` and `applications.commands`.
> 4. Permissions: `Send Messages`, `Create Public Threads`, `Send Messages in Threads`, `Embed Links`, `Read Message History`.

### 4. Run the Bot
```bash
python main.py
```
Upon startup, the bot registers all slash commands globally with Discord!

---

## 🕹️ Slash Commands Reference

| Command | Description |
|---|---|
| `/model [model_name]` | Switch active model with live **autocomplete** (or view current model if empty) |
| `/models` | Browse all supported models across OpenRouter, DeepSeek, Claude, GPT, etc. |
| `/key set <provider> <api_key>` | Set your personal or channel API key privately (ephemeral) |
| `/key list` / `/key clear` | View or remove custom configured keys |
| `/provider add <name> <base_url>` | Connect arbitrary endpoints (OpenCode, LM Studio, vLLM, Ollama) |
| `/skills list` | View loaded tools and active status |
| `/skills toggle <skill_name>` | Enable/disable a skill in this channel |
| `/skills reload` | Hot-reload all skills from disk without rebooting |
| `/system set <prompt>` | Change persona / system prompt for this channel |
| `/system reset` | Reset system prompt to default |
| `/profile set <bio>` | Tell the bot about yourself (preferences, background, habits) |
| `/profile view` / `/profile clear` | View or remove your saved user profile description |
| `/thinking set <mode>` | Choose thinking token display: `spoiler` (click to reveal), `visible`, or `hide` |
| `/clear` | Wipe conversation history in the channel/thread |
| `/config` | View active model, temperature, thinking mode, and enabled tools |

---

## 🛠️ Creating Custom Skills in 10 Seconds

To add a new tool for the LLM to use, simply create a new Python file in `skills/modules/`:

**`skills/modules/weather.py`**:
```python
import httpx
from skills.base import skill

@skill(
    name="get_weather",
    description="Get the current weather for a city name.",
)
async def get_weather(city: str) -> str:
    """Fetch weather data for a city."""
    url = f"https://wttr.in/{city}?format=3"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.text
```

Then in Discord, simply run:
```text
/skills reload
```
The bot will load your new skill instantly, and the LLM will start using it whenever users ask about the weather!

---

## 📁 Project Architecture

```
Discord Harness/
├── cogs/
│   ├── chat.py             # Mention/thread message listener & streaming handler
│   └── commands.py         # Discord slash commands (/model, /key, /skills, etc.)
├── harness/
│   ├── config.py           # SQLite persistence for configs, keys & providers
│   ├── formatter.py        # Discord markdown chunker & code fence preservation
│   ├── llm.py              # Multi-model LiteLLM router & recursive tool loop
│   └── memory.py           # Sliding-window session memory per channel/thread
├── skills/
│   ├── base.py             # @skill decorator & auto JSON schema extractor
│   ├── manager.py          # Dynamic skill loader, registry & execution runner
│   └── modules/            # Drop modular skill files here
│       ├── calculator.py   # Safe math evaluator
│       ├── time_notes.py   # Time inspection & scratchpad memory
│       └── web_search.py   # DuckDuckGo web search
├── tests/                  # Pytest automated test suite
├── .env.example            # Configuration template
├── main.py                 # Bot startup & initialization
└── requirements.txt        # Python package dependencies
```

---

## 🧪 Running Tests

Run the full test suite with:
```bash
pytest -v
```
