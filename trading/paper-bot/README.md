# MNQ Paper-Trading Bot (TypeScript)

An honest, paper-only trading bot built from the Miles High Club "Paper Trading Bot
Prompts" flow, retargeted to **Nasdaq micro futures (MNQ=F)** on the **daily**
timeframe with an **EMA 9/21 crossover** strategy.

> **Paper/backtest only. No live trading, no broker connection, no API keys.**
> Execution never leaves a simulated paper order.

## What it does
- Fetches **real** daily OHLCV for `MNQ=F` from the public Yahoo Finance endpoint.
- Computes a 9/21 EMA crossover signal on the latest **closed** candle.
- Runs a risk check (sizing in MNQ contracts; `QUANTITY > MAX_POSITION` → SKIP).
- Simulates a paper order only when an action passes.
- Keeps a two-file **memory** layer (`data/ledger.csv`, `data/learnings.md`) that can
  turn a repeat of a *real* prior-losing setup into a SKIP.

## Install
```bash
cd trading/paper-bot
npm install
```

## Commands
```bash
npm run scan          # one real scan, no memory (simulated paper order only)
npm run replay:raw    # honest baseline over real MNQ history + metrics
npm run replay:memory # memory-gated pass (SKIP only on a real prior loss)
npm run memory:reset  # clear ledger.csv + learnings.md
npm run typecheck     # tsc --noEmit
```
A memory-gated single scan is also available via `npx tsx src/index.ts scan:memory`.

## How raw vs. memory differ
- **`replay:raw`** ignores memory. It walks real history, pairs each bullish 9/21 EMA
  cross (entry) with the next bearish cross (exit), and prints a trade-by-trade table
  plus win rate / avg PnL / best / worst / total / max drawdown. If it finds **real**
  losing setups it appends a plain-English lesson to `learnings.md` and the trades to
  `ledger.csv`. If it finds none, nothing is seeded.
- **`replay:memory`** reads `ledger.csv` + `learnings.md` first. If a **real** prior
  losing MNQ setup exists it SKIPs a fresh long and logs the SKIP; otherwise it HOLDs
  and tells you to keep paper testing. With empty memory it tells you to run
  `replay:raw` first.

## Configuration
Copy `.env.example` to `.env` and edit. Everything is overridable:
`SYMBOL`, `INTERVAL`, `RANGE`, `FAST_PERIOD`, `SLOW_PERIOD`, `QUANTITY`,
`MAX_POSITION`, `CONTRACT_MULTIPLIER`. To experiment with a different market, change
`SYMBOL` to any Yahoo symbol (e.g. `NQ=F`, `QQQ`, `^NDX`, `BTC-USD`) and re-run.

## Where things live
- `data/ledger.csv` — completed replay/paper trades and SKIP decisions.
- `data/learnings.md` — plain-English lessons from **real** closed trades only.
- `src/` — `market` (data) · `strategy` (EMA 9/21) · `risk` · `execution` (paper only)
  · `memory` + `adaptiveFilter` (the two-file memory) · `replay` · `bot` (scan) · `index` (CLI).

## Honesty & limitations
- Uses real market data or fails loudly — it never invents candles or fakes trades.
- The replay is a **frictionless** model: it does not deduct commission or slippage,
  and fills are at the daily close of the cross candle. Real fills differ.
- EMA 9/21 was the winner **on Bitcoin**, not the Nasdaq. Results on MNQ reflect the
  Nasdaq's own behavior — read them on their own merits, and forward-test in paper
  before trusting anything. A backtest is a verdict on the past, not a promise.
