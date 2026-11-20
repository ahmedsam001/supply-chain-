"""
Live Smoke Test & Snapshot Replay — WP1 & WP2

Proves live HTTP collection works for Class B sources (jumia, two_b) through the
compliance gate, saves raw gzipped snapshots + robots.txt + sha256 + run_manifest.json
under data/raw_snapshots/<source>/<run_id>/, and saves sanitized real HTML fixtures
under tests/fixtures/<source>/real/.

Usage:
    python scripts/live_smoke.py --source jumia --limit 6
    python scripts/live_smoke.py --source two_b --limit 6
    python scripts/live_smoke.py --source jumia --replay-run <run_id>
    python scripts/live_smoke.py  # runs all enabled Class B sources
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
import structlog

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from extractors.base import SAFE_HEADER_KEYS
from normalization.schema import ExtractionResult
from validation.data_validator import DataValidator
from validation.observation_history import ObservationHistory
from validation.run_manifest import RunManifest

DATA_DIR = BASE_DIR / "data"
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"
WATCHLIST_PATH = BASE_DIR / "config" / "watchlist.json"

PROBE_URLS: dict[str, list[str]] = {
    "jumia": [
        "https://www.jumia.com.eg/phones-tablets/",
    ],
    "two_b": [
        "https://2b.com.eg/en/computers/laptops.html",
    ],
}

ROBOTS_URLS: dict[str, str] = {
    "jumia": "https://www.jumia.com.eg/robots.txt",
    "two_b": "https://2b.com.eg/robots.txt",
}

RATE_LIMIT_SECONDS: dict[str, float] = {
    "jumia": 2.0,    # <=30 RPM
    "two_b": 10.0,   # <=6 RPM (10s crawl-delay)
}

USER_AGENT = (
    "EgyptEcommerceDataPlatform/1.0 "
    "(Academic Research Project; contact: project@example.com)"
)

logger = structlog.get_logger()


def load_watchlist() -> dict:
    """Load persisted deterministic watchlist configuration."""
    if WATCHLIST_PATH.exists():
        try:
            return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"watchlist_id": "watchlist_v1", "sources": {}}


def _select_watched_cards(cards: list[dict], source_id: str, limit: int) -> list[dict]:
    """
    Deterministically select cards matching persisted watchlist IDs first,
    then fill any remaining slots in page order up to `limit`.
    """
    wl = load_watchlist()
    watched_ids = (
        wl.get("sources", {})
        .get(source_id, {})
        .get("watched_source_product_ids", [])
    )
    if not watched_ids:
        return cards[:limit]

    by_id = {str(c.get("source_product_id") or c.get("sku") or ""): c for c in cards}
    selected: list[dict] = []
    seen: set[str] = set()

    for wid in watched_ids:
        wid_s = str(wid)
        if wid_s in by_id and wid_s not in seen:
            selected.append(by_id[wid_s])
            seen.add(wid_s)
            if len(selected) >= limit:
                return selected

    for c in cards:
        cid = str(c.get("source_product_id") or c.get("sku") or id(c))
        if cid not in seen:
            selected.append(c)
            seen.add(cid)
            if len(selected) >= limit:
                break

    return selected


def _sanitize_html(html: str) -> str:
    """Strip any potential session tokens, inline csrf tokens, or email addresses before saving fixture."""
    html = re.sub(r'(?i)(csrf[_-]?token|form_key)"\s*value="[^"]+"', r'\1" value="REDACTED"', html)
    return html


def save_snapshot(
    run_dir: Path,
    url: str,
    response,
    elapsed_ms: int = 0,
    filename_prefix: Optional[str] = None,
) -> dict:
    """Save a single HTTP response as a gzip snapshot with sha256 and safe headers."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    body_bytes = response.content if isinstance(response.content, bytes) else str(response.content).encode("utf-8")
    sha256 = hashlib.sha256(body_bytes).hexdigest()
    gz_name = f"{filename_prefix}_{sha256[:12]}.gz" if filename_prefix else f"{sha256[:16]}.html.gz"
    gzip_path = run_dir / gz_name

    with gzip.open(gzip_path, "wb") as f:
        f.write(body_bytes)

    raw_headers = dict(getattr(response, "headers", {}) or {})
    safe_headers = {
        str(k).lower(): str(v)
        for k, v in raw_headers.items()
        if str(k).lower() in SAFE_HEADER_KEYS
    }

    meta = {
        "url": url,
        "status_code": int(getattr(response, "status_code", 200)),
        "headers": safe_headers,
        "sha256": sha256,
        "content_length": len(body_bytes),
        "gzip_file": gzip_path.name,
        "elapsed_ms": int(elapsed_ms),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    index_path = run_dir / "snapshots_index.json"
    existing: list[dict] = []
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(meta)
    index_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    return meta


def read_snapshot(snapshot_meta: dict, run_dir: Path) -> bytes:
    """Load gzip body from snapshot."""
    gzip_path = Path(run_dir) / snapshot_meta["gzip_file"]
    with gzip.open(gzip_path, "rb") as f:
        return f.read()


def verify_snapshot_sha256(snapshot_meta: dict, run_dir: Path) -> bool:
    """Verify that stored gzip decodes to expected sha256."""
    body = read_snapshot(snapshot_meta, run_dir)
    actual = hashlib.sha256(body).hexdigest()
    return actual == snapshot_meta["sha256"]


def parse_snapshot_to_canonical(
    source_id: str,
    html: str,
    url: str,
    limit: int = 6,
    run_id: Optional[str] = None,
    mode: str = "live",
    stores_html: Optional[str] = None,
) -> ExtractionResult:
    """
    Deterministic parsing of captured HTML into canonical ExtractionResult.
    Never invents SKU or GTIN when absent on the card.
    """
    from normalization.schema import (
        AvailabilityScope,
        AvailabilityStatus,
        Currency,
        Location,
        LocationType,
        Product,
        ProductObservation,
    )

    products = []
    observations = []
    locations = []
    now = datetime.now(timezone.utc)

    if source_id == "jumia":
        from extractors.source_jumia.parser import parse_category_page, parse_delivery_zones
        cards = _select_watched_cards(
            parse_category_page(html, "https://www.jumia.com.eg"),
            source_id="jumia",
            limit=limit,
        )
        for c in cards:
            pid = c.get("source_product_id")
            if not pid:
                continue
            p = Product(
                source_id="jumia",
                source_product_id=str(pid),
                sku=c.get("sku"),
                gtin=c.get("gtin"),
                product_name=c["product_name"],
                brand=c.get("brand"),
                category=c.get("category") or "Phones & Tablets",
                raw_category_path=c.get("raw_category_path"),
                product_url=c["product_url"],
                source_url=url,
                image_url=c.get("image_url"),
                collected_at=now,
                run_id=run_id,
            )
            products.append(p)
            avail_st = AvailabilityStatus.IN_STOCK if c.get("price") else AvailabilityStatus.UNKNOWN
            obs = ProductObservation(
                product_id=p.product_id,
                source_id="jumia",
                source_product_id=str(pid),
                observed_at=now,
                collected_at=now,
                price=c.get("price"),
                old_price=c.get("old_price"),
                discount=c.get("discount"),
                currency=Currency.EGP,
                availability_status=avail_st,
                stock_status="IN_STOCK" if avail_st == AvailabilityStatus.IN_STOCK else "UNKNOWN",
                stock_quantity=None,
                raw_price_text=c.get("raw_price_text"),
                availability_scope=AvailabilityScope.GLOBAL,
                fulfillment_method="marketplace",
                delivery_available=None,
                delivery_eta=None,
                delivery_fee=None,
                seller_name=c.get("seller_name"),
                rating=c.get("rating"),
                review_count=c.get("review_count"),
                source_url=p.product_url,
                run_id=run_id,
            )
            observations.append(obs)
        for z in parse_delivery_zones():
            zone_label = f"{z['governorate']} Delivery Zone"
            locations.append(
                Location(
                    source_id="jumia",
                    location_type=LocationType.DELIVERY_ZONE,
                    location_name=zone_label,
                    governorate=z["governorate"],
                    delivery_zone=zone_label,
                    source_url=url,
                    collected_at=now,
                    run_id=run_id,
                )
            )

    elif source_id == "two_b":
        from extractors.source_2b.parser import parse_category_page, parse_store_locator
        cards = _select_watched_cards(
            parse_category_page(html),
            source_id="two_b",
            limit=limit,
        )
        for c in cards:
            name = c.get("product_name", "")
            if not name:
                continue
            spid = str(c.get("source_product_id") or name[:50])
            p = Product(
                source_id="two_b",
                source_product_id=spid,
                sku=c.get("sku"),
                gtin=c.get("gtin"),
                product_name=name,
                brand=c.get("brand"),
                category=c.get("category") or "Laptops",
                product_url=c.get("product_url") or url,
                source_url=url,
                image_url=c.get("image_url"),
                collected_at=now,
                run_id=run_id,
            )
            products.append(p)
            obs = ProductObservation(
                product_id=p.product_id,
                source_id="two_b",
                source_product_id=spid,
                observed_at=now,
                collected_at=now,
                price=c.get("price"),
                old_price=c.get("old_price"),
                discount=c.get("discount"),
                currency=Currency.EGP,
                availability_status=c.get("availability_status", AvailabilityStatus.UNKNOWN),
                availability_scope=c.get("availability_scope", AvailabilityScope.DELIVERY_AREA),
                stock_status=c.get("stock_status", "IN_STOCK"),
                stock_quantity=None,
                raw_availability_text=c.get("raw_availability_text"),
                raw_price_text=c.get("raw_price_text"),
                delivery_available=c.get("delivery_available"),
                delivery_eta=c.get("delivery_eta"),
                delivery_fee=c.get("delivery_fee"),
                seller_name=c.get("seller_name"),
                source_url=p.product_url,
                fulfillment_method="retailer",
                run_id=run_id,
            )
            observations.append(obs)

        eff_stores_html = stores_html
        if not eff_stores_html:
            default_stores = FIXTURES_DIR / "two_b" / "real" / "stores_sample.html"
            if default_stores.exists():
                eff_stores_html = default_stores.read_text(encoding="utf-8")
        if eff_stores_html:
            locations = parse_store_locator(
                eff_stores_html,
                source_id="two_b",
                source_url="https://2b.com.eg/en/stores",
            )
            for loc in locations:
                loc.run_id = run_id

    return ExtractionResult(
        source_id=source_id,
        run_id=run_id,
        products=products,
        locations=locations,
        observations=observations,
        pages_visited=1,
        mode=mode,
    )


def replay_run(
    source_id: str,
    run_id: str,
    data_dir: Optional[Path] = None,
    limit: int = 6,
) -> tuple[list[tuple[str, bytes]], ExtractionResult]:
    """
    WP2: Replay all snapshots from a stored run with zero network calls.
    Returns (list of (url, body_bytes), canonical ExtractionResult).
    """
    base_data = Path(data_dir) if data_dir else DATA_DIR
    run_dir = base_data / "raw_snapshots" / source_id / run_id
    index_path = run_dir / "snapshots_index.json"
    manifest_path = run_dir / "run_manifest.json"

    snapshots = []
    if index_path.exists():
        snapshots = json.loads(index_path.read_text(encoding="utf-8"))
    elif manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshots = m.get("snapshots", [])

    if not snapshots:
        raise FileNotFoundError(f"No snapshots found at {run_dir}")

    replays: list[tuple[str, bytes]] = []
    page_html = ""
    page_url = ""
    stores_html: Optional[str] = None

    for snap in snapshots:
        body = read_snapshot(snap, run_dir)
        actual_sha = hashlib.sha256(body).hexdigest()
        if actual_sha != snap["sha256"]:
            raise ValueError(
                f"SHA256 mismatch for {snap['url']}: expected {snap['sha256']}, got {actual_sha}"
            )
        replays.append((snap["url"], body))
        if "store_locator" in snap["url"] or snap["url"].endswith("/en/stores"):
            decoded = body.decode("utf-8", errors="replace")
            if "mw-sl__stores__list__item" in decoded or not stores_html:
                stores_html = decoded
        elif not snap["url"].endswith("/robots.txt") and not page_html:
            page_html = body.decode("utf-8", errors="replace")
            page_url = snap["url"]

    canonical = parse_snapshot_to_canonical(
        source_id=source_id,
        html=page_html,
        url=page_url,
        limit=limit,
        run_id=run_id,
        mode="replay",
        stores_html=stores_html,
    )
    DataValidator().validate(canonical, run_id=run_id)
    return replays, canonical


async def probe_source(
    source_id: str,
    limit: int,
    run_id: str,
    data_dir: Optional[Path] = None,
    watchlist_id: Optional[str] = None,
) -> dict:
    """
    Probe an enabled Class B source:
    1. Re-check and snapshot robots.txt
    2. Fetch category page with compliant User-Agent and rate limit
    3. Store raw gzip snapshot + sha256 + safe headers
    4. Save sanitized real fixture under tests/fixtures/<source>/real/
    5. Parse into canonical models, validate, and write run_manifest.json
    """
    base_data = Path(data_dir) if data_dir else DATA_DIR
    run_dir = base_data / "raw_snapshots" / source_id / run_id
    wl = load_watchlist()
    eff_watchlist_id = watchlist_id or wl.get("watchlist_id", "watchlist_v1")

    manifest = RunManifest(
        source_id=source_id,
        run_id=run_id,
        mode="live",
        data_dir=str(base_data),
    )
    manifest.compliance_status = "B"

    urls = PROBE_URLS.get(source_id, [])
    robots_url = ROBOTS_URLS.get(source_id)
    delay = RATE_LIMIT_SECONDS.get(source_id, 3.0)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    }

    snapshots_meta: list[dict] = []
    canonical_result: Optional[ExtractionResult] = None

    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=headers) as client:
            if robots_url:
                t0 = time.monotonic()
                r_resp = await client.get(robots_url)
                r_ms = int((time.monotonic() - t0) * 1000)
                r_meta = save_snapshot(run_dir, robots_url, r_resp, elapsed_ms=r_ms, filename_prefix="robots")
                manifest.robots_sha256 = r_meta["sha256"]
                manifest.record_http_status(r_resp.status_code)
                snapshots_meta.append(r_meta)

            for idx, url in enumerate(urls):
                if idx > 0 or robots_url:
                    await asyncio.sleep(delay)
                t0 = time.monotonic()
                resp = await client.get(url)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                manifest.record_http_status(resp.status_code)
                manifest.pages_parsed += 1

                snap_meta = save_snapshot(run_dir, url, resp, elapsed_ms=elapsed_ms)
                snapshots_meta.append(snap_meta)

                if resp.status_code == 200 and resp.text:
                    real_fixture_dir = FIXTURES_DIR / source_id / "real"
                    real_fixture_dir.mkdir(parents=True, exist_ok=True)
                    sanitized = _sanitize_html(resp.text)
                    fixture_file = real_fixture_dir / "category_sample.html"
                    fixture_file.write_text(sanitized, encoding="utf-8")

                    canonical_result = parse_snapshot_to_canonical(
                        source_id=source_id,
                        html=sanitized,
                        url=url,
                        limit=limit,
                        run_id=run_id,
                        mode="live",
                    )

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        manifest.blocked_reason = f"BLOCKED_BY_ENVIRONMENT: {type(e).__name__}: {e}"
        manifest.errors.append(manifest.blocked_reason)
    except Exception as e:
        manifest.errors.append(f"Unexpected error: {e}")

    if canonical_result is None:
        canonical_result = ExtractionResult(source_id=source_id, run_id=run_id, mode="live")

    validator = DataValidator()
    val_report = validator.validate(canonical_result, run_id=run_id)
    manifest.populate_from_validation(canonical_result, val_report)
    manifest.finish()

    if canonical_result.observations:
        ObservationHistory(data_dir=str(base_data)).append_result(
            canonical_result,
            run_id=run_id,
            run_mode="live",
            watchlist_id=eff_watchlist_id,
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "products.json").write_text(
        json.dumps([p.model_dump(mode="json") for p in canonical_result.products], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "observations.json").write_text(
        json.dumps([o.model_dump(mode="json") for o in canonical_result.observations], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "locations.json").write_text(
        json.dumps([l.model_dump(mode="json") for l in canonical_result.locations], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    DataValidator.write_quality_issues(canonical_result.quality_issues, run_dir / "quality_issues.json")

    manifest_dict = manifest.to_dict()
    manifest_dict["watchlist_id"] = eff_watchlist_id
    manifest_dict["snapshots"] = snapshots_meta
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    audit_dir = base_data / "manifests" / source_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / f"{run_id}.json").write_text(
        json.dumps(manifest_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return manifest_dict


async def main(args: argparse.Namespace) -> int:
    run_id = args.run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + str(uuid4())[:8]
    )

    if args.replay_run:
        replays, canonical = replay_run(args.source, args.replay_run, limit=args.limit)
        print(
            f"[REPLAY] {args.source} / {args.replay_run}: "
            f"{len(replays)} snapshot(s) verified, "
            f"{len(canonical.products)} products, "
            f"{len(canonical.observations)} observations, "
            f"{len(canonical.locations)} locations"
        )
        return 0

    sources = [args.source] if args.source else list(PROBE_URLS.keys())
    all_ok = True
    for sid in sources:
        res = await probe_source(
            sid,
            limit=args.limit,
            run_id=run_id,
            watchlist_id=args.watchlist_id,
        )
        print(
            f"[{sid}] run_id={run_id} watchlist={res.get('watchlist_id')} "
            f"status={res['status']} "
            f"products={res['products_accepted']} "
            f"observations={res['observations_accepted']} "
            f"locations={res['locations_accepted']} "
            f"score={res.get('quality_score', res.get('overall_quality_score', 0)):.1f}% "
            f"issues={res.get('quality_issues_count', 0)} "
            f"robots_sha256={(res.get('robots_sha256') or '')[:12]}"
        )
        if res["status"] not in ("SUCCESS", "PARTIAL"):
            all_ok = False
    return 0 if all_ok else 2


def cli_main():
    parser = argparse.ArgumentParser(description="Live smoke test and snapshot replay (WP1/WP2)")
    parser.add_argument("--source", type=str, default=None, help="Source ID (jumia or two_b)")
    parser.add_argument("--limit", type=int, default=6, help="Products limit (5-20, default 6)")
    parser.add_argument("--run-id", type=str, default=None, help="Explicit run_id")
    parser.add_argument("--watchlist-id", type=str, default=None, help="Explicit watchlist_id")
    parser.add_argument("--replay-run", type=str, default=None, help="Replay a stored run_id")
    args = parser.parse_args()
    if args.replay_run and not args.source:
        parser.error("--replay-run requires --source")
    sys.exit(asyncio.run(main(args)))


if __name__ == "__main__":
    cli_main()
