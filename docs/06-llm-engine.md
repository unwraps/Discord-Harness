# 06 — LLM Engine

Implementation: `harness/llm.py` (`LLMEngine`), `harness/models.py` (`ModelCatalog`), `harness/formatter.py`.

## `generate_response(session, user_id, channel_id, max_tool_iterations=5, on_status)`

1. Load `ChannelConfig` for `channel_id or session.channel_id`; normalize bare `deepseek-…` → `deepseek/…`; `session.set_system_prompt(config.system_prompt)` (insert-or-replace position 0).
2. `resolve_credentials(model, user_id, channel_id)` → `api_key` / `api_base`.
3. `SkillManager.get_openai_tools(channel_id)` → `tools` (+ `tool_choice="auto"`) if non-empty.
4. Loop up to 5:
   - `acompletion(model, messages, temperature?, api_key?, api_base?, tools?)`. Temperature omitted for `reasoner|o1-|/o1|o3-|/o3`.
   - No `tool_calls` → `session.add_assistant_message(content)`; extract `reasoning_content`/`thinking`; return `format_with_thinking(content, reasoning, thinking_mode)`.
   - Else record assistant tool-call message, `json.loads` each `function.arguments` (fallback `{}`), `on_status("⚡ Running skill…")`, `SkillManager.execute(name, args)`, `session.add_tool_result(tool_call_id, name, output)`.
5. Exceeded → `"Maximum skill execution iterations reached. Please try refining your query."`
6. Exceptions → `**LLM Error**: <Type>: <msg>` + tip (`/config` or `/key set`; vision-specific tip suggests `openrouter/deepseek/deepseek-vl2`, `janus-pro-7b`, `gpt-4o`, `gemini/gemini-2.0-flash`).

## Model catalog

`ModelCatalog(config_manager, cache_ttl=3600)`:

- `_cached_models` seeded from `FALLBACK_MODELS` (23 entries across DeepSeek/OpenRouter/Claude/GPT/Gemini/Ollama).
- `get_models()` returns cache, background-refreshes if stale; `refresh_models()` fetches OpenRouter (`/api/v1/models`, optional bearer) → `openrouter/<id>`; DeepSeek (`/models`, needs key) → `deepseek/<id>`; Ollama (`<base>/api/tags`) → `ollama/<name>`; custom providers (`<base>/models`) → `<name>/<id>`; OpenAI (`/v1/models`, filtered `gpt-|o1|o3|chatgpt-`). Merges fallbacks-first + sorted discovery.
- `search(query, 25)` — prefix matches then substring matches, case-insensitive.

## Formatting helpers

- `split_message(content, 1950)` — line-based packing; tracks ```` ```lang ```` state; closes fence before overflow and reopens in next chunk.
- `format_with_thinking(content, reasoning, mode)` — falls back to `<think>…</think>` regex when no side-channel reasoning; `hide` drops; `spoiler` → `> 💭 …\n||…||`; `visible` → `> `-quoted block; `button|collapsible` → `<!--THINKING_BLOCK-->…<!--THINKING_END-->` sentinel parsed by chat cog.
- `StreamThrottle(min_interval_sec=1.2)` — `should_update()` gate for future live-edit streaming.
