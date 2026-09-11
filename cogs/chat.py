"""
Chat Event Handler Cog: Handles mentions, threads, DMs, typing indicators,
and streaming responses with markdown splitting.
"""

from __future__ import annotations
import logging
import discord
from discord.ext import commands

from harness.config import ConfigManager
from harness.formatter import split_message
from harness.llm import LLMEngine
from harness.memory import MemoryManager
from skills.manager import SkillManager

logger = logging.getLogger(__name__)

import base64
import io
import re
from typing import List, Optional, Tuple
import httpx


async def extract_message_images(message: discord.Message) -> List[str]:
    """
    Extract visual images from message attachments, replied-to messages, or direct image URLs.
    Encodes attachments <= 10MB into base64 data URIs so they never expire or get blocked by CDNs.
    """
    images: List[str] = []

    # 1. Direct attachments on the message
    candidates = list(message.attachments)

    # 2. Check if user is replying to a message with image attachments
    if message.reference and isinstance(getattr(message.reference, "resolved", None), discord.Message):
        ref_msg = message.reference.resolved
        candidates.extend(ref_msg.attachments)

    for att in candidates:
        is_image = (
            (att.content_type and att.content_type.startswith("image/"))
            or any(att.filename.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"))
        )
        if not is_image:
            continue

        if len(images) >= 3:
            break

        try:
            # Download bytes and convert to base64 data URI if under 10MB
            if getattr(att, "size", 0) <= 10 * 1024 * 1024:
                att_bytes = await att.read()
                b64 = base64.b64encode(att_bytes).decode("utf-8")
                content_type = att.content_type or "image/jpeg"
                images.append(f"data:{content_type};base64,{b64}")
            else:
                images.append(att.url)
        except Exception as e:
            logger.warning(f"Could not read image attachment {att.filename}: {e}")
            images.append(att.url)

    # 3. Direct image URLs in text (if not already having attachments)
    if not images and message.content:
        url_matches = re.findall(
            r'https?://[^\s<>"\'\)]+\.(?:png|jpe?g|webp|gif)(?:\?[^\s<>"\'\)]*)?',
            message.content,
            re.IGNORECASE,
        )
        for u in url_matches[:2]:
            images.append(u)

    return images


async def download_discord_media(url: str) -> Tuple[Optional[discord.File], Optional[discord.Embed]]:
    """Download an image or animated GIF and return as a discord.File attachment or fallback Embed."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=8.0, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code == 200 and len(r.content) > 0 and len(r.content) <= 15 * 1024 * 1024:
                content_type = r.headers.get("content-type", "").lower()
                clean_url_path = url.split("?")[0].lower()
                if "gif" in content_type or clean_url_path.endswith(".gif") or "tenor.com" in url or "giphy.com" in url:
                    filename = "animation.gif"
                elif "png" in content_type or clean_url_path.endswith(".png"):
                    filename = "image.png"
                elif "webp" in content_type or clean_url_path.endswith(".webp"):
                    filename = "image.webp"
                else:
                    filename = "image.jpg"
                return discord.File(io.BytesIO(r.content), filename=filename), None
    except Exception as e:
        logger.warning(f"Failed to download media file from {url}: {e}")

    # Fallback to Discord Embed if download failed or file is too large
    try:
        embed = discord.Embed()
        embed.set_image(url=url)
        return None, embed
    except Exception:
        return None, None


def extract_media_url(session_messages: list, response_text: str) -> Optional[str]:
    """Scan model response and recent tool outputs for media URLs to attach."""
    # 1. Check response_text FIRST: if the model explicitly picked or mentioned a media URL, honor the model's choice!
    match = re.search(r"ATTACH_MEDIA:\s*(https?://\S+)", response_text)
    if match:
        return match.group(1).strip()

    direct_match = re.search(
        r'https?://[^\s<>"\'\)]+\.(?:gif|png|jpe?g|webp)(?:\?[^\s<>"\'\)]*)?',
        response_text,
        re.IGNORECASE,
    )
    if direct_match:
        return direct_match.group(0).strip()

    tenor_match = re.search(
        r'https?://(?:media[0-9]*\.)?(?:tenor\.com|giphy\.com|gifdb\.com)/[^\s<>"\'\)]+',
        response_text,
        re.IGNORECASE,
    )
    if tenor_match:
        return tenor_match.group(0).strip()

    # 2. If the model did not include a specific URL in response_text, fall back to the tool's default selected ATTACH_MEDIA
    last_user_idx = 0
    for idx in range(len(session_messages) - 1, -1, -1):
        if session_messages[idx].get("role") == "user":
            last_user_idx = idx
            break

    for msg in reversed(session_messages[last_user_idx:]):
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            match = re.search(r"ATTACH_MEDIA:\s*(https?://\S+)", content)
            if match:
                return match.group(1).strip()

class ThinkingToggleView(discord.ui.View):
    """Interactive collapsible button view for LLM thinking/reasoning process."""

    def __init__(self, main_text: str, reasoning_text: str, timeout: Optional[float] = 86400):
        super().__init__(timeout=timeout)
        self.main_text = main_text
        self.reasoning_text = reasoning_text
        self.is_expanded = False

    @discord.ui.button(label="View Thought Process", emoji="🧠", style=discord.ButtonStyle.secondary)
    async def toggle_thinking(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            button.label = "Hide Thought Process"
            button.emoji = "🔼"
            button.style = discord.ButtonStyle.primary

            quoted_thinking = "\n".join(f"> {line}" for line in self.reasoning_text.splitlines())
            expanded_text = f"💭 **Thought Process:**\n{quoted_thinking}\n\n{self.main_text}"

            if len(expanded_text) <= 1950:
                await interaction.response.edit_message(content=expanded_text, view=self)
            else:
                # If too long to fit inside one message edit, send as private ephemeral popup!
                button.label = "View Thought Process"
                button.emoji = "🧠"
                button.style = discord.ButtonStyle.secondary
                self.is_expanded = False
                chunks = split_message(f"💭 **Full Thought Process:**\n\n{self.reasoning_text}", limit=1900)
                await interaction.response.send_message(content=chunks[0], ephemeral=True)
        else:
            button.label = "View Thought Process"
            button.emoji = "🧠"
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(content=self.main_text, view=self)


class ChatCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        llm_engine: LLMEngine,
        memory_manager: MemoryManager,
        config_manager: ConfigManager,
        skill_manager: SkillManager,
    ):
        self.bot = bot
        self.llm = llm_engine
        self.memory = memory_manager
        self.config = config_manager
        self.skills = skill_manager

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Ignore messages from any bot, including self
        if message.author.bot:
            return

        # Determine if bot should respond:
        # 1. Direct Message (DM)
        is_dm = isinstance(message.channel, discord.DMChannel)

        # 2. Bot is explicitly mentioned
        is_mentioned = self.bot.user in message.mentions if self.bot.user else False

        # 3. Message is in a thread created by the bot
        is_bot_thread = (
            isinstance(message.channel, discord.Thread)
            and message.channel.owner_id == self.bot.user.id
        )

        if not (is_dm or is_mentioned or is_bot_thread):
            return

        # Clean prompt content by removing bot mention
        clean_content = message.content
        if self.bot.user:
            clean_content = clean_content.replace(f"<@{self.bot.user.id}>", "").strip()
            clean_content = clean_content.replace(f"<@!{self.bot.user.id}>", "").strip()

        # Extract visual images (attachments, replied images, direct image URLs)
        images = await extract_message_images(message)

        if not clean_content and not images:
            return

        if not clean_content and images:
            clean_content = "Please analyze and describe this image in detail."

        # Choose destination channel/thread
        target_channel = message.channel

        # If mentioned in a regular text channel (not DM, not already a thread), create a thread if permitted
        if is_mentioned and not is_dm and not isinstance(message.channel, discord.Thread) and message.guild:
            perms = message.channel.permissions_for(message.guild.me)
            if getattr(perms, "create_public_threads", False) and getattr(perms, "send_messages_in_threads", False):
                try:
                    # Name thread after first 30 chars of prompt
                    thread_name = clean_content[:30].strip() or "Chat"
                    target_channel = await message.create_thread(
                        name=f"🤖 {thread_name}",
                        auto_archive_duration=60,
                    )
                except Exception as e:
                    logger.warning(f"Could not create thread, responding in channel: {e}")
        # Replace role mentions <@&role_id> with @RoleName
        if message.role_mentions:
            for role in message.role_mentions:
                clean_content = clean_content.replace(f"<@&{role.id}>", f"@{role.name}")

        # Replace channel mentions <#channel_id> with #channel-name
        if message.channel_mentions:
            for ch in message.channel_mentions:
                clean_content = clean_content.replace(f"<#{ch.id}>", f"#{ch.name}")

        # Extract other mentioned users in the message (excluding the bot itself)
        mentioned_users_data = []
        for m in message.mentions:
            if self.bot.user and m.id == self.bot.user.id:
                continue

            # Ensure we have the full Member object if in a guild
            if message.guild and not isinstance(m, discord.Member):
                guild_m = message.guild.get_member(m.id)
                if not guild_m:
                    try:
                        guild_m = await message.guild.fetch_member(m.id)
                    except Exception:
                        guild_m = None
                if guild_m:
                    m = guild_m

            # Replace raw Discord <@id> mention with @DisplayName in prompt text
            clean_content = clean_content.replace(f"<@{m.id}>", f"@{m.display_name}")
            clean_content = clean_content.replace(f"<@!{m.id}>", f"@{m.display_name}")

            m_bio = await self.config.get_user_bio(m.id)
            m_roles = [r.name for r in getattr(m, "roles", []) if r.name != "@everyone"]
            m_joined = m.joined_at.strftime("%Y-%m-%d") if getattr(m, "joined_at", None) else None
            m_created = m.created_at.strftime("%Y-%m-%d") if getattr(m, "created_at", None) else None
            m_nick = getattr(m, "nick", None)
            top_role = m.top_role.name if getattr(m, "top_role", None) and m.top_role.name != "@everyone" else None

            mentioned_users_data.append({
                "id": m.id,
                "username": m.name,
                "display_name": m.display_name,
                "nickname": m_nick,
                "top_role": top_role,
                "roles": m_roles,
                "joined_at": m_joined,
                "created_at": m_created,
                "bio": m_bio,
                "is_bot": m.bot,
            })

        # Extract rich author user & environment metadata
        author = message.author
        if message.guild and not isinstance(author, discord.Member):
            guild_author = message.guild.get_member(author.id)
            if not guild_author:
                try:
                    guild_author = await message.guild.fetch_member(author.id)
                except Exception:
                    guild_author = None
            if guild_author:
                author = guild_author

        user_bio = await self.config.get_user_bio(author.id)
        roles = [r.name for r in getattr(author, "roles", []) if r.name != "@everyone"]
        author_top_role = author.top_role.name if getattr(author, "top_role", None) and author.top_role.name != "@everyone" else None

        user_info = {
            "username": author.name,
            "display_name": author.display_name,
            "nickname": getattr(author, "nick", None),
            "top_role": author_top_role,
            "bio": user_bio,
            "roles": roles,
            "server": message.guild.name if message.guild else "Direct Message",
            "channel": getattr(target_channel, "name", "DM"),
            "mentioned_users": mentioned_users_data,
        }

        # Retrieve or initialize session
        session = self.memory.get_session(target_channel.id)
        session.add_user_message(
            clean_content,
            author_name=message.author.display_name,
            user_info=user_info,
            images=images if images else None,
        )

        # Status message placeholder (e.g. for showing skill execution)
        status_msg: discord.Message | None = None

        async def on_status_update(status_text: str) -> None:
            nonlocal status_msg
            try:
                if status_msg is None:
                    status_msg = await target_channel.send(f"_{status_text}_")
                else:
                    await status_msg.edit(content=f"_{status_text}_")
            except Exception:
                pass

        async with target_channel.typing():
            response_text = await self.llm.generate_response(
                session=session,
                user_id=message.author.id,
                channel_id=target_channel.id,
                on_status=on_status_update,
            )

        # Delete status indicator if it was created
        if status_msg is not None:
            try:
                await status_msg.delete()
            except Exception:
                pass

        # Check if response has collapsible thinking process
        thinking_view = None
        thinking_match = re.search(r"<!--THINKING_BLOCK-->\n(.*?)\n<!--THINKING_END-->\n?", response_text, flags=re.DOTALL)
        if thinking_match:
            reasoning_text = thinking_match.group(1).strip()
            response_text = re.sub(r"<!--THINKING_BLOCK-->\n.*?\n<!--THINKING_END-->\n?", "", response_text, flags=re.DOTALL).strip()
            if reasoning_text:
                thinking_view = ThinkingToggleView(main_text=response_text, reasoning_text=reasoning_text)

        # Check if there is any media (GIF or Image) to attach to chat
        media_url = extract_media_url(session.get_messages(), response_text)
        discord_file = None
        discord_embed = None
        if media_url:
            discord_file, discord_embed = await download_discord_media(media_url)
            # Clean technical tags and naked media URL from user-facing text
            response_text = re.sub(r"ATTACH_MEDIA:\s*https?://\S+", "", response_text)
            if media_url in response_text:
                response_text = response_text.replace(media_url, "")
            response_text = re.sub(r'!\[.*?\]\(\s*\)', '', response_text)
            response_text = response_text.strip()
            if thinking_view:
                thinking_view.main_text = response_text

        # Split and send response in Discord-safe chunks
        chunks = split_message(response_text, limit=1950) if response_text else []

        # Auto-speak the reply in VC if enabled (fire-and-forget, never blocks text)
        try:
            voice_cog = self.bot.get_cog("VoiceCog")
            if voice_cog is not None and message.guild is not None and response_text:
                import asyncio as _asyncio

                author_voice = getattr(message.author, "voice", None)
                _asyncio.create_task(
                    voice_cog.speak_response(
                        message.guild,
                        target_channel.id,
                        response_text,
                        parent_id=getattr(target_channel, "parent_id", None),
                        voice_channel=author_voice.channel if author_voice else None,
                    )
                )
        except Exception:
            pass

        if not chunks:
            # If the response only had media/view and no extra text, send directly!
            kwargs = {}
            if discord_file:
                kwargs["file"] = discord_file
            elif discord_embed:
                kwargs["embed"] = discord_embed
            elif media_url:
                kwargs["content"] = media_url
            if thinking_view:
                kwargs["view"] = thinking_view
            if kwargs:
                await target_channel.send(**kwargs)
        else:
            for i, chunk in enumerate(chunks):
                # Attach file/embed/view to the final message chunk
                if i == len(chunks) - 1:
                    kwargs = {"content": chunk}
                    if discord_file:
                        kwargs["file"] = discord_file
                    elif discord_embed:
                        kwargs["embed"] = discord_embed
                    if thinking_view:
                        kwargs["view"] = thinking_view
                    await target_channel.send(**kwargs)
                else:
                    await target_channel.send(content=chunk)


async def setup_chat(
    bot: commands.Bot,
    llm_engine: LLMEngine,
    memory_manager: MemoryManager,
    config_manager: ConfigManager,
    skill_manager: SkillManager,
) -> None:
    await bot.add_cog(ChatCog(bot, llm_engine, memory_manager, config_manager, skill_manager))
