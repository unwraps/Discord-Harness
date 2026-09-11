# 01 — Overview

## What is Discord LLM Harness?

A Python Discord bot (`discord.py`) that puts **any LLM behind a Discord mention** and equips it with **Skills** — Python functions exposed as OpenAI-compatible tools via LiteLLM.

It is a *harness*, not a single-model bot: the model is a swappable string (`openrouter/deepseek/deepseek-chat`, `gpt-4o`, `ollama/llama3.3`, `myproxy/mymodel`…), credentials resolve per user/channel/env, and behavior (persona, temperature, thinking display, enabled tools) is per channel/thread.

## Feature map

| Area | Where | Summary |
|---|---|---|
| Multi-model routing | `harness/llm.py`, `harness/models.py` | LiteLLM `acompletion()` + live catalog (OpenRouter, DeepSeek, OpenAI, Ollama, custom) |
| Keys & providers | `harness/config.py`, `cogs/commands.py` | `/key set/clear`, `/provider add`, precedence: custom provider → user → channel → env |
| Skills / tools | `skills/base.py`, `skills/manager.py`, `skills/modules/` | `@skill` decorator, auto JSON schema, hot-reload, per-channel toggle, 5-step tool loop |
| Chat UX | `cogs/chat.py` | Mention/DM/thread triggers, auto-threads, typing, status line, chunked replies |
| Memory | `harness/memory.py` | `MemoryManager` + `ConversationSession`, rolling window (`MAX_HISTORY_TURNS`), rich identity headers |
| Reasoning | `harness/formatter.py`, `cogs/chat.py` | `reasoning_content`/`thinking`/`<think>` extraction; `button/spoiler/visible/hide` modes |
| Vision | `cogs/chat.py` | Attachments/replies/URLs → `image_url` parts (base64 ≤10 MB) |
| Media out | `cogs/chat.py`, `skills/modules/media_search.py` | `ATTACH_MEDIA:` contract → download (≤15 MB) → `File` / Embed fallback |
| Formatting | `harness/formatter.py` | `split_message()` ~1950 chars with fence preservation; `StreamThrottle` helper |
| Config UI | `cogs/commands.py` | `/model`, `/models`, `/models_refresh`, `/system`, `/thinking`, `/profile`, `/clear`, `/config` |
| Persistence | `harness/config.py`, `data/harness.db` | SQLite (`aiosqlite`): channel configs, keys, providers, bios |

## Who is it for?

- Discord communities wanting one bot fronting many models/keys.
- Builders who want to add LLM tools by dropping a single Python file.
- Local-model users (Ollama/LM Studio/vLLM) who want the same UX as hosted APIs.

## Non-goals

- No web dashboard; all config is `.env` + slash commands.
- No streaming token edits yet (`StreamThrottle` exists as a helper, not wired into live replies).
- Scratchpad notes are in-memory (not yet persistent).
