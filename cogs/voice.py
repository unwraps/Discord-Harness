"""
Voice Channel Cog: join/leave/speak in Discord voice channels using Edge TTS.

Commands (/voice group):
  /voice join          - join your current voice channel
  /voice leave         - leave voice + clear speech queue
  /voice say <text>    - speak text aloud (joins your VC first if needed)
  /voice stop          - stop current speech and clear queue
  /voice auto <on|off> - auto-speak LLM replies from this text channel when in VC
  /voice voice [name]  - view or change the TTS voice for this server

Auto-speak: ChatCog calls VoiceCog.speak_response() (fire-and-forget) after each
LLM reply. Speech is queued per guild so replies never overlap.

Requires: FFmpeg in PATH, PyNaCl installed, bot permissions Connect + Speak,
and the voice_states gateway intent (see main.py create_bot).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.opus import OpusNotLoaded

from harness.tts import CURATED_VOICES, TTSEngine, chunk_for_speech

logger = logging.getLogger(__name__)


@dataclass
class _GuildVoiceState:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    player_task: Optional[asyncio.Task] = None
    auto_channels: set = field(default_factory=set)
    voice: Optional[str] = None


class VoiceCog(commands.Cog, name="VoiceCog"):
    def __init__(self, bot: commands.Bot, tts_engine: Optional[TTSEngine] = None):
        self.bot = bot
        self.tts = tts_engine or TTSEngine()
        self._states: Dict[int, _GuildVoiceState] = {}
        # Last voice channel per guild, so auto-speak can rejoin after a drop.
        # Cleared on explicit /voice leave so the bot never rejoins uninvited.
        self._last_channel: Dict[int, int] = {}

    # --- internal helpers ---

    def _state(self, guild_id: int) -> _GuildVoiceState:
        if guild_id not in self._states:
            self._states[guild_id] = _GuildVoiceState()
        return self._states[guild_id]

    def is_auto(self, guild_id: int, channel_id: int, parent_id: Optional[int] = None) -> bool:
        auto = self._state(guild_id).auto_channels
        if channel_id in auto:
            return True
        # Threads: auto enabled on the parent text channel also covers its threads.
        return parent_id is not None and parent_id in auto

    async def _reply(self, interaction: discord.Interaction, msg: str) -> None:
        """Reply via followup if already deferred/responded, else direct response."""
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def _connect_to_author(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceClient]:
        """Join (or move to) the invoker's voice channel. Returns the VoiceClient."""
        if not interaction.guild:
            await self._reply(interaction, "❌ Voice only works in servers, not DMs.")
            return None

        member = interaction.user
        voice_state = getattr(member, "voice", None)
        if not voice_state or not voice_state.channel:
            await self._reply(interaction, "❌ Join a voice channel first, then run this command.")
            return None

        channel = voice_state.channel
        perms = channel.permissions_for(interaction.guild.me)
        if not getattr(perms, "connect", False) or not getattr(perms, "speak", False):
            await self._reply(
                interaction,
                "❌ I need **Connect** and **Speak** permissions in that voice channel.",
            )
            return None

        vc = interaction.guild.voice_client
        try:
            vc = await self._join_channel(channel)
        except Exception as e:
            logger.error(f"Voice connect failed: {e}", exc_info=True)
            await self._reply(
                interaction,
                "❌ Could not join voice. Make sure **PyNaCl** and **davey** are installed "
                "(`pip install -r requirements.txt`), FFmpeg is in PATH, "
                "and I have Connect/Speak.",
            )
            return None
        if vc is None:
            logger.error("Voice connect timed out during UDP handshake.")
            await self._reply(
                interaction,
                "❌ Timed out reaching Discord's voice server (UDP handshake failed).\n"
                "• Allow **Python through Windows Firewall** (UDP out)\n"
                "• Disable any **VPN/proxy** and retry\n"
                "• Try another network, or change the channel's **voice region** "
                "(channel settings → Region Override)\n"
                "• Then run `/voice join` again.",
            )
            return None
        return vc

    async def _join_channel(
        self, channel: discord.VoiceChannel, attempts: int = 3
    ) -> Optional[discord.VoiceClient]:
        """
        Connect (or move) to a voice channel with retries across flaky UDP.
        Never replies to Discord; returns the VoiceClient or None.
        Remembers the channel per guild for auto-rejoin after drops.
        """
        guild = channel.guild
        for attempt in range(1, attempts + 1):
            # A timed-out attempt can leave a half-open client behind; drop it
            # so the retry starts clean instead of reusing a dead session.
            stale = guild.voice_client
            if stale is not None and not stale.is_connected():
                try:
                    await stale.disconnect(force=True)
                except Exception:
                    pass
            try:
                vc = guild.voice_client
                if vc is None:
                    vc = await channel.connect()
                elif vc.channel is None or vc.channel.id != channel.id:
                    await vc.move_to(channel)
                self._last_channel[guild.id] = channel.id
                return vc
            except (asyncio.TimeoutError, TimeoutError):
                logger.warning(
                    f"Voice UDP handshake timed out "
                    f"(attempt {attempt}/{attempts}) for '{channel.name}'."
                )
                if attempt < attempts:
                    await asyncio.sleep(1.5 * attempt)
        return None

    def _ensure_player(self, guild: discord.Guild) -> None:
        state = self._state(guild.id)
        if state.player_task is None or state.player_task.done():
            state.player_task = asyncio.create_task(self._player_loop(guild))

    async def _player_loop(self, guild: discord.Guild) -> None:
        """Drain the per-guild speech queue sequentially."""
        state = self._state(guild.id)
        loop = asyncio.get_running_loop()
        while True:
            try:
                path = await state.queue.get()
            except asyncio.CancelledError:
                break
            try:
                vc = guild.voice_client
                if vc is None or not vc.is_connected():
                    logger.warning("Skipping speech: not connected to voice.")
                    try:
                        from pathlib import Path as _P

                        _P(str(path)).unlink(missing_ok=True)
                    except Exception:
                        pass
                    continue
                # Wait for any current audio to finish before starting the next file
                while vc.is_playing() or vc.is_paused():
                    await asyncio.sleep(0.3)
                done = asyncio.Event()

                def _after(_err: Optional[Exception]) -> None:
                    # `after` runs in discord.py's voice thread: hop back
                    # onto the event loop thread safely.
                    if _err is not None:
                        logger.warning(f"Speech player reported error: {_err}")
                    loop.call_soon_threadsafe(done.set)

                try:
                    source = discord.FFmpegPCMAudio(str(path))
                except Exception as e:
                    logger.error(f"FFmpeg failed (is ffmpeg in PATH?): {e}")
                    continue
                try:
                    vc.play(source, after=_after)
                except OpusNotLoaded:
                    logger.error(
                        "Opus codec not loaded — cannot encode audio. "
                        "Restart the bot (main.ensure_opus loads discord/bin opus)."
                    )
                    continue
                except Exception as e:
                    logger.error(f"Could not start playback (already playing?): {e}")
                    continue
                logger.info(f"Playing speech file {path} in {guild.name}.")
                await done.wait()
                logger.info("Speech playback finished.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Voice playback error: {e}", exc_info=True)
            finally:
                try:
                    from pathlib import Path as _P

                    _P(str(path)).unlink(missing_ok=True)
                except Exception:
                    pass

    async def _enqueue_text(self, guild: discord.Guild, text: str) -> int:
        """Synthesize text into chunk MP3s and queue them. Returns chunk count."""
        state = self._state(guild.id)
        chunks = chunk_for_speech(text)
        if not chunks:
            return 0
        count = 0
        for chunk in chunks:
            try:
                path = await self.tts.synthesize(chunk, voice=state.voice)
            except Exception as e:
                logger.error(f"TTS synthesize failed: {e}", exc_info=True)
                raise
            await state.queue.put(str(path))
            count += 1
        logger.info(f"Enqueued {count} utterance(s); queue depth now {state.queue.qsize()}.")
        self._ensure_player(guild)
        return count

    # --- auto-speak entry point (called by ChatCog, fire-and-forget) ---

    async def speak_response(
        self,
        guild: Optional[discord.Guild],
        channel_id: int,
        text: str,
        parent_id: Optional[int] = None,
        voice_channel: Optional[discord.VoiceChannel] = None,
    ) -> None:
        """Speak an LLM reply aloud if auto-speak is on and bot is in VC."""
        if guild is None or not text or not text.strip():
            return
        if not self.is_auto(guild.id, channel_id, parent_id):
            logger.info(
                f"Auto-speak skipped: not enabled for channel {channel_id} "
                f"(parent {parent_id}). Run /voice auto mode:on there."
            )
            return
        vc = guild.voice_client
        if vc is None or not vc.is_connected():
            # Don't just skip: rejoin the author's VC, else the last known VC.
            target = voice_channel
            if target is None:
                last_id = self._last_channel.get(guild.id)
                if last_id is not None:
                    target = guild.get_channel(last_id)
            if target is None:
                logger.warning(
                    "Auto-speak skipped: bot is not in a voice channel "
                    "(join one and run /voice join)."
                )
                return
            logger.info(f"Auto-speak: (re)joining voice '{target.name}' before speaking.")
            vc = await self._join_channel(target)
            if vc is None:
                logger.warning("Auto-speak skipped: could not (re)join voice.")
                return
        try:
            count = await self._enqueue_text(guild, text)
            logger.info(f"Auto-speak queued {count} utterance(s) for channel {channel_id}.")
        except Exception as e:
            logger.warning(f"Auto-speak failed: {e}")

    # --- /voice command group ---

    voice_group = app_commands.Group(name="voice", description="Voice channel + speech controls")

    @voice_group.command(name="join", description="Join your current voice channel")
    async def voice_join(self, interaction: discord.Interaction) -> None:
        # Defer up-front: voice handshake can take longer than Discord's 3s
        # interaction window, and responding late raises "Unknown interaction".
        await interaction.response.defer(ephemeral=True)
        vc = await self._connect_to_author(interaction)
        if vc is None:
            return
        await interaction.followup.send(
            f"🔊 Joined **{vc.channel.name}**. Use `/voice say` or `/voice auto on`.",
            ephemeral=True,
        )

    @voice_group.command(name="leave", description="Leave voice and clear the speech queue")
    async def voice_leave(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Voice only works in servers.", ephemeral=True)
            return
        vc = interaction.guild.voice_client
        state = self._state(interaction.guild.id)
        # Drain queue
        while not state.queue.empty():
            try:
                state.queue.get_nowait()
            except Exception:
                break
        if state.player_task and not state.player_task.done():
            state.player_task.cancel()
            state.player_task = None
        # Forget last channel so auto-speak won't rejoin after an explicit leave.
        self._last_channel.pop(interaction.guild.id, None)
        if vc is not None:
            await vc.disconnect(force=True)
            await interaction.response.send_message("👋 Left voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ I'm not in a voice channel.", ephemeral=True)

    @voice_group.command(name="say", description="Speak text aloud in your voice channel")
    @app_commands.describe(text="Text to speak (markdown is simplified automatically)")
    async def voice_say(self, interaction: discord.Interaction, text: str) -> None:
        # Defer before any connect attempt for the same 3s-window reason as /voice join.
        await interaction.response.defer(ephemeral=True)
        vc: Optional[discord.VoiceClient] = None
        if interaction.guild and interaction.guild.voice_client is not None:
            vc = interaction.guild.voice_client
        else:
            vc = await self._connect_to_author(interaction)
            if vc is None:
                return

        try:
            count = await self._enqueue_text(interaction.guild, text)
        except ValueError:
            await interaction.followup.send("ℹ️ Nothing speakable after cleaning that text.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ TTS failed: `{type(e).__name__}: {e}`", ephemeral=True)
            return
        await interaction.followup.send(
            f"🔊 Queued {count} utterance(s) in **{vc.channel.name}**.", ephemeral=True
        )

    @voice_group.command(name="stop", description="Stop current speech and clear the queue")
    async def voice_stop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or interaction.guild.voice_client is None:
            await interaction.response.send_message("ℹ️ I'm not in a voice channel.", ephemeral=True)
            return
        vc = interaction.guild.voice_client
        state = self._state(interaction.guild.id)
        while not state.queue.empty():
            try:
                state.queue.get_nowait()
            except Exception:
                break
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await interaction.response.send_message("⏹️ Stopped speech and cleared the queue.", ephemeral=True)

    @voice_group.command(name="auto", description="Auto-speak LLM replies in this channel when in VC")
    @app_commands.describe(mode="Turn auto-speak on or off for this text channel")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def voice_auto(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Voice only works in servers.", ephemeral=True)
            return
        state = self._state(interaction.guild.id)
        if mode.value == "on":
            state.auto_channels.add(interaction.channel_id)
            await interaction.response.send_message(
                "🔊 **Auto-speak ON** for this channel. Join VC with `/voice join` and my replies will be read aloud.",
                ephemeral=True,
            )
        else:
            state.auto_channels.discard(interaction.channel_id)
            await interaction.response.send_message("🔇 **Auto-speak OFF** for this channel.", ephemeral=True)

    @voice_group.command(name="voice", description="View or change the TTS voice for this server")
    @app_commands.describe(name="Voice name, e.g. en-US-AriaNeural (empty to view current)")
    async def voice_voice(self, interaction: discord.Interaction, name: Optional[str] = None) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ Voice only works in servers.", ephemeral=True)
            return
        state = self._state(interaction.guild.id)
        if not name:
            current = state.voice or self.tts.default_voice
            await interaction.response.send_message(
                f"🎙️ Current voice: `{current}`\nTry: {', '.join(f'`{v}`' for v in CURATED_VOICES[:4])}",
                ephemeral=True,
            )
            return
        state.voice = name.strip()
        await interaction.response.send_message(
            f"🎙️ Voice set to `{state.voice}` for this server.", ephemeral=True
        )

    @voice_voice.autocomplete("name")
    async def voice_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        clean = current.strip().lower()
        matches = [v for v in CURATED_VOICES if not clean or clean in v.lower()]
        return [app_commands.Choice(name=v, value=v) for v in matches[:25]]


async def setup_voice(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCog(bot))
