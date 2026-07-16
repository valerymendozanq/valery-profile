# trading_bot_instructions.md

> Source of truth for the paper-trading bot. Written from the Miles High Club
> "Paper Trading Bot Prompts" flow (Prompt 03), retargeted to Nasdaq micro
> futures per the operator's choice. **Paper/backtest only. No live trading.**

## 1. Project Goal
A local paper-trading bot that evaluates an **EMA 9/21 crossover** strategy on
**MNQ=F (Micro E-mini Nasdaq-100 futures)** on the **daily** timeframe. It fetches
real market data, produces a signal, runs a risk check, and *simulates* a paper
order. It never touches an exchange. Paper/test mode comes first because the whole
point is to forward-test cheaply before risking anything.

Two paths exist side by side:
- **raw** — the honest baseline strategy with no memory.
- **memory** — the same strategy plus a two-file memory layer that can turn a
  repeat of a known-losing setup into a SKIP.

## 2. Safety Rules
- Paper trading by default. **There is no live trading code path in this project.**
- No secrets in source. No API keys are required or requested (market data is a
  public endpoint).
- No frontend, so no frontend credential exposure.
- Execution only ever *simulates* a paper order. No order is sent anywhere.

## 3. Strategy Rules
- **Asset:** `MNQ=F` (Micro E-mini Nasdaq-100). **Timeframe:** `1d` (daily only).
- **Indicators:** 9-period EMA (fast), 21-period EMA (slow).
- **Entry:** fast EMA crosses **above** slow EMA on the daily close → BUY (go long).
- **Exit:** fast EMA crosses **below** slow EMA → SELL (go flat). Long-only, no leverage.
- **Hold/skip:** if there is no fresh crossover on the latest closed candle → HOLD.
- Signals evaluate on the **daily close**, once per candle. Never intra-candle.
- **Backtest note:** EMA 9/21 was the winner on *Bitcoin*, not the Nasdaq. On the
  Nasdaq the same rules historically underperformed buy-and-hold (the index grinds
  rather than trends). This bot reports whatever the real MNQ data shows.

## 4. Risk Rules
- Position sizing is in **MNQ contracts** (multiplier **$2 per index point**).
- `QUANTITY` (contracts per entry) and `MAX_POSITION` (max contracts) are configurable.
- If `QUANTITY > MAX_POSITION` → final action is **SKIP**.
- One position at a time (long-only). Every decision carries a plain-English reason.

## 5. Broker/MCP Rules
- No broker or exchange connection in this project. Market data comes from the
  public Yahoo Finance daily endpoint for `MNQ=F`.
- If a paper broker/MCP adapter is ever added, it must be verified in paper/test
  mode first and kept behind a future adapter — the strategy returns a signal, risk
  approves/rejects, execution only simulates.

## 6. Memory Rules
- `data/ledger.csv` logs completed replay/paper trades and SKIP decisions.
- `data/learnings.md` stores plain-English lessons distilled from **real** closed trades.
- Both files are read before any BUY or SELL in the memory path. Before acting the
  bot asks: has this symbol lost on a similar setup before? does learnings.md warn
  about it? is this signal repeating a known bad trade? If yes → SKIP, no paper order,
  append a SKIP row, print the reason.
- **No seeded fake losses. No invented candles. No forced failure.** Learn only from
  real outcomes. If no prior loss exists, the memory path says to run `replay:raw` first.

## 7. Definition of Done
- `npm install`, `npm run scan`, `npm run replay:raw`, `npm run replay:memory`,
  and `npm run memory:reset` all work.
- The bot uses real public market data or fails clearly if it is unavailable.
- Logs are timestamped and every decision states a reason.
- No real order is ever placed.
