"""
Observation History — WP5

Append-only, idempotent JSONL observation history.
Each source has its partitioned JSONL file under:
    data/observation_history/<source_id>.jsonl

Keyed by (source_id, source_product_id, location_id, run_id/collected_at) and observation_id
so re-running or replaying the same run never duplicates rows.

Every row includes:
- run_id
- run_mode (live, offline_fixture, synthetic)
- watchlist_id
- source
- timestamp

Supports:
- Idempotent append of observations (and optional product/location metadata for run diffs)
- Querying all observations for a product over time
- Cross-run diff with strict run_mode and watchlist_id validation
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from normalization.schema import ExtractionResult, ProductObservation

logger = structlog.get_logger()


class ObservationHistory:
    """
    Append-only JSONL store for product observations and run snapshots.
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self._history_dir = self.data_dir / "observation_history"
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._runs_dir = self._history_dir / "runs"
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, source_id: str) -> Path:
        return self._history_dir / f"{source_id}.jsonl"

    def _run_meta_path(self, source_id: str, run_id: str) -> Path:
        src_dir = self._runs_dir / source_id
        src_dir.mkdir(parents=True, exist_ok=True)
        return src_dir / f"{run_id}.json"

    @staticmethod
    def _composite_key(record: dict) -> str:
        """
        Composite idempotency key:
        (source_id, source_product_id_or_product_id, location_id, run_id_or_observed_at)
        """
        src = record.get("source_id") or record.get("source") or "unknown"
        spid = record.get("source_product_id") or record.get("product_id") or ""
        loc = record.get("location_id") or "global"
        run_or_ts = (
            record.get("_run_id")
            or record.get("run_id")
            or record.get("timestamp")
            or record.get("collected_at")
            or record.get("observed_at")
            or ""
        )
        return f"{src}|{spid}|{loc}|{run_or_ts}"

    def _load_existing_keys(self, source_id: str) -> tuple[set[str], set[str]]:
        """Load all observation_ids and composite keys already stored for this source."""
        path = self._path(source_id)
        if not path.exists():
            return set(), set()
        obs_ids: set[str] = set()
        comp_keys: set[str] = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    oid = record.get("observation_id")
                    if oid:
                        obs_ids.add(oid)
                    comp_keys.add(self._composite_key(record))
                except json.JSONDecodeError:
                    continue
        return obs_ids, comp_keys

    def append(
        self,
        observations: list[ProductObservation],
        run_id: Optional[str] = None,
        products: Optional[list] = None,
        locations: Optional[list] = None,
        run_mode: str = "live",
        watchlist_id: str = "default_v1",
    ) -> tuple[int, int]:
        """
        Append observations to history. Skips duplicates by observation_id OR composite key.
        Returns (appended_count, skipped_count).
        """
        if not observations:
            return 0, 0

        source_id = observations[0].source_id or "unknown"
        existing_ids, existing_comp_keys = self._load_existing_keys(source_id)
        path = self._path(source_id)

        prod_by_pid = {}
        prod_by_spid = {}
        if products:
            for p in products:
                p_dict = p.model_dump(mode="json") if hasattr(p, "model_dump") else dict(p)
                prod_by_pid[p_dict.get("product_id")] = p_dict
                prod_by_spid[p_dict.get("source_product_id")] = p_dict

        appended = 0
        skipped = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        with open(path, "a", encoding="utf-8") as f:
            for obs in observations:
                eff_run_id = run_id or obs.run_id or "unspecified_run"
                record = obs.model_dump(mode="json")
                record["_run_id"] = eff_run_id
                record["run_id"] = eff_run_id
                record["run_mode"] = run_mode
                record["watchlist_id"] = watchlist_id
                record["source"] = source_id
                record["source_id"] = source_id
                record["timestamp"] = (
                    record.get("observed_at")
                    or record.get("collected_at")
                    or now_iso
                )

                p_meta = prod_by_pid.get(obs.product_id) or prod_by_spid.get(obs.source_product_id)
                if p_meta:
                    if not record.get("source_product_id"):
                        record["source_product_id"] = p_meta.get("source_product_id")
                    record["_sku"] = p_meta.get("sku")
                    record["_product_url"] = p_meta.get("product_url")
                    record["_product_name"] = p_meta.get("product_name")

                comp_key = self._composite_key(record)
                if obs.observation_id in existing_ids or comp_key in existing_comp_keys:
                    skipped += 1
                    continue

                record["_appended_at"] = now_iso
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                existing_ids.add(obs.observation_id)
                existing_comp_keys.add(comp_key)
                appended += 1

        if run_id and (products is not None or locations is not None or observations):
            meta_path = self._run_meta_path(source_id, run_id)
            if not meta_path.exists():
                run_meta = {
                    "source_id": source_id,
                    "source": source_id,
                    "run_id": run_id,
                    "run_mode": run_mode,
                    "watchlist_id": watchlist_id,
                    "timestamp": now_iso,
                    "products": [
                        p.model_dump(mode="json") if hasattr(p, "model_dump") else dict(p)
                        for p in (products or [])
                    ],
                    "locations": [
                        loc.model_dump(mode="json") if hasattr(loc, "model_dump") else dict(loc)
                        for loc in (locations or [])
                    ],
                }
                with open(meta_path, "w", encoding="utf-8") as mf:
                    json.dump(run_meta, mf, ensure_ascii=False, indent=2)

        logger.info(
            "observation_history.append",
            source=source_id,
            run_id=run_id,
            run_mode=run_mode,
            watchlist_id=watchlist_id,
            appended=appended,
            skipped=skipped,
            total_stored=len(existing_ids),
        )
        return appended, skipped

    def append_result(
        self,
        result: ExtractionResult,
        run_id: Optional[str] = None,
        run_mode: Optional[str] = None,
        watchlist_id: str = "default_v1",
    ) -> tuple[int, int]:
        """Append all observations, products, and locations from an ExtractionResult."""
        eff_run_id = run_id or result.run_id
        eff_mode = run_mode or getattr(result, "mode", None) or "live"
        for obs in result.observations:
            if not obs.source_id:
                obs.source_id = result.source_id
        return self.append(
            result.observations,
            run_id=eff_run_id,
            products=result.products,
            locations=result.locations,
            run_mode=eff_mode,
            watchlist_id=watchlist_id,
        )

    def load_all(self, source_id: str) -> list[dict]:
        """Load all stored observations for a source (as raw dicts)."""
        path = self._path(source_id)
        if not path.exists():
            return []
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def load_run(self, source_id: str, run_id: str) -> list[dict]:
        """Load observations for a specific run_id."""
        all_obs = self.load_all(source_id)
        return [o for o in all_obs if o.get("_run_id") == run_id or o.get("run_id") == run_id]

    def get_product_history(
        self,
        source_id: str,
        source_product_id: str,
    ) -> list[dict]:
        """Return all observations for a product over time in chronological order."""
        all_obs = self.load_all(source_id)
        product_obs = [
            o for o in all_obs
            if o.get("source_product_id") == source_product_id
            or o.get("product_id") == source_product_id
        ]
        product_obs.sort(key=lambda r: r.get("observed_at") or r.get("collected_at") or "")
        return product_obs

    def get_last_observation(
        self,
        source_id: str,
        source_product_id: str,
    ) -> Optional[dict]:
        """Get the most recent observation for a specific product."""
        history = self.get_product_history(source_id, source_product_id)
        return history[-1] if history else None

    def cross_run_diff(
        self,
        source_id: str,
        run_id_a: str,
        run_id_b: str,
    ) -> dict:
        """
        Compare observations between two runs.
        Refuses comparisons across different run_mode (e.g. live vs offline_fixture
        or live vs synthetic) or different watchlist_id with a clear ValueError.
        """
        rows_a = self.load_run(source_id, run_id_a)
        rows_b = self.load_run(source_id, run_id_b)

        meta_a_path = self._run_meta_path(source_id, run_id_a)
        meta_b_path = self._run_meta_path(source_id, run_id_b)
        meta_a = json.loads(meta_a_path.read_text(encoding="utf-8")) if meta_a_path.exists() else {}
        meta_b = json.loads(meta_b_path.read_text(encoding="utf-8")) if meta_b_path.exists() else {}

        mode_a = (rows_a[0].get("run_mode") if rows_a else None) or meta_a.get("run_mode") or "live"
        mode_b = (rows_b[0].get("run_mode") if rows_b else None) or meta_b.get("run_mode") or "live"
        if mode_a != mode_b:
            raise ValueError(
                f"Cannot diff incompatible run modes for source '{source_id}': "
                f"{run_id_a} has run_mode='{mode_a}' vs {run_id_b} has run_mode='{mode_b}'"
            )

        wl_a = (rows_a[0].get("watchlist_id") if rows_a else None) or meta_a.get("watchlist_id") or "default_v1"
        wl_b = (rows_b[0].get("watchlist_id") if rows_b else None) or meta_b.get("watchlist_id") or "default_v1"
        if wl_a != wl_b:
            raise ValueError(
                f"Cannot diff runs with different watchlists for source '{source_id}': "
                f"{run_id_a} has watchlist_id='{wl_a}' vs {run_id_b} has watchlist_id='{wl_b}'"
            )

        obs_a = {
            (o.get("source_product_id") or o.get("product_id")): o
            for o in rows_a
        }
        obs_b = {
            (o.get("source_product_id") or o.get("product_id")): o
            for o in rows_b
        }

        price_changes = []
        availability_changes = []
        scope_changes = []
        new_products = []
        removed_products = []
        identifier_changes = []
        new_locations = []

        for pid, obs in obs_b.items():
            if pid not in obs_a:
                new_products.append(pid)
                continue

            prev = obs_a[pid]

            p_old = prev.get("price")
            p_new = obs.get("price")
            if p_old is not None and p_new is not None and abs(p_old - p_new) > 0.01:
                price_changes.append({
                    "source_product_id": pid,
                    "old_price": p_old,
                    "new_price": p_new,
                    "delta": round(p_new - p_old, 2),
                    "delta_pct": round((p_new - p_old) / p_old * 100, 1) if p_old else None,
                })

            avail_old = prev.get("availability_status")
            avail_new = obs.get("availability_status")
            if avail_old != avail_new:
                availability_changes.append({
                    "source_product_id": pid,
                    "old_status": avail_old,
                    "new_status": avail_new,
                })

            scope_old = prev.get("availability_scope")
            scope_new = obs.get("availability_scope")
            if scope_old and scope_new and scope_old != scope_new:
                scope_changes.append({
                    "source_product_id": pid,
                    "old_scope": scope_old,
                    "new_scope": scope_new,
                })

        for pid in obs_a:
            if pid not in obs_b:
                removed_products.append(pid)

        sku_map_a = {
            o.get("_sku"): (pid, o.get("_product_url") or o.get("source_url"))
            for pid, o in obs_a.items()
            if o.get("_sku")
        }
        for pid, o in obs_b.items():
            sku = o.get("_sku")
            if sku and sku in sku_map_a:
                old_pid, old_url = sku_map_a[sku]
                new_url = o.get("_product_url") or o.get("source_url")
                if old_pid != pid or (old_url and new_url and old_url != new_url):
                    identifier_changes.append({
                        "sku": sku,
                        "old_source_product_id": old_pid,
                        "new_source_product_id": pid,
                        "old_url": old_url,
                        "new_url": new_url,
                    })

        if meta_a and meta_b:
            locs_a = {loc.get("location_id") for loc in meta_a.get("locations", [])}
            for loc in meta_b.get("locations", []):
                lid = loc.get("location_id")
                if lid and lid not in locs_a:
                    new_locations.append(lid)

        changed = price_changes + availability_changes + scope_changes + identifier_changes
        return {
            "source_id": source_id,
            "source": source_id,
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
            "run_mode": mode_a,
            "watchlist_id": wl_a,
            "products_in_run_1": len(obs_a),
            "products_in_run_2": len(obs_b),
            "products_in_a": len(obs_a),
            "products_in_b": len(obs_b),
            "products_in_a_eq_products_in_b": len(obs_a) == len(obs_b),
            "added": new_products,
            "removed": removed_products,
            "changed": changed,
            "new_products": new_products,
            "removed_products": removed_products,
            "delisted_products": removed_products,
            "price_changes": price_changes,
            "availability_changes": availability_changes,
            "scope_changes": scope_changes,
            "identifier_changes": identifier_changes,
            "new_locations": new_locations,
            "price_changes_count": len(price_changes),
            "availability_changes_count": len(availability_changes),
            "scope_changes_count": len(scope_changes),
            "identifier_changes_count": len(identifier_changes),
            "new_locations_count": len(new_locations),
        }

    def count_records(self, source_id: str) -> int:
        """Count total stored observations for a source."""
        path = self._path(source_id)
        if not path.exists():
            return 0
        count = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
