"""
Compliance Gate — Runs before any extractor to verify legal clearance.

Checks:
1. Source compliance status from configuration
2. robots.txt directives (if applicable)
3. Configured policy conditions for B-status sources
4. Logs the compliance decision
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog

from normalization.schema import ComplianceStatus, Source

logger = structlog.get_logger()


class ComplianceViolation(Exception):
    """Raised when a source fails compliance checks."""
    pass


class ComplianceChecker:
    """
    Verifies that a source is cleared for automated extraction
    before any requests are made.
    """

    # Our bot identifier for robots.txt checking
    USER_AGENT = "EgyptEcommerceDataPlatform"

    def __init__(self):
        self._robots_cache: dict[str, RobotFileParser] = {}

    async def check(
        self,
        source: Source,
        target_paths: Optional[list[str]] = None,
    ) -> bool:
        """
        Run all compliance checks for a source.

        Args:
            source: Source configuration
            target_paths: Optional list of URL paths to check against robots.txt

        Returns:
            True if extraction is permitted

        Raises:
            ComplianceViolation: If extraction is not permitted
        """
        log = logger.bind(
            source=source.source_name,
            domain=source.domain,
        )

        # 1. Check compliance status
        if source.compliance_status == ComplianceStatus.DO_NOT_AUTOMATE:
            msg = (
                f"BLOCKED: {source.source_name} has compliance status C "
                f"(DO NOT AUTOMATE). Extraction is prohibited."
            )
            log.error("compliance.blocked", reason="status_C")
            raise ComplianceViolation(msg)

        if source.compliance_status == ComplianceStatus.UNKNOWN:
            msg = (
                f"BLOCKED: {source.source_name} has compliance status D "
                f"(UNKNOWN). Manual review required before extraction."
            )
            log.error("compliance.blocked", reason="status_D")
            raise ComplianceViolation(msg)

        # 2. Check if source is enabled
        if not source.enabled:
            msg = f"BLOCKED: {source.source_name} extraction is disabled."
            log.error("compliance.blocked", reason="disabled")
            raise ComplianceViolation(msg)

        # 3. For B-status sources, log the conditional status
        if source.compliance_status == ComplianceStatus.CONDITIONAL:
            log.warning(
                "compliance.conditional",
                message=(
                    f"{source.source_name} has conditional compliance (B). "
                    f"Proceeding with configured conditions. "
                    f"Notes: {source.notes}"
                ),
            )

        # 4. Check robots.txt if we have target paths
        if target_paths:
            robots_ok = await self._check_robots(source, target_paths)
            if not robots_ok:
                msg = (
                    f"BLOCKED: robots.txt disallows access to target paths "
                    f"for {source.source_name}"
                )
                log.error("compliance.blocked", reason="robots_txt")
                raise ComplianceViolation(msg)

        # 5. Log compliance decision
        log.info(
            "compliance.passed",
            status=source.compliance_status.value,
            rate_limit_rpm=source.rate_limit_rpm,
            method=source.extraction_method.value,
        )

        return True

    async def _check_robots(
        self,
        source: Source,
        paths: list[str],
    ) -> bool:
        """
        Check if the specified paths are allowed by robots.txt.

        Returns True if ALL paths are allowed.
        """
        domain = source.domain
        if domain in self._robots_cache:
            rp = self._robots_cache[domain]
        else:
            robots_url = f"https://{domain}/robots.txt"
            rp = RobotFileParser()

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(robots_url)
                    if response.status_code == 200:
                        rp.parse(response.text.splitlines())
                    else:
                        # No robots.txt found — does NOT imply permission
                        logger.info(
                            "robots.not_found",
                            url=robots_url,
                            status=response.status_code,
                        )
                        # We still proceed but log it
                        return True
            except Exception as e:
                logger.warning(
                    "robots.fetch_error",
                    url=robots_url,
                    error=str(e),
                )
                return True

            self._robots_cache[domain] = rp

        # Check each path
        for path in paths:
            full_url = f"https://{domain}{path}"
            if not rp.can_fetch(self.USER_AGENT, full_url):
                # Also check with generic user agent
                if not rp.can_fetch("*", full_url):
                    logger.warning(
                        "robots.disallowed",
                        path=path,
                        source=source.source_name,
                    )
                    return False

        return True

    async def fetch_robots_txt(self, domain: str) -> Optional[str]:
        """Fetch and return raw robots.txt content for a domain."""
        robots_url = f"https://{domain}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(robots_url)
                if response.status_code == 200:
                    return response.text
        except Exception:
            pass
        return None

    def parse_crawl_delay(self, robots_text: str) -> Optional[float]:
        """Extract Crawl-delay directive from robots.txt."""
        for line in robots_text.splitlines():
            match = re.match(r"Crawl-delay:\s*(\d+\.?\d*)", line, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None


    def is_path_allowed(self, robots_text: str, path: str, domain: str = "example.com") -> bool:
        """Check synchronously if a URL path is allowed by raw robots.txt text."""
        if not robots_text:
            return True
        rp = RobotFileParser()
        rp.parse(robots_text.splitlines())
        full_url = path if path.startswith("http") else f"https://{domain}{path}"
        return rp.can_fetch(self.USER_AGENT, full_url) and rp.can_fetch("*", full_url)
