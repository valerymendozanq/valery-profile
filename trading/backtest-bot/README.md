# MNQ EMA 9/21 Executable Bot (Python)

Built from the **Backtest Machine** "from backtest to execution" prompt, retargeted to
**Nasdaq micro futures (MNQ=F)**. It carries the *rules* (EMA 9/21, daily, long-only)
and is structured to run once per day at the candle close — but it ships **paper-only**:
there is no live venue adapter, and `testnet`/`live` modes refuse to start.

> **Paper-first. No live adapter ships here. No API keys needed for paper.**

## Strategy (do not modify the logic)
- Asset: `MNQ=F` (Micro E-mini Nasdaq-100), **daily candles only**.
- Entry: 9 EMA closes above 21 EMA → long, `QUANTITY` contracts.
- Exit: 9 EMA closes below 21 EMA → flat. Long-only, no leverage.
- Evaluate signals **once per day on the daily close**. Never intra-candle.

## Architecture (clean modules)
```
bot/
  config.py      env-overridable settings, no secrets
  data.py        real daily OHLCV from Yahoo (urllib, stdlib only)
  signals.py     EMA 9/21 crossover
  backtest.py    --backfill engine (commission + slippage applied)
  execution.py   paper simulate; testnet/live gated + refused
  state.py       SQLite so restarts never double-enter
  alerts.py      Telegram if configured, else stdout
  main.py        CLI
run.py           launcher
```

## Install & run
```bash
cd trading/backtest-bot
pip install -r requirements.txt      # no third-party deps; stdlib only

python run.py --backfill --years 3   # replay real history, print the trade list
python run.py --status               # mode, config, open position
python run.py --scan                 # evaluate the latest closed candle once (paper)
python run.py --loop --sleep 86400   # once-per-day loop (paper); Ctrl-C to stop
```

### Verify against TradingView
Run `--backfill` and compare its trade list to the TradingView Strategy Tester for the
same symbol/timeframe/window. **If they disagree, stop and fix — never run logic you
haven't verified.** (Small differences are expected: this bot applies explicit
commission + slippage and fills at the daily close.)

## Modes & safety rails
- `MODE=paper` (default) — the only mode that runs. Execution is simulated.
- `MODE=testnet` — refuses unless `MAX_CAPITAL>0`, then still halts safely (no adapter
  is wired in this build) rather than pretending to reach a venue.
- `MODE=live` — **refuses to start**. A real live path would require a **trade-only**
  API key (withdrawals disabled, IP-whitelisted), verified in testnet first, and a hard
  `MAX_CAPITAL` cap. None of that ships here on purpose.
- The bot sizes from `QUANTITY`/`MAX_POSITION` (a cap you set), never from an account
  balance. `QUANTITY > MAX_POSITION` → SKIP.
- Any tutorial that asks you to deposit funds *into* a bot/contract address to "activate"
  it is a scam. A real bot trades inside your own account with your own keys.

## Honesty
- Real market data or a loud failure — no fabricated candles, no faked trades.
- `--backfill` reports the **net** result and a plain verdict vs. buy-and-hold. On
  Nasdaq this strategy has historically *lost* to buy-and-hold — the report says so when
  the data says so. Backtested performance is simulated and does not guarantee the future.
