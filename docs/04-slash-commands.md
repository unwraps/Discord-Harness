# 04 — Slash Commands

All commands sync globally on `on_ready`. Implementation: `cogs/commands.py`.

## Model selection

- **`/model [model_name]`** — with no arg, shows embed (current model, catalog size, reasoning/fast picks). With arg, sets channel model (auto-prefixes bare `deepseek-…` → `deepseek/…`). Autocomplete searches `ModelCatalog.search()` (prefix first, then substring, 25 max) and offers `Custom: <typing>` at top.
- **`/setmodel <model_name>`** — alias with same autocomplete.
- **`/models`** — static popular-models embed (DeepSeek, OpenRouter, Anthropic/OpenAI, Gemini, Ollama).
- **`/models_refresh`** — defers ephemeral, calls `refresh_models()`, reports count.

Example:
```
/model model_name:openrouter/deepseek/deepseek-chat
/models_refresh
```

## Keys & providers

- **`/key set provider:<openrouter|deepseek|openai|anthropic|gemini|groq|mistral|custom> api_key:<k> scope:<user|channel>`** — default scope `user`. Ephemeral confirm with masked key.
- **`/key clear provider:<p> scope:<…>`** — ephemeral deleted/not-found notice.
- **`/provider add name:<prefix> base_url:<https://…/v1> [api_key]`** — ephemeral confirm; use as `/model model_name:<prefix>/<model>`.

Example:
```
/provider add name:opencode base_url:http://localhost:11434/v1
/model model_name:opencode/qwen2.5
```

## Persona & memory

- **`/system set prompt:<text>`** — sets channel system prompt (echoes first 200 chars).
- **`/system reset`** — restores `DEFAULT_SYSTEM_PROMPT`.
- **`/clear`** — `MemoryManager.clear_session()` (keeps system message).
- **`/config`** — gold embed: model, temperature, thinking mode, enabled skills, system prompt (300 chars).

## Skills

- **`/skills list`** — green embed, one field per skill: `name (🟢 Active|🔴 Disabled)` + 150-char description.
- **`/skills toggle skill_name:<name>`** — autocomplete over registry; flips channel-disabled set; missing name → ephemeral error + hint.
- **`/skills reload`** — `reload_all()` (clears + `load_modules()`), reports count.

## Thinking display

- **`/thinking set mode:<button|spoiler|visible|hide>`**
  - `button` — collapsible 🧠 View Thought Process (default, recommended).
  - `spoiler` — `||reasoning||` block.
  - `visible` — `> ` blockquote.
  - `hide` — drop reasoning.

## Profiles

- **`/profile set bio:<text>`** — saved per user, ephemeral confirm (300-char echo).
- **`/profile view`** — ephemeral bio or setup hint.
- **`/profile clear`** — deletes; reports deleted vs not-found.
