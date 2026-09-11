# 🤖 Discord LLM Harness

A modular, multi-model AI harness bot for Discord built with Python. Connect **any LLM** — OpenRouter, DeepSeek, OpenAI, Anthropic, Google Gemini, Groq, Mistral, Ollama, LM Studio, vLLM, OpenCode, or any OpenAI-compatible endpoint — and give it superpowers with dynamic, hot-reloadable **Skills** (function tools), per-channel memory, vision, GIF/image search, and reasoning-model support.

> **Docs:** Full guides live in [`docs/`](./docs/README.md) — setup, configuration, slash commands, chat flow, LLM engine, skills authoring, architecture, testing & troubleshooting.

---

## Table of Contents

- [Features](#-features)
- [How It Works](#-how-it-works)
- [Quickstart](#-quickstart)
- [Configuration](#️-configuration)
- [Slash Commands Reference](#️-slash-commands-reference)
- [Chat Behavior](#-chat-behavior)
- [Skills — Built-in & Custom](#️-skills--built-in--custom)
- [Project Architecture](#-project-architecture)
- [Data & Database](#-data--database)
- [Running Tests](#-running-tests)
- [Troubleshooting](#-troubleshooting)
- [Security Notes](#-security-notes)
- [Roadmap / Ideas](#-roadmap--ideas)

---

## ✨ Features

### 🌐 Connect Any Model
Powered by **LiteLLM** (`harness/llm.py`), one identifier style routes everywhere:

| Provider | Example identifiers |
|---|---|
| OpenRouter (universal gateway) | `openrouter/anthropic/claude-3.5-sonnet`, `openrouter/deepseek/deepseek-chat`, `openrouter/openai/gpt-4o` |
| DeepSeek official | `deepseek/deepseek-chat`, `deepseek/deepseek-reasoner` |
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini` |
| Anthropic | `claude-3-5-sonnet-20241022`, `claude-3-7-sonnet-20250219` |
| Google Gemini | `gemini/gemini-2.0-flash`, `gemini/gemini-2.0-pro-exp-02-05` |
| Local / self-hosted | `ollama/llama3.3`, `ollama/qwen2.5`, `ollama/deepseek-r1` |
| Custom endpoints | `<name>/<model>` after `/provider add <name> <base_url>` (OpenCode, LM Studio, vLLM, etc.) |

Live model discovery (`harness/models.py`) pulls from OpenRouter, DeepSeek, OpenAI, local Ollama (`http://localhost:11434/api/tags`), and every custom provider registered in SQLite. Results back `/model` autocomplete and `/models_refresh`. Falls back to a curated list when offline.

### 🔒 Flexible API Key Management
Credential resolution order in `ConfigManager.resolve_credentials()`:

1. **Custom provider match** — if model starts with `provider_name/...`, use that provider's `base_url` + key.
2. **User key** (`/key set` with Personal scope) — your key follows you across channels.
3. **Channel key** (`/key set` with Channel scope).
4. **Environment** — `.env` (`OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `CUSTOM_API_KEY` / `CUSTOM_API_BASE`).

Keys set via Discord use **ephemeral** (private) replies and are stored in SQLite, never in channel history.

### 🧩 Plug-and-Play Skills (Tools)
- Drop a Python file with a `@skill` decorator into `skills/modules/` → JSON schema auto-extracted from type hints.
- LLM calls skills autonomously in a recursive tool loop (max 5 iterations per turn), inspects results, answers.
- Hot-reload without reboot: `/skills reload`.
- Toggle per channel: `/skills toggle`.
- Built-ins: `calculator`, `duckduckgo_search` / `web_search`, `fetch_webpage`, `search_gif`, `search_image`, `get_current_time`, `save_scratchpad_note`, `get_scratchpad_note`.

### 🧵 Clean Thread Conversations
- Mention the bot in a busy channel → auto-creates a `🤖 <prompt…>` public thread (if permissions allow) so discussion stays isolated.
- DMs, direct mentions, and bot-owned threads all trigger responses. Other messages are ignored.
- Per-thread/channel rolling memory (`harness/memory.py`, default 20 turns).

### 🧠 Reasoning / Thinking Models
Native support for DeepSeek-R1 / `deepseek-reasoner`, Claude Extended Thinking, `o1`/`o3-mini`, and local `<think>` models:
- `reasoning_content` / `thinking` fields + inline `<think>…</think>` extraction (`harness/formatter.py`).
- Display modes per channel via `/thinking set`: `button` (collapsible 🧠 View Thought Process, default) | `spoiler` (`||…||`) | `visible` (blockquote) | `hide`.

### 👁️ Vision + 🎞️ Media
- Attachments (≤10 MB → base64 data URI), replied-to images, or direct image URLs are forwarded as OpenAI-style `image_url` parts. Non-vision models get a helpful tip to switch (`gpt-4o`, `gemini/gemini-2.0-flash`, etc.).
- `search_gif` / `search_image` return `ATTACH_MEDIA: <url>` + numbered options; `cogs/chat.py` downloads (≤15 MB) and re-uploads as `discord.File`, falling back to Embed/raw URL.

### 💬 Discord-Safe Formatting
- `split_message()` chunks at ~1950 chars, closes/reopens ```` ``` ```` fences across chunks so code never breaks.
- Rich author context injected per message: display name, nickname, top role, roles, server/channel, bio (`/profile set`), plus tagged-user cards — so the model knows *who* it's talking to.

---

## 🔄 How It Works

```
User mentions bot / DMs / replies in bot thread
  → cogs/chat.py: clean mention, extract images, resolve thread, build user_info
  → MemoryManager.get_session(channel_id).add_user_message(...)
  → LLMEngine.generate_response(session, user_id, channel_id)
      → ConfigManager.get_channel_config() + resolve_credentials()
      → SkillManager.get_openai_tools() → LiteLLM acompletion() loop
      → SkillManager.execute(name, args) → session.add_tool_result(...)
      → format_with_thinking(content, reasoning, mode)
  → ThinkingToggleView (if button mode) + extract_media_url() + split_message()
  → send chunk(s) + file/embed/view
```

Per-channel config (model, system prompt, temperature, thinking mode), custom keys/providers, and user bios persist in `data/harness.db` (SQLite via `aiosqlite`).

---

## 🚀 Quickstart

### 1. Prerequisites
- Python 3.10+ (tested 3.11 / 3.12 / 3.13)
- Discord Bot Token — [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Install
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
```bash
cp .env.example .env
```
```ini
DISCORD_BOT_TOKEN=your_bot_token_here
DEFAULT_MODEL=openrouter/deepseek/deepseek-chat
DEFAULT_SYSTEM_PROMPT=You are a versatile, intelligent AI assistant inside a Discord server...
MAX_HISTORY_TURNS=20
DEFAULT_TEMPERATURE=0.7

OPENROUTER_API_KEY=sk-or-v1-...
DEEPSEEK_API_KEY=sk-...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...
MISTRAL_API_KEY=...
# CUSTOM_API_BASE=http://localhost:11434/v1
# CUSTOM_API_KEY=
```

> [!IMPORTANT]
> **Discord Bot Permissions** (Developer Portal → your Application):
> 1. **Bot → Privileged Gateway Intents** → enable **Message Content Intent**.
> 2. **OAuth2 → URL Generator** → scopes `bot` + `applications.commands`.
> 3. Bot permissions: `Send Messages`, `Create Public Threads`, `Send Messages in Threads`, `Embed Links`, `Read Message History`, `Attach Files` (for GIF/image upload).

### 4. Run
```bash
python main.py
```
On `on_ready` the bot syncs slash commands globally and sets presence to `watching mentions & /commands | LLM Harness`.

---

## ⚙️ Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *(required)* | Bot token |
| `DEFAULT_MODEL` | `openrouter/deepseek/deepseek-chat` | Fallback model for new channels |
| `DEFAULT_SYSTEM_PROMPT` | concise helpful assistant | Fallback persona |
| `MAX_HISTORY_TURNS` | `20` | Rolling window size (`MemoryManager` / `ConversationSession`) |
| `DEFAULT_TEMPERATURE` | `0.7` | Sampling temp (skipped for strict reasoners: `reasoner`, `o1`, `o3`) |
| `OPENROUTER/DEEPSEEK/OPENAI/ANTHROPIC/GEMINI/GROQ/MISTRAL_API_KEY` | empty | Provider keys |
| `OLLAMA_API_BASE` | `http://localhost:11434` | Ollama tag discovery |
| `CUSTOM_API_BASE` / `CUSTOM_API_KEY` | empty | Single legacy custom endpoint (prefer `/provider add`) |

Per-channel overrides live in SQLite and are managed entirely from Discord (`/model`, `/system set`, `/thinking set`, `/config`). See [`docs/03-configuration.md`](./docs/03-configuration.md).

---

## 🕹️ Slash Commands Reference

| Command | Description |
|---|---|
| `/model [model_name]` | Switch model with live autocomplete, or view current config embed |
| `/setmodel <model_name>` | Alias of `/model` |
| `/models` | Browse popular models + catalog size |
| `/models_refresh` | Force-refresh live catalog from all provider APIs |
| `/key set <provider> <api_key> [scope]` | Save personal (`user`) or channel key — ephemeral/private |
| `/key clear <provider> [scope]` | Remove a custom key |
| `/provider add <name> <base_url> [api_key]` | Register OpenAI-compatible endpoint; use as `<name>/<model>` |
| `/skills list` | Embed of loaded skills + 🟢/🔴 per-channel status |
| `/skills toggle <skill_name>` | Enable/disable a skill for this channel (autocomplete) |
| `/skills reload` | Hot-reload everything in `skills/modules/` |
| `/system set <prompt>` / `/system reset` | Set / reset channel persona |
| `/profile set <bio>` / `/profile view` / `/profile clear` | Personal memory injected into every prompt as `About User:` |
| `/thinking set <button\|spoiler\|visible\|hide>` | Reasoning display mode for this channel |
| `/clear` | Wipe conversation (keeps system prompt) |
| `/config` | Embed: model, temperature, thinking mode, enabled skills, system prompt |

Full usage + examples: [`docs/04-slash-commands.md`](./docs/04-slash-commands.md).

---

## 💬 Chat Behavior

- **Triggers:** DM · `@bot mention` in guild · any message in a bot-owned thread. Bot messages ignored.
- **Threads:** mention in a text channel → `🤖 <first 30 chars>` thread (60-min auto-archive) when `Create Public Threads` + `Send Messages in Threads` granted; otherwise replies in-channel.
- **Mentions cleanup:** `<@bot>`, `<@&role>` → `@RoleName`, `<#channel>` → `#name`, `<@user>` → `@DisplayName`, with full tagged-user cards (roles, join dates, bios).
- **Images:** up to 3 attachments/replied images/raw URLs per turn; empty-text + image → defaults to *“Please analyze and describe this image in detail.”*
- **Status:** `⚡ Running skill: …` placeholder while tools execute, deleted before final reply.
- **Thinking UI:** `button` mode posts `<!--THINKING_BLOCK-->…` parsed into a 🧠 toggle View (falls back to ephemeral chunk if too long).
- **Media:** first `ATTACH_MEDIA:` URL or direct gif/jpg/png/webp (or tenor/giphy/gifdb) link in reply or recent tool outputs is downloaded and attached.

Deep dive: [`docs/05-chat-flow.md`](./docs/05-chat-flow.md).

---

## 🛠️ Skills — Built-in & Custom

### Built-in (`skills/modules/`)

| Skill | File | What it does |
|---|---|---|
| `calculator` | `calculator.py` | Safe AST math: `+-*/%**`, `sqrt/sin/cos/log/round/abs`, `pi`/`e`. No `eval`. |
| `duckduckgo_search`, `web_search` | `web_search.py` | Open-web search (`ddgs` → raw HTML → Wikipedia fallbacks); `query`, `max_results`, `search_type: all/funny/discussions/news`. |
| `fetch_webpage` | `fetch_webpage.py` | Clean text extraction (lxml, strips script/style/nav/footer), 4000-char cap, SSRF guard (blocks localhost/private/169.254.169.254, DNS-rebind check). |
| `search_gif`, `search_image` | `media_search.py` | DDG images, top-8 GIF candidates / top-6 images, `index` picker, `ATTACH_MEDIA` contract for auto-attach. |
| `get_current_time` | `time_notes.py` | UTC timestamp + ISO. |
| `save_scratchpad_note`, `get_scratchpad_note` | `time_notes.py` | In-memory key-value scratchpad (empty key lists all). |

### Create a skill in ~10 seconds

`skills/modules/weather.py`:
```python
import httpx
from skills.base import skill

@skill(name="get_weather", description="Get the current weather for a city name.")
async def get_weather(city: str) -> str:
    """Fetch weather data for a city."""
    url = f"https://wttr.in/{city}?format=3"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.text
```
Then in Discord: `/skills reload` — the LLM starts using it immediately. Schema (`type/object/properties/required`) is derived from signature + type hints; `Optional[X]` unwraps; `list[T]` gets `items`.

Full authoring guide, `SkillManager` API, enable/disable semantics: [`docs/07-skills.md`](./docs/07-skills.md).

---

## 📁 Project Architecture

```
Discord Harness/
├── main.py                 # Entrypoint: intents, DB init, skills, catalog refresh, cogs, bot.start
├── cogs/
│   ├── chat.py             # on_message, vision extract, threads, thinking view, media attach
│   └── commands.py         # /model /key /provider /system /skills /thinking /profile /clear /config
├── harness/
│   ├── config.py           # ConfigManager: env + SQLite (channel_configs, custom_keys, custom_providers, user_profiles)
│   ├── llm.py              # LLMEngine: LiteLLM routing + recursive tool loop + error tips
│   ├── memory.py           # MemoryManager + ConversationSession (rolling window, identity headers)
│   ├── models.py           # ModelCatalog: live fetch (OpenRouter/DeepSeek/Ollama/OpenAI/custom) + search()
│   └── formatter.py        # split_message(), StreamThrottle, format_with_thinking()
├── skills/
│   ├── base.py             # @skill, Skill, extract_parameter_schema(), python_type_to_json_type()
│   ├── manager.py          # SkillManager: discover/reload/toggle/get_openai_tools()/execute()
│   └── modules/            # calculator, web_search, fetch_webpage, media_search, time_notes
├── tests/                  # pytest suite (chat media, commands, config, formatter, llm, memory, models, skills, vision…)
├── data/                   # harness.db (gitignored) + .gitkeep
├── .env.example            # Config template
└── requirements.txt        # discord.py, litellm, dotenv, pydantic, aiosqlite, ddgs, httpx, pytest…
```

Module contracts, request lifecycle, DB schema: [`docs/08-architecture.md`](./docs/08-architecture.md) and [`docs/02-getting-started.md`](./docs/02-getting-started.md).

---

## 💾 Data & Database

SQLite at `data/harness.db` (auto-created, gitignored):

- `channel_configs(channel_id PK, model, system_prompt, temperature, thinking_mode)` — per-channel/thread overrides.
- `custom_keys(scope, scope_id, provider, api_key)` — PK `(scope, scope_id, provider)`, scope ∈ `user|channel|guild`.
- `custom_providers(name PK, base_url, api_key)` — arbitrary OpenAI-compatible endpoints.
- `user_profiles(user_id PK, bio)` — `/profile` memory.

---

## 🧪 Running Tests

```bash
pytest -v
```

Covers formatter splitting/fences, thinking modes, memory trim/identity headers, config CRUD + credential precedence, skill registration/toggle/schema, model catalog search/fallback, LLM tool-loop mocking, vision extraction, media download fallback, and webpage SSRF guards. Details: [`docs/09-testing-troubleshooting.md`](./docs/09-testing-troubleshooting.md).

---

## 🆘 Troubleshooting

| Symptom | Fix |
|---|---|
| `DISCORD_BOT_TOKEN is not set!` | Copy `.env.example` → `.env`, set real token, restart. |
| Bot doesn't respond | Enable **Message Content Intent**; check `bot` + `applications.commands` scopes; ensure mention/DM/thread trigger; check logs for `on_ready` + synced count. |
| Slash commands missing | Wait up to ~1h for global sync, or restart; check sync error in logs. |
| `LLM Error: BadRequestError/AuthenticationError` | `/config` → verify model ID; `/key set` or `.env` for that provider; `/models_refresh` to confirm catalog. |
| Vision error tip | Switch to `gpt-4o`, `gemini/gemini-2.0-flash`, or `openrouter/…janus/vl` vision model. |
| `Maximum skill execution iterations reached` | Refine query; `/skills toggle` off noisy tools; check tool output in context. |
| Threads not created | Grant `Create Public Threads` + `Send Messages in Threads`; bot replies in-channel as fallback. |
| Ollama models missing | Ensure Ollama running at `OLLAMA_API_BASE` (default `http://localhost:11434`); `/models_refresh`. |

---

## 🔐 Security Notes

- `.env` and `*.db` are gitignored — never commit tokens or `data/harness.db`.
- `/key set` replies are ephemeral; still, prefer Personal scope and rotate leaked keys.
- `fetch_webpage` blocks `localhost/127.0.0.1/::1/0.0.0.0/169.254.169.254/metadata.google.internal`, private/loopback/link-local/reserved IPs, and DNS-rebind targets; `http(s)` only.
- `calculator` uses AST allow-list, not `eval`.
- Image attachments ≤10 MB inlined as base64; media downloads ≤15 MB, else Embed fallback.

---

## 🗺️ Roadmap / Ideas

- Persistent scratchpad (SQLite) + per-user notes.
- Streaming edits with `StreamThrottle` wired into chat replies.
- Guild-scoped keys UI (`/key list`), temperature slash control.
- Skill permissions (admin-only skills), usage quotas.
- Docker + `docker-compose` (bot + Ollama) example.

Contributions welcome: add a file under `skills/modules/`, add a test under `tests/`, run `pytest -v`, open a PR.

---

## 📚 Docs Index

- [01 Overview](./docs/01-overview.md) · [02 Getting Started](./docs/02-getting-started.md) · [03 Configuration](./docs/03-configuration.md) · [04 Slash Commands](./docs/04-slash-commands.md) · [05 Chat Flow](./docs/05-chat-flow.md) · [06 LLM Engine](./docs/06-llm-engine.md) · [07 Skills](./docs/07-skills.md) · [08 Architecture](./docs/08-architecture.md) · [09 Testing & Troubleshooting](./docs/09-testing-troubleshooting.md)
