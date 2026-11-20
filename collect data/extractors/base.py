"""
Base extractor — abstract interface that every source extractor must implement.

Provides:
- Consistent lifecycle (init → compliance check → robots re-check → extract → validate → save)
- Rate limiting with configurable delays
- Retry logic with exponential backoff
- Structured logging with run_id bound on every log line (WP3)
- Raw-data gzip snapshot management and deterministic offline replay (WP2)
- RunManifest and ObservationHistory integration (WP3, WP5)
- Playwright browser management
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

from compliance.compliance_check import ComplianceChecker
from normalization.schema import (
    AvailabilityStatus,
    ComplianceStatus,
    ExtractionMethod,
    ExtractionResult,
    Location,
    Product,
    ProductObservation,
    Source,
)
from validation.data_validator import DataValidator
from validation.observation_history import ObservationHistory
from validation.run_manifest import RunManifest

logger = structlog.get_logger()

SAFE_HEADER_KEYS = {
    "content-type",
    "content-length",
    "date",
    "server",
    "cache-control",
    "etag",
    "last-modified",
}

DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

ACCEPT_LANGUAGE_HEADERS = [
    "en-US,en;q=0.9,ar-EG;q=0.8,ar;q=0.7",
    "en-GB,en-US;q=0.9,en;q=0.8,ar;q=0.7",
    "en-US,en;q=0.9",
]


def get_rotated_headers(url: str = "") -> dict[str, str]:
    """Return realistic rotated desktop browser headers for anti-ban protection."""
    headers = {
        "User-Agent": random.choice(DESKTOP_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "Accept-Language": random.choice(ACCEPT_LANGUAGE_HEADERS),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if url:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    return headers


class ExtractionError(Exception):
    """Raised when extraction fails for a source."""
    pass


class CircuitBreakerOpenError(ExtractionError):
    """Raised when consecutive failures trip the fail-fast circuit breaker."""
    pass


class ComplianceError(Exception):
    """Raised when a source fails compliance checks."""
    pass


def _is_retryable_fetch_error(exc: BaseException) -> bool:
    """Retry transient network/timeout/5xx/429 errors, but fail fast on 403/404."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        return status in (408, 429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.HTTPError, TimeoutError))


