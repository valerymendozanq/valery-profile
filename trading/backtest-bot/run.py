#!/usr/bin/env python3
"""Convenience launcher so you can run `python run.py --backfill` from this folder."""
from bot.main import main

if __name__ == "__main__":
    raise SystemExit(main())
