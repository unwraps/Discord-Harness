"""Tests for VoiceCog auto-speak gating (no Discord connection needed)."""

from cogs.voice import VoiceCog


def _cog() -> VoiceCog:
    return VoiceCog(bot=None)  # type: ignore[arg-type]

def test_is_auto_direct_channel():
    cog = _cog()
    assert cog.is_auto(1, 100) is True
    cog._state(1).auto_disabled_channels.add(100)
    assert cog.is_auto(1, 100) is False
    assert cog.is_auto(1, 999) is True


def test_is_auto_covers_threads_via_parent():
    cog = _cog()
    assert cog.is_auto(1, 555, parent_id=100) is True
    cog._state(1).auto_disabled_channels.add(100)
    # Reply lands in thread 555 whose parent is channel 100 -> covered
    assert cog.is_auto(1, 555, parent_id=100) is False
    # Unrelated parent -> not covered
    assert cog.is_auto(1, 555, parent_id=777) is True


def test_is_auto_isolated_per_guild():
    cog = _cog()
    cog._state(1).auto_disabled_channels.add(100)
    assert cog.is_auto(1, 100) is False
    assert cog.is_auto(2, 100) is True


def test_ensure_opus_loads_encoder():
    from discord import opus

    from main import ensure_opus

    ensure_opus()
    assert opus.is_loaded() is True
    enc = opus.Encoder()  # raises OpusNotLoaded if the codec is missing
    assert enc is not None
