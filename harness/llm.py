"""
LLM Execution Engine with Multi-Model Routing, Dynamic Tools, and Streaming.
Integrates with LiteLLM to support OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter,
and arbitrary OpenAI-compatible custom endpoints.
"""

from __future__ import annotations
import json
import logging
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

import litellm
from litellm import acompletion

from harness.config import ConfigManager
from harness.formatter import format_with_thinking
from harness.memory import ConversationSession
from skills.manager import SkillManager

logger = logging.getLogger(__name__)

# Suppress overly verbose litellm logs
litellm.suppress_debug_info = True


class LLMEngine:
    def __init__(self, config_manager: ConfigManager, skill_manager: SkillManager):
        self.config_manager = config_manager
        self.skill_manager = skill_manager

    @staticmethod
    def _usage_numbers(usage: Any) -> tuple[int, int]:
        """Extract (prompt_tokens, completion_tokens) from LiteLLM usage (object or dict)."""
        if usage is None:
            return (0, 0)
        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens", 0) or 0
            completion = usage.get("completion_tokens", 0) or 0
        else:
            prompt = getattr(usage, "prompt_tokens", 0) or 0
            completion = getattr(usage, "completion_tokens", 0) or 0
        try:
            return (max(0, int(prompt)), max(0, int(completion)))
        except (TypeError, ValueError):
            return (0, 0)

    async def _record_usage(self, user_id: Optional[int], response: Any) -> None:
        """Persist token usage from a LiteLLM response (best-effort, never raises)."""
        if user_id is None:
            return
        try:
            prompt, completion = self._usage_numbers(getattr(response, "usage", None))
            await self.config_manager.add_token_usage(user_id, prompt, completion)
        except Exception as e:
            logger.debug(f"Could not record token usage: {e}")

    async def generate_response(
        self,
        session: ConversationSession,
        user_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        max_tool_iterations: int = 5,
        on_status: Optional[Callable[[str], Any]] = None,
    ) -> str:
        """
        Run complete conversational inference, executing tool calls in a loop until
        the model generates a final response.
        """
        # Fetch channel settings
        target_id = channel_id or session.channel_id
        config = await self.config_manager.get_channel_config(target_id)
        model = config.model
        # Auto-normalize bare deepseek models so LiteLLM doesn't fail with BadRequestError
        if model.lower().startswith("deepseek-") and not (
            model.lower().startswith("deepseek/") or model.lower().startswith("openrouter/")
        ):
            model = f"deepseek/{model}"
        temperature = config.temperature
        thinking_mode = config.thinking_mode

        # Ensure system prompt is synced
        session.set_system_prompt(config.system_prompt)

        # Resolve credentials (keys / base_url)
        credentials = await self.config_manager.resolve_credentials(
            model=model,
            user_id=user_id,
            channel_id=target_id,
        )
        api_key = credentials.get("api_key")
        api_base = credentials.get("api_base")

        # Tools available for this channel
        tools = self.skill_manager.get_openai_tools(channel_id=target_id)
        tools_param = tools if tools else None

        # Per-user daily token budget: refuse up front if already exhausted.
        if user_id is not None:
            refusal = await self.config_manager.check_daily_limit(user_id)
            if refusal:
                return refusal

        iteration = 0
        while iteration < max_tool_iterations:
            iteration += 1
            messages = session.get_messages()

            # Stop mid-turn if the budget ran out during tool iterations.
            if user_id is not None and iteration > 1:
                mid_refusal = await self.config_manager.check_daily_limit(user_id)
                if mid_refusal:
                    return mid_refusal + "\n\n_(Stopped mid-response: budget exhausted during tool use.)_"

            completion_kwargs: Dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            # Reasoning models (e.g. o1, o3, deepseek-reasoner) often reject temperature
            is_strict_reasoning = any(k in model.lower() for k in ("reasoner", "o1-", "/o1", "o3-", "/o3"))
            if not is_strict_reasoning:
                completion_kwargs["temperature"] = temperature

            if api_key:
                completion_kwargs["api_key"] = api_key
            if api_base:
                completion_kwargs["api_base"] = api_base
            if tools_param:
                completion_kwargs["tools"] = tools_param
                completion_kwargs["tool_choice"] = "auto"

            try:
                response = await acompletion(**completion_kwargs)
                await self._record_usage(user_id, response)
            except Exception as e:
                logger.error(f"LiteLLM completion error for model {model}: {e}", exc_info=True)
                err_str = str(e)
                tip = "*(Tip: Verify your API key or model identifier with `/config` or `/key set`)*"
                if any(k in err_str.lower() for k in ("image", "vision", "multimodal", "unsupported content")):
                    tip = f"*(Tip: The model `{model}` may not support vision/image input. Try switching to a vision model like `openrouter/deepseek/deepseek-vl2`, `openrouter/deepseek/janus-pro-7b`, `gpt-4o`, or `gemini/gemini-2.0-flash` with `/model`)*"
                return f"**LLM Error**: `{type(e).__name__}`: {err_str}\n\n{tip}"

            choice = response.choices[0]
            message = choice.message
            tool_calls = getattr(message, "tool_calls", None)

            # If no tool calls requested, we got our final answer
            if not tool_calls:
                content = message.content or ""
                # Extract reasoning tokens (DeepSeek R1, Claude 3.7 Thinking, OpenRouter reasoning)
                reasoning = getattr(message, "reasoning_content", None) or getattr(message, "thinking", None)
                session.add_assistant_message(content=content)
                return format_with_thinking(content, reasoning=reasoning, mode=thinking_mode)

            # Model requested tool/skill executions
            # 1. Add assistant message with tool calls into history
            raw_tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
            session.add_assistant_message(content=message.content, tool_calls=raw_tool_calls)

            # 2. Execute each requested skill
            for tc in tool_calls:
                fn_name = tc.function.name
                call_id = tc.id
                raw_args = tc.function.arguments or "{}"

                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                if on_status:
                    try:
                        await on_status(f"⚡ Running skill: `{fn_name}`...")
                    except Exception:
                        pass

                logger.info(f"Executing skill '{fn_name}' with args {args}")
                tool_output = await self.skill_manager.execute(fn_name, args)

                # Record tool result in session
                session.add_tool_result(tool_call_id=call_id, name=fn_name, result=tool_output)

        return "Maximum skill execution iterations reached. Please try refining your query."
