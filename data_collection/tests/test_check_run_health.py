"""Unit tests for dwh/check_run_health.py (post-upload silent-failure guard)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb

from dwh.cdc_snapshot import DEFAULT_STORES, ensure_live_market_schema, seed_stores
from dwh.check_run_health import evaluate_run_health, main


def _seed_db(
    db_path: Path,
    run_rows: list[tuple],
    with_status_col: bool = False,
) -> Path:
    conn = duckdb.connect(str(db_path))
    try:
        ensure_live_market_schema(conn)
        seed_stores(conn)
        if with_status_col:
            conn.execute("ALTER TABLE live_market.RUN_LOGS ADD COLUMN STATUS VARCHAR")
            conn.executemany(
                "INSERT INTO live_market.RUN_LOGS VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                run_rows,
            )
        else:
            conn.executemany(
                "INSERT INTO live_market.RUN_LOGS VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                run_rows,
            )
    finally:
        conn.close()
    return db_path


def _make_store_rows(
    token: str,
    counts: dict[str, int],
    finished: datetime,
    mode: str = "hourly",
    statuses: dict[str, str] | None = None,
) -> list[tuple]:
    rows = []
    for idx, (store, cnt) in enumerate(counts.items()):
        base = (
            f"{store}_{token}_abc12{idx}",
            store,
            mode,
            finished.date(),
            cnt,
            min(cnt, 5),
            max(cnt - 5, 0),
            12.5,
            finished,
            finished,
        )
        if statuses is not None:
            base = base + (statuses.get(store, "SUCCESS"),)
        rows.append(base)
    return rows


def test_healthy_run_exits_zero(tmp_path: Path, capsys) -> None:
    counts = {s["store_id"]: 250 for s in DEFAULT_STORES}
    db = _seed_db(
        tmp_path / "healthy.duckdb",
        _make_store_rows("hourly_20261120T031700Z", counts, datetime(2026, 11, 20, 3, 22, 0)),
    )

    rc = main(["--db-path", str(db)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "HEALTH CHECK PASSED" in out
    assert "6 stores healthy" in out
    assert "1,500 products scraped" in out


def test_single_blocked_store_zero_products_exits_one(tmp_path: Path, capsys) -> None:
    counts = {s["store_id"]: 200 for s in DEFAULT_STORES}
    counts["jumia"] = 0
    db = _seed_db(
        tmp_path / "blocked.duckdb",
        _make_store_rows("hourly_20261120T041700Z", counts, datetime(2026, 11, 20, 4, 21, 0)),
    )

    rc = main(["--db-path", str(db)])
    out = capsys.readouterr().out

    assert rc == 1
    assert "HEALTH CHECK FAILED" in out
    assert "jumia" in out
    assert "0 products" in out


def test_all_stores_zero_products_exits_one(tmp_path: Path) -> None:
    counts = {s["store_id"]: 0 for s in DEFAULT_STORES}
    db = _seed_db(
        tmp_path / "all_zero.duckdb",
        _make_store_rows("hourly_20261120T051700Z", counts, datetime(2026, 11, 20, 5, 20, 0)),
    )

    report = evaluate_run_health(db_path=db)

    assert not report.ok
    assert report.total_products == 0
    assert any("Total scraped products across the latest run is 0" in e for e in report.errors)
    assert main(["--db-path", str(db)]) == 1


def test_failed_status_column_exits_one(tmp_path: Path) -> None:
    counts = {s["store_id"]: 150 for s in DEFAULT_STORES}
    statuses = {s["store_id"]: "SUCCESS" for s in DEFAULT_STORES}
    statuses["raya"] = "FAILED"
    db = _seed_db(
        tmp_path / "status_fail.duckdb",
        _make_store_rows(
            "hourly_20261120T061700Z",
            counts,
            datetime(2026, 11, 20, 6, 20, 0),
            statuses=statuses,
        ),
        with_status_col=True,
    )

    report = evaluate_run_health(db_path=db)

    assert not report.ok
    assert any("raya" in e and "FAILED" in e for e in report.errors)
    assert main(["--db-path", str(db)]) == 1


def test_missing_expected_store_exits_one(tmp_path: Path) -> None:
    counts = {s["store_id"]: 180 for s in DEFAULT_STORES if s["store_id"] != "carrefour"}
    db = _seed_db(
        tmp_path / "missing_store.duckdb",
        _make_store_rows("hourly_20261120T071700Z", counts, datetime(2026, 11, 20, 7, 20, 0)),
    )

    report = evaluate_run_health(db_path=db)

    assert not report.ok
    assert any("carrefour" in e and "missing" in e for e in report.errors)
    assert main(["--db-path", str(db)]) == 1


def test_ignores_older_failed_run_when_latest_run_is_healthy(tmp_path: Path) -> None:
    bad_counts = {s["store_id"]: 0 for s in DEFAULT_STORES}
    good_counts = {s["store_id"]: 300 for s in DEFAULT_STORES}
    rows = (
        _make_store_rows("hourly_20261120T011700Z", bad_counts, datetime(2026, 11, 20, 1, 20, 0))
        + _make_store_rows("hourly_20261120T021700Z", good_counts, datetime(2026, 11, 20, 2, 20, 0))
    )
    db = _seed_db(tmp_path / "recovered.duckdb", rows)

    report = evaluate_run_health(db_path=db)

    assert report.ok
    assert report.run_label == "hourly_20261120T021700Z"
    assert report.total_products == 1800
    assert main(["--db-path", str(db)]) == 0
