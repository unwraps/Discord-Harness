import pytest
from unittest.mock import patch
from skills.modules.media_search import search_gif, search_image, _fetch_ddg_images


@pytest.mark.asyncio
async def test_search_gif_mock():
    mock_results = [
        {"title": "Cat Dancing 1", "image": "https://media.tenor.com/abc/cat1.gif", "url": "https://tenor.com/view/1"},
        {"title": "Cat Dancing 2", "image": "https://media.tenor.com/abc/cat2.gif", "url": "https://tenor.com/view/2"},
    ]
    with patch("skills.modules.media_search._fetch_ddg_images", return_value=mock_results):
        # Default index=1
        res1 = await search_gif("cat dancing")
        assert "ATTACH_MEDIA: https://media.tenor.com/abc/cat1.gif" in res1
        assert "Cat Dancing 1" in res1
        assert "Cat Dancing 2" in res1

        # Explicit index=2
        res2 = await search_gif("cat dancing", index=2)
        assert "ATTACH_MEDIA: https://media.tenor.com/abc/cat2.gif" in res2



@pytest.mark.asyncio
async def test_search_image_mock():
    mock_results = [
        {"title": "Red Panda", "image": "https://wallpapers.com/red-panda.jpg", "url": "https://wallpapers.com/123"}
    ]
    with patch("skills.modules.media_search._fetch_ddg_images", return_value=mock_results):
        res = await search_image("red panda")
        assert "https://wallpapers.com/red-panda.jpg" in res
        assert "Red Panda" in res
        assert "URL: https://wallpapers.com/red-panda.jpg" in res


@pytest.mark.asyncio
async def test_search_empty_results():
    with patch("skills.modules.media_search._fetch_ddg_images", return_value=[]):
        res_gif = await search_gif("nonexistentxyz123")
        assert "No GIFs found" in res_gif

        res_img = await search_image("nonexistentxyz123")
        assert "No images found" in res_img
