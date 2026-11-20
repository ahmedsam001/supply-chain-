#!/usr/bin/env python3
"""Top-level runner entrypoint for data_collection."""

import sys
from pathlib import Path

# Ensure data_collection directory is at the front of sys.path
_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from dwh.run_pipeline import main  # noqa: E402

if __name__ == "__main__":
    main()
