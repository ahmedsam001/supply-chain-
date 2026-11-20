"""
Change Detection — Identifies new products, price changes, availability/scope changes,
identifier changes, and new locations across runs (WP5).

Compares current extraction results against previous observations or between two runs:
- New products (first seen)
- Removed/delisted products
- Price changes (increase/decrease)
- Availability status & scope changes (in-stock ↔ out-of-stock, GLOBAL ↔ PHYSICAL_BRANCH)
- Changed identifiers (same SKU with changed source_product_id or URL)
- New branches/locations
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from normalization.schema import (
    AvailabilityStatus,
    ExtractionResult,
    Product,
    ProductObservation,
)

logger = structlog.get_logger()


class ChangeDetector:
    """Detects changes between extraction runs."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)

    def detect_changes(
        self,
        source_id: str,
        current_result: ExtractionResult,
        previous_data: Optional[dict] = None,
    ) -> dict:
        """
        Compare current extraction against the most recent previous run (or provided previous_data).
        Returns a dict with change summary.
        """
        previous = previous_data if previous_data is not None else self._load_previous(source_id)

        if previous is None:
            return {
                "source_id": source_id,
                "is_first_run": True,
                "new_products": len(current_result.products),
                "removed_products": 0,
                "delisted_products": [],
                "price_changes": 0,
                "availability_changes": 0,
                "scope_changes": 0,
                "identifier_changes": 0,
                "new_locations": len(current_result.locations),
            }

        # Build lookup maps
        prev_products = {
            p["source_product_id"]: p for p in previous.get("products", [])
            if "source_product_id" in p
        }
        prev_pid_to_spid = {
            p["product_id"]: p["source_product_id"]
            for p in previous.get("products", [])
            if "product_id" in p and "source_product_id" in p
        }
        curr_products = {
            p.source_product_id: p for p in current_result.products
        }
        curr_pid_to_spid = {
            p.product_id: p.source_product_id for p in current_result.products
        }

        # New and removed/delisted products
        new_ids = sorted(set(curr_products.keys()) - set(prev_products.keys()))
        removed_ids = sorted(set(prev_products.keys()) - set(curr_products.keys()))

        # Changed identifiers (same SKU with different source_product_id or product_url)
        identifier_changes = []
        prev_by_sku = {
            p.get("sku"): p
            for p in previous.get("products", [])
            if p.get("sku")
        }
        for spid, prod in curr_products.items():
            if prod.sku and prod.sku in prev_by_sku:
                prev_p = prev_by_sku[prod.sku]
                old_spid = prev_p.get("source_product_id")
                old_url = prev_p.get("product_url")
                if old_spid != spid or (old_url and prod.product_url and old_url != prod.product_url):
                    identifier_changes.append({
                        "sku": prod.sku,
                        "old_source_product_id": old_spid,
                        "new_source_product_id": spid,
                        "old_url": old_url,
                        "new_url": prod.product_url,
                    })

        # New locations
        prev_locs = {
            loc.get("location_id") or loc.get("branch_name")
            for loc in previous.get("locations", [])
        }
        new_locs = [
            loc.location_id or loc.branch_name
            for loc in current_result.locations
            if (loc.location_id or loc.branch_name) not in prev_locs
        ]

        # Price, availability, scope, and row-hash changes
        price_changes = []
        availability_changes = []
        scope_changes = []
        rows_compared = 0
        changed_rows = 0
        unchanged_rows = 0
        changed_fields_set: set[str] = set()

        prev_obs = {}
        for obs in previous.get("observations", []):
            raw_pid = obs.get("product_id", "")
            key = (
                obs.get("source_product_id")
                or prev_pid_to_spid.get(raw_pid)
                or raw_pid
            )
            if not key:
                continue
            if key not in prev_obs or raw_pid == key:
                prev_obs[key] = obs

        curr_obs_map = {}
        for obs in current_result.observations:
            raw_pid = obs.product_id
            key = (
                obs.source_product_id
                or curr_pid_to_spid.get(raw_pid)
                or raw_pid
            )
            if not key:
                continue
            if key not in curr_obs_map or raw_pid == key:
                curr_obs_map[key] = obs

        for key, obs in curr_obs_map.items():
            prev = prev_obs.get(key)
            if prev is None:
                continue

            rows_compared += 1
            row_changed = False

            # Price change
            prev_price = prev.get("price")
            curr_price = obs.price
            if prev_price and curr_price and abs(prev_price - curr_price) > 0.01:
                row_changed = True
                changed_fields_set.add("price")
                change_pct = ((curr_price - prev_price) / prev_price) * 100
                price_changes.append({
                    "product_id": key,
                    "old_price": prev_price,
                    "new_price": curr_price,
                    "change_pct": round(change_pct, 2),
                    "type": "increase" if change_pct > 0 else "decrease",
                })

            # Old price / discount change
            if prev.get("old_price") != obs.old_price:
                row_changed = True
                changed_fields_set.add("old_price")
            if prev.get("discount") != obs.discount:
                row_changed = True
                changed_fields_set.add("discount")

            # Availability status change
            prev_avail = prev.get("availability_status")
            curr_avail = obs.availability_status.value if obs.availability_status else None
            if prev_avail and curr_avail and prev_avail != curr_avail:
                row_changed = True
                changed_fields_set.add("availability_status")
                availability_changes.append({
                    "product_id": key,
                    "old_status": prev_avail,
                    "new_status": curr_avail,
                })

            # Availability scope change
            prev_scope = prev.get("availability_scope")
            curr_scope = obs.availability_scope.value if obs.availability_scope else None
            if prev_scope and curr_scope and prev_scope != curr_scope:
                row_changed = True
                changed_fields_set.add("availability_scope")
                scope_changes.append({
                    "product_id": key,
                    "old_scope": prev_scope,
                    "new_scope": curr_scope,
                })

            if row_changed:
                changed_rows += 1
            else:
                unchanged_rows += 1

        if identifier_changes:
            changed_fields_set.add("identifier")

        changes = {
            "source_id": source_id,
            "is_first_run": False,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "rows_compared": rows_compared,
            "changed_rows": changed_rows,
            "unchanged_rows": unchanged_rows,
            "changed_fields": sorted(changed_fields_set),
            "hash_version": 2,
            "new_products": len(new_ids),
            "new_product_ids": new_ids[:50],
            "removed_products": len(removed_ids),
            "delisted_products": removed_ids[:50],
            "price_changes": len(price_changes),
            "price_change_details": price_changes[:50],
            "availability_changes": len(availability_changes),
            "availability_change_details": availability_changes[:50],
            "scope_changes": len(scope_changes),
            "scope_change_details": scope_changes[:50],
            "identifier_changes": len(identifier_changes),
            "identifier_change_details": identifier_changes[:50],
            "new_locations": len(new_locs),
            "new_location_ids": new_locs[:50],
        }

        self._save_changes(source_id, changes)
        return changes

    def detect_changes_between_runs(
        self,
        source_id: str,
        previous_result: ExtractionResult,
        current_result: ExtractionResult,
    ) -> dict:
        """Compare two ExtractionResult objects directly."""
        prev_dict = {
            "products": [p.model_dump(mode="json") for p in previous_result.products],
            "observations": [o.model_dump(mode="json") for o in previous_result.observations],
            "locations": [loc.model_dump(mode="json") for loc in previous_result.locations],
        }
        return self.detect_changes(source_id, current_result, previous_data=prev_dict)

    def _load_previous(self, source_id: str) -> Optional[dict]:
        """Load the most recent previous extraction for a source."""
        source_dir = self.data_dir / "raw" / source_id
        if not source_dir.exists():
            return None

        date_dirs = sorted(
            [d for d in source_dir.iterdir() if d.is_dir()],
            reverse=True,
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for d in date_dirs:
            if d.name != today:
                products_file = d / "products.json"
                obs_file = d / "observations.json"
                locs_file = d / "locations.json"
                if products_file.exists():
                    data = {"products": [], "observations": [], "locations": []}
                    with open(products_file, encoding="utf-8") as f:
                        data["products"] = json.load(f)
                    if obs_file.exists():
                        with open(obs_file, encoding="utf-8") as f:
                            data["observations"] = json.load(f)
                    if locs_file.exists():
                        with open(locs_file, encoding="utf-8") as f:
                            data["locations"] = json.load(f)
                    return data

        return None

    def _save_changes(self, source_id: str, changes: dict):
        """Save the change detection report."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        changes_dir = self.data_dir / "bronze" / source_id / "changes"
        changes_dir.mkdir(parents=True, exist_ok=True)

        changes_file = changes_dir / f"{today}_changes.json"
        with open(changes_file, "w", encoding="utf-8") as f:
            json.dump(changes, f, indent=2, ensure_ascii=False)

        logger.info("changes.saved", file=str(changes_file))
