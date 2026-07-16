# Trading — Claude + TradingView build kit (Nasdaq micro)

Three faithful, **paper/backtest-only** builds from the Miles Deutscher / Miles High Club
material, all retargeted to **Nasdaq micro futures (MNQ — Micro E-mini Nasdaq-100)** with the
**EMA 9/21 crossover** strategy. Real market data throughout (Yahoo Finance `MNQ=F`), no live
trading, no API keys, nothing fabricated.

## The three pieces
| Folder | Source doc | What it is | Runs here? |
|--------|-----------|-----------|-----------|
| [`paper-bot/`](./paper-bot) | Trading Bot V2 (6-prompt flow) | TypeScript/Node paper bot: no-memory baseline → two-file memory → raw-vs-memory comparison | ✅ yes |
| [`backtest-bot/`](./backtest-bot) | The Backtest Machine | Python executable bot: `--backfill` trade list, SQLite state, paper/testnet/live gating, optional **Alpaca paper** broker | ✅ yes |
| [`tradingview-mcp-setup/`](./tradingview-mcp-setup) | Copy-Paste Kit | TradingView MCP configs + local setup/verification guide | ⚠️ config only — verify on your own machine |

## Quick start
```bash
# 1) TypeScript paper bot
cd paper-bot && npm install
npm run replay:raw        # honest baseline over real MNQ history
npm run replay:memory     # memory-gated pass

# 2) Python backtest bot
cd ../backtest-bot
python run.py --backfill --years 3   # trade list + verdict vs buy-and-hold
python run.py --scan                 # one paper evaluation of the latest close
python run.py --broker-check         # optional: verify an Alpaca PAPER connection

# 3) TradingView MCP — see tradingview-mcp-setup/README.md (run locally)
```

## The honest headline
Both bots agree on the real numbers for MNQ over ~5 years (2021-07 → 2026-07), 1 contract:

| Metric | EMA 9/21 | Buy & hold |
|--------|----------|-----------|
| Trades | 24 (37.5% win rate) | 1 |
| Profit factor | ~2.2 | — |
| Net PnL | ~**+$19.9k** | ~**+$29.8k** |

The strategy made money — but **lost to simply buying and holding**, exactly the mismatch
*The Backtest Machine* warns about: EMA 9/21 was the winner **on Bitcoin**, which trends
violently; the Nasdaq grinds, so trend-following pays a whipsaw tax it doesn't earn back.
The `--backfill` verdict prints this automatically from whatever the live data shows.

## Ground rules baked into everything here
- **Paper only.** No live venue adapter ships. `live` mode refuses to start; `testnet`
  halts safely. Execution is either local simulation or an **Alpaca _paper_** account
  (fake money) — the Alpaca adapter hard-refuses the live host, so real-money trading has
  no code path.
- **Real data or a loud failure.** No invented candles, no faked or seeded trades.
- **No secrets.** Market data is a public endpoint; there are no API keys in this repo.
- **Sizing from a cap you set** (`QUANTITY`/`MAX_POSITION`), never from an account balance.
- Any tutorial that tells you to deposit funds *into* a bot/contract to "activate" it is a
  scam — a real bot trades inside your own account with your own keys.

## Validation ladder (before trusting any of this with real money)
1. Backtest → 2. **paper/forward test for weeks** → 3. testnet → 4. small live, trade-only key.
Never skip a rung. A backtest is a verdict on the past, not a promise about the future.

*Education, not financial advice. Trade only what you can afford to lose.*
