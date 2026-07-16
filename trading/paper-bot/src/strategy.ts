// EMA 9/21 crossover strategy. Long-only. Signals evaluate on closed candles.

import type { Candle, StrategyResult } from "./types.js";
import { config } from "./config.js";

// Standard EMA. Returns an array aligned to `values`; entries before the first
// full period are seeded with an SMA so the first EMA value is well-defined.
export function ema(values: number[], period: number): number[] {
  const out: number[] = new Array(values.length).fill(NaN);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let seed = 0;
  for (let i = 0; i < period; i++) seed += values[i];
  let prev = seed / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

// Evaluate the strategy on the candle at index `i` (must be a closed candle).
// A fresh crossover is detected by comparing the EMA relationship at i vs i-1.
export function evaluateAt(candles: Candle[], i: number): StrategyResult {
  const closes = candles.map((c) => c.close);
  const fast = ema(closes, config.fastPeriod);
  const slow = ema(closes, config.slowPeriod);
  return classify(fast, slow, i);
}

export function classify(fast: number[], slow: number[], i: number): StrategyResult {
  const f = fast[i];
  const s = slow[i];
  const fPrev = fast[i - 1];
  const sPrev = slow[i - 1];

  if ([f, s, fPrev, sPrev].some((x) => Number.isNaN(x) || x === undefined)) {
    return {
      signal: "HOLD",
      reason: "Not enough history for both EMAs yet.",
      fastEMA: f,
      slowEMA: s,
    };
  }

  const crossedUp = fPrev <= sPrev && f > s;
  const crossedDown = fPrev >= sPrev && f < s;

  if (crossedUp) {
    return {
      signal: "BUY",
      reason: `9 EMA crossed above 21 EMA (${f.toFixed(1)} > ${s.toFixed(1)}) — momentum up.`,
      fastEMA: f,
      slowEMA: s,
    };
  }
  if (crossedDown) {
    return {
      signal: "SELL",
      reason: `9 EMA crossed below 21 EMA (${f.toFixed(1)} < ${s.toFixed(1)}) — momentum down.`,
      fastEMA: f,
      slowEMA: s,
    };
  }
  return {
    signal: "HOLD",
    reason: `No fresh crossover (9 EMA ${f.toFixed(1)} vs 21 EMA ${s.toFixed(1)}).`,
    fastEMA: f,
    slowEMA: s,
  };
}
