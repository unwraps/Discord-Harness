# 03 — Configuration

## Environment variables (`.env`)

| Variable | Default | Notes |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *(required)* | Validated in `main.py`; exits if missing/placeholder. |
| `DEFAULT_MODEL` | `openrouter/deepseek/deepseek-chat` | Used when channel has no override. Bare `deepseek-…` auto-normalized to `deepseek/…` in `LLMEngine` + `/model`. |
| `DEFAULT_SYSTEM_PROMPT` | helpful assistant | Seeded into every new `ConversationSession` via `set_system_prompt()`. |
| `MAX_HISTORY_TURNS` | `20` | Passed to `MemoryManager`; session keeps ~`max_turns*3` messages. |
| `DEFAULT_TEMPERATURE` | `0.7` | Skipped for strict reasoners (`reasoner`, `o1`, `o3` substrings). |
| `OPENROUTER_API_KEY` … `MISTRAL_API_KEY` | empty | Per-provider keys; see `resolve_credentials()` env map. |
| `OLLAMA_API_BASE` | `http://localhost:11434` | Used only for tag discovery (`/api/tags`). |
| `CUSTOM_API_BASE` / `CUSTOM_API_KEY` | empty | Legacy single custom endpoint. Prefer `/provider add` for N endpoints. |

## Per-channel config

`channel_configs(channel_id PK, model, system_prompt, temperature, thinking_mode)`:

- `get_channel_config()` returns row or defaults (`thinking_mode` defaults to `button`).
- `set_channel_config()` upserts partial fields (model / prompt / temp / thinking).
- Managed via `/model`, `/system set|reset`, `/thinking set`, viewed with `/config`.

## API keys

`custom_keys(scope, scope_id, provider, api_key)`, PK `(scope, scope_id, provider)`:

- `/key set provider:<p> api_key:<k> scope:<user|channel>` → `set_api_key()`. Replies ephemeral with masked key (`abcd...wxyz`).
- `/key clear` → `delete_api_key()`.
- Resolution (`resolve_credentials(model, user_id, channel_id)`):
  1. Custom provider prefix match (`opencode/…` → `get_custom_provider()` → `api_base` + key or `CUSTOM_API_KEY` or `"none"`).
  2. Provider inferred from model string (`openrouter/…` → first segment; `gpt-/o1/o3` → `openai`; `claude` → `anthropic`; `deepseek` → `deepseek`; `gemini` → `gemini`; else `openai`).
  3. `user` key → `channel` key → env map.

## Custom providers

`custom_providers(name PK, base_url, api_key)`:

- `/provider add name:<n> base_url:<url> [api_key]` → `add_custom_provider()` (lowercases name, strips trailing `/`).
- Use as `<name>/<model>` in `/model`. `resolve_credentials()` returns `api_base=base_url`.
- `ModelCatalog._fetch_custom_providers()` queries `<base>/models` (handles `/v1` suffix) and contributes `<name>/<id>` entries; on failure offers `<name>/default`.

## User profiles

`user_profiles(user_id PK, bio)`:

- `/profile set|view|clear` → `set_user_bio()` / `get_user_bio()` / `clear_user_bio()`.
- Bio injected into every user turn as `About User: <bio>` plus username/display/nickname/roles/server/channel (see `ConversationSession.add_user_message()`).
