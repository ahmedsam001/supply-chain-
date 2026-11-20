#!/usr/bin/env python3
"""Top-level Azure sync entrypoint for data_collection."""

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from dwh.azure_sync import main  # noqa: E402

if __name__ == "__main__":
    main()
