import pytest
from skills.modules.fetch_webpage import _is_safe_url, _clean_html, fetch_webpage


def test_is_safe_url_blocks_dangerous():
    # Loopback / local hosts
    assert not _is_safe_url("http://localhost/admin")[0]
    assert not _is_safe_url("http://127.0.0.1:8000/api")[0]
    assert not _is_safe_url("http://[::1]/")[0]
    assert not _is_safe_url("http://0.0.0.0/")[0]
    assert not _is_safe_url("http://169.254.169.254/latest/meta-data/")[0]

    # Private IP ranges
    assert not _is_safe_url("http://192.168.1.1/router")[0]
    assert not _is_safe_url("http://10.0.0.5/secrets")[0]
    assert not _is_safe_url("http://172.16.0.1/")[0]

    # Dangerous protocols
    assert not _is_safe_url("file:///etc/passwd")[0]
    assert not _is_safe_url("ftp://ftp.example.com")[0]
    assert not _is_safe_url("javascript:alert(1)")[0]


def test_is_safe_url_allows_public():
    assert _is_safe_url("https://example.com")[0]
    assert _is_safe_url("https://en.wikipedia.org/wiki/Python")[0]
    assert _is_safe_url("http://httpbin.org/get")[0]


def test_clean_html():
    raw = """
    <html>
      <head><title>Test Page</title><style>.bad { color: red; }</style></head>
      <body>
        <nav><a href="/">Home</a></nav>
        <h1>Article Heading</h1>
        <p>This is important content that the user wants to read.</p>
        <script>console.log("malicious code");</script>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    cleaned = _clean_html(raw)
    assert "Test Page" in cleaned
    assert "Article Heading" in cleaned
    assert "This is important content that the user wants to read." in cleaned
    assert "malicious code" not in cleaned
    assert ".bad {" not in cleaned


@pytest.mark.asyncio
async def test_fetch_webpage_blocks_ssrf():
    result = await fetch_webpage("http://127.0.0.1:5000/secret")
    assert "Security Error" in result
