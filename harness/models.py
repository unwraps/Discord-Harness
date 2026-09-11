"""
Live Model Catalog & API Fetcher.
Dynamically queries model list endpoints from OpenRouter, DeepSeek, OpenAI, Ollama,
and registered custom providers, caching them in-memory for instant Discord autocomplete.
"""

from __future__ import annotations
import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Set
import httpx

from harness.config import ConfigManager

logger = logging.getLogger(__name__)

# Fallback models if APIs are temporarily unreachable or offline
FALLBACK_MODELS = [
    "deepseek/deepseek-chat",
    "deepseek/deepseek-reasoner",
    "openrouter/deepseek/deepseek-r1",
    "openrouter/deepseek/deepseek-chat",
    "openrouter/anthropic/claude-3.7-sonnet",
    "openrouter/anthropic/claude-3.5-sonnet",
    "openrouter/openai/gpt-4o",
    "openrouter/openai/gpt-4o-mini",
    "openrouter/openai/o3-mini",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
    "openrouter/qwen/qwq-32b",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "gpt-4o",
    "gpt-4o-mini",
    "o3-mini",
    "o1",
    "gemini/gemini-2.0-flash",
    "gemini/gemini-2.0-pro-exp-02-05",
    "ollama/deepseek-r1",
    "ollama/llama3.3",
    "ollama/qwen2.5",
]


class ModelCatalog:
    """Maintains an in-memory cache of live models fetched directly from provider APIs."""

    def __init__(self, config_manager: ConfigManager, cache_ttl_seconds: int = 3600):
        self.config_manager = config_manager
        self.cache_ttl = cache_ttl_seconds
        self._cached_models: List[str] = list(FALLBACK_MODELS)
        self._last_refresh: float = 0.0
        self._is_refreshing: bool = False

    @property
    def models(self) -> List[str]:
        return self._cached_models

    async def get_models(self, force_refresh: bool = False) -> List[str]:
        """Return cached models, triggering background refresh if stale."""
        now = time.monotonic()
        if force_refresh or (now - self._last_refresh > self.cache_ttl and not self._is_refreshing):
            asyncio.create_task(self.refresh_models())
        return self._cached_models

    async def refresh_models(self) -> int:
        """Query live provider APIs and update internal cache."""
        if self._is_refreshing:
            return len(self._cached_models)

        self._is_refreshing = True
        discovered: Set[str] = set()

        try:
            logger.info("Starting live model fetch from connected providers...")
            async with httpx.AsyncClient(timeout=6.0) as client:
                # 1. Fetch OpenRouter Models (Public or Auth)
                openrouter_models = await self._fetch_openrouter(client)
                discovered.update(openrouter_models)

                # 2. Fetch DeepSeek Models
                deepseek_models = await self._fetch_deepseek(client)
                discovered.update(deepseek_models)

                # 3. Fetch Local Ollama Models (if running)
                ollama_models = await self._fetch_ollama(client)
                discovered.update(ollama_models)

                # 4. Fetch Custom Registered Providers from SQLite
                custom_models = await self._fetch_custom_providers(client)
                discovered.update(custom_models)

                # 5. Fetch OpenAI Models (if key present)
                openai_models = await self._fetch_openai(client)
                discovered.update(openai_models)

            # If any models were discovered, merge with fallback
            if discovered:
                # Keep fallbacks at top if present, followed by newly discovered models sorted alphabetically
                combined: List[str] = []
                for m in FALLBACK_MODELS:
                    if m in discovered:
                        combined.append(m)
                for m in sorted(discovered):
                    if m not in combined:
                        combined.append(m)
                self._cached_models = combined
                self._last_refresh = time.monotonic()
                logger.info(f"Live model catalog updated: {len(self._cached_models)} models available.")
            else:
                logger.warning("No models discovered from APIs; retaining existing model cache.")

        except Exception as e:
            logger.error(f"Error during model refresh: {e}", exc_info=True)
        finally:
            self._is_refreshing = False

        return len(self._cached_models)

    async def _fetch_openrouter(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch all models currently available on OpenRouter."""
        models: List[str] = []
        api_key = os.getenv("OPENROUTER_API_KEY")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    model_id = item.get("id")
                    if model_id:
                        models.append(f"openrouter/{model_id}")
        except Exception as e:
            logger.debug(f"OpenRouter model fetch skipped or failed: {e}")
        return models

    async def _fetch_deepseek(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch models from DeepSeek official API if key configured."""
        models: List[str] = []
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return models

        try:
            resp = await client.get(
                "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    model_id = item.get("id")
                    if model_id:
                        models.append(f"deepseek/{model_id}")
        except Exception as e:
            logger.debug(f"DeepSeek model fetch skipped or failed: {e}")
        return models

    async def _fetch_ollama(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch models from local Ollama instance if active."""
        models: List[str] = []
        base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")
        try:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("models", []):
                    name = item.get("name")
                    if name:
                        # Clean :latest suffix if desired, or keep as is
                        models.append(f"ollama/{name}")
        except Exception:
            # Expected if local ollama is not running
            pass
        return models

    async def _fetch_openai(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch models from OpenAI if key configured."""
        models: List[str] = []
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return models

        try:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    mid = item.get("id", "")
                    if any(mid.startswith(p) for p in ("gpt-", "o1", "o3", "chatgpt-")):
                        models.append(mid)
        except Exception as e:
            logger.debug(f"OpenAI model fetch skipped: {e}")
        return models

    async def _fetch_custom_providers(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch models from custom OpenAI-compatible endpoints registered in SQLite."""
        models: List[str] = []
        try:
            import aiosqlite
            async with aiosqlite.connect(self.config_manager.db_path) as db:
                async with db.execute("SELECT name, base_url, api_key FROM custom_providers") as cursor:
                    rows = await cursor.fetchall()
                    for name, base_url, api_key in rows:
                        headers = {}
                        if api_key:
                            headers["Authorization"] = f"Bearer {api_key}"
                        clean_base = base_url.rstrip("/")
                        url = f"{clean_base}/models" if not clean_base.endswith("/v1") else f"{clean_base}/models"
                        try:
                            resp = await client.get(url, headers=headers)
                            if resp.status_code == 200:
                                data = resp.json()
                                for item in data.get("data", []):
                                    mid = item.get("id")
                                    if mid:
                                        models.append(f"{name}/{mid}")
                        except Exception as ce:
                            logger.debug(f"Could not fetch models for custom provider {name}: {ce}")
                            # At minimum offer provider default
                            models.append(f"{name}/default")
        except Exception as e:
            logger.debug(f"Custom providers fetch error: {e}")
        return models

    def search(self, query: str, limit: int = 25) -> List[str]:
        """Instant in-memory substring search across all cached live models."""
        clean_q = query.strip().lower()
        if not clean_q:
            return self._cached_models[:limit]

        # 1. Exact prefix matches first
        prefix_matches = [m for m in self._cached_models if m.lower().startswith(clean_q)]
        # 2. Substring matches
        other_matches = [
            m for m in self._cached_models
            if clean_q in m.lower() and not m.lower().startswith(clean_q)
        ]

        results = prefix_matches + other_matches
        return results[:limit]
