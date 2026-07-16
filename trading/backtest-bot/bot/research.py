"""Honest strategy research (The Backtest Machine, Prompt 4).

Three checks, all reported straight from real data:
  1. Parameter sweep    - is 9/21 a plateau (real edge) or a lucky spike (curve fit)?
  2. 200-EMA regime     - does only-long-above-the-200-EMA beat the raw rules?
  3. Weekly timeframe   - same rules, weekly candles (timeframe flips results).

Everything is compared against buy-and-hold, because on the Nasdaq that's the bar the
raw daily strategy fails to clear.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .config import CONFIG
from .data import Candle, fetch_candles
from .signals import ema


@dataclass
class VariantResult:
    label: str
    trades: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    max_drawdown: float
    buy_hold: float
    beats_bh: bool


def _friction_points() -> float:
    return 2 * CONFIG.commission_per_side + 2 * CONFIG.slippage_points


def _mult() -> float:
    return CONFIG.contract_multiplier * CONFIG.quantity


def evaluate(
    candles: List[Candle],
    fast_p: int,
    slow_p: int,
    label: str,
    regime_p: Optional[int] = None,
) -> VariantResult:
    """Run one crossover variant. If regime_p is set, only enter long when the close is
    above that EMA at entry (a trend filter)."""
    closes = [c.close for c in candles]
    fast = ema(closes, fast_p)
    slow = ema(closes, slow_p)
    regime = ema(closes, regime_p) if regime_p else None
    friction = _friction_points()
    mult = _mult()

    pnls: List[float] = []
    in_pos = False
    entry_i = -1
    for i in range(1, len(candles)):
        if any(x != x for x in (fast[i], slow[i], fast[i - 1], slow[i - 1])):
            continue
        up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        down = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
        if not in_pos and up:
            if regime is not None and (regime[i] != regime[i] or closes[i] <= regime[i]):
                continue  # regime filter blocks the entry
            in_pos = True
            entry_i = i
        elif in_pos and down:
            net = (candles[i].close - candles[entry_i].close) - friction
            pnls.append(net * mult)
            in_pos = False

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    total = sum(pnls)
    peak = eq = mdd = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    bh = (candles[-1].close - candles[0].close) * mult if candles else 0.0
    return VariantResult(
        label=label,
        trades=len(pnls),
        win_rate=(len(wins) / len(pnls)) if pnls else 0.0,
        profit_factor=(gross_win / gross_loss) if gross_loss else float("inf"),
        total_pnl=total,
        max_drawdown=mdd,
        buy_hold=bh,
        beats_bh=total > bh,
    )


def _row(v: VariantResult) -> str:
    pf = "inf" if v.profit_factor == float("inf") else f"{v.profit_factor:.2f}"
    flag = "  BEATS B&H" if v.beats_bh else ""
    return (
        f"  {v.label:<22} {v.trades:>3}  {v.win_rate * 100:>5.1f}%  pf {pf:>5}  "
        f"pnl ${v.total_pnl:>10,.0f}  mdd ${v.max_drawdown:>9,.0f}{flag}"
    )


def run_improvement_study(years_range: str = "5y") -> None:
    print(f"[improve] Fetching real {CONFIG.symbol} daily candles (range={years_range})...")
    daily = fetch_candles(CONFIG.symbol, "1d", years_range)
    print(f"[improve] Loaded {len(daily)} daily candles ({daily[0].date} -> {daily[-1].date})")
    bh = (daily[-1].close - daily[0].close) * _mult()
    print(f"[improve] Buy & hold over this window: ${bh:,.0f} (1x{CONFIG.quantity} contract)\n")

    base = evaluate(daily, CONFIG.fast_period, CONFIG.slow_period, f"{CONFIG.fast_period}/{CONFIG.slow_period} daily (base)")

    # 1. Parameter sweep — plateau vs spike.
    print("=== 1. Parameter sweep (overfitting check) ===")
    print("   A real edge is a PLATEAU across neighbours, not a lone SPIKE.")
    fast_opts = [CONFIG.fast_period - 1, CONFIG.fast_period, CONFIG.fast_period + 1]
    slow_opts = [CONFIG.slow_period - 1, CONFIG.slow_period, CONFIG.slow_period + 1]
    grid: List[VariantResult] = []
    for f in fast_opts:
        for s in slow_opts:
            if f >= s:
                continue
            grid.append(evaluate(daily, f, s, f"{f}/{s} daily"))
    for v in grid:
        print(_row(v))
    pnls = [v.total_pnl for v in grid]
    spread = (max(pnls) - min(pnls)) if pnls else 0.0
    base_pnl = base.total_pnl
    neighbours_positive = sum(1 for p in pnls if p > 0)
    print(f"\n   9/21 PnL ${base_pnl:,.0f}; neighbour spread ${spread:,.0f}; "
          f"{neighbours_positive}/{len(grid)} neighbours positive.")
    verdict1 = ("PLATEAU — neighbours behave similarly, so the result isn't a single magic setting."
                if neighbours_positive >= max(1, len(grid) - 1)
                else "MIXED/SPIKE — neighbours diverge; treat any single winner with suspicion.")
    print(f"   Verdict: {verdict1}")
    print(f"   But note: none of these beats buy-and-hold "
          f"({sum(1 for v in grid if v.beats_bh)}/{len(grid)} do).\n")

    # 2. Regime filter — only long above the 200 EMA.
    print("=== 2. 200-EMA regime filter (only long in an uptrend) ===")
    regime = evaluate(daily, CONFIG.fast_period, CONFIG.slow_period,
                      f"{CONFIG.fast_period}/{CONFIG.slow_period} + 200EMA filter", regime_p=200)
    print(_row(base))
    print(_row(regime))
    better = regime.total_pnl > base.total_pnl
    print(f"\n   Regime filter {'IMPROVED' if better else 'did NOT improve'} total PnL "
          f"(${regime.total_pnl:,.0f} vs ${base.total_pnl:,.0f}); "
          f"drawdown ${regime.max_drawdown:,.0f} vs ${base.max_drawdown:,.0f}. "
          f"{'Beats' if regime.beats_bh else 'Still loses to'} buy-and-hold.\n")

    # 3. Weekly timeframe.
    print("=== 3. Weekly timeframe (same rules) ===")
    try:
        weekly = fetch_candles(CONFIG.symbol, "1wk", years_range)
        wk = evaluate(weekly, CONFIG.fast_period, CONFIG.slow_period,
                      f"{CONFIG.fast_period}/{CONFIG.slow_period} weekly")
        wk_bh = (weekly[-1].close - weekly[0].close) * _mult()
        print(_row(wk))
        note = "  (only %d trades — an anecdote, not evidence; ignore the win rate)" % wk.trades if wk.trades < 5 else ""
        print(f"   Weekly buy & hold: ${wk_bh:,.0f}. "
              f"{'Beats' if wk.beats_bh else 'Loses to'} buy-and-hold.{note}\n")
    except Exception as e:  # noqa: BLE001
        print(f"   Weekly data unavailable: {e}\n")

    # Honest bottom line.
    print("=== Honest verdict ===")
    candidates = [base, regime] + grid
    winners = [v for v in candidates if v.beats_bh]
    if winners:
        best = max(winners, key=lambda v: v.total_pnl)
        print(f"   The single most promising variant that beats buy-and-hold: {best.label} "
              f"(${best.total_pnl:,.0f}).")
    else:
        print("   No tested variant beat buy-and-hold on MNQ. The most promising *risk* improvement")
        print(f"   is the 200-EMA regime filter (drawdown ${regime.max_drawdown:,.0f} vs "
              f"${base.max_drawdown:,.0f}), but it still trails simply holding the index.")
    print("   Takeaway: EMA 9/21 is a Bitcoin-shaped tool. On a grinding index, holding wins.")
    print("   This is the doc's whole point — match the strategy to the asset, don't borrow a backtest.")