def save_raw_snapshot_bytes(
    run_dir: Path,
    url: str,
    status_code: int,
    body_bytes: bytes,
    headers: dict,
    elapsed_ms: int = 0,
    filename_prefix: Optional[str] = None,
) -> dict:
    """
    WP2: Store raw response body (gzip), sha256, URL, HTTP status, fetch time,
    and minimal safe headers under data/raw_snapshots/<source>/<run_id>/.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    sha256 = hashlib.sha256(body_bytes).hexdigest()
    gz_name = f"{filename_prefix}_{sha256[:12]}.gz" if filename_prefix else f"{sha256[:16]}.html.gz"
    gzip_path = run_dir / gz_name

    with gzip.open(gzip_path, "wb") as f:
        f.write(body_bytes)

    safe_headers = {
        str(k).lower(): str(v)
        for k, v in (headers or {}).items()
        if str(k).lower() in SAFE_HEADER_KEYS
    }

    meta = {
        "url": url,
        "status_code": int(status_code),
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


def load_raw_snapshot_bytes(snapshot_meta: dict, run_dir: Path) -> bytes:
    """WP2: Read gzipped snapshot body and verify sha256."""
    gzip_path = Path(run_dir) / snapshot_meta["gzip_file"]
    with gzip.open(gzip_path, "rb") as f:
        body = f.read()
    actual_sha = hashlib.sha256(body).hexdigest()
    if actual_sha != snapshot_meta["sha256"]:
        raise ValueError(
            f"Snapshot SHA256 mismatch for {snapshot_meta.get('url')}: "
            f"expected {snapshot_meta['sha256']}, got {actual_sha}"
        )
    return body


class BaseExtractor(ABC):
    """
    Abstract base class for all source extractors.

    Subclasses must implement:
        - source_config() → Source
        - extract_products() → list[Product]

    May optionally implement:
        - extract_product_details(product) → ProductObservation
        - extract_locations() → list[Location]
        - extract_availability() → list[ProductObservation]
    """

    def __init__(
        self,
        data_dir: str = "./data",
        headless: bool = True,
        max_pages: int = 5,
        max_products: int = 20,
        run_id: Optional[str] = None,
        replay_run_id: Optional[str] = None,
        department: Optional[str] = None,
    ):
        from normalization.taxonomy import resolve_department_alias
        self.data_dir = Path(data_dir)
        self.headless = headless
        self.max_pages = max_pages
        self.max_products = max_products
        self.department = resolve_department_alias(department) if department else None
        self.run_id = run_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + str(uuid4())[:8]
        )
        self.replay_run_id = replay_run_id
        self._browser = None
        self._context = None
        self._page = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._request_count = 0
        self._start_time: Optional[float] = None
        self._errors: list[str] = []
        self._robots_txt: Optional[str] = None
        self._robots_sha256: Optional[str] = None
        self._manifest: Optional[RunManifest] = None
        self._replay_snapshots: dict[str, dict] = {}
        self._replay_ordered: list[dict] = []
        self._replay_cursor: int = 0
        self._consecutive_failures: int = 0
        self._circuit_breaker_threshold: int = 3
        self._circuit_breaker_tripped: bool = False

    def record_request_success(self) -> None:
        """Reset consecutive failure counter after a healthy page/response."""
        self._consecutive_failures = 0

    def record_request_failure(self, reason: str) -> bool:
        """Increment consecutive failure counter; return True when circuit breaker trips."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._circuit_breaker_threshold:
            self._circuit_breaker_tripped = True
            msg = (
                f"Circuit breaker tripped after {self._consecutive_failures} consecutive "
                f"failures ({reason}) — aborting store scrape fail-fast."
            )
            self._errors.append(msg)
            logger.error(
                "circuit_breaker.tripped",
                consecutive_failures=self._consecutive_failures,
                reason=reason,
                run_id=self.run_id,
            )
            return True
        return False

    # ─── Abstract interface ───────────────────────────────────────

    @abstractmethod
    def source_config(self) -> Source:
        """Return the source configuration."""
        ...

    @abstractmethod
    async def extract_products(self) -> list[Product]:
        """Extract product catalog from the source."""
        ...

    async def extract_product_details(
        self, product: Product
    ) -> Optional[ProductObservation]:
        """Extract detailed price/availability for a single product."""
        return None

    async def extract_locations(self) -> list[Location]:
        """Extract store/branch/delivery-zone locations."""
        return []

    async def extract_availability(self) -> list[ProductObservation]:
        """Extract availability observations across products."""
        return []

    @property
    def snapshot_run_dir(self) -> Path:
        source = self.source_config()
        return self.data_dir / "raw_snapshots" / source.source_id / self.run_id

    # ─── Lifecycle ────────────────────────────────────────────────

    async def run(self) -> ExtractionResult:
        """
        Full extraction lifecycle:
        1. Verify compliance (and re-check robots.txt on live runs)
        2. Initialize browser/client (or load replay snapshots)
        3. Extract products
        4. Extract locations
        5. Extract observations
        6. Validate & record RunManifest + ObservationHistory
        7. Save raw data
        8. Cleanup
        """
        source = self.source_config()
        self._start_time = time.monotonic()

        is_fixture = bool(getattr(self, "_fixture_path", None))
        mode = "replay" if self.replay_run_id else ("offline_fixture" if is_fixture else "live")

        self._manifest = RunManifest(
            source_id=source.source_id,
            run_id=self.run_id,
            mode=mode,
            data_dir=str(self.data_dir),
        )
        self._manifest.compliance_status = source.compliance_status.value
        self._manifest.evidence_reference = {
            "evidence_url": source.evidence_url or f"https://{source.domain}/robots.txt",
            "captured_on": source.evidence_captured_on or "2026-09-28",
            "summary": source.evidence_summary or source.notes,
        }

        log = logger.bind(source=source.source_name, source_id=source.source_id, run_id=self.run_id)
        log.info("extraction.start", method=source.extraction_method.value, mode=mode)

        # 1. Compliance gate
        try:
            self._verify_compliance(source)
        except ComplianceError as ce:
            self._manifest.blocked_reason = str(ce)
            self._manifest.finish()
            self._manifest.save()
            raise

        result = ExtractionResult(source_id=source.source_id, run_id=self.run_id, mode=mode)

        try:
            # 2. Initialize client or replay store
            if self.replay_run_id:
                self._init_replay_store(source.source_id, self.replay_run_id)
            elif not is_fixture:
                await self._init_client(source)
                await self._recheck_robots_txt(source)

            # 3. Extract products
            log.info("extraction.products.start")
            products = await self.extract_products()
            result.products = products
            log.info("extraction.products.done", count=len(products))

            # 4. Extract locations
            log.info("extraction.locations.start")
            locations = await self.extract_locations()
            result.locations = locations
            log.info("extraction.locations.done", count=len(locations))

            # 5. Extract observations
            log.info("extraction.observations.start")
            obs_by_key: dict[str, ProductObservation] = {}
            for product in products[: self.max_products]:
                try:
                    obs = await self.extract_product_details(product)
                    if obs:
                        okey = str(obs.source_product_id or obs.product_id or product.source_product_id)
                        obs_by_key[okey] = obs
                except Exception as e:
                    err_msg = f"Failed details for {product.source_product_id}: {e}"
                    self._errors.append(err_msg)
                    log.warning("extraction.product_detail.error", error=str(e))

            bulk_obs = await self.extract_availability()
            for b_obs in bulk_obs:
                okey = str(b_obs.source_product_id or b_obs.product_id)
                if okey not in obs_by_key:
                    obs_by_key[okey] = b_obs

            observations = list(obs_by_key.values())
            result.observations = observations
            log.info("extraction.observations.done", count=len(observations))

        except ComplianceError as ce:
            self._manifest.blocked_reason = str(ce)
            self._errors.append(str(ce))
            log.error("extraction.blocked", error=str(ce))
            raise
        except Exception as e:
            err_msg = f"Extraction failed: {e}"
            self._errors.append(err_msg)
            log.error("extraction.failed", error=str(e))

        finally:
            await self._cleanup()

        # Stamp run_id on all records
        for p in result.products:
            p.run_id = self.run_id
        for o in result.observations:
            o.run_id = self.run_id
            if not o.source_id:
                o.source_id = source.source_id
        for loc in result.locations:
            loc.run_id = self.run_id

        result.errors = self._errors
        result.pages_visited = self._request_count
        result.duration_seconds = time.monotonic() - self._start_time

        # 6. Validate and update RunManifest & ObservationHistory
        validator = DataValidator()
        val_report = validator.validate(result, run_id=self.run_id)
        self._manifest.populate_from_validation(result, val_report)
        self._manifest.finish()

        if result.observations:
            hist = ObservationHistory(data_dir=str(self.data_dir))
            hist.append_result(result, run_id=self.run_id)

        # 7. Save raw data + manifest
        raw_dir = self._save_raw(source, result)
        self._manifest.save(extra_dir=raw_dir)

        log.info(
            "extraction.complete",
            status=self._manifest.status,
            products=len(result.products),
            locations=len(result.locations),
            observations=len(result.observations),
            quality_issues=len(result.quality_issues),
            errors=len(result.errors),
            pages=result.pages_visited,
            duration=f"{result.duration_seconds:.1f}s",
        )

        return result

    # ─── Compliance & Robots Re-check (WP9) ───────────────────────

    def _verify_compliance(self, source: Source) -> None:
        """Abort if source is not cleared for extraction."""
        if source.compliance_status == ComplianceStatus.DO_NOT_AUTOMATE:
            raise ComplianceError(
                f"Automation disabled for {source.source_name} "
                f"(compliance status: C — DO NOT AUTOMATE)"
            )
        if source.compliance_status == ComplianceStatus.UNKNOWN:
            raise ComplianceError(
                f"Compliance unknown for {source.source_name} "
                f"(status: D — requires human review)"
            )
        if not source.enabled:
            raise ComplianceError(
                f"Extraction disabled for {source.source_name}"
            )

        logger.info(
            "compliance.passed",
            source=source.source_name,
            status=source.compliance_status.value,
            run_id=self.run_id,
        )

    async def _recheck_robots_txt(self, source: Source) -> None:
        """
        WP2 + WP9: On each live run, re-fetch robots.txt, store body (gzip) + sha256
        under data/raw_snapshots/<source>/<run_id>/, and enforce disallow rules.
        """
        robots_url = f"https://{source.domain}/robots.txt"
        t0 = time.monotonic()
        try:
            resp = await self._http_client.get(robots_url, timeout=10.0)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if resp.status_code == 200 and resp.content:
                self._robots_txt = resp.text
                self._robots_sha256 = hashlib.sha256(resp.content).hexdigest()
                if self._manifest:
                    self._manifest.robots_sha256 = self._robots_sha256
                save_raw_snapshot_bytes(
                    self.snapshot_run_dir,
                    robots_url,
                    resp.status_code,
                    resp.content,
                    dict(resp.headers),
                    elapsed_ms=elapsed_ms,
                    filename_prefix="robots",
                )
                logger.info(
                    "compliance.robots_rechecked",
                    source=source.source_id,
                    run_id=self.run_id,
                    robots_sha256=self._robots_sha256[:16],
                )
        except Exception as e:
            logger.warning(
                "compliance.robots_recheck_failed",
                source=source.source_id,
                run_id=self.run_id,
                error=str(e),
            )

    def _init_replay_store(self, source_id: str, replay_run_id: str) -> None:
        """WP2: Load snapshot index for offline replay with zero network calls."""
        replay_dir = self.data_dir / "raw_snapshots" / source_id / replay_run_id
        index_path = replay_dir / "snapshots_index.json"
        manifest_path = replay_dir / "run_manifest.json"

        snapshots = []
        if index_path.exists():
            snapshots = json.loads(index_path.read_text(encoding="utf-8"))
        elif manifest_path.exists():
            mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
            snapshots = mdata.get("snapshots", [])

        if not snapshots:
            raise ExtractionError(
                f"No snapshots found to replay in {replay_dir}"
            )

        self._replay_dir = replay_dir
        self._replay_snapshots = {}
        self._replay_ordered = []
        for s in snapshots:
            url = s.get("url", "")
            if url.endswith("/robots.txt"):
                if self._manifest:
                    self._manifest.robots_sha256 = s.get("sha256")
                continue
            self._replay_snapshots[url] = s
            self._replay_ordered.append(s)
        self._replay_cursor = 0

    # ─── Browser management ───────────────────────────────────────

    async def _init_browser(self):
        """Launch Playwright Chromium browser."""
        from playwright.async_api import async_playwright

        proxy_url = os.getenv("PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or None
        proxy_cfg = {"server": proxy_url} if proxy_url else None

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            proxy=proxy_cfg,
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(DESKTOP_USER_AGENTS),
            locale="en-US",
            extra_http_headers={
                "Accept-Language": random.choice(ACCEPT_LANGUAGE_HEADERS),
            },
        )
        self._page = await self._context.new_page()
        logger.info("browser.launched", headless=self.headless, run_id=self.run_id, proxy=bool(proxy_url))

    async def _init_http_client(self):
        """Initialize httpx async client for non-browser requests with optional proxy."""
        proxy = os.getenv("PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or None
        self._http_client = httpx.AsyncClient(
            http2=True,
            proxy=proxy,
            timeout=15.0,
            follow_redirects=True,
            headers=get_rotated_headers(),
        )

    async def _init_client(self, source: Source):
        """Initialize the appropriate client based on extraction method."""
        if source.extraction_method == ExtractionMethod.PLAYWRIGHT:
            await self._init_browser()
        else:
            await self._init_http_client()

    async def _cleanup(self):
        """Clean up browser and HTTP resources."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
            self._playwright = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        logger.info("resources.cleaned_up", run_id=self.run_id)

    # ─── Rate limiting ────────────────────────────────────────────

    async def _rate_limit_delay(self, source: Optional[Source] = None):
        """Apply polite human-like randomized rate-limiting delay between requests."""
        if self.replay_run_id:
            self._request_count += 1
            return

        if source is None:
            source = self.source_config()

        min_d = max(1.5, min(source.min_delay_seconds, 2.5))
        max_d = max(3.5, min(source.max_delay_seconds, 4.5))
        delay = random.uniform(min_d, max_d)
        await asyncio.sleep(delay)
        self._request_count += 1

    async def navigate(self, url: str, wait_selector: Optional[str] = None):
        """Navigate browser to URL with rate limiting and optional wait."""
        source = self.source_config()
        await self._rate_limit_delay(source)

        log = logger.bind(url=url, run_id=self.run_id)
        log.debug("navigate.start")

        try:
            await self._page.set_extra_http_headers(get_rotated_headers(url))
            response = await self._page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(source.min_delay_seconds * 1000 + 30000),
            )

            if wait_selector:
                await self._page.wait_for_selector(
                    wait_selector, timeout=15000
                )

            log.debug(
                "navigate.done",
                status=response.status if response else None,
            )
            return response
        except Exception as e:
            log.warning("navigate.error", error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1.5, min=2, max=10),
        retry=retry_if_exception(_is_retryable_fetch_error),
        reraise=True,
    )
    async def fetch(self, url: str) -> httpx.Response:
        """
        Fetch URL with httpx (or replay from stored snapshot if replay_run_id is set).
        Enforces live robots.txt disallow rules (WP9), rotates User-Agent/Accept-Language/Referer
        headers on every request, applies smart exponential backoff (10s, 20s, 40s, 80s + jitter)
        on HTTP 429/503, and saves raw gzip snapshot (WP2).
        """
        # WP9: Check live robots.txt disallow rules before fetching
        if self._robots_txt:
            parsed_path = urlparse(url).path or "/"
            checker = ComplianceChecker()
            if not checker.is_path_allowed(self._robots_txt, parsed_path):
                msg = f"BLOCKED: path '{parsed_path}' is disallowed by live robots.txt for {url}"
                if self._manifest:
                    self._manifest.blocked_reason = msg
                raise ComplianceError(msg)

        # WP2: Replay mode — zero network calls
        if self.replay_run_id:
            snap = self._replay_snapshots.get(url)
            if snap is None and self._replay_cursor < len(self._replay_ordered):
                snap = self._replay_ordered[self._replay_cursor]
                self._replay_cursor += 1
            if snap is None:
                raise ExtractionError(f"URL not found in replay snapshot store: {url}")

            body_bytes = load_raw_snapshot_bytes(snap, self._replay_dir)
            self._request_count += 1
            if self._manifest:
                self._manifest.record_http_status(snap["status_code"])
                self._manifest.pages_parsed += 1
            return httpx.Response(
                status_code=snap["status_code"],
                content=body_bytes,
                headers=snap.get("headers", {}),
                request=httpx.Request("GET", url),
            )

        if self._http_client is None:
            await self._init_http_client()

        await self._rate_limit_delay()

        log = logger.bind(url=url, run_id=self.run_id)
        log.debug("fetch.start")

        backoff_schedule = [10.0, 20.0, 40.0, 80.0]
        response = None
        elapsed_ms = 0

        for attempt in range(len(backoff_schedule) + 1):
            req_headers = get_rotated_headers(url)
            t0 = time.monotonic()
            response = await self._http_client.get(url, headers=req_headers)
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            if self._manifest:
                self._manifest.record_http_status(response.status_code)
                self._manifest.pages_parsed += 1

            save_raw_snapshot_bytes(
                self.snapshot_run_dir,
                url,
                response.status_code,
                response.content,
                dict(response.headers),
                elapsed_ms=elapsed_ms,
            )

            if response.status_code in (429, 503) and attempt < len(backoff_schedule):
                retry_after = response.headers.get("retry-after")
                parsed_delay = self._parse_retry_after(retry_after) if retry_after else None
                base_wait = backoff_schedule[attempt]
                jitter = random.uniform(1.5, 4.5)
                effective_delay = max(parsed_delay or 0.0, base_wait) + jitter
                log.warning(
                    "fetch.rate_limited_backoff",
                    status_code=response.status_code,
                    attempt=attempt + 1,
                    retry_after=retry_after,
                    effective_delay=round(effective_delay, 2),
                )
                await asyncio.sleep(effective_delay)
                continue
            break

        if response.status_code >= 400:
            log.warning(
                "fetch.http_error",
                status_code=response.status_code,
                server=response.headers.get("server"),
                cf_ray=response.headers.get("cf-ray"),
                elapsed_ms=elapsed_ms,
            )

        response.raise_for_status()

        log.debug("fetch.done", status=response.status_code, elapsed_ms=elapsed_ms)
        return response

    @staticmethod
    def _parse_retry_after(header_val: Optional[str]) -> Optional[float]:
        """Parse HTTP Retry-After header (either seconds integer or RFC 2822 date)."""
        if not header_val:
            return None
        s = header_val.strip()
        try:
            return max(0.0, float(s))
        except ValueError:
            pass
        try:
            from email.utils import parsedate_to_datetime
            target_dt = parsedate_to_datetime(s)
            now_dt = datetime.now(timezone.utc)
            delta = (target_dt - now_dt).total_seconds()
            return max(0.0, delta)
        except Exception:
            return None

    # ─── Data extraction helpers ──────────────────────────────────

    async def get_page_html(self) -> str:
        """Get current page HTML content."""
        return await self._page.content()

    async def get_json_ld(self) -> list[dict]:
        """Extract JSON-LD structured data from the current page."""
        scripts = await self._page.query_selector_all(
            'script[type="application/ld+json"]'
        )
        results = []
        for script in scripts:
            try:
                text = await script.inner_text()
                data = json.loads(text)
                results.append(data)
            except (json.JSONDecodeError, Exception):
                continue
        return results

    async def screenshot(self, name: str, source_id: str):
        """Save a screenshot for debugging."""
        path = self.data_dir / "research" / source_id / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._page.screenshot(path=str(path), full_page=False)
        logger.debug("screenshot.saved", path=str(path), run_id=self.run_id)

    # ─── Raw data persistence ────────────────────────────────────

    def _save_raw(self, source: Source, result: ExtractionResult) -> Path:
        """Save raw extraction results to date-partitioned directory."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        raw_dir = self.data_dir / "raw" / source.source_id / today
        raw_dir.mkdir(parents=True, exist_ok=True)

        # Products (merge by source_product_id so multi-department runs on the same day accumulate)
        products_file = raw_dir / "products.json"
        existing_prods: list[dict] = []
        if products_file.exists():
            try:
                existing_prods = json.loads(products_file.read_text(encoding="utf-8"))
            except Exception:
                existing_prods = []
        prod_by_spid: dict[str, dict] = {
            str(ep.get("source_product_id") or ep.get("product_id")): ep
            for ep in existing_prods
        }
        for p in result.products:
            pd = p.model_dump(mode="json")
            prod_by_spid[str(pd.get("source_product_id") or pd.get("product_id"))] = pd
        with open(products_file, "w", encoding="utf-8") as f:
            json.dump(list(prod_by_spid.values()), f, ensure_ascii=False, indent=2)

        # Locations (merge by location_id / branch_name)
        if result.locations:
            locations_file = raw_dir / "locations.json"
            existing_locs: list[dict] = []
            if locations_file.exists():
                try:
                    existing_locs = json.loads(locations_file.read_text(encoding="utf-8"))
                except Exception:
                    existing_locs = []
            loc_by_key: dict[str, dict] = {
                str(el.get("branch_name") or el.get("location_name") or el.get("location_id")): el
                for el in existing_locs
            }
            for loc in result.locations:
                ld = loc.model_dump(mode="json")
                loc_by_key[str(ld.get("branch_name") or ld.get("location_name") or ld.get("location_id"))] = ld
            with open(locations_file, "w", encoding="utf-8") as f:
                json.dump(list(loc_by_key.values()), f, ensure_ascii=False, indent=2)

        # Observations (merge by (source_product_id, row_hash))
        if result.observations:
            obs_file = raw_dir / "observations.json"
            existing_obs: list[dict] = []
            if obs_file.exists():
                try:
                    existing_obs = json.loads(obs_file.read_text(encoding="utf-8"))
                except Exception:
                    existing_obs = []
            obs_by_key: dict[tuple, dict] = {
                (
                    str(eo.get("source_product_id") or eo.get("product_id")),
                    str(eo.get("row_hash") or eo.get("observation_id")),
                ): eo
                for eo in existing_obs
            }
            for obs in result.observations:
                od = obs.model_dump(mode="json")
                obs_by_key[
                    (
                        str(od.get("source_product_id") or od.get("product_id")),
                        str(od.get("row_hash") or od.get("observation_id")),
                    )
                ] = od
            with open(obs_file, "w", encoding="utf-8") as f:
                json.dump(list(obs_by_key.values()), f, ensure_ascii=False, indent=2)

        # Quality issues
        qi_file = raw_dir / "quality_issues.json"
        DataValidator.write_quality_issues(result.quality_issues, qi_file)

        # Metadata
        meta_file = raw_dir / "extraction_meta.json"
        meta = {
            "run_id": self.run_id,
            "mode": result.mode,
            "source_id": source.source_id,
            "source_name": source.source_name,
            "extracted_at": result.extracted_at.isoformat(),
            "products_count": len(result.products),
            "locations_count": len(result.locations),
            "observations_count": len(result.observations),
            "quality_issues_count": len(result.quality_issues),
            "quality_score": self._manifest.quality_score if self._manifest else None,
            "status": self._manifest.status if self._manifest else None,
            "errors_count": len(result.errors),
            "pages_visited": result.pages_visited,
            "duration_seconds": result.duration_seconds,
            "errors": result.errors,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info("raw_data.saved", directory=str(raw_dir), run_id=self.run_id)
        return raw_dir

    # ─── Report ───────────────────────────────────────────────────

    def generate_report(self, result: ExtractionResult) -> str:
        """Generate a human-readable extraction report."""
        source = self.source_config()
        lines = [
            f"{'='*60}",
            f"Source: {source.source_name} (run_id={result.run_id or self.run_id})",
            f"Domain: {source.domain} | Mode: {result.mode}",
            f"{'='*60}",
            f"",
            f"Compliance: {source.compliance_status.value}",
            f"Extraction method: {source.extraction_method.value}",
            f"",
            f"Pages visited: {result.pages_visited}",
            f"Products extracted: {len(result.products):,}",
            f"Locations extracted: {len(result.locations):,}",
            f"Observations: {len(result.observations):,}",
            f"Quality issues: {len(result.quality_issues):,}",
            f"Duration: {result.duration_seconds:.1f}s",
            f"",
            f"Fields extracted:",
        ]

        field_checks = {
            "product_name": any(p.product_name for p in result.products),
            "SKU": any(p.sku for p in result.products),
            "GTIN": any(p.gtin for p in result.products),
            "brand": any(p.brand for p in result.products),
            "category": any(p.category for p in result.products),
            "price": any(o.price for o in result.observations),
            "old_price": any(o.old_price for o in result.observations),
            "availability": any(
                o.availability_status != AvailabilityStatus.UNKNOWN
                for o in result.observations
            ),
            "rating": any(o.rating for o in result.observations),
            "review_count": any(o.review_count for o in result.observations),
            "image_url": any(p.image_url for p in result.products),
            "branch": any(loc.branch_name for loc in result.locations),
            "address": any(loc.address for loc in result.locations),
            "city": any(loc.city for loc in result.locations),
            "governorate": any(loc.governorate for loc in result.locations),
            "coordinates": any(
                loc.latitude and loc.longitude for loc in result.locations
            ),
            "delivery_zone": any(loc.delivery_zone for loc in result.locations),
        }

        for field, present in field_checks.items():
            symbol = "✓" if present else "✗"
            lines.append(f"  {field:20s} {symbol}")

        lines.append("")
        lines.append(f"Errors: {len(result.errors)}")
        for err in result.errors[:10]:
            lines.append(f"  - {err}")

        return "\n".join(lines)
