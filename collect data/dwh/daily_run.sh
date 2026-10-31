#!/usr/bin/env bash
# ================================================================
# Egypt E-Commerce — Daily 19:00 (7:00 PM) Scraping & Databricks Sync
# ================================================================
# Scheduled in crontab to run every day at 19:00 (7:00 PM):
#   0 19 * * * "/home/ahmed-sami/Desktop/spplychaun data collection/egypt-ecommerce-data-platform/dwh/daily_run.sh" --live >> "/home/ahmed-sami/Desktop/spplychaun data collection/egypt-ecommerce-data-platform/dwh/logs/cron_1900.log" 2>&1
#
# Or run manually:
#   ./dwh/daily_run.sh --live     (live scraping across Egypt + Databricks sync)
#   ./dwh/daily_run.sh            (uses COLLECTION_MODE from .env)
# ================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
VENV="$PROJECT_DIR/.venv/bin/python3"
LOG_DIR="$PROJECT_DIR/dwh/logs"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/run_$TODAY.log"

mkdir -p "$LOG_DIR"

# ── Concurrency Protection (Lockfile via flock) ──────────────────
LOCK_FILE="/tmp/egypt_ecommerce_daily_run.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️ Another instance of daily_run.sh is currently running (locked by $LOCK_FILE). Exiting safely." | tee -a "$LOG_FILE"
    exit 0
fi

# ── Log Maintenance & Rotation ───────────────────────────────────
# Purge daily run logs older than 14 days
find "$LOG_DIR" -name "run_*.log" -type f -mtime +14 -delete 2>/dev/null || true
# Rotate cron_1900.log if it exceeds 20MB
CRON_LOG="$LOG_DIR/cron_1900.log"
if [[ -f "$CRON_LOG" ]]; then
    CRON_SIZE=$(stat -c%s "$CRON_LOG" 2>/dev/null || stat -f%z "$CRON_LOG" 2>/dev/null || echo 0)
    if [[ "$CRON_SIZE" -gt 20971520 ]]; then
        mv "$CRON_LOG" "$CRON_LOG.1"
        touch "$CRON_LOG"
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] Rotated $CRON_LOG (size was ${CRON_SIZE} bytes)." >> "$CRON_LOG"
    fi
fi

# Load .env if present
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

echo "================================================================" | tee -a "$LOG_FILE"
echo "Egypt DWH Daily Midnight Run — $TODAY $(date +%H:%M:%S)" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"

# Determine mode (--live flag or COLLECTION_MODE=live in .env, unless --offline is passed)
LIVE_FLAG=""
LIMIT_VAL="${MAX_PRODUCTS_PER_SOURCE:-10000}"

if [[ "${1:-}" == "--offline" ]]; then
    LIVE_FLAG=""
    echo "MODE: offline_fixture (explicit --offline)" | tee -a "$LOG_FILE"
elif [[ "${1:-}" == "--live" ]] || [[ "${COLLECTION_MODE:-}" == "live" ]]; then
    LIVE_FLAG="--live"
    echo "MODE: LIVE (scraping Egypt e-commerce catalogs, limit=$LIMIT_VAL)" | tee -a "$LOG_FILE"
else
    echo "MODE: offline_fixture (no live requests)" | tee -a "$LOG_FILE"
fi

# Step 1: Run extraction pipeline → DuckDB + Department Partitions
echo "" | tee -a "$LOG_FILE"
echo "Step 1/3: Running Egypt extraction pipeline..." | tee -a "$LOG_FILE"
"$VENV" "$PROJECT_DIR/dwh/pipeline.py" $LIVE_FLAG --limit "$LIMIT_VAL" 2>&1 | tee -a "$LOG_FILE"

# Step 2: Sync to Databricks Lakehouse
echo "" | tee -a "$LOG_FILE"
echo "Step 2/3: Syncing Egypt DWH to Databricks..." | tee -a "$LOG_FILE"
if [[ -n "${DATABRICKS_HOST:-}" && "${DATABRICKS_HOST}" != "your_host" && -n "${DATABRICKS_HTTP_PATH:-}" ]]; then
    "$VENV" "$PROJECT_DIR/dwh/export_to_databricks.py" 2>&1 | tee -a "$LOG_FILE"
else
    echo "  ℹ️  Databricks host/http_path in .env are still unconfigured — running dry-run verification:" | tee -a "$LOG_FILE"
    "$VENV" "$PROJECT_DIR/dwh/export_to_databricks.py" --dry-run 2>&1 | tee -a "$LOG_FILE"
    echo "  👉 Fill in DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_USERNAME, DATABRICKS_PASSWORD in .env to enable live Databricks upload." | tee -a "$LOG_FILE"
fi

# Step 3: Optional PostgreSQL Sync (if PG_URL or DATABASE_URL is set)
TARGET_PG_URL="${PG_URL:-${DATABASE_URL:-}}"
if [[ -n "${TARGET_PG_URL:-}" && "${TARGET_PG_URL}" != *"user:password@localhost"* ]]; then
    echo "" | tee -a "$LOG_FILE"
    echo "Step 3/3: Exporting to PostgreSQL..." | tee -a "$LOG_FILE"
    "$VENV" "$PROJECT_DIR/dwh/export_to_postgres.py" --pg-url "$TARGET_PG_URL" 2>&1 | tee -a "$LOG_FILE"
else
    echo "" | tee -a "$LOG_FILE"
    echo "Step 3/3: PostgreSQL sync skipped (set PG_URL if needed)" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo "Done. Log: $LOG_FILE" | tee -a "$LOG_FILE"
