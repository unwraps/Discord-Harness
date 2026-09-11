# 10 — Per-User Daily Token Limits

Track and cap each user's LLM token spend per UTC day. Every LiteLLM completion
(prompt + completion tokens, including tool-loop steps) is recorded in SQLite;
users at their cap get a refusal instead of burning more budget.

## How it works

- Storage (`harness/config.py`, tables auto-created in `init_db`):
  - `user_token_limits(user_id PK, daily_limit)` — per-user override. `0` = unlimited.
  - `user_token_usage(user_id, day, prompt_tokens, completion_tokens)` — PK `(user_id, day)`, accumulated with upsert. Day = UTC `YYYY-MM-DD`, resets at UTC midnight.
- Default cap: `DEFAULT_DAILY_TOKEN_LIMIT` env var (`0` = unlimited). Per-user overrides win.
- Enforcement (`harness/llm.py`):
  - Refusal up front if `used >= limit` — the LLM is never called (costs nothing).
  - Usage recorded after **every** completion in the tool loop.
  - Re-checked before tool iterations 2–5, so a long tool chain stops mid-turn instead of overshooting.
- Key methods: `set/clear/get_user_token_limit()`, `add_token_usage()`,
  `get_token_usage()`, `check_daily_limit()` (returns refusal text or `None`).

## Commands (`/limit` group, `cogs/commands.py`)

| Command | Who | Effect |
|---|---|---|
| `/limit set user:@x tokens:50000` | Manage Server / Admin | Cap a user (`0` = unlimited) |
| `/limit view [user]` | self, or admin for others | Shows `used / cap` + in/out split, UTC-midnight reset |
| `/limit clear user:@x` | Manage Server / Admin | Drop override → back to `DEFAULT_DAILY_TOKEN_LIMIT` |

All replies are ephemeral. Setting/clearing/viewing *others* requires
`Manage Server` (or Administrator); in DMs those admin actions are refused.

## Example

```
/limit set user:@heavyuser tokens:20000
/limit view user:@heavyuser
→ 📊 **heavyuser** has used `3,412` / `20,000` tokens today ...
```

Capped users see: `⚠️ Daily token limit reached — you've used X / Y tokens today...`
