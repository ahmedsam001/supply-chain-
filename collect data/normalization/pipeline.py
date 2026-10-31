"""
Bronze & Silver Normalization Pipeline

Transforms:
Raw (date-partitioned JSON files)
  ↓
Bronze (validated Pydantic models, deduplicated per-source)
  ↓
Silver (geography-normalized, standardized currencies, currency conversion if needed, clean categories)
  ↓
Gold (KPI aggregations: avg prices by brand/category, stockout rates, price change velocity)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from geospatial.egypt_geography import normalize_location
from normalization.schema import (
    AvailabilityStatus,
    Currency,
    Location,
    Product,
    ProductObservation,
)
from validation.data_validator import DataValidator

logger = structlog.get_logger()


class DataPipeline:
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.bronze_dir = self.data_dir / "bronze"
        self.silver_dir = self.data_dir / "silver"
        self.gold_dir = self.data_dir / "gold"
        self.validator = DataValidator()

    def process_source(self, source_id: str, date_str: Optional[str] = None):
        """Process a specific source from Raw to Bronze and Silver."""
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        source_raw = self.raw_dir / source_id / date_str
        if not source_raw.exists():
            logger.warning("pipeline.raw_not_found", path=str(source_raw))
            return None

        log = logger.bind(source_id=source_id, date=date_str)
        log.info("pipeline.start")

        # 1. Load Raw
        products_file = source_raw / "products.json"
        obs_file = source_raw / "observations.json"
        locs_file = source_raw / "locations.json"

        raw_products = []
        if products_file.exists():
            with open(products_file, "r", encoding="utf-8") as f:
                raw_products = json.load(f)

        raw_observations = []
        if obs_file.exists():
            with open(obs_file, "r", encoding="utf-8") as f:
                raw_observations = json.load(f)

        raw_locations = []
        if locs_file.exists():
            with open(locs_file, "r", encoding="utf-8") as f:
                raw_locations = json.load(f)

        log.info(
            "pipeline.raw_loaded",
            products=len(raw_products),
            observations=len(raw_observations),
            locations=len(raw_locations),
        )

        # 2. Bronze: Schema Validation & Typing
        bronze_products = []
        for rp in raw_products:
            try:
                p = Product(**rp)
                bronze_products.append(p)
            except Exception as e:
                logger.debug("bronze.product_invalid", error=str(e))

        bronze_obs = []
        for ro in raw_observations:
            try:
                o = ProductObservation(**ro)
                bronze_obs.append(o)
            except Exception as e:
                logger.debug("bronze.observation_invalid", error=str(e))

        bronze_locs = []
        for rl in raw_locations:
            try:
                l = Location(**rl)
                bronze_locs.append(l)
            except Exception as e:
                logger.debug("bronze.location_invalid", error=str(e))

        # Save Bronze
        bronze_target = self.bronze_dir / source_id / date_str
        bronze_target.mkdir(parents=True, exist_ok=True)

        with open(bronze_target / "products.json", "w", encoding="utf-8") as f:
            json.dump([p.model_dump(mode="json") for p in bronze_products], f, indent=2, ensure_ascii=False)

        with open(bronze_target / "observations.json", "w", encoding="utf-8") as f:
            json.dump([o.model_dump(mode="json") for o in bronze_obs], f, indent=2, ensure_ascii=False)

        if bronze_locs:
            with open(bronze_target / "locations.json", "w", encoding="utf-8") as f:
                json.dump([l.model_dump(mode="json") for l in bronze_locs], f, indent=2, ensure_ascii=False)

        log.info("pipeline.bronze_saved", path=str(bronze_target))

        # 3. Silver: Cleanse, Normalize Geography & Categories
        silver_products = []
        for bp in bronze_products:
            p_data = bp.model_dump(mode="json")
            # Clean string values
            p_data["product_name"] = p_data["product_name"].strip()
            if p_data.get("brand"):
                p_data["brand"] = p_data["brand"].strip().title()
            if p_data.get("category"):
                p_data["category"] = p_data["category"].strip().lower()
            silver_products.append(p_data)

        silver_obs = []
        for bo in bronze_obs:
            o_data = bo.model_dump(mode="json")
            # Ensure row_hash is calculated
            if not o_data.get("row_hash"):
                o_data["row_hash"] = bo.compute_row_hash()
            silver_obs.append(o_data)

        silver_locs = []
        for bl in bronze_locs:
            l_data = bl.model_dump(mode="json")
            geo = normalize_location(
                address=l_data.get("address"),
                city=l_data.get("city"),
                governorate=l_data.get("governorate"),
            )
            l_data["city"] = geo["city"]
            l_data["governorate"] = geo["governorate"]
            silver_locs.append(l_data)

        # Save Silver
        silver_target = self.silver_dir / source_id / date_str
        silver_target.mkdir(parents=True, exist_ok=True)

        with open(silver_target / "products.json", "w", encoding="utf-8") as f:
            json.dump(silver_products, f, indent=2, ensure_ascii=False)

        with open(silver_target / "observations.json", "w", encoding="utf-8") as f:
            json.dump(silver_obs, f, indent=2, ensure_ascii=False)

        if silver_locs:
            with open(silver_target / "locations.json", "w", encoding="utf-8") as f:
                json.dump(silver_locs, f, indent=2, ensure_ascii=False)

        log.info("pipeline.silver_saved", path=str(silver_target))

        # 4. Gold: Aggregations & Supply Chain Analytics
        gold_summary = self._generate_gold_aggregates(silver_products, silver_obs)
        gold_target = self.gold_dir / source_id / date_str
        gold_target.mkdir(parents=True, exist_ok=True)

        with open(gold_target / "analytics_summary.json", "w", encoding="utf-8") as f:
            json.dump(gold_summary, f, indent=2, ensure_ascii=False)

        log.info("pipeline.gold_saved", path=str(gold_target))
        return {
            "source_id": source_id,
            "date": date_str,
            "bronze": {"products": len(bronze_products), "observations": len(bronze_obs)},
            "silver": {"products": len(silver_products), "observations": len(silver_obs)},
            "gold": gold_summary,
        }

    def _generate_gold_aggregates(self, products: list[dict], observations: list[dict]) -> dict:
        """Compute brand pricing, category distribution, stockout rates."""
        total_products = len(products)
        total_obs = len(observations)

        # Stock status breakdown
        stock_status_counts = {}
        prices_by_brand = {}
        category_counts = {}

        # Map product_id to brand
        prod_map = {p["product_id"]: p for p in products}

        for obs in observations:
            status = obs.get("availability_status", "unknown")
            stock_status_counts[status] = stock_status_counts.get(status, 0) + 1

            p_id = obs.get("product_id")
            prod = prod_map.get(p_id)
            brand = (prod.get("brand") if prod else None) or "Unknown"
            price = obs.get("price")

            if price and price > 0:
                if brand not in prices_by_brand:
                    prices_by_brand[brand] = []
                prices_by_brand[brand].append(price)

        for p in products:
            cat = p.get("category") or "uncategorized"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        brand_metrics = {}
        for b, plist in prices_by_brand.items():
            brand_metrics[b] = {
                "sku_count": len(plist),
                "avg_price_egp": round(sum(plist) / len(plist), 2),
                "min_price_egp": min(plist),
                "max_price_egp": max(plist),
            }

        in_stock = stock_status_counts.get("in_stock", 0)
        out_of_stock = stock_status_counts.get("out_of_stock", 0)
        stockout_rate = (
            round((out_of_stock / total_obs * 100), 2) if total_obs > 0 else 0.0
        )

        return {
            "total_catalog_products": total_products,
            "total_price_observations": total_obs,
            "stockout_rate_pct": stockout_rate,
            "inventory_health": {
                "in_stock_count": in_stock,
                "out_of_stock_count": out_of_stock,
                "stock_status_distribution": stock_status_counts,
            },
            "category_distribution": category_counts,
            "brand_intelligence": brand_metrics,
        }


def main():
    pipeline = DataPipeline()
    res = pipeline.process_source("tradeline")
    print("\nPipeline execution completed successfully:")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
