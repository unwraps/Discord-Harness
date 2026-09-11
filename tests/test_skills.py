import pytest
from skills.base import skill, extract_parameter_schema, python_type_to_json_type
from skills.manager import SkillManager
from skills.modules.calculator import calculate
from skills.modules.time_notes import get_current_time, save_scratchpad_note, get_scratchpad_note


def test_python_type_to_json_type():
    assert python_type_to_json_type(int) == "integer"
    assert python_type_to_json_type(float) == "number"
    assert python_type_to_json_type(bool) == "boolean"
    assert python_type_to_json_type(str) == "string"


def test_schema_extraction():
    @skill(name="test_tool", description="A test tool")
    def sample_func(query: str, count: int = 5) -> str:
        """Sample docstring."""
        return f"{query}:{count}"

    schema = sample_func.parameters_schema
    assert schema["type"] == "object"
    assert "query" in schema["properties"]
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["count"]["type"] == "integer"
    assert schema["properties"]["count"]["default"] == 5
    assert "query" in schema["required"]
    assert "count" not in schema["required"]


@pytest.mark.asyncio
async def test_skill_execution():
    @skill(name="sync_add")
    def sync_add(a: int, b: int) -> int:
        return a + b

    @skill(name="async_multiply")
    async def async_multiply(a: int, b: int) -> int:
        return a * b

    res1 = await sync_add.execute(a=3, b=7)
    assert res1 == "10"

    res2 = await async_multiply.execute(a=4, b=5)
    assert res2 == "20"


def test_calculator_skill():
    assert calculate("2 + 2") == "4"
    assert calculate("10 * (5 - 3)") == "20"
    assert calculate("sqrt(144)") == "12.0"
    assert calculate("pow(2, 3)") == "8"
    assert "error" in calculate("__import__('os').system('dir')").lower()


def test_time_notes_skill():
    time_str = get_current_time()
    assert "UTC" in time_str

    save_res = save_scratchpad_note(key="project_goal", content="Build Discord LLM Harness")
    assert "Successfully saved" in save_res

    read_res = get_scratchpad_note(key="project_goal")
    assert "Build Discord LLM Harness" in read_res


def test_skill_manager_discovery_and_toggle():
    manager = SkillManager()
    count = manager.load_modules()
    assert count >= 3
    assert manager.get_skill("calculator") is not None
    assert manager.get_skill("get_current_time") is not None

    # Check toggle for channel
    channel_id = 12345
    assert manager.is_skill_enabled("calculator", channel_id) is True
    # Toggle off
    is_enabled = manager.toggle_skill_for_channel(channel_id, "calculator")
    assert is_enabled is False
    assert manager.is_skill_enabled("calculator", channel_id) is False

    # Toggle on
    is_enabled = manager.toggle_skill_for_channel(channel_id, "calculator")
    assert is_enabled is True
    assert manager.is_skill_enabled("calculator", channel_id) is True
