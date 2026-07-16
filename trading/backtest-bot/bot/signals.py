"""EMA 9/21 crossover signal logic. Long-only, evaluated on closed candles."""
from __future__ import annotations

from typing import List, Literal

from .data import Candle

Signal = Literal["BUY", "SELL", "HOLD"]


def ema(values: List[float], period: int) -> List[float]:
    """EMA aligned to `values`; NaN before the first full period, seeded with an SMA."""
    out: List[float] = [float("nan")] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    prev = seed
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _is_num(x: float) -> bool:
    return x == x  # False for NaN


def signal_at(fast: List[float], slow: List[float], i: int) -> tuple[Signal, str]:
    if i < 1:
        return "HOLD", "Not enough history."
    f, s, fp, sp = fast[i], slow[i], fast[i - 1], slow[i - 1]
    if not all(_is_num(x) for x in (f, s, fp, sp)):
        return "HOLD", "EMAs not warmed up yet."
    crossed_up = fp <= sp and f > s
    crossed_down = fp >= sp and f < s
    if crossed_up:
        return "BUY", f"9 EMA crossed above 21 EMA ({f:.1f} > {s:.1f})."
    if crossed_down:
        return "SELL", f"9 EMA crossed below 21 EMA ({f:.1f} < {s:.1f})."
    return "HOLD", f"No fresh crossover (9 EMA {f:.1f} vs 21 EMA {s:.1f})."


def latest_signal(candles: List[Candle], fast_p: int, slow_p: int) -> tuple[Signal, str]:
    closes = [c.close for c in candles]
    return signal_at(ema(closes, fast_p), ema(closes, slow_p), len(candles) - 1)
