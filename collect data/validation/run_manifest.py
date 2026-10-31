"""
Run Manifest — WP3

Every run produces a run_manifest.json with:
- run_id, source_id, mode, started_at, finished_at, duration_seconds
- compliance_status and evidence_reference
- robots_sha256
- fetch_counts and http_status_counts
- parsed / accepted / rejected counts (strictly reconciled: parsed == accepted + rejected)
- per-field coverage and null rates
- quality_issues_count, issue_counts_by_code, issue_counts_by_severity
- status: SUCCESS | PARTIAL | FAILED | BLOCKED
- drift detection vs previous run

Rule: A run with zero products, or a parse-failure ratio above threshold,
must be FAILED or PARTIAL with a drift warning, never SUCCESS.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class RunManifest:
    """
    Records reconciled metadata, quality coverage, status, and drift for a single extraction run.
    """

    def __init__(
        self,
        source_id: str,
        run_id: Optional[str] = None,
        mode: str = "live",
        data_dir: str = "./data",
        parse_failure_threshold: float = 0.25,
    ):
        self.source_id = source_id
        self.run_id = run_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + str(uuid4())[:8]
        )
        self.mode = mode
        self.data_dir = Path(data_dir)
        self.parse_failure_threshold = parse_failure_threshold

        self._started_at = datetime.now(timezone.utc)
        self._finished_at: Optional[datetime] = None

        # Compliance & robots metadata
        self.compliance_status: str = "D"
        self.evidence_reference: dict = {}
        self.robots_sha256: Optional[str] = None
        self.blocked_reason: Optional[str] = None

        # Fetch & HTTP status counts
        self.pages_fetched: int = 0
        self.pages_parsed: int = 0
        self.http_status_counts: dict[str, int] = {}

        # Reconciled entity counts (parsed == accepted + rejected)
        self.products_parsed: int = 0
        self.products_accepted: int = 0
        self.products_rejected: int = 0

        self.observations_parsed: int = 0
        self.observations_accepted: int = 0
        self.observations_rejected: int = 0

        self.locations_parsed: int = 0
        self.locations_accepted: int = 0
        self.locations_rejected: int = 0

        # Quality & coverage
        self.quality_score: float = 0.0
        self.quality_issues_count: int = 0
        self.issue_counts_by_code: dict[str, int] = {}
        self.issue_counts_by_severity: dict[str, int] = {}
        self.field_coverage: dict[str, float] = {}
        self.null_rates: dict[str, float] = {}

        # Status & diagnostics
        self.status: str = "PENDING"  # SUCCESS | PARTIAL | FAILED | BLOCKED
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.drift: Optional[dict] = None

        logger.info(
            "manifest.init",
            source=source_id,
            run_id=self.run_id,
            mode=self.mode,
        )

    def record_http_status(self, status_code: int) -> None:
        key = str(status_code)
        self.http_status_counts[key] = self.http_status_counts.get(key, 0) + 1
        self.pages_fetched += 1

    def reconcile_counts(self) -> None:
        """
        Ensure parsed == accepted + rejected for products, observations, and locations.
        If only accepted was set, set parsed = accepted + rejected.
        If parsed and accepted were set, compute rejected = max(0, parsed - accepted).
        """
        if self.products_parsed == 0 and (self.products_accepted > 0 or self.products_rejected > 0):
            self.products_parsed = self.products_accepted + self.products_rejected
        elif self.products_parsed >= self.products_accepted and self.products_rejected == 0:
            self.products_rejected = self.products_parsed - self.products_accepted
        else:
            self.products_parsed = self.products_accepted + self.products_rejected

        if self.observations_parsed == 0 and (self.observations_accepted > 0 or self.observations_rejected > 0):
            self.observations_parsed = self.observations_accepted + self.observations_rejected
        elif self.observations_parsed >= self.observations_accepted and self.observations_rejected == 0:
            self.observations_rejected = self.observations_parsed - self.observations_accepted
        else:
            self.observations_parsed = self.observations_accepted + self.observations_rejected

        if self.locations_parsed == 0 and (self.locations_accepted > 0 or self.locations_rejected > 0):
            self.locations_parsed = self.locations_accepted + self.locations_rejected
        elif self.locations_parsed >= self.locations_accepted and self.locations_rejected == 0:
            self.locations_rejected = self.locations_parsed - self.locations_accepted
        else:
            self.locations_parsed = self.locations_accepted + self.locations_rejected

    def compute_status(self) -> str:
        """
        Compute honest run status:
        - BLOCKED if blocked_reason is set
        - FAILED if products_accepted == 0 (zero products never succeeds!)
        - FAILED if parse failure ratio == 1.0
        - PARTIAL if parse failure ratio > threshold or errors present
        - SUCCESS otherwise
        """
        self.reconcile_counts()

        if self.blocked_reason:
            self.status = "BLOCKED"
            return self.status

        if self.products_accepted == 0:
            self.status = "FAILED"
            msg = "ZERO_PRODUCTS_EXTRACTED: run accepted 0 products"
            if msg not in self.warnings:
                self.warnings.append(msg)
            return self.status

        failure_ratio = (
            self.products_rejected / self.products_parsed
            if self.products_parsed > 0
            else 0.0
        )

        if failure_ratio >= 1.0:
            self.status = "FAILED"
            msg = f"PARSE_FAILURE_RATIO_100PCT: {self.products_rejected}/{self.products_parsed} rejected"
            if msg not in self.warnings:
                self.warnings.append(msg)
        elif failure_ratio > self.parse_failure_threshold:
            self.status = "PARTIAL"
            msg = (
                f"HIGH_PARSE_FAILURE_RATIO: {failure_ratio:.1%} "
                f"({self.products_rejected}/{self.products_parsed}) exceeds threshold "
                f"{self.parse_failure_threshold:.1%}"
            )
            if msg not in self.warnings:
                self.warnings.append(msg)
        elif self.errors:
            self.status = "PARTIAL"
            msg = f"RUN_HAD_ERRORS: {len(self.errors)} error(s) recorded during extraction"
            if msg not in self.warnings:
                self.warnings.append(msg)
        else:
            self.status = "SUCCESS"

        return self.status

    def finish(self) -> None:
        """Mark run as finished, reconcile counts, compute status, and detect drift."""
        self._finished_at = datetime.now(timezone.utc)
        self.reconcile_counts()
        self.compute_status()
        if self.drift is None:
            self.detect_drift()

    def detect_drift(self) -> dict:
        """
        Compare current run counts against the previous run manifest.
        Returns a drift summary dict and stores it in self.drift.
        """
        self.reconcile_counts()
        prev = self._load_previous_manifest()
        drift_warnings: list[str] = list(self.warnings)

        if prev is None:
            self.drift = {
                "is_first_run": True,
                "warnings": drift_warnings,
            }
            return self.drift

        def pct_change(current: int, previous: int) -> Optional[float]:
            if previous == 0:
                return None
            return round((current - previous) / previous * 100, 1)

        prev_prod = prev.get("products_accepted", 0)
        delta_prod = self.products_accepted - prev_prod
        pct_prod = pct_change(self.products_accepted, prev_prod)

        if self.products_accepted == 0:
            drift_warnings.append("DRIFT_ZERO_PRODUCTS: current run extracted 0 products")
        if pct_prod is not None:
            if abs(pct_prod) > 50:
                drift_warnings.append(
                    f"LARGE PRODUCT COUNT DRIFT: {pct_prod}% vs previous run ({prev_prod} -> {self.products_accepted})"
                )
            elif abs(pct_prod) > 20:
                drift_warnings.append(
                    f"Product count drift: {pct_prod}% vs previous run"
                )
        if delta_prod < 0:
            drift_warnings.append(
                f"Product count DECREASED by {abs(delta_prod)} vs previous run"
            )

        prev_robots = prev.get("robots_sha256")
        if prev_robots and self.robots_sha256 and prev_robots != self.robots_sha256:
            drift_warnings.append(
                f"ROBOTS_TXT_CHANGED: sha256 changed from {prev_robots[:12]} to {self.robots_sha256[:12]}"
            )

        drift = {
            "is_first_run": False,
            "previous_run_id": prev.get("run_id"),
            "products_accepted_delta": delta_prod,
            "products_accepted_pct": pct_prod,
            "observations_accepted_delta": self.observations_accepted - prev.get("observations_accepted", 0),
            "locations_accepted_delta": self.locations_accepted - prev.get("locations_accepted", 0),
            "quality_issues_delta": self.quality_issues_count - prev.get("quality_issues_count", 0),
            "robots_txt_changed": bool(prev_robots and self.robots_sha256 and prev_robots != self.robots_sha256),
            "warnings": drift_warnings,
        }

        for w in drift_warnings:
            if w not in self.warnings:
                self.warnings.append(w)
            logger.warning("manifest.drift_warning", warning=w, source=self.source_id, run_id=self.run_id)

        self.drift = drift
        return drift

    def populate_from_validation(self, result, validation_report: dict) -> None:
        """Populate manifest counts, coverage, null rates, and issues from ExtractionResult + DataValidator report."""
        if self.products_accepted == 0 and len(result.products) > 0:
            self.products_accepted = len(result.products)
        if self.observations_accepted == 0 and len(result.observations) > 0:
            self.observations_accepted = len(result.observations)
        if self.locations_accepted == 0 and len(result.locations) > 0:
            self.locations_accepted = len(result.locations)
        if self.pages_fetched == 0 and result.pages_visited > 0:
            self.pages_fetched = result.pages_visited
            self.pages_parsed = result.pages_visited

        self.errors = list(result.errors)
        self.quality_score = round(validation_report.get("overall_quality_score", 0.0), 2)
        self.quality_issues_count = len(result.quality_issues)

        by_code: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for qi in result.quality_issues:
            c = qi.issue_code.value if hasattr(qi.issue_code, "value") else str(qi.issue_code)
            s = qi.severity.value if hasattr(qi.severity, "value") else str(qi.severity)
            by_code[c] = by_code.get(c, 0) + 1
            by_sev[s] = by_sev.get(s, 0) + 1
        self.issue_counts_by_code = by_code
        self.issue_counts_by_severity = by_sev

        prod_rep = validation_report.get("products", {})
        obs_rep = validation_report.get("observations", {})
        self.field_coverage = prod_rep.get("field_coverage", {})
        self.null_rates = {
            **{f"product.{k}": v for k, v in prod_rep.get("null_rates", {}).items()},
            **{f"observation.{k}": v for k, v in obs_rep.get("null_rates", {}).items()},
        }
        self.reconcile_counts()
        self.compute_status()

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        self.reconcile_counts()
        if self.status == "PENDING":
            self.compute_status()

        duration = None
        if self._finished_at:
            duration = round((self._finished_at - self._started_at).total_seconds(), 3)

        failure_ratio = (
            round(self.products_rejected / self.products_parsed, 4)
            if self.products_parsed > 0
            else 0.0
        )

        return {
            "run_id": self.run_id,
            "source_id": self.source_id,
            "mode": self.mode,
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "started_at": self._started_at.isoformat(),
            "finished_at": self._finished_at.isoformat() if self._finished_at else None,
            "duration_seconds": duration,
            "compliance_status": self.compliance_status,
            "evidence_reference": self.evidence_reference,
            "robots_sha256": self.robots_sha256,
            "pages_fetched": self.pages_fetched,
            "pages_parsed": self.pages_parsed,
            "http_status_counts": self.http_status_counts,
            "products_parsed": self.products_parsed,
            "products_accepted": self.products_accepted,
            "products_rejected": self.products_rejected,
            "parse_failure_ratio": failure_ratio,
            "observations_parsed": self.observations_parsed,
            "observations_accepted": self.observations_accepted,
            "observations_rejected": self.observations_rejected,
            "locations_parsed": self.locations_parsed,
            "locations_accepted": self.locations_accepted,
            "locations_rejected": self.locations_rejected,
            "reconciled": (
                self.products_parsed == self.products_accepted + self.products_rejected
                and self.observations_parsed == self.observations_accepted + self.observations_rejected
                and self.locations_parsed == self.locations_accepted + self.locations_rejected
            ),
            "quality_score": self.quality_score,
            "quality_issues_count": self.quality_issues_count,
            "issue_counts_by_code": self.issue_counts_by_code,
            "issue_counts_by_severity": self.issue_counts_by_severity,
            "field_coverage": self.field_coverage,
            "null_rates": self.null_rates,
            "errors": self.errors,
            "warnings": self.warnings,
            "drift": self.drift,
        }

    def save(self, extra_dir: Optional[Path] = None) -> Path:
        """
        Save manifest to:
        1. data/raw_snapshots/<source>/<run_id>/run_manifest.json
        2. data/manifests/<source>/<run_id>.json
        3. Optional extra_dir/run_manifest.json
        """
        if self._finished_at is None:
            self.finish()
        elif self.drift is None:
            self.detect_drift()

        manifest_dict = self.to_dict()

        primary_dir = self.data_dir / "raw_snapshots" / self.source_id / self.run_id
        primary_dir.mkdir(parents=True, exist_ok=True)
        primary_path = primary_dir / "run_manifest.json"
        with open(primary_path, "w", encoding="utf-8") as f:
            json.dump(manifest_dict, f, ensure_ascii=False, indent=2)

        audit_dir = self.data_dir / "manifests" / self.source_id
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / f"{self.run_id}.json"
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(manifest_dict, f, ensure_ascii=False, indent=2)

        if extra_dir:
            extra_dir = Path(extra_dir)
            extra_dir.mkdir(parents=True, exist_ok=True)
            extra_path = extra_dir / "run_manifest.json"
            with open(extra_path, "w", encoding="utf-8") as f:
                json.dump(manifest_dict, f, ensure_ascii=False, indent=2)

        logger.info(
            "manifest.saved",
            source=self.source_id,
            run_id=self.run_id,
            status=self.status,
            path=str(primary_path),
        )
        return primary_path

    def _load_previous_manifest(self) -> Optional[dict]:
        """Load the most recent previous manifest for this source."""
        audit_dir = self.data_dir / "manifests" / self.source_id
        if not audit_dir.exists():
            return None

        manifests = sorted(audit_dir.glob("*.json"))
        previous = [m for m in manifests if self.run_id not in m.name]
        if not previous:
            return None

        with open(previous[-1], encoding="utf-8") as f:
            return json.load(f)


def load_manifest(source_id: str, run_id: str, data_dir: str = "./data") -> dict:
    """Load a manifest by run_id."""
    path = Path(data_dir) / "manifests" / source_id / f"{run_id}.json"
    if not path.exists():
        path = Path(data_dir) / "raw_snapshots" / source_id / run_id / "run_manifest.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_manifests(source_id: str, data_dir: str = "./data") -> list[dict]:
    """List all manifests for a source (newest first)."""
    audit_dir = Path(data_dir) / "manifests" / source_id
    if not audit_dir.exists():
        return []
    files = sorted(audit_dir.glob("*.json"), reverse=True)
    result = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            result.append(json.load(fh))
    return result
