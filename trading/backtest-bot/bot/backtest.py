"""Backfill engine: replay real MNQ history through the EMA 9/21 rules and print the
trade list so it can be checked against TradingView. Applies commission + slippage so
the numbers are honest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .config import CONFIG
from .data import Candle
from .signals import ema


@dataclass
class Trade:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    points: float
    pnl: float
    outcome: str  # WIN / LOSS / FLAT


@dataclass
class Summary:
    total: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    avg_pnl: float
    best: float
    worst: float
    total_pnl: float
    max_drawdown: float
    buy_hold_pnl: float


def build_trades(candles: List[Candle]) -> List[Trade]:
    closes = [c.close for c in candles]
    fast = ema(closes, CONFIG.fast_period)
    slow = ema(closes, CONFIG.slow_period)
    mult = CONFIG.contract_multiplier * CONFIG.quantity
    # Round-trip friction in index points: commission both sides + slippage both sides.
    friction_points = 2 * CONFIG.commission_per_side + 2 * CONFIG.slippage_points

    trades: List[Trade] = []
    in_pos = False
    entry_i = -1
    for i in range(1, len(candles)):
        if any(x != x for x in (fast[i], slow[i], fast[i - 1], slow[i - 1])):
            continue
        up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        down = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
        if not in_pos and up:
            in_pos = True
            entry_i = i
        elif in_pos and down:
            e, x = candles[entry_i], candles[i]
            gross_points = x.close - e.close
            net_points = gross_points - friction_points
            pnl = net_points * mult
            trades.append(
                Trade(
                    entry_date=e.date,
                    exit_date=x.date,
                    entry_price=e.close,
                    exit_price=x.close,
                    points=net_points,
                    pnl=pnl,
                    outcome="WIN" if net_points > 0 else "LOSS" if net_points < 0 else "FLAT",
                )
            )
            in_pos = False
    return trades


def summarize(trades: List[Trade], candles: List[Candle]) -> Summary:
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    total_pnl = sum(pnls)

    peak = equity = max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    mult = CONFIG.contract_multiplier * CONFIG.quantity
    bh = (candles[-1].close - candles[0].close) * mult if candles else 0.0

    return Summary(
        total=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=(len(wins) / len(trades)) if trades else 0.0,
        profit_factor=(gross_win / gross_loss) if gross_loss else float("inf"),
        avg_pnl=(total_pnl / len(trades)) if trades else 0.0,
        best=max(pnls) if pnls else 0.0,
        worst=min(pnls) if pnls else 0.0,
        total_pnl=total_pnl,
        max_drawdown=max_dd,
        buy_hold_pnl=bh,
    )


def _usd(n: float) -> str:
    return f"-${abs(n):,.2f}" if n < 0 else f"${n:,.2f}"


def print_report(trades: List[Trade], candles: List[Candle]) -> Summary:
    if not trades:
        print("  No completed EMA crossover setups in this window — not enough to judge.")
        return summarize(trades, candles)

    print("\n   #  entry        exit         entry px    exit px     net pts     pnl          outcome")
    print("   -- ------------ ------------ ----------- ----------- ----------- ------------ -------")
    for i, t in enumerate(trades, 1):
        print(
            f"   {i:>2} {t.entry_date}   {t.exit_date}   "
            f"{t.entry_price:>10.2f}  {t.exit_price:>10.2f}  {t.points:>10.1f}  "
            f"{_usd(t.pnl):>11}  {t.outcome}"
        )

    s = summarize(trades, candles)
    pf = "inf" if s.profit_factor == float("inf") else f"{s.profit_factor:.2f}"
    print("\n  Summary (net of commission + slippage)")
    print(f"    Total trades  : {s.total}")
    print(f"    Wins / Losses : {s.wins} / {s.losses}")
    print(f"    Win rate      : {s.win_rate * 100:.1f}%")
    print(f"    Profit factor : {pf}")
    print(f"    Avg PnL       : {_usd(s.avg_pnl)}")
    print(f"    Best / Worst  : {_usd(s.best)} / {_usd(s.worst)}")
    print(f"    Total PnL     : {_usd(s.total_pnl)}")
    print(f"    Max drawdown  : {_usd(s.max_drawdown)}")
    print(f"    Buy & hold    : {_usd(s.buy_hold_pnl)}  (same {CONFIG.quantity} contract, same window)")
    if s.total < 20:
        print(f"\n  Note: only {s.total} trades — an anecdote, not evidence. 20+ is the bar.")
    verdict = "beat" if s.total_pnl > s.buy_hold_pnl else "LOST to"
    print(f"  Verdict: EMA {CONFIG.fast_period}/{CONFIG.slow_period} {verdict} buy-and-hold on "
          f"{CONFIG.symbol} over this window.")
    return s
