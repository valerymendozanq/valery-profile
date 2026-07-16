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
from .research import run_improvement_study
from .config import CONFIG
from .data import Candle, fetch_candles
from .execution import UnsafeModeError, preflight, get_broker, execution_symbol
from .brokers.base import BrokerError
from .signals import ema, signal_at
from .state import State
from .alerts import alert
from . import memory


def _friction_pnl(entry_price: float, exit_price: float) -> float:
    """Net dollar PnL of one long, applying commission + slippage (index points)."""
    friction = 2 * CONFIG.commission_per_side + 2 * CONFIG.slippage_points
    mult = CONFIG.contract_multiplier * CONFIG.quantity
    return ((exit_price - entry_price) - friction) * mult


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


def _evaluate_bar(candles: List[Candle], i: int) -> tuple[str, str, str, Candle]:
    """Signal + reason + setup signature at bar i (a closed candle)."""
    closes = [c.close for c in candles]
    fast = ema(closes, CONFIG.fast_period)
    slow = ema(closes, CONFIG.slow_period)
    sig, reason = signal_at(fast, slow, i)
    setup = memory.signature_at(closes, i)
    return sig, reason, setup, candles[i]


def cmd_scan(state: State) -> None:
    preflight(CONFIG.mode)  # refuses unsafe modes before doing anything
    broker = get_broker()  # BrokerError if alpaca config is incomplete/unsafe
    exec_sym = execution_symbol()

    # 2y of daily candles so the 200-EMA (used for the setup signature) is warmed up.
    candles = fetch_candles(CONFIG.symbol, CONFIG.interval, "2y")
    i = len(candles) - 1
    sig, reason, setup, c = _evaluate_bar(candles, i)
    ts = c.time
    stamp = dt.datetime.utcnow().isoformat(timespec="seconds")
    tag = f"{CONFIG.mode}/{broker.name}"
    ordersym = f" (orders on {exec_sym})" if exec_sym != CONFIG.symbol else ""
    print(f"[{stamp}] [scan] {CONFIG.symbol} {c.date} close={c.close:.2f} "
          f"setup={setup} -> {sig}: {reason}{ordersym}")

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
        entry_price = bpos.avg_price if bpos else 0.0
    else:
        srow = state.get_position(exec_sym)
        in_pos = srow is not None
        held_qty = int(srow["quantity"]) if srow else 0
        entry_price = float(srow["entry_price"]) if srow else 0.0

    if sig == "BUY" and not in_pos:
        if CONFIG.quantity > CONFIG.max_position:
            print(f"[scan] SKIP: quantity {CONFIG.quantity} > max position {CONFIG.max_position}.")
            memory.append_row(c.date, exec_sym, "SKIP", c.close, CONFIG.quantity, setup,
                              "quantity exceeds max position", tag, "SKIPPED", None)
        else:
            skip, why = memory.should_skip(exec_sym, setup)
            if skip:
                print(f"[scan] 🧠 SKIP (learned) — {why}")
                memory.append_row(c.date, exec_sym, "SKIP", c.close, CONFIG.quantity, setup,
                                  why, tag, "SKIPPED", None)
                alert(f"{exec_sym} SKIP long — {why}")
            else:
                res = broker.submit(exec_sym, "BUY", CONFIG.quantity, c.close)
                _report_order(res)
                if res.ok:
                    state.open_position(exec_sym, c.close, CONFIG.quantity, ts)
                    state.meta_set(f"open_sig::{exec_sym}", setup)
                    memory.append_row(c.date, exec_sym, "BUY", c.close, CONFIG.quantity, setup,
                                      why, tag, "OPEN", None)
                    alert(f"{exec_sym} BUY {CONFIG.quantity} @ {c.close:.2f} ({tag}) setup={setup}")
    elif sig == "SELL" and in_pos:
        qty = held_qty or CONFIG.quantity
        entry_sig = state.meta_get(f"open_sig::{exec_sym}") or setup
        pnl = _friction_pnl(entry_price, c.close)
        outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT"
        res = broker.submit(exec_sym, "SELL", qty, c.close)
        _report_order(res)
        if res.ok:
            state.close_position(exec_sym)
            memory.append_row(c.date, exec_sym, "SELL", c.close, qty, entry_sig,
                              f"closed {outcome}", tag, outcome, pnl)
            alert(f"{exec_sym} SELL {qty} @ {c.close:.2f} pnl ${pnl:,.0f} ({outcome})")
            rec = memory.signature_record(exec_sym, entry_sig)
            if rec.trades >= memory.MIN_SAMPLES and rec.net_pnl < 0:
                memory.append_learning(
                    f"{exec_sym} setup '{entry_sig}' is net-losing "
                    f"({rec.losses}/{rec.trades} losers, net ${rec.net_pnl:,.0f}) — "
                    f"future longs with this setup will be skipped.")
                print(f"[scan] 🧠 Lesson recorded: setup '{entry_sig}' now flagged as net-losing.")
    elif sig == "BUY" and in_pos:
        print("[scan] BUY signal but already long — holding the open position.")
    elif sig == "SELL" and not in_pos:
        print("[scan] SELL signal but flat — nothing to close.")
    else:
        print(f"[scan] HOLD — position={'open' if in_pos else 'flat'}, no fresh actionable cross.")

    state.set_last_processed_time(exec_sym, ts)


