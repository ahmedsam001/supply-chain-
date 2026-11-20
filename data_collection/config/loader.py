"""
Configuration loader — reads YAML configs and returns typed Source objects.
Also provides watchlist loading and deterministic bounded selection (WP4).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from normalization.schema import (
    ComplianceStatus,
    ExtractionMethod,
    Product,
    Source,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(config_path: str | Path) -> Path:
    path = Path(config_path)
    if not path.is_absolute() and not path.exists():
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate
    return path


def load_sources_config(
    config_path: str = "config/sources.yaml",
) -> dict[str, Source]:
    """
    Load all source configurations from YAML.

    Returns:
        Dictionary mapping source_id → Source
    """
    path = _resolve_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Sources config not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    sources = {}
    for key, cfg in raw.get("sources", {}).items():
        ev = cfg.get("evidence", {}) or {}
        source = Source(
            source_id=cfg["source_id"],
            source_name=cfg["source_name"],
            domain=cfg["domain"],
            compliance_status=ComplianceStatus(cfg["compliance_status"]),
            extraction_method=ExtractionMethod(cfg["extraction_method"]),
            last_verified_at=datetime.now(timezone.utc),
            rate_limit_rpm=cfg.get("rate_limit", {}).get("requests_per_minute", 30),
            min_delay_seconds=cfg.get("delay", {}).get("min_seconds", 1.5),
            max_delay_seconds=cfg.get("delay", {}).get("max_seconds", 4.0),
            enabled=cfg.get("enabled", False),
            notes=cfg.get("notes", ""),
            official_url=cfg.get("official_url"),
            business_type=cfg.get("business_type"),
            research_status=cfg.get("research_status"),
            implementation_status=cfg.get("implementation_status"),
            reason=cfg.get("reason"),
            evidence_url=cfg.get("evidence_url") or ev.get("evidence_url"),
            evidence_captured_on=cfg.get("evidence_captured_on") or ev.get("captured_on"),
            evidence_summary=cfg.get("evidence_summary") or ev.get("summary"),
            evidence_decided_by=cfg.get("evidence_decided_by") or ev.get("decided_by"),
        )
        sources[source.source_id] = source

    return sources


def load_extraction_config(
    config_path: str = "config/extraction.yaml",
) -> dict:
    """Load extraction configuration."""
    path = _resolve_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Extraction config not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_watchlist(
    watchlist_path: str = "config/watchlist.json",
) -> dict:
    """Load persisted product watchlist (WP4)."""
    path = _resolve_path(watchlist_path)
    if not path.exists():
        return {"default_limit": 10, "sources": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_watchlist(
    source_id: str,
    product_ids: list[str],
    watchlist_path: str = "config/watchlist.json",
) -> None:
    """Persist watched source_product_ids for a source so repeated runs observe the same items."""
    path = _resolve_path(watchlist_path)
    data = load_watchlist(watchlist_path) if path.exists() else {"version": 1, "default_limit": 10, "sources": {}}
    src_entry = data.setdefault("sources", {}).setdefault(source_id, {})
    existing = list(src_entry.get("watched_source_product_ids", []))
    for pid in product_ids:
        if pid and pid not in existing:
            existing.append(pid)
    src_entry["watched_source_product_ids"] = existing
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def select_deterministic_products(
    products: list[Product],
    source_id: str,
    limit: int = 10,
    watchlist_path: str = "config/watchlist.json",
) -> list[Product]:
    """
    WP4: Deterministic, bounded product selection prioritizing watched products first,
    then sorted deterministically by source_product_id.
    """
    if not products:
        return []
    wl = load_watchlist(watchlist_path)
    watched_ids = wl.get("sources", {}).get(source_id, {}).get("watched_source_product_ids", [])
    watched_rank = {pid: idx for idx, pid in enumerate(watched_ids)}

    def sort_key(p: Product) -> tuple[int, int, str]:
        if p.source_product_id in watched_rank:
            return (0, watched_rank[p.source_product_id], p.source_product_id)
        if p.sku and p.sku in watched_rank:
            return (0, watched_rank[p.sku], p.source_product_id)
        return (1, 0, p.source_product_id or p.product_name)

    ordered = sorted(products, key=sort_key)
    return ordered[: max(1, limit)]


def get_enabled_sources(
    config_path: str = "config/sources.yaml",
) -> dict[str, Source]:
    """Get only sources that are enabled for extraction."""
    all_sources = load_sources_config(config_path)
    return {
        sid: src for sid, src in all_sources.items()
        if src.enabled
    }


def get_sources_by_status(
    status: ComplianceStatus,
    config_path: str = "config/sources.yaml",
) -> dict[str, Source]:
    """Get sources filtered by compliance status."""
    all_sources = load_sources_config(config_path)
    return {
        sid: src for sid, src in all_sources.items()
        if src.compliance_status == status
    }
