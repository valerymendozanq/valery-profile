"""Learning memory for the live bot.

Two files, mirroring the paper-trading PDFs:
- data/ledger.csv    — every decision (BUY/SELL/SKIP) with its setup signature + outcome.
- data/learnings.md  — plain-English lessons distilled from REAL closed trades only.

The "smart" part: each long entry is tagged with a **setup signature** (mainly whether
price was above or below the 200-EMA — trend vs. counter-trend). The bot tracks the
win/loss record per signature and refuses new entries whose signature already has a
losing track record. Nothing is seeded or invented — it learns only from closed trades.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import CONFIG
from .signals import ema

LEDGER_HEADER = ["timestamp", "symbol", "action", "price", "quantity",
                 "signature", "reason", "mode", "outcome", "pnl"]

LEDGER_PATH = os.path.join("data", "ledger.csv")
LEARNINGS_PATH = os.path.join("data", "learnings.md")

MIN_SAMPLES = 2  # need at least this many closed trades of a signature before trusting it


# ---- setup signature --------------------------------------------------------
def signature_at(closes: List[float], i: int) -> str:
    """Describe the setup at bar i: trend regime (vs 200-EMA) + 21-EMA slope."""
    ema200 = ema(closes, 200)
    slow = ema(closes, CONFIG.slow_period)
    regime = "unknown"
    if i < len(ema200) and ema200[i] == ema200[i]:  # not NaN
        regime = "above200" if closes[i] > ema200[i] else "below200"
    slope = "unknown"
    if i >= 5 and slow[i] == slow[i] and slow[i - 5] == slow[i - 5]:
        slope = "slopeUp" if slow[i] >= slow[i - 5] else "slopeDown"
    return f"{regime}|{slope}"


# ---- files ------------------------------------------------------------------
def ensure_files() -> None:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH, "w", newline="") as f:
            csv.writer(f).writerow(LEDGER_HEADER)
    if not os.path.exists(LEARNINGS_PATH):
        with open(LEARNINGS_PATH, "w") as f:
            f.write("# Learnings\n\nPlain-English lessons from **real** closed paper "
                    "trades only. Nothing here is seeded or invented.\n\n")


def append_row(timestamp, symbol, action, price, quantity, signature,
               reason, mode, outcome, pnl) -> None:
    ensure_files()
    with open(LEDGER_PATH, "a", newline="") as f:
        csv.writer(f).writerow([timestamp, symbol, action, f"{price:.2f}", quantity,
                                signature, reason, mode, outcome,
                                "" if pnl is None else f"{pnl:.2f}"])


def read_rows() -> List[dict]:
    if not os.path.exists(LEDGER_PATH):
        return []
    with open(LEDGER_PATH, newline="") as f:
        return list(csv.DictReader(f))


def append_learning(text: str) -> None:
    ensure_files()
    with open(LEARNINGS_PATH, "a") as f:
        f.write(f"- {text}\n")


def reset() -> None:
    os.makedirs("data", exist_ok=True)
    with open(LEDGER_PATH, "w", newline="") as f:
        csv.writer(f).writerow(LEDGER_HEADER)
    with open(LEARNINGS_PATH, "w") as f:
        f.write("# Learnings\n\nPlain-English lessons from **real** closed paper "
                "trades only. Nothing here is seeded or invented.\n\n")


# ---- the learning ----------------------------------------------------------
@dataclass
class SigRecord:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    net_pnl: float = 0.0


def signature_record(symbol: str, signature: str) -> SigRecord:
    """Closed-trade record for one setup signature, from the ledger."""
    rec = SigRecord()
    for r in read_rows():
        if r["symbol"] != symbol or r["signature"] != signature:
            continue
        if r["action"] != "SELL" or r["outcome"] not in ("WIN", "LOSS"):
            continue  # only closed trades count toward learning
        rec.trades += 1
        pnl = float(r["pnl"]) if r["pnl"] else 0.0
        rec.net_pnl += pnl
        if r["outcome"] == "WIN":
            rec.wins += 1
        else:
            rec.losses += 1
    return rec


def should_skip(symbol: str, signature: str) -> tuple[bool, str]:
    """Skip a new long if this setup signature has a real losing track record."""
    rec = signature_record(symbol, signature)
    if rec.trades >= MIN_SAMPLES and rec.net_pnl < 0:
        return True, (
            f"memory: setup '{signature}' has lost before "
            f"({rec.losses}/{rec.trades} losers, net ${rec.net_pnl:,.0f}) — SKIP this long."
        )
    return False, (
        f"memory: setup '{signature}' has no losing record yet "
        f"({rec.wins}W/{rec.losses}L) — cleared to trade."
    )
