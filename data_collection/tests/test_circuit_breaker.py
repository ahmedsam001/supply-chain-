"""Unit tests for the Fail-Fast Circuit Breaker across BaseExtractor, Jumia, and 2B."""

from __future__ import annotations

import asyncio

import httpx

from extractors.base import _is_retryable_fetch_error
from extractors.source_2b.extractor import TwoBExtractor
from extractors.source_jumia.extractor import JumiaExtractor


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.com")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"HTTP {status}", request=req, response=resp)


def test_retryable_fetch_error_skips_403_and_404_but_retries_429_and_503() -> None:
    assert not _is_retryable_fetch_error(_http_status_error(403))
    assert not _is_retryable_fetch_error(_http_status_error(404))
    assert _is_retryable_fetch_error(_http_status_error(429))
    assert _is_retryable_fetch_error(_http_status_error(503))
    assert _is_retryable_fetch_error(httpx.ReadTimeout("timeout"))


def test_two_b_circuit_breaker_aborts_after_3_consecutive_failures(tmp_path) -> None:
    ext = TwoBExtractor(data_dir=str(tmp_path), max_products=100)
    calls = 0

    async def fake_fetch(url: str):
        nonlocal calls
        calls += 1
        raise _http_status_error(403)

    ext.fetch = fake_fetch  # type: ignore[method-assign]
    products = asyncio.run(ext.extract_products())

    assert products == []
    assert calls == 3
    assert ext._circuit_breaker_tripped is True
    assert any("Circuit breaker tripped" in e for e in ext._errors)


def test_jumia_circuit_breaker_aborts_after_3_consecutive_empty_or_failed_categories(tmp_path) -> None:
    ext = JumiaExtractor(data_dir=str(tmp_path), max_products=100)
    calls = 0

    async def fake_fetch_html(url: str) -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 403 Forbidden")

    ext._fetch_html = fake_fetch_html  # type: ignore[method-assign]
    products = asyncio.run(ext.extract_products())

    assert products == []
    assert calls == 3
    assert ext._circuit_breaker_tripped is True
    assert any("Circuit breaker tripped" in e for e in ext._errors)
