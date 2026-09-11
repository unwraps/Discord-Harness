"""
Base Skill definitions and decorator for modular tool calling.
Automatically generates OpenAI-compatible tool/function schemas from Python functions.
"""

from __future__ import annotations
import inspect
import typing
from typing import Any, Callable, Dict, List, Optional, get_type_hints
from dataclasses import dataclass, field


def python_type_to_json_type(py_type: Any) -> str:
    """Map python types to JSON Schema types."""
    if py_type in (int,):
        return "integer"
    elif py_type in (float,):
        return "number"
    elif py_type in (bool,):
        return "boolean"
    elif py_type in (str,):
        return "string"
    elif py_type in (list, List) or getattr(py_type, "__origin__", None) in (list, List):
        return "array"
    elif py_type in (dict, Dict) or getattr(py_type, "__origin__", None) in (dict, Dict):
        return "object"
    # Optional[T] or Union[T, None]
    origin = getattr(py_type, "__origin__", None)
    if origin is typing.Union:
        args = [a for a in py_type.__args__ if a is not type(None)]
        if len(args) == 1:
            return python_type_to_json_type(args[0])
    return "string"


@dataclass
class Skill:
    name: str
    description: str
    func: Callable[..., Any]
    is_async: bool = False
    enabled_by_default: bool = True
    parameters_schema: Dict[str, Any] = field(default_factory=dict)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Allow calling the skill directly like a function."""
        return self.func(*args, **kwargs)

    async def execute(self, **kwargs: Any) -> str:
        """Execute the skill function, handling sync or async transparently."""
        try:
            if self.is_async:
                result = await self.func(**kwargs)
            else:
                result = self.func(**kwargs)
            return str(result)
        except Exception as e:
            return f"Error executing {self.name}: {type(e).__name__}: {str(e)}"

    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert the skill to an OpenAI/LiteLLM tool definition dictionary."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


def extract_parameter_schema(func: Callable[..., Any]) -> Dict[str, Any]:
    """Extract a JSON schema object for function parameters from type hints and docstring."""
    sig = inspect.signature(func)
    try:
        type_hints = get_type_hints(func)
    except Exception:
        type_hints = {}

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for param_name, param in sig.parameters.items():
        # Ignore self, cls, context parameters if any
        if param_name in ("self", "cls", "ctx", "context"):
            continue

        param_type = type_hints.get(param_name, str)
        json_type = python_type_to_json_type(param_type)

        param_info: Dict[str, Any] = {
            "type": json_type,
            "description": f"The {param_name} parameter",
        }

        # Check for array inner items
        if json_type == "array":
            args = getattr(param_type, "__args__", None)
            if args:
                param_info["items"] = {"type": python_type_to_json_type(args[0])}
            else:
                param_info["items"] = {"type": "string"}

        properties[param_name] = param_info

        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            param_info["default"] = param.default

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def skill(
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled_by_default: bool = True,
) -> Callable[[Callable[..., Any]], Skill]:
    """
    Decorator to turn a function into a modular Skill tool.
    
    Usage:
        @skill(name="calculate", description="Safely calculate mathematical expressions")
        def calculate(expression: str) -> str:
            ...
    """
    def decorator(fn: Callable[..., Any]) -> Skill:
        skill_name = name or fn.__name__
        skill_desc = description or (fn.__doc__ or "").strip() or f"Execute {skill_name}"
        is_async = inspect.iscoroutinefunction(fn)
        schema = extract_parameter_schema(fn)

        return Skill(
            name=skill_name,
            description=skill_desc,
            func=fn,
            is_async=is_async,
            enabled_by_default=enabled_by_default,
            parameters_schema=schema,
        )

    return decorator
