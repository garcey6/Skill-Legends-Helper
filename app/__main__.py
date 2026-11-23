"""Source entry point for M1 replay: ``python -m app --replay IMAGE``."""
from __future__ import annotations

from app.replay import main

if __name__ == "__main__":
    raise SystemExit(main())
