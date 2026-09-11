# 07 — Skills

Definitions: `skills/base.py`. Loading/execution: `skills/manager.py`. Built-ins: `skills/modules/`.

## Concepts

- **`@skill(name, description, enabled_by_default=True)`** decorates sync or async functions → `Skill(name, description, func, is_async, enabled_by_default, parameters_schema)`.
- **Schema:** `extract_parameter_schema()` inspects signature + `get_type_hints()`; skips `self/cls/ctx/context`; maps `int→integer, float→number, bool→boolean, str→string, list→array (+items), dict→object, Optional[T]→T`; missing annotation → `string`; no-default → `required`, else `default`.
- **`Skill.execute(**kwargs)`** awaits if async, else calls directly; returns `str(result)` or `Error executing <name>: <Type>: <msg>`.
- **`to_openai_tool()`** → `{"type":"function","function":{"name","description","parameters"}}` for LiteLLM.

## `SkillManager`

- `__init__(modules_dir=skills/modules)`; `_disabled_by_channel: {channel_id: {skill}}` (in-memory only — resets on reboot).
- `load_modules()` — ensures `sys.path`, imports/reloads `skills.modules.*` (skips `__*`), registers every `Skill` (or `list[Skill]`) attribute; returns newly-added count; logs import failures per file without crashing.
- `reload_all()` — clears + reloads.
- `is_skill_enabled(name, channel_id)` — false if unknown or `enabled_by_default=False` or channel-disabled.
- `toggle_skill_for_channel(channel_id, name)` — flips membership; returns new enabled state.
- `get_openai_tools(channel_id)` — enabled skills only.
- `execute(name, args)` — `"Error: Skill '<name>' not found."` if unknown, else delegate.

## Built-in skills

| Name(s) | File | Signature highlights | Behavior |
|---|---|---|---|
| `calculator` | `calculator.py` | `calculate(expression: str)` | AST allow-list (`+-*/ // % **`, unary, `abs/round/pow/min/max/sqrt/sin/cos/tan/log/log10/exp/ceil/floor`, `pi`/`e`); returns result or `Calculation error: …`. |
| `duckduckgo_search`, `web_search` | `web_search.py` | `(query, max_results=4, search_type="all")` | `ddgs.text` (executor thread) → raw HTML POST fallback → Wikipedia API; `funny` appends `funny memes jokes`, `discussions` appends site filter, `news` augments; formats `### title\nbody\n**Source**: url`. |
| `fetch_webpage` | `fetch_webpage.py` | `fetch_webpage(url: str)` | SSRF guard (`http(s)` only, block localhost/private/169.254.169.254/metadata, DNS-rebind check); lxml clean (drops script/style/nav/footer/noscript/svg/header, 4000 chars); JSON/unsupported-type handling; 10 s timeout. |
| `search_gif` | `media_search.py` | `(query, index=1)` | `ddgs.images` (8, retry 6), prefer `.gif`/tenor/giphy; returns `ATTACH_MEDIA: <selected>` + top-5 numbered options + picker note. |
| `search_image` | `media_search.py` | `(query, index=1)` | `ddgs.images` (6); same `ATTACH_MEDIA` contract for photos/art/wallpapers. |
| `get_current_time` | `time_notes.py` | `()` | UTC `YYYY-MM-DD HH:MM:SS UTC` + ISO. |
| `save_scratchpad_note` | `time_notes.py` | `(key, content)` | Lowercased in-memory dict; confirm message. |
| `get_scratchpad_note` | `time_notes.py` | `(key="")` | Empty → list all or empty notice; else hit/miss message. |

## Authoring a new skill

1. Create `skills/modules/<name>.py`:
   ```python
   from skills.base import skill

   @skill(name="shout", description="Uppercase text with exclamation.")
   def shout(text: str, excl: int = 1) -> str:
       """Shout text."""
       return text.upper() + "!" * excl
   ```
2. Run `/skills reload` in Discord (or restart).
3. Test: mention the bot with a prompt that needs it; watch `⚡ Running skill: …`; `/skills toggle` to gate per channel.

Tips: keep args JSON-simple (`str/int/float/bool`); `Optional` for optional; `async def` + `httpx` for I/O; return concise strings (they consume context); handle errors by returning messages, not raising; prefer `enabled_by_default=False` for admin/noisy tools.
