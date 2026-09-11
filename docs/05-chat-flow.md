# 05 — Chat Flow

Implementation: `cogs/chat.py` (`ChatCog.on_message`, helpers, `ThinkingToggleView`).

## Triggers

Responds iff **any** is true; else returns silently:

1. **DM** (`isinstance(channel, DMChannel)`).
2. **Mentioned** (`bot.user in message.mentions`).
3. **Bot-owned thread** (`Thread.owner_id == bot.user.id`).

Ignores all bot-authored messages (including self).

## Pre-processing

1. Strip `<@id>` / `<@!id>` bot mentions → `clean_content`.
2. `extract_message_images(message)`:
   - Direct attachments + replied-to message attachments that are `image/*` or `.png/.jpg/.jpeg/.webp/.gif`.
   - ≤10 MB → download → `data:<mime>;base64,…`; larger → raw URL. Cap 3.
   - Else regex direct image URLs in text (cap 2).
3. Empty text + no images → ignore. Images-only → default prompt *“Please analyze and describe this image in detail.”*
4. Thread routing: mentioned in a guild text channel (not DM/thread) + has `Create Public Threads` & `Send Messages in Threads` → `create_thread(name="🤖 <first 30 chars>", auto_archive_duration=60)`; on failure stay in channel.
5. Replace `<@&role>` → `@RoleName`, `<#ch>` → `#name`, `<@user>` → `@DisplayName`.
6. Build `mentioned_users_data` (skip bot): fetch full `Member` if needed; capture username/display/nick/top role/roles/join/created/bio/is_bot. Replace raw mentions in text.
7. Build `user_info` for author: username/display/nick/top role/bio/roles/server/channel + mentions; `get_session(target.id).add_user_message(clean_content, author_name, user_info, images)`.

## Generation

- `async with target.typing()` + `on_status` callback posts/edits `_⚡ Running skill: …_` message per tool call (deleted before final send).
- `LLMEngine.generate_response(session, user_id, channel_id, on_status)` runs the tool loop.

## Post-processing & send

1. **Thinking view:** regex `<!--THINKING_BLOCK-->…<!--THINKING_END-->` (button mode) → strip from text, build `ThinkingToggleView(main_text, reasoning_text)`. Button toggles expanded `💭 Thought Process` + main text; if >1950 chars, sends first 1900-char chunk ephemerally instead.
2. **Media:** `extract_media_url(session_messages, response_text)` priority: explicit `ATTACH_MEDIA: <url>` in reply → direct `.gif/.png/.jpg/.jpeg/.webp` URL → tenor/giphy/gifdb link → last `ATTACH_MEDIA:` in tool outputs since last user turn. `download_discord_media(url)` (≤15 MB, UA-spoofed) → `File(animation.gif|image.png|webp|jpg)` else `Embed(image=url)`. Strips `ATTACH_MEDIA:` line, naked media URL, and empty `![]()` from visible text.
3. **Chunk & send:** `split_message(text, 1950)`; if no text but media/view exists, send media alone; else send chunks in order, attaching file/embed/view to the **last** chunk.

## Vision & media limits

| Direction | Cap | Behavior |
|---|---|---|
| Inbound images | 3 attachments + 2 URL fallback | base64 inline ≤10 MB else URL |
| Outbound media | first match wins | download ≤15 MB → File; else Embed; else raw URL |
| Chunks | 1950 chars | fence-aware split |
| Thinking ephemeral | 1900 chars | first chunk only when too long for edit |
