# Runbook — Operations Guide

## Prerequisites

```bash
# Python 3.12, venv activated
source .venv/bin/activate

# Verify dependencies
pip list | grep -E "httpx|pydantic|structlog|tenacity|beautifulsoup4"
```

---

## List All Sources

```bash
python run_extraction.py --list
```

Output shows every source with compliance class, extraction method, and enabled status.

---

## Run Compliance Audit

```bash
python run_extraction.py --audit
```

Fetches `robots.txt` for all accessible domains and reports compliance status.
Run this before enabling any new source.

---

## Run Live Extraction

Only Class B enabled sources will run. Currently: **Jumia** and **2B Egypt**.

```bash
# All enabled sources (default: 500 products each)
python run_extraction.py

# Specific source
python run_extraction.py --source jumia

# Limit product count
python run_extraction.py --source jumia --max-products 50

# Custom data directory
python run_extraction.py --data-dir ./data/prod
```

---

## Run in Offline Fixture Mode

For testing parsers without live network requests:

```bash
# 2B Egypt using synthetic fixture
python run_extraction.py --source two_b --offline-fixture
```

Fixture file: `tests/fixtures/twob_sample.html`

---

## Run Tests

```bash
# Full test suite
.venv/bin/pytest tests/ -v

# Specific test file
.venv/bin/pytest tests/test_2b.py -v

# Quick (no verbose)
.venv/bin/pytest tests/ -q

# With coverage (if pytest-cov installed)
.venv/bin/pytest tests/ --cov=extractors --cov=normalization --cov=validation
```

Expected: **all tests pass**. Zero failures. Zero warnings about 0-byte files.

---

## Validate Sample Data

```bash
python -c "
import json
from pathlib import Path
from normalization.schema import Product, ProductObservation, Location, ExtractionResult
from validation.data_validator import DataValidator

# Load samples
for source in ['jumia', 'carrefour', 'tradeline', 'dream2000', 'two_b', 'raya']:
    sample_dir = Path(f'samples/{source}')
    if not sample_dir.exists():
        continue
    products = [Product(**p) for p in json.loads((sample_dir / 'products.json').read_text())]
    observations = [ProductObservation(**o) for o in json.loads((sample_dir / 'observations.json').read_text())]
    locations = [Location(**l) for l in json.loads((sample_dir / 'locations.json').read_text())]
    result = ExtractionResult(source_id=source, products=products, observations=observations, locations=locations)
    validator = DataValidator()
    report = validator.validate(result)
    score = report['overall']['quality_score']
    print(f'{source}: {score:.1%}')
"
```

---

## Adding a New Source

1. Add entry to `config/sources.yaml` (set `enabled: false` initially)
2. Create `extractors/source_<id>/` directory with:
   - `__init__.py`
   - `config.py` — constants and compliance note
   - `parser.py` — offline parsing functions
   - `extractor.py` — BaseExtractor subclass
3. Add to `get_extractor()` in `run_extraction.py`
4. Create fixture: `tests/fixtures/<id>_sample.html` or `.json`
5. Create test file: `tests/test_<id>.py`
6. Run audit: `python run_extraction.py --audit`
7. Run tests: `.venv/bin/pytest tests/ -v`
8. Only set `enabled: true` after human compliance review

---

## Updating the Canonical Model (schema.py)

**All changes must be backward-compatible:**

1. New fields must have `Optional` type with a `None` default
2. Existing sample JSON files must still deserialize without error after the change
3. Run: `.venv/bin/pytest tests/test_core.py -v` immediately after
4. The `compute_row_hash()` method version must be incremented (`hash_version`) if hash inputs change
5. Update `DATA_DICTIONARY.md` to document new fields

---

## Data Directory Layout

```
data/
└── raw/
    └── <source_id>/
        └── <YYYY-MM-DD>/
            ├── products.json     # Raw Shopify/HTML output
            ├── metadata.json     # Extraction metadata
            └── ...
```

Raw files are written by `BaseExtractor.save_raw_snapshot()` during extraction.
They are gitignored by default.

---

## Troubleshooting

### "Extractor not implemented yet"
The source's extractor package files are 0 bytes. Check:
```bash
wc -c extractors/source_<id>/*.py
```

### "Compliance check failed"
The source is Class C (blocked) or Class D with `enabled: false` in `sources.yaml`.
Do not override this without a human compliance review.

### "Cannot import AvailabilityScope"
Schema was not updated. Run:
```bash
python -c "from normalization.schema import AvailabilityScope; print('OK')"
```
If this fails, check `normalization/schema.py`.

### Tests failing after schema change
Likely a backward-compatibility issue. Check that new fields have `Optional` defaults.
Run: `.venv/bin/pytest tests/test_core.py -v --tb=long`

### "Invalid price" quality issue
The validator flags prices of 0 or > 5,000,000 EGP. Review the raw HTML/JSON
to confirm whether the parser is correctly extracting the price field.

### Delivery zone locations failing validation
Old behavior (pre-fix): validator penalized delivery zones for missing `branch_name`.
Current behavior: delivery zones skip `branch_name`/`address` checks.
If you see this issue, confirm `validation/data_validator.py` has the fix.

---

## Git Workflow

```bash
# Check what was committed
git log --oneline

# Check current state
git status

# Commit a logical unit of work
git -c user.name="Egypt Platform" -c user.email="platform@egypt-ecommerce" \
    commit -am "description of change"
```

Expected git log after full implementation:
```
baseline: 38 tests passing, pre-implementation snapshot
step1-2-5: extend schema with AvailabilityScope, DataQualityIssue, fix validator
step3-4-6-7: connectors, fixtures, tests for tradeline/dream2000/2b/raya
step8-9: documentation, README fix
```


---

## 7. Snapshot Replay & Observation History Usage (WP2 / WP4 / WP5)

### 7.1 Controlled Live Smoke Capture (`scripts/live_smoke.py`)
```bash
# Probe all enabled Class B sources (jumia, two_b) with bounded limit (5-20)
.venv/bin/python3 scripts/live_smoke.py --limit 6 --run-id live_20260928_wp1

# Probe a single enabled source
.venv/bin/python3 scripts/live_smoke.py --source jumia --limit 6
```
Stores raw gzipped HTTP bodies (`*.html.gz`), `robots.txt` snapshot (`robots_*.gz`), `snapshots_index.json`, and `run_manifest.json` under `data/raw_snapshots/<source>/<run_id>/`, and writes sanitized real HTML fixtures under `tests/fixtures/<source>/real/category_sample.html`.

### 7.2 Deterministic Offline Replay (`--replay-run`)
Re-parses stored raw gzip snapshots with **zero network calls**, verifying SHA-256 digests and yielding identical canonical output:
```bash
.venv/bin/python3 scripts/live_smoke.py --source jumia --replay-run live_20260928_wp1 --limit 6
.venv/bin/python3 run_extraction.py --source jumia --replay-run live_20260928_wp1 --limit 6
```

### 7.3 Observation History & Cross-Run Diff (`--diff`)
Every run appends idempotently to `data/observation_history/<source_id>.jsonl` (re-running or replaying the same `run_id` never duplicates rows). To compare two runs:
```bash
.venv/bin/python3 run_extraction.py --source jumia --diff <run_id_a> <run_id_b>
```
