# 09 — Testing & Troubleshooting

## Running tests

```bash
pytest -v
```

Suite (`tests/`): `test_formatter` (chunking, fence preservation, thinking modes), `test_memory` (system-prompt pinning, trim keeps ≤`max_turns*3` and drops orphan `tool` heads, identity/mention headers), `test_config` (channel CRUD, keys, providers, bio, credential precedence), `test_skills` (register/toggle/schema/execute), `test_models` (search ordering, fallback), `test_llm` (mocked `acompletion` tool loop, error tips), `test_vision` / `test_chat_media` (attachment/reply/URL extraction, base64, media-URL priority, download fallback), `test_media_search` (GIF/image option formatting), `test_fetch_webpage` (SSRF blocks, HTML cleaning), `test_commands` (slash wiring).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `DISCORD_BOT_TOKEN is not set!` + exit 1 | Missing `.env` | `cp .env.example .env`, set real token. |
| No reply to messages | Missing intent / wrong trigger | Enable Message Content Intent; use DM/mention/bot-thread; check `on_ready` + `synced N commands` logs. |
| Commands not appearing | Global sync delay | Wait ≤1 h or restart; inspect sync exception. |
| `LLM Error: AuthenticationError` | Wrong/missing key for that provider | `/config` → model; `/key set` or `.env`; retry. |
| `LLM Error: BadRequestError/NotFound` | Bad model ID | `/models_refresh`, pick from `/model` autocomplete. |
| Vision/multimodal tip | Non-vision model + images | Switch to `gpt-4o`, `gemini/gemini-2.0-flash`, `openrouter/…vl/janus`. |
| `Maximum skill execution iterations reached` | Tool ping-pong | Narrow prompt; `/skills toggle` off extras; `/clear`. |
| No auto-thread | Missing perms | Grant Create Public Threads + Send in Threads; else in-channel reply is expected. |
| Ollama models absent | Daemon down / wrong base | Start Ollama; set `OLLAMA_API_BASE`; `/models_refresh`. |
| Skill not found after add | Forgot reload / bad import | Check logs `Failed to load skill module`; `/skills reload`. |
| Toggles reset on reboot | By design (in-memory `_disabled_by_channel`) | Re-toggle or extend to persist in SQLite. |
| Scratchpad empty after reboot | In-memory `_SCRATCHPAD` | Same — persist if needed. |

## Security checklist

- Never commit `.env` or `data/harness.db` (both gitignored; `.env.example` is the only template).
- Rotate any key pasted in a non-ephemeral channel; prefer Personal scope.
- `fetch_webpage` is SSRF-hardened but `verify=False` — avoid sensitive intranet use.
- `calculator` is AST-restricted; do not replace with `eval`.
- Cap awareness: 10 MB inline images, 15 MB media downloads, 1950-char chunks, 5 tool steps/turn.

## Useful paths when debugging

- Startup: `main.py:main`, `main.py:on_ready`.
- Chat: `cogs/chat.py:on_message`, `extract_message_images`, `extract_media_url`, `ThinkingToggleView`.
- LLM: `harness/llm.py:generate_response`.
- Config/creds: `harness/config.py:resolve_credentials`, `get_channel_config`.
- Models: `harness/models.py:refresh_models`, `search`.
- Skills: `skills/manager.py:load_modules`, `execute`; `skills/base.py:extract_parameter_schema`.