def cmd_forward(days: int) -> None:
    """Simulate the LIVE memory bot day-by-day over recent history so you can watch it
    learn: it takes trades, records outcomes, and starts SKIPping setups that have lost.
    Resets memory first so it's a clean run. Paper simulation only."""
    print(f"[forward] Simulating the memory bot day-by-day on {CONFIG.symbol} "
          f"(last {days} trading days). Resetting memory for a clean run.\n")
    candles = fetch_candles(CONFIG.symbol, CONFIG.interval, "5y")
    closes = [c.close for c in candles]
    fast = ema(closes, CONFIG.fast_period)
    slow = ema(closes, CONFIG.slow_period)
    memory.reset()

    start = max(210, len(candles) - days)  # keep 200-EMA warmup
    pos = None            # memory bot's open long: {price, sig, date}
    raw_pos = None        # no-memory baseline's open long: entry price
    taken = skipped = 0
    mem_pnl = raw_pnl = 0.0

    for i in range(start, len(candles)):
        s, _ = signal_at(fast, slow, i)
        setup = memory.signature_at(closes, i)
        c = candles[i]

        # --- memory bot ---
        if s == "BUY" and pos is None:
            skip, why = memory.should_skip(CONFIG.symbol, setup)
            if skip:
                skipped += 1
                memory.append_row(c.date, CONFIG.symbol, "SKIP", c.close, CONFIG.quantity,
                                  setup, why, "paper/sim", "SKIPPED", None)
                print(f"  {c.date}  🧠 SKIP long   setup={setup}")
            else:
                pos = {"price": c.close, "sig": setup}
                memory.append_row(c.date, CONFIG.symbol, "BUY", c.close, CONFIG.quantity,
                                  setup, why, "paper/sim", "OPEN", None)
                print(f"  {c.date}  BUY  @ {c.close:>8.0f}  setup={setup}")
        elif s == "SELL" and pos is not None:
            pnl = _friction_pnl(pos["price"], c.close)
            mem_pnl += pnl
            taken += 1
            outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT"
            memory.append_row(c.date, CONFIG.symbol, "SELL", c.close, CONFIG.quantity,
                              pos["sig"], f"closed {outcome}", "paper/sim", outcome, pnl)
            rec = memory.signature_record(CONFIG.symbol, pos["sig"])
            if rec.trades >= memory.MIN_SAMPLES and rec.net_pnl < 0:
                memory.append_learning(
                    f"{CONFIG.symbol} setup '{pos['sig']}' net-losing "
                    f"({rec.losses}/{rec.trades}, ${rec.net_pnl:,.0f}) — skipping future longs.")
            print(f"  {c.date}  SELL @ {c.close:>8.0f}  pnl ${pnl:>8,.0f}  {outcome:4}  setup={pos['sig']}")
            pos = None

        # --- no-memory baseline (takes every signal) ---
        if s == "BUY" and raw_pos is None:
            raw_pos = c.close
        elif s == "SELL" and raw_pos is not None:
            raw_pnl += _friction_pnl(raw_pos, c.close)
            raw_pos = None

    diff = mem_pnl - raw_pnl
    verdict = "HELPED" if diff > 0 else "HURT" if diff < 0 else "made no difference"
    print("\n[forward] Summary")
    print(f"  Trades taken (memory bot) : {taken}")
    print(f"  Longs skipped by memory   : {skipped}")
    print(f"  Net PnL WITH memory       : ${mem_pnl:,.0f}")
    print(f"  Net PnL NO memory (raw)   : ${raw_pnl:,.0f}")
    print(f"  Memory {verdict}: ${diff:,.0f} vs the raw strategy over this window.")
    print(f"  Ledger + lessons written to {memory.LEDGER_PATH} and {memory.LEARNINGS_PATH}.")
    print("  (Paper simulation. Learns only from real closed trades. Not financial advice.)")


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
    g.add_argument("--improve", action="store_true", help="honest study: param sweep, regime filter, weekly")
    g.add_argument("--forward", action="store_true", help="simulate the memory bot day-by-day and show what it learned")
    g.add_argument("--scan", action="store_true", help="evaluate the latest closed candle once (memory-aware)")
    g.add_argument("--status", action="store_true", help="print mode/config/position")
    g.add_argument("--broker-check", action="store_true", help="verify the broker connection (paper only)")
    g.add_argument("--loop", action="store_true", help="run the once-per-day loop")
    p.add_argument("--years", type=int, default=3, help="years of history for --backfill (default 3)")
    p.add_argument("--days", type=int, default=250, help="trading days for --forward (default 250)")
    p.add_argument("--sleep", type=int, default=86400, help="loop sleep seconds (default 86400)")
    args = p.parse_args(argv)

    if args.backfill:
        cmd_backfill(args.years)
        return 0

    if args.improve:
        run_improvement_study()
        return 0

    if args.forward:
        cmd_forward(args.days)
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
