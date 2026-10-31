"""
Data Validation — Validates extracted data against the canonical schema (WP8).

Performs:
- Schema validation (via Pydantic)
- Business rule validation
- Full WP8 data quality detection (persisted per run with run_id):
  * missing fields (brand, category, branch_name, address, GPS)
  * missing SKU
  * duplicate products (within run and across runs)
  * duplicate listings (same normalized title or URL under different IDs)
  * duplicate observations
  * multiple sellers / multiple variants
  * invalid/zero/negative prices
  * old_price < price (price inconsistency)
  * inconsistent discount
  * non-EGP currency
  * malformed/relative URLs
  * inconsistent categories
  * inconsistent location names
  * invalid/out-of-Egypt coordinates
  * unknown governorate
  * ambiguous availability
  * scope semantics violations & stock_quantity without evidence
  * changing source_product_id or URL for same SKU across runs
- Informational cross-source GTIN collision report
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from normalization.schema import (
    AvailabilityScope,
    AvailabilityStatus,
    Currency,
    DataQualityIssue,
    ExtractionResult,
    IssueCode,
    IssueSeverity,
    Location,
    LocationType,
    Product,
    ProductObservation,
)

logger = structlog.get_logger()

# Egypt bounding box
_EG_LAT_MIN, _EG_LAT_MAX = 22.0, 31.5
_EG_LON_MIN, _EG_LON_MAX = 25.0, 36.5

# Location types that represent delivery/service zones (not physical branches)
_ZONE_TYPES = {
    LocationType.DELIVERY_ZONE,
    LocationType.DELIVERY_AREA,
    LocationType.PRESENCE,
    LocationType.COVERAGE,
    LocationType.UNKNOWN,
}


class DataValidator:
    """Validates extraction results for data quality."""

    def validate(
        self,
        result: ExtractionResult,
        run_id: Optional[str] = None,
        previous_products: Optional[list[dict]] = None,
    ) -> dict:
        """
        Run all validation checks on an extraction result.

        Returns a validation report dict and populates result.quality_issues.
        """
        effective_run_id = run_id or result.run_id
        quality_issues: list[DataQualityIssue] = []

        prod_report = self._validate_products(
            result.products,
            result.source_id,
            quality_issues,
            run_id=effective_run_id,
            previous_products=previous_products,
        )
        obs_report = self._validate_observations(
            result.observations,
            result.source_id,
            quality_issues,
            run_id=effective_run_id,
        )
        loc_report = self._validate_locations(
            result.locations,
            result.source_id,
            quality_issues,
            run_id=effective_run_id,
        )

        # Stamp run_id on every issue
        if effective_run_id:
            for qi in quality_issues:
                if not qi.run_id:
                    qi.run_id = effective_run_id

        report = {
            "source_id": result.source_id,
            "run_id": effective_run_id,
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "products": prod_report,
            "observations": obs_report,
            "locations": loc_report,
            "overall_quality_score": 0.0,
            "quality_issues": [qi.model_dump(mode="json") for qi in quality_issues],
        }

        total_checks = (
            report["products"]["total_checks"]
            + report["observations"]["total_checks"]
            + report["locations"]["total_checks"]
        )
        passed_checks = (
            report["products"]["passed_checks"]
            + report["observations"]["passed_checks"]
            + report["locations"]["passed_checks"]
        )

        report["overall_quality_score"] = (
            (passed_checks / total_checks * 100) if total_checks > 0 else 0.0
        )
        result.quality_issues = quality_issues

        return report

    def _validate_products(
        self,
        products: list[Product],
        source_id: str = "",
        quality_issues: list[DataQualityIssue] | None = None,
        run_id: Optional[str] = None,
        previous_products: Optional[list[dict]] = None,
    ) -> dict:
        """Validate product records."""
        issues = []
        total_checks = 0
        passed = 0
        qi = quality_issues if quality_issues is not None else []

        brand_categories: dict[str, set[str]] = {}
        seen_titles: dict[str, str] = {}
        seen_urls: dict[str, str] = {}

        for product in products:
            total_checks += 6

            # 1. Name present
            if product.product_name and len(product.product_name) > 2:
                passed += 1
            else:
                issues.append(f"Product {product.source_product_id}: missing/short name")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.source_product_id or "unknown",
                    issue_code=IssueCode.MISSING_FIELD,
                    severity=IssueSeverity.HIGH,
                    message=f"Product {product.source_product_id}: missing or short product_name",
                    raw_value=product.product_name,
                ))

            # 2. URL valid (not malformed or relative)
            if product.product_url and (
                product.product_url.startswith("http://")
                or product.product_url.startswith("https://")
            ) and " " not in product.product_url.strip():
                passed += 1
            else:
                issues.append(f"Product {product.source_product_id}: invalid URL")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.source_product_id,
                    issue_code=IssueCode.INVALID_URL,
                    severity=IssueSeverity.HIGH,
                    message=f"Product URL is malformed or relative: {product.product_url}",
                    raw_value=product.product_url,
                ))

            # 3. Source product ID present
            if product.source_product_id:
                passed += 1
            else:
                issues.append("Product: missing source_product_id")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.product_id,
                    issue_code=IssueCode.MISSING_FIELD,
                    severity=IssueSeverity.HIGH,
                    message="Product missing source_product_id",
                ))

            # 4. Brand present (soft check)
            if product.brand:
                passed += 1
            else:
                issues.append(f"Product {product.source_product_id}: missing brand")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.source_product_id,
                    issue_code=IssueCode.MISSING_FIELD,
                    severity=IssueSeverity.LOW,
                    message=f"Product {product.source_product_id}: missing brand",
                    source_url=product.product_url,
                ))

            # 5. Category present (soft check)
            if product.category and product.category.strip():
                passed += 1
                if product.brand:
                    brand_categories.setdefault(product.brand.lower(), set()).add(
                        product.category.strip().lower()
                    )
            else:
                issues.append(f"Product {product.source_product_id}: missing category")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.source_product_id,
                    issue_code=IssueCode.MISSING_FIELD,
                    severity=IssueSeverity.LOW,
                    message=f"Product {product.source_product_id}: missing category",
                    source_url=product.product_url,
                ))

            # 6. GTIN present (counted in quality score)
            if product.gtin and str(product.gtin).strip():
                passed += 1
            else:
                issues.append(f"Product {product.source_product_id}: missing GTIN")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.source_product_id,
                    issue_code=IssueCode.MISSING_FIELD,
                    severity=IssueSeverity.LOW,
                    message=f"Product {product.source_product_id}: missing GTIN",
                    source_url=product.product_url,
                ))

            # Missing SKU (low severity)
            if not product.sku:
                issues.append(f"Product {product.source_product_id}: missing SKU")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.source_product_id,
                    issue_code=IssueCode.MISSING_SKU,
                    severity=IssueSeverity.LOW,
                    message=f"Product {product.source_product_id}: missing SKU",
                    source_url=product.product_url,
                ))

            # Multiple variants detection
            if product.variants and len(product.variants) > 1:
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=product.source_product_id,
                    issue_code=IssueCode.MULTIPLE_VARIANTS,
                    severity=IssueSeverity.INFO,
                    message=f"Product {product.source_product_id} has {len(product.variants)} variants",
                    raw_value=str(len(product.variants)),
                    source_url=product.product_url,
                ))

            # Duplicate listing detection (same normalized title or URL under different source_product_id)
            norm_title = re.sub(r"\s+", " ", (product.product_name or "").strip().lower())
            if norm_title:
                if norm_title in seen_titles and seen_titles[norm_title] != product.source_product_id:
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="product",
                        entity_id=product.source_product_id,
                        issue_code=IssueCode.DUPLICATE_LISTING,
                        severity=IssueSeverity.LOW,
                        message=(
                            f"Duplicate product listing title '{product.product_name}' "
                            f"(also listed as {seen_titles[norm_title]})"
                        ),
                        raw_value=product.product_name,
                        source_url=product.product_url,
                    ))
                else:
                    seen_titles[norm_title] = product.source_product_id

            if product.product_url:
                if product.product_url in seen_urls and seen_urls[product.product_url] != product.source_product_id:
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="product",
                        entity_id=product.source_product_id,
                        issue_code=IssueCode.DUPLICATE_LISTING,
                        severity=IssueSeverity.MEDIUM,
                        message=(
                            f"Duplicate product_url '{product.product_url}' shared by "
                            f"{seen_urls[product.product_url]} and {product.source_product_id}"
                        ),
                        raw_value=product.product_url,
                        source_url=product.product_url,
                    ))
                else:
                    seen_urls[product.product_url] = product.source_product_id

        # Duplicate source_product_id check within run
        seen_ids: set = set()
        duplicates = 0
        for p in products:
            if p.source_product_id in seen_ids:
                duplicates += 1
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=p.source_product_id,
                    issue_code=IssueCode.DUPLICATE_PRODUCT,
                    severity=IssueSeverity.MEDIUM,
                    message=f"Duplicate source_product_id within run: {p.source_product_id}",
                    source_url=p.product_url,
                ))
            seen_ids.add(p.source_product_id)

        # Inconsistent category check (e.g. same brand assigned >3 distinct categories in one small batch)
        for brand_key, cats in brand_categories.items():
            if len(cats) > 3:
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="product",
                    entity_id=brand_key,
                    issue_code=IssueCode.INCONSISTENT_CATEGORY,
                    severity=IssueSeverity.INFO,
                    message=f"Brand '{brand_key}' spans {len(cats)} categories: {sorted(cats)}",
                    raw_value=",".join(sorted(cats)),
                ))

        # Cross-run SKU -> source_product_id / product_url change check
        if previous_products:
            prev_by_sku = {
                p.get("sku"): p
                for p in previous_products
                if p.get("sku")
            }
            for p in products:
                if p.sku and p.sku in prev_by_sku:
                    prev_p = prev_by_sku[p.sku]
                    prev_spid = prev_p.get("source_product_id")
                    prev_url = prev_p.get("product_url")
                    if prev_spid and prev_spid != p.source_product_id:
                        qi.append(DataQualityIssue(
                            run_id=run_id,
                            source_id=source_id,
                            entity_type="product",
                            entity_id=p.source_product_id,
                            issue_code=IssueCode.IDENTIFIER_CHANGE,
                            severity=IssueSeverity.HIGH,
                            message=(
                                f"SKU {p.sku} changed source_product_id from "
                                f"{prev_spid} to {p.source_product_id}"
                            ),
                            raw_value=f"{prev_spid} -> {p.source_product_id}",
                            source_url=p.product_url,
                        ))
                    elif prev_url and prev_url != p.product_url:
                        qi.append(DataQualityIssue(
                            run_id=run_id,
                            source_id=source_id,
                            entity_type="product",
                            entity_id=p.source_product_id,
                            issue_code=IssueCode.IDENTIFIER_CHANGE,
                            severity=IssueSeverity.MEDIUM,
                            message=(
                                f"SKU {p.sku} changed product_url from "
                                f"{prev_url} to {p.product_url}"
                            ),
                            raw_value=f"{prev_url} -> {p.product_url}",
                            source_url=p.product_url,
                        ))

        total_n = max(len(products), 1)
        return {
            "count": len(products),
            "total_checks": total_checks,
            "passed_checks": passed,
            "duplicates": duplicates,
            "issues": issues[:20],
            "field_coverage": {
                "product_name": sum(1 for p in products if p.product_name) / total_n,
                "sku": sum(1 for p in products if p.sku) / total_n,
                "gtin": sum(1 for p in products if p.gtin) / total_n,
                "brand": sum(1 for p in products if p.brand) / total_n,
                "category": sum(1 for p in products if p.category) / total_n,
                "image_url": sum(1 for p in products if p.image_url) / total_n,
                "specifications": sum(1 for p in products if p.specifications) / total_n,
            },
            "null_rates": {
                "product_name": round(sum(1 for p in products if not p.product_name) / total_n, 4),
                "sku": round(sum(1 for p in products if not p.sku) / total_n, 4),
                "gtin": round(sum(1 for p in products if not p.gtin) / total_n, 4),
                "brand": round(sum(1 for p in products if not p.brand) / total_n, 4),
                "category": round(sum(1 for p in products if not p.category) / total_n, 4),
                "image_url": round(sum(1 for p in products if not p.image_url) / total_n, 4),
            },
        }

    def _validate_observations(
        self,
        observations: list[ProductObservation],
        source_id: str = "",
        quality_issues: list[DataQualityIssue] | None = None,
        run_id: Optional[str] = None,
    ) -> dict:
        """Validate price/availability observation records."""
        issues = []
        total_checks = 0
        passed = 0
        qi = quality_issues if quality_issues is not None else []

        seen_obs_keys: set[tuple] = set()
        sellers_by_product: dict[str, set[str]] = {}

        for obs in observations:
            total_checks += 4
            entity_key = obs.source_product_id or obs.product_id

            # Duplicate observation check within run
            obs_dedup_key = (entity_key, obs.location_id or "global")
            if obs_dedup_key in seen_obs_keys:
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.DUPLICATE_OBSERVATION,
                    severity=IssueSeverity.MEDIUM,
                    message=f"Duplicate observation in run for product {entity_key}",
                    source_url=obs.source_url,
                ))
            seen_obs_keys.add(obs_dedup_key)

            # Track sellers per product
            if obs.seller_name:
                sellers_by_product.setdefault(entity_key, set()).add(obs.seller_name)
            if obs.sellers and len(obs.sellers) > 1:
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.MULTIPLE_SELLERS,
                    severity=IssueSeverity.INFO,
                    message=f"Product {entity_key} has multiple sellers: {obs.sellers}",
                    raw_value=",".join(obs.sellers),
                    source_url=obs.source_url,
                ))

            # Currency check (non-EGP currency)
            if obs.currency != Currency.EGP:
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.NON_EGP_CURRENCY,
                    severity=IssueSeverity.MEDIUM,
                    message=f"Non-EGP currency detected: {obs.currency.value}",
                    raw_value=obs.currency.value,
                    source_url=obs.source_url,
                ))

            # 1. Price reasonable
            if obs.price is not None and obs.price > 0:
                if obs.price <= 500_000:
                    passed += 1
                else:
                    issues.append(f"Observation: suspiciously high price {obs.price}")
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="observation",
                        entity_id=entity_key,
                        issue_code=IssueCode.INVALID_PRICE,
                        severity=IssueSeverity.MEDIUM,
                        message=f"Suspiciously high price: {obs.price}",
                        raw_value=str(obs.price),
                        source_url=obs.source_url,
                    ))
            elif obs.price == 0:
                issues.append("Observation: zero price")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.INVALID_PRICE,
                    severity=IssueSeverity.HIGH,
                    message="Price is zero",
                    raw_value="0",
                    source_url=obs.source_url,
                ))
            else:
                issues.append("Observation: missing price")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.INVALID_PRICE,
                    severity=IssueSeverity.MEDIUM,
                    message="Observation missing price",
                    source_url=obs.source_url,
                ))

            # 2. Old price > current price (if both exist)
            if obs.old_price is not None and obs.price is not None:
                if obs.old_price >= obs.price:
                    passed += 1
                else:
                    issues.append(
                        f"Observation: old_price ({obs.old_price}) < price ({obs.price})"
                    )
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="observation",
                        entity_id=entity_key,
                        issue_code=IssueCode.PRICE_INCONSISTENCY,
                        severity=IssueSeverity.MEDIUM,
                        message=f"old_price ({obs.old_price}) < price ({obs.price})",
                        raw_value=f"old={obs.old_price}, new={obs.price}",
                        source_url=obs.source_url,
                    ))
            else:
                passed += 1

            # 3. Availability not unknown
            if obs.availability_status.value != "unknown" and obs.availability_scope != AvailabilityScope.UNKNOWN:
                passed += 1
            else:
                issues.append("Observation: availability is unknown")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.AMBIGUOUS_AVAILABILITY,
                    severity=IssueSeverity.LOW,
                    message=(
                        f"Ambiguous availability: status={obs.availability_status.value}, "
                        f"scope={obs.availability_scope.value}"
                    ),
                    raw_value=obs.raw_availability_text,
                    source_url=obs.source_url,
                ))

            # 4. Seller name present (counted in quality score)
            if obs.seller_name and str(obs.seller_name).strip():
                passed += 1
            else:
                issues.append(f"Observation {entity_key}: missing seller_name")
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.MISSING_FIELD,
                    severity=IssueSeverity.LOW,
                    message=f"Observation {entity_key}: missing seller_name",
                    source_url=obs.source_url,
                ))

            # stock_quantity set without evidence -> SCOPE_SEMANTICS_VIOLATION & STOCK_QUANTITY_WITHOUT_EVIDENCE
            if obs.stock_quantity is not None and not obs.stock_quantity_evidence:
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.SCOPE_SEMANTICS_VIOLATION,
                    severity=IssueSeverity.HIGH,
                    message=(
                        f"stock_quantity={obs.stock_quantity} set without "
                        f"stock_quantity_evidence"
                    ),
                    raw_value=str(obs.stock_quantity),
                    source_url=obs.source_url,
                ))
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.STOCK_QUANTITY_WITHOUT_EVIDENCE,
                    severity=IssueSeverity.HIGH,
                    message=f"stock_quantity={obs.stock_quantity} lacks structured evidence",
                    raw_value=str(obs.stock_quantity),
                    source_url=obs.source_url,
                ))

            # Low-stock signal misparsed as stock_quantity
            if (
                obs.stock_quantity is not None
                and obs.raw_availability_text
                and any(k in obs.raw_availability_text.lower() for k in ("only", "left"))
                and not obs.stock_quantity_evidence
            ):
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=entity_key,
                    issue_code=IssueCode.LOW_STOCK_SIGNAL_MISPARSE,
                    severity=IssueSeverity.CRITICAL,
                    message=f"Low-stock text '{obs.raw_availability_text}' converted to stock_quantity",
                    raw_value=obs.raw_availability_text,
                    source_url=obs.source_url,
                ))

            # Discount consistency check on observation
            if (
                obs.price is not None
                and obs.old_price is not None
                and obs.old_price > 0
                and obs.discount is not None
            ):
                expected_discount = (obs.old_price - obs.price) / obs.old_price * 100
                if abs(obs.discount - expected_discount) >= 2.0:
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="observation",
                        entity_id=entity_key,
                        issue_code=IssueCode.INVALID_DISCOUNT,
                        severity=IssueSeverity.LOW,
                        message=(
                            f"Discount inconsistency: stated={obs.discount:.1f}%, "
                            f"computed={expected_discount:.1f}%"
                        ),
                        raw_value=str(obs.discount),
                        source_url=obs.source_url,
                    ))

        for prod_key, sellers_set in sellers_by_product.items():
            if len(sellers_set) > 1:
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="observation",
                    entity_id=prod_key,
                    issue_code=IssueCode.MULTIPLE_SELLERS,
                    severity=IssueSeverity.INFO,
                    message=f"Product {prod_key} observed across multiple sellers: {sorted(sellers_set)}",
                    raw_value=",".join(sorted(sellers_set)),
                ))

        total_n = max(len(observations), 1)
        return {
            "count": len(observations),
            "total_checks": total_checks,
            "passed_checks": passed,
            "issues": issues[:20],
            "price_stats": self._price_stats(observations),
            "null_rates": {
                "price": round(sum(1 for o in observations if o.price is None) / total_n, 4),
                "old_price": round(sum(1 for o in observations if o.old_price is None) / total_n, 4),
                "discount": round(sum(1 for o in observations if o.discount is None) / total_n, 4),
                "seller_name": round(sum(1 for o in observations if not o.seller_name) / total_n, 4),
                "stock_quantity": round(sum(1 for o in observations if o.stock_quantity is None) / total_n, 4),
            },
        }

    def _validate_locations(
        self,
        locations: list[Location],
        source_id: str = "",
        quality_issues: list[DataQualityIssue] | None = None,
        run_id: Optional[str] = None,
    ) -> dict:
        """Validate location records."""
        issues = []
        total_checks = 0
        passed = 0
        qi = quality_issues if quality_issues is not None else []

        seen_coords_to_name: dict[tuple[float, float], str] = {}
        seen_norm_names_to_raw: dict[str, str] = {}

        for loc in locations:
            is_zone = loc.location_type in _ZONE_TYPES

            if is_zone:
                # Delivery/service zones: only require governorate
                total_checks += 1
                if loc.governorate and loc.governorate.lower() != "unknown":
                    passed += 1
                else:
                    issues.append("Location (delivery zone): missing or unknown governorate")
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="location",
                        entity_id=loc.location_id,
                        issue_code=IssueCode.UNKNOWN_GOVERNORATE,
                        severity=IssueSeverity.MEDIUM,
                        message="Delivery zone location missing governorate",
                        source_url=loc.source_url,
                    ))
            else:
                # Physical locations: full checks
                total_checks += 3

                if loc.branch_name:
                    passed += 1
                    norm_bname = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", loc.branch_name.lower())
                    if norm_bname in seen_norm_names_to_raw and seen_norm_names_to_raw[norm_bname] != loc.branch_name:
                        qi.append(DataQualityIssue(
                            run_id=run_id,
                            source_id=source_id,
                            entity_type="location",
                            entity_id=loc.location_id,
                            issue_code=IssueCode.INCONSISTENT_LOCATION_NAME,
                            severity=IssueSeverity.LOW,
                            message=(
                                f"Inconsistent location naming: '{loc.branch_name}' vs "
                                f"'{seen_norm_names_to_raw[norm_bname]}'"
                            ),
                            raw_value=loc.branch_name,
                            source_url=loc.source_url,
                        ))
                    elif norm_bname:
                        seen_norm_names_to_raw[norm_bname] = loc.branch_name
                else:
                    issues.append("Location: missing branch_name")
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="location",
                        entity_id=loc.location_id,
                        issue_code=IssueCode.MISSING_FIELD,
                        severity=IssueSeverity.MEDIUM,
                        message="Physical store location missing branch_name",
                        source_url=loc.source_url,
                    ))

                if loc.city or loc.governorate:
                    passed += 1
                else:
                    issues.append(f"Location {loc.branch_name}: missing city/governorate")
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="location",
                        entity_id=loc.location_id,
                        issue_code=IssueCode.UNKNOWN_GOVERNORATE,
                        severity=IssueSeverity.MEDIUM,
                        message=f"Location {loc.branch_name}: missing city/governorate",
                        raw_value=loc.branch_name,
                        source_url=loc.source_url,
                    ))

                if loc.address:
                    passed += 1
                else:
                    issues.append(f"Location {loc.branch_name}: missing address")
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="location",
                        entity_id=loc.location_id,
                        issue_code=IssueCode.MISSING_FIELD,
                        severity=IssueSeverity.LOW,
                        message=f"Location '{loc.branch_name}' missing street address (governorate-level record only)",
                        raw_value=loc.branch_name,
                        source_url=loc.source_url,
                    ))

                if loc.latitude is None or loc.longitude is None:
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="location",
                        entity_id=loc.location_id,
                        issue_code=IssueCode.MISSING_FIELD,
                        severity=IssueSeverity.INFO,
                        message=f"Physical store '{loc.branch_name}' missing GPS coordinates (latitude/longitude)",
                        raw_value=loc.branch_name,
                        source_url=loc.source_url,
                    ))

            # Coordinate bounds check (for any location that has coordinates)
            if loc.latitude is not None and loc.longitude is not None:
                coord_key = (round(loc.latitude, 5), round(loc.longitude, 5))
                if coord_key in seen_coords_to_name and loc.branch_name and seen_coords_to_name[coord_key] != loc.branch_name:
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="location",
                        entity_id=loc.location_id,
                        issue_code=IssueCode.INCONSISTENT_LOCATION_NAME,
                        severity=IssueSeverity.LOW,
                        message=(
                            f"Same GPS coordinates {coord_key} have different names: "
                            f"'{seen_coords_to_name[coord_key]}' vs '{loc.branch_name}'"
                        ),
                        raw_value=loc.branch_name,
                        source_url=loc.source_url,
                    ))
                elif loc.branch_name:
                    seen_coords_to_name[coord_key] = loc.branch_name

                if not (
                    _EG_LAT_MIN <= loc.latitude <= _EG_LAT_MAX
                    and _EG_LON_MIN <= loc.longitude <= _EG_LON_MAX
                ):
                    qi.append(DataQualityIssue(
                        run_id=run_id,
                        source_id=source_id,
                        entity_type="location",
                        entity_id=loc.location_id,
                        issue_code=IssueCode.OUT_OF_EGYPT_COORDINATES,
                        severity=IssueSeverity.HIGH,
                        message=(
                            f"Coordinates ({loc.latitude}, {loc.longitude}) "
                            f"are outside Egypt bounds"
                        ),
                        raw_value=f"{loc.latitude},{loc.longitude}",
                        source_url=loc.source_url,
                    ))

            # Unknown governorate
            if loc.governorate and loc.governorate.lower() == "unknown":
                qi.append(DataQualityIssue(
                    run_id=run_id,
                    source_id=source_id,
                    entity_type="location",
                    entity_id=loc.location_id,
                    issue_code=IssueCode.UNKNOWN_GOVERNORATE,
                    severity=IssueSeverity.LOW,
                    message="Governorate is set to 'unknown'",
                    raw_value=loc.governorate,
                    source_url=loc.source_url,
                ))

        return {
            "count": len(locations),
            "total_checks": total_checks,
            "passed_checks": passed,
            "issues": issues[:20],
        }

    def _price_stats(self, observations: list[ProductObservation]) -> dict:
        """Calculate price statistics."""
        prices = [o.price for o in observations if o.price]
        if not prices:
            return {"min": 0, "max": 0, "avg": 0, "count": 0}

        return {
            "min": min(prices),
            "max": max(prices),
            "avg": round(sum(prices) / len(prices), 2),
            "count": len(prices),
        }

    @staticmethod
    def write_quality_issues(
        issues: list[DataQualityIssue], output_path: Path
    ) -> None:
        """Write quality issues to a JSON file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(
                [issue.model_dump(mode="json") for issue in issues],
                f,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

    @staticmethod
    def generate_gtin_collision_report(
        products_by_source: dict[str, list[Product | dict]],
        output_path: Optional[Path] = None,
    ) -> dict:
        """
        WP8: Informational cross-source GTIN collision report (no product-matching engine).
        Finds identical GTINs (or 8-14 digit numeric EAN/UPC codes in gtin/sku)
        appearing across multiple sources or multiple products within a source.
        """
        gtin_map: dict[str, list[dict]] = {}
        for source_id, prods in products_by_source.items():
            for p in prods:
                if isinstance(p, dict):
                    gtin = p.get("gtin")
                    sku = p.get("sku")
                    spid = p.get("source_product_id")
                    pname = p.get("product_name")
                else:
                    gtin = p.gtin
                    sku = p.sku
                    spid = p.source_product_id
                    pname = p.product_name

                code = gtin
                if not code and sku and re.fullmatch(r"\d{8,14}", str(sku).strip()):
                    code = str(sku).strip()

                if code:
                    gtin_map.setdefault(str(code).strip(), []).append({
                        "source_id": source_id,
                        "source_product_id": spid,
                        "product_name": pname,
                    })

        cross_source_collisions = {}
        within_source_collisions = {}
        for gtin_code, entries in gtin_map.items():
            sources_involved = {e["source_id"] for e in entries}
            if len(sources_involved) > 1:
                cross_source_collisions[gtin_code] = entries
            elif len(entries) > 1:
                within_source_collisions[gtin_code] = entries

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_gtins_indexed": len(gtin_map),
            "cross_source_collisions_count": len(cross_source_collisions),
            "within_source_collisions_count": len(within_source_collisions),
            "cross_source_collisions": cross_source_collisions,
            "within_source_collisions": within_source_collisions,
        }

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

        return report
