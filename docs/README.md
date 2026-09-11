# Docs Index

Welcome to the **Discord LLM Harness** documentation. Start here, or jump to a topic.

## Contents

1. [01 Overview](./01-overview.md) — what this bot is, feature map, who's it for
2. [02 Getting Started](./02-getting-started.md) — Discord portal setup, install, `.env`, first run
3. [03 Configuration](./03-configuration.md) — env vars, per-channel config, keys, custom providers, profiles
4. [04 Slash Commands](./04-slash-commands.md) — every command with examples
5. [05 Chat Flow](./05-chat-flow.md) — triggers, threads, vision, thinking UI, media attach
6. [06 LLM Engine](./06-llm-engine.md) — LiteLLM routing, tool loop, reasoning, errors
7. [07 Skills](./07-skills.md) — built-ins + authoring your own in 10 seconds
8. [08 Architecture](./08-architecture.md) — file map, lifecycle, DB schema, key classes
9. [09 Testing & Troubleshooting](./09-testing-troubleshooting.md) — pytest, common errors, security
10. [10 Token Limits](./10-token-limits.md) — per-user daily budgets, `/limit` commands

> Source of truth is code: `main.py`, `cogs/chat.py`, `cogs/commands.py`, `harness/config.py`, `harness/llm.py`, `harness/memory.py`, `harness/models.py`, `harness/formatter.py`, `skills/base.py`, `skills/manager.py`, `skills/modules/`.
