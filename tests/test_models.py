import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from harness.config import ConfigManager
from harness.models import ModelCatalog, FALLBACK_MODELS


def test_model_catalog_search():
    mgr = MagicMock(spec=ConfigManager)
    cat = ModelCatalog(config_manager=mgr)
    cat._cached_models = [
        "deepseek/deepseek-chat",
        "deepseek/deepseek-reasoner",
        "openrouter/deepseek/deepseek-r1",
        "openrouter/anthropic/claude-3.5-sonnet",
        "gpt-4o",
    ]

    # Search with prefix
    res_deep = cat.search("deepseek")
    assert len(res_deep) == 3
    assert res_deep[0].startswith("deepseek")

    # Search substring
    res_sonnet = cat.search("sonnet")
    assert len(res_sonnet) == 1
    assert "claude-3.5-sonnet" in res_sonnet[0]

    # Empty query returns top models
    res_all = cat.search("")
    assert len(res_all) == 5


@pytest.mark.asyncio
async def test_model_catalog_fetch_mock(tmp_path):
    mgr = ConfigManager(db_path=tmp_path / "test_cat.db")
    await mgr.init_db()
    cat = ModelCatalog(config_manager=mgr)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "meta-llama/llama-3.3-70b-instruct"},
            {"id": "qwen/qwq-32b"},
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        count = await cat.refresh_models()

        assert count > 0
        search_res = cat.search("qwq")
        assert any("qwq-32b" in m for m in search_res)
