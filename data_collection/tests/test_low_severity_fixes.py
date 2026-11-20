"""
Unit Tests for Low Severity Fixes & Optimizations:
1. HTTP Retry-After header parsing (integers, floats, RFC 2822 dates, edge cases)
2. Lockfile concurrency protection (flock single-instance execution)
3. Parquet bulk staging generation
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

import duckdb
import pytest

from extractors.base import BaseExtractor


class TestRetryAfterParsing:
    def test_parse_integer_seconds(self):
        assert BaseExtractor._parse_retry_after("120") == 120.0
        assert BaseExtractor._parse_retry_after("  60  ") == 60.0
        assert BaseExtractor._parse_retry_after("0") == 0.0

    def test_parse_float_seconds(self):
        assert BaseExtractor._parse_retry_after("15.5") == 15.5

    def test_parse_rfc_date_future(self):
        future_time = datetime.now(timezone.utc) + timedelta(seconds=90)
        http_date = future_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        val = BaseExtractor._parse_retry_after(http_date)
        assert val is not None
        assert 80.0 <= val <= 100.0

    def test_parse_rfc_date_past(self):
        past_time = datetime.now(timezone.utc) - timedelta(seconds=90)
        http_date = past_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        val = BaseExtractor._parse_retry_after(http_date)
        assert val == 0.0

    def test_parse_invalid_or_none(self):
        assert BaseExtractor._parse_retry_after(None) is None
        assert BaseExtractor._parse_retry_after("") is None
        assert BaseExtractor._parse_retry_after("   ") is None
        assert BaseExtractor._parse_retry_after("invalid_header_xyz") is None


class TestLockfileProtection:
    def test_flock_concurrency_exclusion(self):
        lock_file = "/tmp/test_egypt_ecommerce_lock.lock"
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR)
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        cmd = f'flock -n "{lock_file}" -c "echo SUCCESS" || echo LOCKED'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        assert "LOCKED" in res.stdout

        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

        res2 = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        assert "SUCCESS" in res2.stdout

        if os.path.exists(lock_file):
            os.remove(lock_file)


class TestParquetBulkStaging:
    def test_duckdb_parquet_export_compatibility(self):
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE test_table (
                id TEXT,
                name TEXT,
                price DOUBLE,
                created_at TIMESTAMP
            );
            INSERT INTO test_table VALUES
                ('p1', 'Product 1', 100.5, '2026-10-02 01:00:00'),
                ('p2', 'Product 2', NULL, '2026-10-02 02:00:00');
        """)

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            tmp_parquet = f.name

        try:
            cols = ["id", "name", "price", "created_at"]
            col_selects = ", ".join(f"{c} AS {c.upper()}" for c in cols)
            conn.execute(f"COPY (SELECT {col_selects} FROM test_table) TO '{tmp_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)")

            assert os.path.exists(tmp_parquet)
            assert os.path.getsize(tmp_parquet) > 0

            read_back = conn.execute(f"SELECT * FROM read_parquet('{tmp_parquet}')").fetchall()
            assert len(read_back) == 2
            assert read_back[0][0] == "p1"
            assert read_back[0][2] == 100.5
            assert read_back[1][2] is None
        finally:
            if os.path.exists(tmp_parquet):
                os.remove(tmp_parquet)
            conn.close()
