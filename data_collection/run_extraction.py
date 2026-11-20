#!/usr/bin/env python3
"""
Egypt E-Commerce Data Platform — Main Extraction Runner

Usage:
    python run_extraction.py                                   # Run all enabled sources (bounded --limit 10)
    python run_extraction.py --source jumia --limit 6          # Run Jumia live (6 products)
    python run_extraction.py --source tradeline --offline-fixture  # Run offline fixture
    python run_extraction.py --source jumia --replay-run <id>  # Replay stored raw snapshot with no network
    python run_extraction.py --source jumia --diff <r1> <r2>   # Diff two runs from observation history
    python run_extraction.py --list                            # List all sources and status
    python run_extraction.py --audit                           # Run compliance audit only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.loader import load_sources_config, get_enabled_sources, select_deterministic_products
from compliance.compliance_check import ComplianceChecker, ComplianceViolation
from normalization.schema import (
    ComplianceStatus,
    ExtractionResult,
)
from validation.data_validator import DataValidator
from validation.observation_history import ObservationHistory
from validation.run_manifest import RunManifest


# ─── Extractor Registry ──────────────────────────────────────────────

def get_extractor(
    source_id: str,
    data_dir: str = "./data",
    max_products: int = 1000000000000,
    run_id: Optional[str] = None,
    replay_run_id: Optional[str] = None,
    department: Optional[str] = None,
):
    """Factory function — returns the appropriate extractor for a source."""
    kwargs = {
        "data_dir": data_dir,
        "max_products": max_products,
        "run_id": run_id,
        "replay_run_id": replay_run_id,
        "department": department,
    }

    if source_id == "tradeline":
        from extractors.source_tradeline.extractor import TradelineExtractor
        return TradelineExtractor(**kwargs)

    elif source_id == "dream2000":
        from extractors.source_dream2000.extractor import Dream2000Extractor
        return Dream2000Extractor(**kwargs)

    elif source_id == "two_b":
        from extractors.source_2b.extractor import TwoBExtractor
        return TwoBExtractor(**kwargs)

    elif source_id == "raya":
        from extractors.source_raya.extractor import RayaExtractor
        return RayaExtractor(**kwargs)

    elif source_id == "btech":
        from extractors.source_btech.extractor import BTechExtractor
        return BTechExtractor(**kwargs)

    elif source_id == "jumia":
        from extractors.source_jumia.extractor import JumiaExtractor
        return JumiaExtractor(**kwargs)

    elif source_id == "carrefour":
        from extractors.source_carrefour.extractor import CarrefourExtractor
        return CarrefourExtractor(**kwargs)

    else:
        raise ValueError(f"No extractor implemented for source: {source_id}")


async def _run_single_offline_fixture(
    sid: str,
    data_dir: str = "./data",
    max_products: int = 10,
    run_id: Optional[str] = None,
) -> ExtractionResult:
    """Parse saved offline fixture for a source without making any network requests."""
    fixtures_dir = PROJECT_ROOT / "tests" / "fixtures"
    eff_run_id = run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + str(uuid4())[:8]
    )
    t0 = time.monotonic()

    if sid == "jumia":
        from extractors.source_jumia.extractor import JumiaExtractor
        cat_fixture = fixtures_dir / "jumia_sample.html"
        ext = JumiaExtractor(
            fixture_path=cat_fixture,
            pdp_fixture_path=fixtures_dir / "jumia_pdp_sample.html",
            data_dir=data_dir,
            max_products=max_products,
            run_id=eff_run_id,
        )
        products = await ext.extract_products()
        locations = await ext.extract_locations()
        observations = []
        for p in products:
            obs = await ext.extract_product_details(p)
            if obs:
                observations.append(obs)
        result = ExtractionResult(
            source_id=sid,
            run_id=eff_run_id,
            products=products,
            locations=locations,
            observations=observations,
            pages_visited=1,
            duration_seconds=time.monotonic() - t0,
            mode="offline_fixture",
        )

    elif sid == "carrefour":
        from extractors.source_carrefour.extractor import CarrefourExtractor
        ext = CarrefourExtractor(
            fixture_path=fixtures_dir / "carrefour_sample.html",
            data_dir=data_dir,
            max_products=max_products,
            run_id=eff_run_id,
        )
        products = await ext.extract_products()
        locations = await ext.extract_locations()
        observations = []
        for p in products:
            obs = await ext.extract_product_details(p)
            if obs:
                observations.append(obs)
        result = ExtractionResult(
            source_id=sid,
            run_id=eff_run_id,
            products=products,
            locations=locations,
            observations=observations,
            pages_visited=1,
            duration_seconds=time.monotonic() - t0,
            mode="offline_fixture",
        )

    elif sid == "tradeline":
        from extractors.source_tradeline.parser import (
            parse_shopify_products_json,
            parse_store_locator_html,
        )
        data = json.loads((fixtures_dir / "tradeline_products_sample.json").read_text(encoding="utf-8"))
        products, observations = parse_shopify_products_json(data, source_id="tradeline")
        loc_html = (fixtures_dir / "tradeline_locator_sample.html").read_text(encoding="utf-8")
        locations = parse_store_locator_html(loc_html, source_id="tradeline")
        result = ExtractionResult(
            source_id=sid,
            run_id=eff_run_id,
            products=products[:max_products],
            locations=locations,
            observations=observations[:max_products],
            pages_visited=2,
            duration_seconds=time.monotonic() - t0,
            mode="offline_fixture",
        )

    elif sid == "dream2000":
        from extractors.source_dream2000.parser import parse_shopify_products_json
        data = json.loads((fixtures_dir / "dream2000_products_sample.json").read_text(encoding="utf-8"))
        products, observations = parse_shopify_products_json(data, source_id="dream2000")
        result = ExtractionResult(
            source_id=sid,
            run_id=eff_run_id,
            products=products[:max_products],
            locations=[],
            observations=observations[:max_products],
            pages_visited=1,
            duration_seconds=time.monotonic() - t0,
            mode="offline_fixture",
        )

    elif sid == "two_b":
        from extractors.source_2b.extractor import TwoBExtractor
        ext = TwoBExtractor(
            fixture_path=fixtures_dir / "twob_sample.html",
            data_dir=data_dir,
            max_products=max_products,
            run_id=eff_run_id,
        )
        products = await ext.extract_products()
        observations = await ext.extract_availability()
        result = ExtractionResult(
            source_id=sid,
            run_id=eff_run_id,
            products=products[:max_products],
            locations=[],
            observations=observations[:max_products],
            pages_visited=1,
            duration_seconds=time.monotonic() - t0,
            mode="synthetic",
        )

    elif sid == "raya":
        from extractors.source_raya.extractor import RayaExtractor
        ext = RayaExtractor(
            fixture_path=fixtures_dir / "raya_sample.html",
            data_dir=data_dir,
            max_products=max_products,
            run_id=eff_run_id,
        )
        products = await ext.extract_products()
        observations = await ext.extract_availability()
        result = ExtractionResult(
            source_id=sid,
            run_id=eff_run_id,
            products=products[:max_products],
            locations=[],
            observations=observations[:max_products],
            pages_visited=1,
            duration_seconds=time.monotonic() - t0,
            mode="synthetic",
        )

    else:
        raise ValueError(f"No offline fixture configured for source: {sid}")

    # Stamp run_id, validate, record manifest and history
    for p in result.products:
        p.run_id = eff_run_id
    for o in result.observations:
        o.run_id = eff_run_id
        if not o.source_id:
            o.source_id = sid
    for loc in result.locations:
        loc.run_id = eff_run_id

    val_report = DataValidator().validate(result, run_id=eff_run_id)
    manifest = RunManifest(
        source_id=sid,
        run_id=eff_run_id,
        mode=result.mode,
        data_dir=data_dir,
    )
    manifest.populate_from_validation(result, val_report)
    manifest.finish()
    manifest.save()

    if result.observations:
        ObservationHistory(data_dir=data_dir).append_result(result, run_id=eff_run_id)

    return result


# ─── Commands ─────────────────────────────────────────────────────────

async def run_extraction(
    source_id: str | None = None,
    data_dir: str = "./data",
    max_products: int = 10,
    offline_fixture: bool = False,
    replay_run_id: str | None = None,
    run_id: str | None = None,
    department: str | None = None,
) -> list[ExtractionResult]:
    """Run extraction for one or all enabled sources (or offline fixture / replay)."""
    sources = load_sources_config()
    checker = ComplianceChecker()
    results = []

    if source_id:
        if source_id not in sources:
            logger.error("source.not_found", source_id=source_id)
            return []
        targets = {source_id: sources[source_id]}
    else:
        targets = {
            sid: src for sid, src in sources.items()
            if src.enabled
        }

    if not targets:
        logger.warning("no_sources_enabled")
        print("\n⚠️  No sources are enabled for extraction.")
        print("   Enable sources in config/sources.yaml")
        return []

    for sid, source in targets.items():
        eff_run_id = run_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + str(uuid4())[:8]
        )
        log = logger.bind(source=source.source_name, source_id=sid, run_id=eff_run_id)

        if replay_run_id:
            from scripts.live_smoke import replay_run
            replays, canonical = replay_run(
                sid,
                replay_run_id,
                data_dir=Path(data_dir),
                limit=max_products,
            )
            results.append(canonical)
            extractor = get_extractor(sid, data_dir, max_products, run_id=replay_run_id, department=department)
            print(f"\n[REPLAY: {replay_run_id} | {len(replays)} snapshot(s)]")
            print(extractor.generate_report(canonical))
            continue

        if offline_fixture:
            if source.compliance_status == ComplianceStatus.DO_NOT_AUTOMATE:
                print(f"\n❌ {source.source_name}: BLOCKED (Class C — DO NOT AUTOMATE)")
                continue
            try:
                result = await _run_single_offline_fixture(
                    sid, data_dir, max_products, run_id=eff_run_id
                )
                results.append(result)
                extractor = get_extractor(sid, data_dir, max_products, run_id=eff_run_id, department=department)
                report = extractor.generate_report(result)
                print(f"\n[MODE: {result.mode}]\n{report}")
            except ValueError as e:
                print(f"\n⏭️  {source.source_name}: {e}")
            continue

        # 1. Compliance check
        try:
            await checker.check(source)
        except ComplianceViolation as e:
            log.error("compliance.failed", error=str(e))
            print(f"\n❌ {source.source_name}: BLOCKED — {e}")
            continue

        # 2. Get extractor
        try:
            extractor = get_extractor(sid, data_dir, max_products, run_id=eff_run_id, department=department)
        except ValueError as e:
            log.warning("extractor.not_implemented", error=str(e))
            print(f"\n⏭️  {source.source_name}: Extractor not implemented yet")
            continue

        # 3. Run extraction
        print(f"\n{'='*60}")
        print(f"🚀 Starting extraction: {source.source_name} (run_id={eff_run_id})")
        print(f"   Method: {source.extraction_method.value}")
        print(f"   Compliance: {source.compliance_status.value}")
        print(f"{'='*60}")

        try:
            result = await extractor.run()
            results.append(result)

            report = extractor.generate_report(result)
            print(f"\n{report}")

        except Exception as e:
            log.error("extraction.fatal", error=str(e))
            print(f"\n❌ {source.source_name}: FAILED — {e}")

    return results


def list_sources():
    """List all configured sources and their status."""
    sources = load_sources_config()

    print(f"\n{'='*90}")
    print(f"{'Source':<20} {'Domain':<30} {'Status':<6} {'Method':<15} {'Enabled'}")
    print(f"{'='*90}")

    status_symbols = {
        ComplianceStatus.ALLOWED: "✅ A",
        ComplianceStatus.CONDITIONAL: "🟡 B",
        ComplianceStatus.DO_NOT_AUTOMATE: "🔴 C",
        ComplianceStatus.UNKNOWN: "❓ D",
    }

    for sid, source in sorted(sources.items()):
        symbol = status_symbols.get(source.compliance_status, "?")
        enabled = "✓" if source.enabled else "✗"
        print(
            f"{source.source_name:<20} {source.domain:<30} "
            f"{symbol:<6} {source.extraction_method.value:<15} {enabled}"
        )

    enabled_count = sum(1 for s in sources.values() if s.enabled)
    c_count = sum(
        1 for s in sources.values()
        if s.compliance_status == ComplianceStatus.DO_NOT_AUTOMATE
    )
    b_count = sum(
        1 for s in sources.values()
        if s.compliance_status == ComplianceStatus.CONDITIONAL
    )

    print(f"\n📊 Summary: {len(sources)} sources total")
    print(f"   🟡 {b_count} conditional (Class B)")
    print(f"   🔴 {c_count} prohibited (Class C)")
    print(f"   ✓  {enabled_count} enabled for extraction")


async def run_compliance_audit():
    """Run compliance audit for all sources."""
    sources = load_sources_config()
    checker = ComplianceChecker()

    print(f"\n{'='*60}")
    print("📋 Compliance Audit Report")
    print(f"   Date: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}\n")

    for sid, source in sorted(sources.items()):
        print(f"--- {source.source_name} ({source.domain}) ---")
        print(f"    Status: {source.compliance_status.value}")

        try:
            await checker.check(source)
            print("    Result: ✅ PASSED")
        except ComplianceViolation as e:
            print(f"    Result: ❌ BLOCKED — {e}")

        robots = await checker.fetch_robots_txt(source.domain)
        if robots:
            crawl_delay = checker.parse_crawl_delay(robots)
            print(f"    robots.txt: Found ({len(robots)} bytes)")
            if crawl_delay:
                print(f"    Crawl-delay: {crawl_delay}s")
        else:
            print("    robots.txt: Not found or inaccessible")

        print()


def print_final_summary(results: list[ExtractionResult]):
    """Print a summary of all extraction results."""
    if not results:
        return

    print(f"\n{'='*60}")
    print("📈 EXTRACTION SUMMARY")
    print(f"{'='*60}")

    total_products = sum(len(r.products) for r in results)
    total_locations = sum(len(r.locations) for r in results)
    total_observations = sum(len(r.observations) for r in results)
    total_errors = sum(len(r.errors) for r in results)

    print(f"\nSources extracted: {len(results)}")
    print(f"Total products: {total_products:,}")
    print(f"Total locations: {total_locations:,}")
    print(f"Total observations: {total_observations:,}")
    print(f"Total errors: {total_errors}")


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Egypt E-Commerce Data Platform — Extraction Runner"
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Run extraction for a specific source ID",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all sources and their compliance status",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run compliance audit for all sources",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Bounded number of products to extract per source (default: 10, recommended 5-20)",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=None,
        help="Alias for --limit (backward-compatible)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data",
        help="Data directory for raw output (default: ./data)",
    )
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Parse saved offline fixtures instead of making live HTTP requests",
    )
    parser.add_argument(
        "--replay-run",
        type=str,
        default=None,
        help="Replay stored raw snapshots from a previous run_id with no network calls",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Explicit run_id for traceability",
    )
    parser.add_argument(
        "--department",
        "--category",
        dest="department",
        type=str,
        default=None,
        help="Target a specific department (e.g. mobiles, laptops, electronics, appliances, meats, dairy, grocery, beverages, cleaning, beauty)",
    )
    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("RUN_ID_A", "RUN_ID_B"),
        help="Compute cross-run observation diff between two run IDs (requires --source)",
    )

    args = parser.parse_args()

    if args.list:
        list_sources()
        return

    if args.audit:
        asyncio.run(run_compliance_audit())
        return

    if args.diff:
        if not args.source:
            parser.error("--diff requires --source")
        hist = ObservationHistory(data_dir=args.data_dir)
        diff = hist.cross_run_diff(args.source, args.diff[0], args.diff[1])
        print(json.dumps(diff, indent=2, ensure_ascii=False))
        return

    effective_limit = args.max_products if args.max_products is not None else args.limit

    results = asyncio.run(
        run_extraction(
            source_id=args.source,
            data_dir=args.data_dir,
            max_products=effective_limit,
            offline_fixture=args.offline_fixture,
            replay_run_id=args.replay_run,
            run_id=args.run_id,
            department=args.department,
        )
    )

    print_final_summary(results)


if __name__ == "__main__":
    main()
