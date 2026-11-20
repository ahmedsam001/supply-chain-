#!/usr/bin/env bash
# ================================================================
# Local runner wrapper (optional cron entrypoint) — no Airflow/cloud.
#   ./dwh/daily_run.sh            -> --mode daily
#   ./dwh/daily_run.sh hourly     -> --mode hourly
#   extra args are forwarded, e.g. ./dwh/daily_run.sh daily --limit 200
# Overlap protection is handled inside run_pipeline.py (file lock).
# ================================================================
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
MODE="${1:-daily}"; [[ $# -gt 0 ]] && shift
LOG_DIR="$PROJECT_DIR/dwh/logs"; mkdir -p "$LOG_DIR"
find "$LOG_DIR" -name "run_*.log" -type f -mtime +14 -delete 2>/dev/null || true
exec "$PROJECT_DIR/.venv/bin/python3" dwh/run_pipeline.py --mode "$MODE" "$@" \
  >> "$LOG_DIR/run_$(date +%Y-%m-%d).log" 2>&1
