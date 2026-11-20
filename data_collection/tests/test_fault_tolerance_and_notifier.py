"""Unit tests for Partial-Success incremental save, error accumulation, and email alerts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb

from dwh import run_pipeline
from notifier import send_failure_alert


def test_send_failure_alert_noop_on_empty_list(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_EMAIL_SENDER", "sender@example.com")
    monkeypatch.setenv("ALERT_EMAIL_PASSWORD", "app-pass")
    monkeypatch.setenv("ALERT_EMAIL_RECIPIENT", "ops@example.com")
    assert send_failure_alert([]) is False


def test_send_failure_alert_skips_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("ALERT_EMAIL_SENDER", raising=False)
    monkeypatch.delenv("ALERT_EMAIL_PASSWORD", raising=False)
    monkeypatch.delenv("ALERT_EMAIL_RECIPIENT", raising=False)
    assert send_failure_alert([{"store": "jumia", "reason": "HTTP 403"}]) is False


def test_send_failure_alert_sends_email_with_store_details(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_EMAIL_SENDER", "bot@example.com")
    monkeypatch.setenv("ALERT_EMAIL_PASSWORD", "secret-app-pw")
    monkeypatch.setenv("ALERT_EMAIL_RECIPIENT", "ops@example.com, lead@example.com")
    monkeypatch.setenv("ALERT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ALERT_SMTP_PORT", "465")

    mock_smtp = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_smtp

    with patch("notifier.smtplib.SMTP_SSL", return_value=mock_cm) as smtp_cls:
        ok = send_failure_alert(
            [
                {"store": "jumia", "reason": "Circuit breaker tripped (HTTP 403)"},
                {"store": "two_b", "reason": "ReadTimeout"},
            ],
            run_id="hourly_20261120T081700Z",
            mode="hourly",
        )

    assert ok is True
    smtp_cls.assert_called_once_with("smtp.example.com", 465, timeout=20)
    mock_smtp.login.assert_called_once_with("bot@example.com", "secret-app-pw")
    assert mock_smtp.send_message.call_count == 1
    sent_msg = mock_smtp.send_message.call_args[0][0]
    body = sent_msg.get_content()
    assert "jumia" in sent_msg["Subject"]
    assert "two_b" in sent_msg["Subject"]
    assert "Circuit breaker tripped (HTTP 403)" in body
    assert "ReadTimeout" in body
    assert "secret-app-pw" not in body


def test_send_failure_alert_handles_smtp_error_gracefully(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_EMAIL_SENDER", "bot@example.com")
    monkeypatch.setenv("ALERT_EMAIL_PASSWORD", "secret-app-pw")
    monkeypatch.setenv("ALERT_EMAIL_RECIPIENT", "ops@example.com")
    monkeypatch.setenv("ALERT_SMTP_PORT", "465")

    with patch("notifier.smtplib.SMTP_SSL", side_effect=OSError("SMTP unreachable")):
        assert send_failure_alert([{"store": "jumia", "reason": "0 products"}]) is False


def test_run_once_incremental_save_partial_success_and_alert(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "partial.duckdb"
    bronze_root = tmp_path / "bronze"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async def fake_scrape_one(source_id, offline, limit, with_locations, run_id, run_date):
        if source_id == "tradeline":
            return {
                "source": "tradeline",
                "run_id": run_id,
                "started_at": now,
                "products": [
                    {
                        "source_product_id": "TL-100",
                        "product_id": "tradeline:TL-100",
                        "product_name": "Apple AirPods Pro 2",
                        "brand": "Apple",
                        "category": "Audio",
                        "product_url": "https://tradeline-stores.com/p/tl-100",
                        "image_url": "https://tradeline-stores.com/img/tl-100.jpg",
                    }
                ],
                "observations": [
                    {
                        "source_product_id": "TL-100",
                        "product_id": "tradeline:TL-100",
                        "price": 12500.0,
                        "old_price": 13500.0,
                        "discount": 7.4,
                        "stock_status": "IN_STOCK",
                    }
                ],
                "locations": [],
                "error": None,
                "scrape_seconds": 1.2,
            }
        if source_id == "jumia":
            await asyncio.sleep(0.05)
            raise RuntimeError("Simulated crash on jumia")
        # two_b: circuit breaker / 0 products
        await asyncio.sleep(0.02)
        return {
            "source": "two_b",
            "run_id": run_id,
            "started_at": now,
            "products": [],
            "observations": [],
            "locations": [],
            "error": None,
            "circuit_breaker": True,
            "scrape_seconds": 2.1,
        }

    alert_mock = MagicMock(return_value=True)
    monkeypatch.setattr(run_pipeline, "_scrape_one", fake_scrape_one)
    monkeypatch.setattr(run_pipeline, "send_failure_alert", alert_mock)

    summary = run_pipeline.run_once(
        mode="hourly",
        sources=["tradeline", "jumia", "two_b"],
        limit=10,
        offline=False,
        db_path=db_path,
        bronze_root=bronze_root,
        skip_erp=True,
        concurrency=3,
    )

    # Healthy store was saved to DuckDB & Bronze Parquet
    assert summary["stores"]["tradeline"]["scraped"] == 1
    assert summary["stores"]["tradeline"]["inserted"] == 1

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        prod_count = conn.execute(
            "SELECT COUNT(*) FROM live_market.PRODUCTS WHERE STORE = 'tradeline'"
        ).fetchone()[0]
        run_log_count = conn.execute("SELECT COUNT(*) FROM live_market.RUN_LOGS").fetchone()[0]
    finally:
        conn.close()

    assert prod_count == 1
    assert run_log_count == 3

    bronze_files = list((bronze_root / "market_changes").rglob("*.parquet"))
    assert len(bronze_files) == 1

    # Both failing stores accumulated & emailed
    failed_names = {f["store"] for f in summary["failed_stores"]}
    assert failed_names == {"jumia", "two_b"}
    assert alert_mock.call_count == 1
    sent_failures = alert_mock.call_args[0][0]
    assert {f["store"] for f in sent_failures} == {"jumia", "two_b"}
