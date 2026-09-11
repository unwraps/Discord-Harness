"""
Conversation Memory & Context Management.
Maintains rolling window of messages per Discord channel or thread.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from collections import defaultdict


class ConversationSession:
    """Session history for a single channel or thread."""

    def __init__(self, channel_id: int, max_turns: int = 20):
        self.channel_id = channel_id
        self.max_turns = max_turns
        self.messages: List[Dict[str, Any]] = []

    def set_system_prompt(self, system_prompt: str) -> None:
        """Ensure system prompt is first message."""
        if not system_prompt:
            return
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = system_prompt
        else:
            self.messages.insert(0, {"role": "system", "content": system_prompt})

    def add_user_message(
        self,
        content: str,
        author_name: Optional[str] = None,
        user_info: Optional[Dict[str, Any]] = None,
        images: Optional[List[str]] = None,
    ) -> None:
        """Append user message with rich identity context and optional visual images."""
        if user_info:
            header_parts = []
            username = user_info.get("username")
            display_name = user_info.get("display_name")
            if username and display_name and username != display_name:
                header_parts.append(f"User: {display_name} (@{username})")
            elif display_name or username:
                header_parts.append(f"User: {display_name or username}")

            nick = user_info.get("nickname")
            if nick and nick != display_name:
                header_parts.append(f"Nickname: {nick}")
            if user_info.get("top_role"):
                header_parts.append(f"Top Role: {user_info['top_role']}")
            if user_info.get("bio"):
                header_parts.append(f"About User: {user_info['bio']}")
            if user_info.get("roles"):
                header_parts.append(f"Roles: {', '.join(user_info['roles'][:4])}")
            if user_info.get("server"):
                header_parts.append(f"Server: {user_info['server']}")
            if user_info.get("channel"):
                header_parts.append(f"Channel: #{user_info['channel']}")

            header = f"[{' | '.join(header_parts)}]\n" if header_parts else ""

            # Format any other users mentioned/tagged in the message
            mentioned = user_info.get("mentioned_users", [])
            for u in mentioned:
                m_parts = []
                u_name = u.get("display_name") or u.get("username")
                handle = u.get("username")
                m_nick = u.get("nickname")
                if m_nick and m_nick != u_name:
                    m_parts.append(f"Tagged User: {m_nick} (Display: {u_name}, @{handle})")
                elif handle and u_name != handle:
                    m_parts.append(f"Tagged User: {u_name} (@{handle})")
                else:
                    m_parts.append(f"Tagged User: {u_name}")

                if u.get("is_bot"):
                    m_parts.append("Is Bot: Yes")
                if u.get("top_role"):
                    m_parts.append(f"Top Role: {u['top_role']}")
                if u.get("roles"):
                    m_parts.append(f"Roles: {', '.join(u['roles'][:4])}")
                if u.get("joined_at"):
                    m_parts.append(f"Joined Server: {u['joined_at']}")
                if u.get("created_at"):
                    m_parts.append(f"Account Created: {u['created_at']}")
                if u.get("bio"):
                    m_parts.append(f"Bio/Info: {u['bio']}")

                header += f"[{' | '.join(m_parts)}]\n"

            text = f"{header}{content}"
        elif author_name:
            text = f"[{author_name}]: {content}"
        else:
            text = content

        if images:
            parts: List[Dict[str, Any]] = [{"type": "text", "text": text}]
            for img_url in images:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": img_url},
                })
            self.messages.append({"role": "user", "content": parts})
        else:
            self.messages.append({"role": "user", "content": text})

        self._trim()

    def add_assistant_message(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Append assistant response (can include text or tool calls)."""
        msg: Dict[str, Any] = {"role": "assistant"}
        if content:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        self._trim()

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        """Append the output of a skill tool call."""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result,
        })
        self._trim()

    def get_messages(self) -> List[Dict[str, Any]]:
        """Return full current conversation messages list."""
        return list(self.messages)

    def clear(self) -> None:
        """Clear conversation history, keeping only system prompt if present."""
        if self.messages and self.messages[0].get("role") == "system":
            self.messages = [self.messages[0]]
        else:
            self.messages = []

    def _trim(self) -> None:
        """Trim messages keeping system prompt and up to max_turns user/assistant pairs."""
        if len(self.messages) <= 1:
            return

        has_system = self.messages[0].get("role") == "system"
        start_idx = 1 if has_system else 0
        content_messages = self.messages[start_idx:]

        # Turn count is approximately number of non-tool messages // 2
        # To avoid unbounded growth, keep last (max_turns * 3) messages
        max_msgs = self.max_turns * 3
        if len(content_messages) > max_msgs:
            trimmed = content_messages[-max_msgs:]
            # Ensure we don't start with a 'tool' role message without its matching assistant tool_call
            while trimmed and trimmed[0].get("role") == "tool":
                trimmed.pop(0)
            if has_system:
                self.messages = [self.messages[0]] + trimmed
            else:
                self.messages = trimmed


class MemoryManager:
    """Central registry of conversation sessions across all Discord channels/threads."""

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.sessions: Dict[int, ConversationSession] = {}

    def get_session(self, channel_id: int) -> ConversationSession:
        """Get or create session for a channel/thread."""
        if channel_id not in self.sessions:
            self.sessions[channel_id] = ConversationSession(channel_id, max_turns=self.max_turns)
        return self.sessions[channel_id]

    def clear_session(self, channel_id: int) -> None:
        """Clear session memory for a channel/thread."""
        if channel_id in self.sessions:
            self.sessions[channel_id].clear()
