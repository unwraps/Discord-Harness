"""
Skill Manager: dynamic discovery, registration, hot-reloading, and execution of modular skills.
"""

from __future__ import annotations
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from skills.base import Skill

logger = logging.getLogger(__name__)


class SkillManager:
    def __init__(self, modules_dir: Optional[Path] = None):
        if modules_dir is None:
            modules_dir = Path(__file__).parent / "modules"
        self.modules_dir = modules_dir
        self.skills: Dict[str, Skill] = {}
        # Channel-specific overrides: channel_id -> set of disabled skill names
        self._disabled_by_channel: Dict[int, Set[str]] = {}

    def register(self, skill_item: Skill) -> None:
        """Register a Skill instance."""
        self.skills[skill_item.name] = skill_item
        logger.info(f"Registered skill: '{skill_item.name}'")

    def unregister(self, name: str) -> None:
        """Unregister a skill by name."""
        if name in self.skills:
            del self.skills[name]
            logger.info(f"Unregistered skill: '{name}'")

    def get_skill(self, name: str) -> Optional[Skill]:
        """Retrieve a registered skill by name."""
        return self.skills.get(name)

    def load_modules(self) -> int:
        """
        Dynamically discover and load all python modules inside self.modules_dir.
        Returns the count of newly registered skills.
        """
        if not self.modules_dir.exists():
            self.modules_dir.mkdir(parents=True, exist_ok=True)
            return 0

        # Ensure directory is in sys.path
        modules_path_str = str(self.modules_dir.parent.parent.resolve())
        if modules_path_str not in sys.path:
            sys.path.insert(0, modules_path_str)

        initial_count = len(self.skills)

        for py_file in self.modules_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue

            module_name = f"skills.modules.{py_file.stem}"
            try:
                if module_name in sys.modules:
                    mod = importlib.reload(sys.modules[module_name])
                else:
                    mod = importlib.import_module(module_name)

                # Find any Skill objects defined or exported in the module
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, Skill):
                        self.register(attr)
                    elif isinstance(attr, list):
                        for item in attr:
                            if isinstance(item, Skill):
                                self.register(item)

            except Exception as e:
                logger.error(f"Failed to load skill module '{py_file.name}': {e}", exc_info=True)

        loaded = len(self.skills) - initial_count
        logger.info(f"Loaded {len(self.skills)} total skills from {self.modules_dir}")
        return loaded

    def reload_all(self) -> int:
        """Clear and reload all skills."""
        self.skills.clear()
        return self.load_modules()

    def is_skill_enabled(self, skill_name: str, channel_id: Optional[int] = None) -> bool:
        """Check if a skill is enabled globally or for a specific channel."""
        skill_obj = self.skills.get(skill_name)
        if not skill_obj:
            return False
        if not skill_obj.enabled_by_default:
            return False
        if channel_id and channel_id in self._disabled_by_channel:
            if skill_name in self._disabled_by_channel[channel_id]:
                return False
        return True

    def toggle_skill_for_channel(self, channel_id: int, skill_name: str) -> bool:
        """
        Toggle skill on/off for a specific channel.
        Returns True if enabled, False if disabled.
        """
        if channel_id not in self._disabled_by_channel:
            self._disabled_by_channel[channel_id] = set()

        disabled_set = self._disabled_by_channel[channel_id]
        if skill_name in disabled_set:
            disabled_set.remove(skill_name)
            return True
        else:
            disabled_set.add(skill_name)
            return False

    def get_openai_tools(self, channel_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get the list of OpenAI/LiteLLM tool definitions for enabled skills.
        """
        tools = []
        for name, skill_obj in self.skills.items():
            if self.is_skill_enabled(name, channel_id):
                tools.append(skill_obj.to_openai_tool())
        return tools

    async def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute a skill by name with supplied arguments."""
        skill_obj = self.skills.get(name)
        if not skill_obj:
            return f"Error: Skill '{name}' not found."
        return await skill_obj.execute(**arguments)
