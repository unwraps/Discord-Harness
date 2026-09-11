"""
Time and Scratchpad Notes Skill.
Allows checking current time and saving/retrieving persistent scratchpad notes.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, List
from skills.base import skill

# In-memory notes scratchpad (can be enhanced to persistent storage)
_SCRATCHPAD: Dict[str, str] = {}


@skill(
    name="get_current_time",
    description="Get the current UTC time and date, helpful for time-sensitive questions.",
)
def get_current_time() -> str:
    """Get the current UTC timestamp and formatted date."""
    now = datetime.now(timezone.utc)
    return f"Current UTC Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')} (ISO: {now.isoformat()})"


@skill(
    name="save_scratchpad_note",
    description="Save a key-value note or reminder into the channel scratchpad.",
)
def save_scratchpad_note(key: str, content: str) -> str:
    """Save a note to the scratchpad."""
    _SCRATCHPAD[key.strip().lower()] = content.strip()
    return f"Successfully saved note with key: '{key}'"


@skill(
    name="get_scratchpad_note",
    description="Retrieve a previously saved note or list all saved notes in the scratchpad.",
)
def get_scratchpad_note(key: str = "") -> str:
    """Retrieve note(s) from the scratchpad."""
    k = key.strip().lower()
    if not k:
        if not _SCRATCHPAD:
            return "Scratchpad is currently empty."
        items = [f"- **{name}**: {val}" for name, val in _SCRATCHPAD.items()]
        return "All Saved Scratchpad Notes:\n" + "\n".join(items)

    if k in _SCRATCHPAD:
        return f"Note '{k}': {_SCRATCHPAD[k]}"
    return f"No note found with key: '{key}'"
