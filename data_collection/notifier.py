#!/usr/bin/env python3
"""
Email notification helper for partial-success / store-failure alerts.

Uses Python's built-in `smtplib` and `email.message.EmailMessage`.
Configured via environment variables (or `.env`):
  - ALERT_EMAIL_SENDER
  - ALERT_EMAIL_PASSWORD
  - ALERT_EMAIL_RECIPIENT   (comma-separated for multiple recipients)
  - ALERT_SMTP_HOST         (optional, default: smtp.gmail.com)
  - ALERT_SMTP_PORT         (optional, default: 465)
"""

from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv

    load_dotenv(_THIS_DIR / ".env")
    load_dotenv(_THIS_DIR.parent / ".env")
except Exception:  # pragma: no cover
    pass


def _format_failed_store(entry: Any) -> tuple[str, str]:
    if isinstance(entry, dict):
        store = str(entry.get("store") or entry.get("name") or "unknown")
        reason = str(entry.get("reason") or entry.get("error") or "0 products returned")
        return store, reason
    if isinstance(entry, (tuple, list)) and len(entry) >= 2:
        return str(entry[0]), str(entry[1])
    return str(entry), "failed"


def send_failure_alert(
    failed_stores: list[Any],
    *,
    run_id: str = "",
    mode: str = "",
) -> bool:
    """Send an email alert listing all failed/skipped stores and their reasons.

    Returns True if the email was sent, False if skipped (empty list or missing
    SMTP credentials) or if delivery failed. Never raises to avoid breaking the
    pipeline after valid data has been persisted.
    """
    if not failed_stores:
        return False

    sender = os.environ.get("ALERT_EMAIL_SENDER", "").strip()
    password = os.environ.get("ALERT_EMAIL_PASSWORD", "").strip()
    recipient_raw = os.environ.get("ALERT_EMAIL_RECIPIENT", "").strip()
    smtp_host = os.environ.get("ALERT_SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    smtp_port = int(os.environ.get("ALERT_SMTP_PORT", "465").strip() or "465")

    if not (sender and password and recipient_raw):
        print(
            "  ⚠️  Email alert skipped: ALERT_EMAIL_SENDER, ALERT_EMAIL_PASSWORD, "
            "or ALERT_EMAIL_RECIPIENT not configured."
        )
        return False

    recipients = [r.strip() for r in recipient_raw.split(",") if r.strip()]
    if not recipients:
        return False

    formatted = [_format_failed_store(item) for item in failed_stores]
    store_names = ", ".join(s for s, _ in formatted)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    mode_tag = f" [{mode.upper()}]" if mode else ""
    subject = f"[Retail Lakehouse Alert]{mode_tag} {len(formatted)} store(s) failed: {store_names}"

    lines = [
        "Retail Lakehouse Pipeline — Partial Success / Store Failure Alert",
        "=" * 64,
        f"Timestamp : {now_utc}",
    ]
    if run_id:
        lines.append(f"Run ID    : {run_id}")
    if mode:
        lines.append(f"Mode      : {mode}")
    lines.extend(["", "Failed / Skipped Stores:", "-" * 64])
    for store, reason in formatted:
        lines.append(f"• {store}: {reason}")
    lines.extend([
        "",
        "Note: Data from all healthy stores was saved incrementally to DuckDB and Bronze Parquet.",
    ])

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content("\n".join(lines) + "\n")

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
                server.login(sender, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender, password)
                server.send_message(msg)
        print(f"  📧 Failure alert email sent to {len(recipients)} recipient(s) for: {store_names}")
        return True
    except Exception as exc:
        print(f"  ⚠️  Failed to send alert email ({type(exc).__name__}): {exc}")
        return False
