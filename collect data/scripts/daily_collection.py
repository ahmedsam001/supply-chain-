#!/usr/bin/env python3
"""
Daily Collection Script — Runs all enabled extractors once per day.

Designed for 7-day initial collection and ongoing daily incremental runs.

Usage:
    python scripts/daily_collection.py
    python scripts/daily_collection.py --day 1    # Day 1 of initial collection
    python scripts/daily_collection.py --sources tradeline dream2000

Can be scheduled via cron:
    0 6 * * * /path/to/.venv/bin/python /path/to/scripts/daily_collection.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


async def run_daily_collection(
    sources: list[str] | None = None,
    max_products: int = 500,
    data_dir: str = "./data",
):
    """Run extraction for all enabled sources (or specified ones)."""
    from run_extraction import run_extraction, print_final_summary

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("daily_collection.start", date=today)

    if sources:
        results = []
        for source_id in sources:
            r = await run_extraction(
                source_id=source_id,
                data_dir=data_dir,
                max_products=max_products,
            )
            results.extend(r)
    else:
        results = await run_extraction(
            data_dir=data_dir,
            max_products=max_products,
        )

    # Save daily summary
    summary_dir = Path(data_dir) / "raw" / "_daily_summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "date": today,
        "sources_extracted": len(results),
        "total_products": sum(len(r.products) for r in results),
        "total_locations": sum(len(r.locations) for r in results),
        "total_observations": sum(len(r.observations) for r in results),
        "total_errors": sum(len(r.errors) for r in results),
        "sources": [
            {
                "source_id": r.source_id,
                "products": len(r.products),
                "locations": len(r.locations),
                "observations": len(r.observations),
                "errors": len(r.errors),
                "duration": r.duration_seconds,
            }
            for r in results
        ],
    }

    summary_file = summary_dir / f"{today}.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print_final_summary(results)
    logger.info("daily_collection.done", date=today, summary_file=str(summary_file))


def main():
    parser = argparse.ArgumentParser(description="Daily Collection Runner")
    parser.add_argument("--sources", nargs="+", help="Specific sources to run")
    parser.add_argument("--max-products", type=int, default=500)
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--day", type=int, help="Day number for initial 7-day collection")

    args = parser.parse_args()

    if args.day:
        print(f"\n📅 Day {args.day} of initial 7-day collection")

    asyncio.run(
        run_daily_collection(
            sources=args.sources,
            max_products=args.max_products,
            data_dir=args.data_dir,
        )
    )


if __name__ == "__main__":
    main()
