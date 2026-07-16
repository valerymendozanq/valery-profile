"""CLI entry point for the MNQ EMA 9/21 bot.

Commands:
  --backfill [--years N]   Replay real history and print the trade list (verify vs TradingView).
  --scan                   Evaluate the latest closed daily candle once; act in SQLite state.
  --status                 Print current mode, config, and open position.
  --loop                   Run the once-per-day loop (evaluates on the latest close, then waits).

Modes (env MODE): paper (default) / testnet / live. Non-paper modes are gated by
execution.preflight() and this build ships no real venue adapter — paper is the only
path that runs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from typing import List

from .backtest import build_trades, print_report
from .config import CONFIG
from .data import Candle, fetch_candles
from .execution import UnsafeModeError, execute, preflight
from .signals import ema, signal_at
from .state import State
from .alerts import alert


def _years_to_range(years: int) -> str:
    if years <= 1:
        return "1y"
    if years <= 2:
        return "2y"
    if years <= 5:
        return "5y"
    return "max"


def cmd_backfill(years: int) -> None:
    rng = _years_to_range(years)
    print(f"[backfill] Fetching real {CONFIG.symbol} {CONFIG.interval} candles (range={rng})...")
    candles = fetch_candles(CONFIG.symbol, CONFIG.interval, rng)
    print(f"[backfill] Loaded {len(candles)} candles ({candles[0].date} -> {candles[-1].date})")
    trades = build_trades(candles)
    print_report(trades, candles)


def _evaluate_once(candles: List[Candle]) -> tuple[str, str, Candle]:
    closes = [c.close for c in candles]
    fast = ema(closes, CONFIG.fast_period)
    slow = ema(closes, CONFIG.slow_period)
    i = len(candles) - 1
    sig, reason = signal_at(fast, slow, i)
    return sig, reason, candles[i]


def cmd_scan(state: State) -> None:
    preflight(CONFIG.mode)  # refuses unsafe modes before doing anything
    candles = fetch_candles(CONFIG.symbol, CONFIG.interval, "3mo")
    sig, reason, c = _evaluate_once(candles)
    ts = c.time
    stamp = dt.datetime.utcnow().isoformat(timespec="seconds")
    print(f"[{stamp}] [scan] {CONFIG.symbol} {c.date} close={c.close:.2f} -> {sig}: {reason}")

    # Idempotency: never act twice on the same candle.
    if state.last_processed_time(CONFIG.symbol) == ts:
        print(f"[scan] Candle {c.date} already processed — no double action.")
        return

    pos = state.get_position(CONFIG.symbol)
    if sig == "BUY" and pos is None:
        if CONFIG.quantity > CONFIG.max_position:
            print(f"[scan] SKIP: quantity {CONFIG.quantity} > max position {CONFIG.max_position}.")
            state.log_action(ts, CONFIG.symbol, "SKIP", c.close, CONFIG.quantity, CONFIG.mode, reason)
        else:
            execute(CONFIG.symbol, "BUY", c.close, CONFIG.quantity)
            state.open_position(CONFIG.symbol, c.close, CONFIG.quantity, ts)
            state.log_action(ts, CONFIG.symbol, "BUY", c.close, CONFIG.quantity, CONFIG.mode, reason)
            alert(f"{CONFIG.symbol} BUY {CONFIG.quantity} @ {c.close:.2f} ({CONFIG.mode}, simulated)")
    elif sig == "SELL" and pos is not None:
        execute(CONFIG.symbol, "SELL", c.close, pos["quantity"])
        state.close_position(CONFIG.symbol)
        state.log_action(ts, CONFIG.symbol, "SELL", c.close, pos["quantity"], CONFIG.mode, reason)
        alert(f"{CONFIG.symbol} SELL {pos['quantity']} @ {c.close:.2f} ({CONFIG.mode}, simulated)")
    elif sig == "BUY" and pos is not None:
        print("[scan] BUY signal but already long — holding the open position.")
    elif sig == "SELL" and pos is None:
        print("[scan] SELL signal but flat — nothing to close.")
    else:
        print(f"[scan] HOLD — position={'open' if pos else 'flat'}, no fresh actionable cross.")

    state.set_last_processed_time(CONFIG.symbol, ts)


def cmd_status(state: State) -> None:
    print("=== MNQ EMA bot status ===")
    print(f"  mode          : {CONFIG.mode}")
    print(f"  symbol        : {CONFIG.symbol} ({CONFIG.interval})")
    print(f"  strategy      : EMA {CONFIG.fast_period}/{CONFIG.slow_period}, long-only")
    print(f"  sizing        : {CONFIG.quantity} contract(s), max {CONFIG.max_position}, "
          f"${CONFIG.contract_multiplier}/pt")
    print(f"  max_capital   : {CONFIG.max_capital if CONFIG.max_capital else 'unset (paper)'}")
    pos = state.get_position(CONFIG.symbol)
    if pos:
        print(f"  position      : OPEN {pos['quantity']} @ {pos['entry_price']:.2f} "
              f"since {dt.datetime.utcfromtimestamp(pos['entry_time']).date()}")
    else:
        print("  position      : flat")
    try:
        preflight(CONFIG.mode)
        print("  preflight     : OK")
    except UnsafeModeError as e:
        print(f"  preflight     : BLOCKED — {e}")


def cmd_loop(state: State, sleep_seconds: int) -> None:
    print(f"[loop] Daily loop started for {CONFIG.symbol}. Evaluates on the close, then sleeps.")
    while True:
        try:
            cmd_scan(state)
        except Exception as e:  # noqa: BLE001 - loop must survive transient errors
            alert(f"[loop] error (halting this cycle): {e}")
        print(f"[loop] Sleeping {sleep_seconds}s until next check...")
        time.sleep(sleep_seconds)


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MNQ EMA 9/21 executable bot (paper-first).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--backfill", action="store_true", help="replay real history + print trade list")
    g.add_argument("--scan", action="store_true", help="evaluate the latest closed candle once")
    g.add_argument("--status", action="store_true", help="print mode/config/position")
    g.add_argument("--loop", action="store_true", help="run the once-per-day loop")
    p.add_argument("--years", type=int, default=3, help="years of history for --backfill (default 3)")
    p.add_argument("--sleep", type=int, default=86400, help="loop sleep seconds (default 86400)")
    args = p.parse_args(argv)

    if args.backfill:
        cmd_backfill(args.years)
        return 0

    # Every non-backfill command touches state and enforces mode safety.
    try:
        preflight(CONFIG.mode)
    except UnsafeModeError as e:
        print(f"[preflight] {e}")
        return 2

    state = State(CONFIG.db_path)
    try:
        if args.scan:
            cmd_scan(state)
        elif args.status:
            cmd_status(state)
        elif args.loop:
            cmd_loop(state, args.sleep)
        else:
            cmd_status(state)
            print("\nNothing to do. Try --backfill, --scan, --status, or --loop.")
    finally:
        state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
