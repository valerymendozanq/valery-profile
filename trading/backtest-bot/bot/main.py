"""CLI entry point for the MNQ EMA 9/21 bot.

Commands:
  --backfill [--years N]   Replay real history and print the trade list (verify vs TradingView).
  --scan                   Evaluate the latest closed daily candle once; act via the broker.
  --status                 Print current mode, config, and open position.
  --broker-check           Verify the configured broker connection (paper only).
  --loop                   Run the once-per-day loop (evaluates on the latest close, then waits).

Modes (env MODE): paper (default) / testnet / live. Non-paper modes are gated by
execution.preflight() and this build ships no live venue adapter — paper is the only
path that runs. Broker (env BROKER): sim (default) or alpaca_paper (Alpaca PAPER account).
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from typing import List

from .backtest import build_trades, print_report
from .config import CONFIG
from .data import Candle, fetch_candles
from .execution import UnsafeModeError, preflight, get_broker, execution_symbol
from .brokers.base import BrokerError
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
    broker = get_broker()  # BrokerError if alpaca config is incomplete/unsafe
    exec_sym = execution_symbol()

    candles = fetch_candles(CONFIG.symbol, CONFIG.interval, "3mo")
    sig, reason, c = _evaluate_once(candles)
    ts = c.time
    stamp = dt.datetime.utcnow().isoformat(timespec="seconds")
    tag = f"{CONFIG.mode}/{broker.name}"
    ordersym = f" (orders on {exec_sym})" if exec_sym != CONFIG.symbol else ""
    print(f"[{stamp}] [scan] {CONFIG.symbol} {c.date} close={c.close:.2f} -> {sig}: {reason}{ordersym}")

    # Idempotency: never act twice on the same candle.
    if state.last_processed_time(exec_sym) == ts:
        print(f"[scan] Candle {c.date} already processed — no double action.")
        return

    # Source of truth for "am I already in a position?": the real broker for a live
    # paper account, SQLite for the local sim.
    if broker.name == "alpaca_paper":
        bpos = broker.get_position(exec_sym)
        in_pos = bpos is not None
        held_qty = int(bpos.qty) if bpos else 0
    else:
        srow = state.get_position(exec_sym)
        in_pos = srow is not None
        held_qty = int(srow["quantity"]) if srow else 0

    if sig == "BUY" and not in_pos:
        if CONFIG.quantity > CONFIG.max_position:
            print(f"[scan] SKIP: quantity {CONFIG.quantity} > max position {CONFIG.max_position}.")
            state.log_action(ts, exec_sym, "SKIP", c.close, CONFIG.quantity, tag, reason)
        else:
            res = broker.submit(exec_sym, "BUY", CONFIG.quantity, c.close)
            _report_order(res)
            if res.ok:
                state.open_position(exec_sym, c.close, CONFIG.quantity, ts)
                state.log_action(ts, exec_sym, "BUY", c.close, CONFIG.quantity, tag, reason)
                alert(f"{exec_sym} BUY {CONFIG.quantity} @ {c.close:.2f} ({tag})")
    elif sig == "SELL" and in_pos:
        qty = held_qty or CONFIG.quantity
        res = broker.submit(exec_sym, "SELL", qty, c.close)
        _report_order(res)
        if res.ok:
            state.close_position(exec_sym)
            state.log_action(ts, exec_sym, "SELL", c.close, qty, tag, reason)
            alert(f"{exec_sym} SELL {qty} @ {c.close:.2f} ({tag})")
    elif sig == "BUY" and in_pos:
        print("[scan] BUY signal but already long — holding the open position.")
    elif sig == "SELL" and not in_pos:
        print("[scan] SELL signal but flat — nothing to close.")
    else:
        print(f"[scan] HOLD — position={'open' if in_pos else 'flat'}, no fresh actionable cross.")

    state.set_last_processed_time(exec_sym, ts)


def _report_order(res) -> None:
    kind = "SIMULATED" if res.simulated else "PAPER-API"
    if res.ok:
        print(f"[scan] {kind} {res.action} {res.qty} {res.symbol} @ {res.price:.2f} "
              f"[{res.order_id or 'n/a'}] — {res.detail}")
    else:
        print(f"[scan] ORDER FAILED ({kind}) — {res.detail}")


def cmd_broker_check() -> int:
    print("=== broker:check ===")
    try:
        broker = get_broker()
    except BrokerError as e:
        print(f"  BLOCKED — {e}")
        return 2
    print(f"  broker        : {broker.name}")
    try:
        acct = broker.check()
    except BrokerError as e:
        print(f"  connection    : FAILED — {e}")
        return 2
    print(f"  connection    : OK")
    print(f"  account mode  : {'PAPER' if acct.is_paper else 'LIVE (!!)'}")
    print(f"  account status: {acct.status}")
    print(f"  cash          : {acct.cash:,.2f}")
    print(f"  order symbol  : {execution_symbol()}")
    if not acct.is_paper:
        print("  REFUSING: account is not paper. Stop and fix before any scan.")
        return 2
    return 0


def cmd_status(state: State) -> None:
    print("=== MNQ EMA bot status ===")
    print(f"  mode          : {CONFIG.mode}")
    print(f"  broker        : {CONFIG.broker}"
          + (f" -> orders on {execution_symbol()}" if CONFIG.broker.lower() == "alpaca_paper" else ""))
    print(f"  symbol        : {CONFIG.symbol} ({CONFIG.interval})")
    print(f"  strategy      : EMA {CONFIG.fast_period}/{CONFIG.slow_period}, long-only")
    print(f"  sizing        : {CONFIG.quantity} contract(s), max {CONFIG.max_position}, "
          f"${CONFIG.contract_multiplier}/pt")
    print(f"  max_capital   : {CONFIG.max_capital if CONFIG.max_capital else 'unset (paper)'}")
    pos = state.get_position(execution_symbol())
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
    g.add_argument("--broker-check", action="store_true", help="verify the broker connection (paper only)")
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

    if args.broker_check:
        return cmd_broker_check()

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
            print("\nNothing to do. Try --backfill, --scan, --status, --broker-check, or --loop.")
    except BrokerError as e:
        print(f"[broker] BLOCKED — {e}")
        return 2
    finally:
        state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
