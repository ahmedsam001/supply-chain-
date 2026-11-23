#!/usr/bin/env python3
"""
Azure Lakehouse Compute Runner (designed for Azure Container Apps Jobs)
=======================================================================
Decoupled from GitHub Actions scraping. Runs on a schedule (hourly or daily):
  1. Pulls latest DuckDB state from Azure ADLS Gen2 (`state/` container)
  2. Executes dbt transformations + data quality tests:
       - hourly: refreshes live market Silver & Gold models + 126 tests (< 15s)
       - daily:  full dbt seed + dbt run (33 models) + dbt test (364 tests)
  3. Exports & uploads Silver (14 tables) and Gold (19 tables) Parquet to
     Azure ADLS Gen2 (`silver/` and `gold/` containers).
  4. On ANY failure (pull, dbt run, dbt test, or upload), fails closed (no corrupt
     Parquet uploaded) AND sends an immediate Gmail alert with the failed step
     and trailing error logs.

Usage:
    python lakehouse/run_lakehouse.py --mode daily
    python lakehouse/run_lakehouse.py --mode hourly
    python lakehouse/run_lakehouse.py --mode daily --local   # local test, no Azure I/O
"""

from __future__ import annotations

import argparse
import os
import shutil
import smtplib
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
TRANS_DIR = REPO_ROOT / "transformations"
AZURE_SYNC = REPO_ROOT / "data_collection" / "azure_sync.py"
DEFAULT_ALERT_RECIPIENT = "ahmedssami001@gmail.com"

HOURLY_MODELS = [
    "dim_date",
    "slv_stores",
    "dim_store",
    "slv_products",
    "slv_price_history",
    "slv_market_snapshots",
    "slv_run_logs",
    "dim_product",
    "dim_market_status",
    "dim_price_event_status",
    "fct_market_snapshots",
    "fct_price_changes",
]


def _resolve_dbt() -> str:
    venv_dbt = REPO_ROOT / ".venv" / "bin" / "dbt"
    if venv_dbt.exists():
        return str(venv_dbt)
    found = shutil.which("dbt")
    if found:
        return found
    sys.exit("dbt executable not found on PATH or in .venv/bin/dbt")


def _send_lakehouse_alert(mode: str, step: str, cmd: list[str], exit_code: int, tail_lines: list[str]) -> bool:
    """Send Gmail failure notification when any Lakehouse step or dbt test fails."""
    sender = os.environ.get("ALERT_EMAIL_SENDER", "").strip()
    password = os.environ.get("ALERT_EMAIL_PASSWORD", "").strip()
    recipient_raw = os.environ.get("ALERT_EMAIL_RECIPIENT", "").strip() or DEFAULT_ALERT_RECIPIENT
    smtp_host = os.environ.get("ALERT_SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    smtp_port = int(os.environ.get("ALERT_SMTP_PORT", "465").strip() or "465")

    if not (sender and password):
        print(
            "  ⚠️  Lakehouse email alert skipped: ALERT_EMAIL_SENDER or ALERT_EMAIL_PASSWORD not configured.",
            flush=True,
        )
        return False

    recipients = [r.strip() for r in recipient_raw.split(",") if r.strip()]
    if not recipients:
        return False

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"[Azure Lakehouse Alert] [{mode.upper()}] Failed at step: {step}"
    body = "\n".join(
        [
            "Azure Retail Lakehouse Job — Failure Alert",
            "=" * 64,
            f"Timestamp : {now_utc}",
            f"Mode      : {mode}",
            f"Step      : {step}",
            f"Exit Code : {exit_code}",
            f"Command   : {' '.join(cmd)}",
            "",
            "Status    : FAIL-CLOSED — Silver/Gold Parquet on Azure was NOT overwritten.",
            "",
            "Last 45 log lines:",
            "-" * 64,
            *(tail_lines or ["(no captured output)"]),
            "",
        ]
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

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
        print(f"  📧 Lakehouse failure alert sent to {', '.join(recipients)}", flush=True)
        return True
    except Exception as exc:
        print(f"  ⚠️  Failed to send Lakehouse alert email ({type(exc).__name__}): {exc}", flush=True)
        return False


def _run(cmd: list[str], step: str, mode: str, cwd: Path = REPO_ROOT, send_alert: bool = True) -> None:
    print(f"\n>>> [{step}] {' '.join(cmd)}", flush=True)
    tail: deque[str] = deque(maxlen=45)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        tail.append(line.rstrip("\n"))
    exit_code = proc.wait()
    if exit_code != 0:
        if send_alert:
            _send_lakehouse_alert(mode, step, cmd, exit_code, list(tail))
        raise subprocess.CalledProcessError(exit_code, cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Azure Lakehouse dbt transformations & ADLS Gen2 publish.")
    parser.add_argument("--mode", choices=["hourly", "daily"], default="daily")
    parser.add_argument("--local", action="store_true", help="Skip Azure pull/push; export Parquet locally only.")
    parser.add_argument(
        "--test-alert",
        action="store_true",
        help="Send a test alert email to verify Gmail SMTP credentials and exit.",
    )
    args = parser.parse_args()

    if args.test_alert:
        ok = _send_lakehouse_alert(
            mode=args.mode,
            step="test-alert",
            cmd=["run_lakehouse.py", "--test-alert"],
            exit_code=0,
            tail_lines=["✅ This is a test notification from Azure Retail Lakehouse Container Apps Job."],
        )
        sys.exit(0 if ok else 1)

    dbt_bin = _resolve_dbt()
    py_bin = sys.executable
    notify = not args.local

    # 1. Pull latest state from Azure ADLS Gen2
    if not args.local:
        _run([py_bin, str(AZURE_SYNC), "--action", "pull-state"], "pull-state", args.mode, send_alert=notify)

    # 2. Run dbt transformations & tests
    if args.mode == "daily":
        _run([dbt_bin, "seed", "--profiles-dir", "."], "dbt-seed", args.mode, cwd=TRANS_DIR, send_alert=notify)
        _run([dbt_bin, "run", "--profiles-dir", "."], "dbt-run-daily", args.mode, cwd=TRANS_DIR, send_alert=notify)
        _run([dbt_bin, "test", "--profiles-dir", "."], "dbt-test-daily", args.mode, cwd=TRANS_DIR, send_alert=notify)
    else:
        select_args = ["--select", *HOURLY_MODELS]
        _run(
            [dbt_bin, "run", "--profiles-dir", ".", *select_args],
            "dbt-run-hourly",
            args.mode,
            cwd=TRANS_DIR,
            send_alert=notify,
        )
        _run(
            [dbt_bin, "test", "--profiles-dir", ".", "--indirect-selection=cautious", *select_args],
            "dbt-test-hourly",
            args.mode,
            cwd=TRANS_DIR,
            send_alert=notify,
        )

    # 3. Export & upload Silver + Gold Parquet to Azure ADLS Gen2
    extra = ["--local-only"] if args.local else []
    _run([py_bin, str(AZURE_SYNC), "--action", "push-silver", *extra], "push-silver", args.mode, send_alert=notify)
    _run([py_bin, str(AZURE_SYNC), "--action", "push-gold", *extra], "push-gold", args.mode, send_alert=notify)

    print(f"\nLakehouse run ({args.mode}, local={args.local}) completed successfully!", flush=True)


if __name__ == "__main__":
    main()
