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
  execution.py   MODE gating + broker factory
  brokers/
    base.py      broker interface (Account / Position / OrderResult)
    sim.py       local simulation (default)
    alpaca.py    Alpaca PAPER adapter — paper host only, hard-refuses live
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
python run.py --improve              # honest study: param sweep, 200-EMA filter, weekly
python run.py --forward --days 650   # simulate the LEARNING bot day-by-day (see it skip)
python run.py --status               # mode, config, broker, open position
python run.py --scan                 # evaluate the latest closed candle once (memory-aware)
python run.py --broker-check         # verify the configured broker connection
python run.py --loop --sleep 86400   # once-per-day loop (paper); Ctrl-C to stop
```

## The learning memory (the "smart bot")
The live bot (`--scan` / `--loop`) keeps a two-file memory and adapts:
- Every long entry is tagged with a **setup signature** — trend regime (price above/below
  the 200-EMA) + 21-EMA slope, e.g. `above200|slopeUp`.
- Closed trades are logged to `data/ledger.csv` with their signature and PnL.
- Before a new long, the bot checks that signature's **real track record**. If it has ≥2
  closed trades and a net loss, the bot **SKIPs** and writes a plain-English note to
  `data/learnings.md`. It only ever learns from real closed paper trades — nothing seeded.

Watch it happen without waiting days:
```bash
python run.py --forward --days 650
```
It replays real MNQ history through the *live* decision logic, so you see it take trades,
record outcomes, then start skipping setups that lost — and it prints whether the memory
**helped or hurt** vs. the raw strategy over that window.

## Run it automatically every day (macOS)
```bash
python run.py --forward --days 650        # (optional) seed the memory from history first
bash schedule/install-macos.sh 17         # run --scan daily at 17:00 local (5pm)
tail -f data/bot.log                       # watch what it does each day
bash schedule/uninstall-macos.sh           # stop & remove the schedule
```
This installs a `launchd` agent that runs `--scan` once a day (even after reboots; missed
runs fire on next wake). Everything stays **paper** — the schedule changes *when* the bot
runs, never *what* it's allowed to do.

## Live paper trading via Alpaca (optional)
By default the bot uses the local `sim` broker (no network venue). To place **real orders
on an Alpaca _paper_ account** (fake money, real API), set these and re-run:
```bash
export BROKER=alpaca_paper
export ALPACA_API_KEY_ID=...        # your Alpaca PAPER key
export ALPACA_API_SECRET_KEY=...    # your Alpaca PAPER secret
python run.py --broker-check        # confirms PAPER account + connection first
python run.py --scan                # routes the order through Alpaca paper
```
Guardrails baked into the adapter:
- **Paper host only.** It accepts exactly `https://paper-api.alpaca.markets` and
  **hard-refuses** the live host — there is no code path to real-money trading.
- Keys are read from the environment, never from source or logs.
- `--broker-check` refuses to proceed unless the account reports as paper.
- **Alpaca has no futures**, so MNQ can't trade there. Orders route to `ALPACA_SYMBOL`
  (default **QQQ**, which tracks the Nasdaq-100). The strategy signal is still computed on
  `MNQ=F` daily; QQQ is the executable proxy. Get free paper keys at
  https://alpaca.markets .

### Verify against TradingView
Run `--backfill` and compare its trade list to the TradingView Strategy Tester for the
same symbol/timeframe/window. **If they disagree, stop and fix — never run logic you
haven't verified.** (Small differences are expected: this bot applies explicit
commission + slippage and fills at the daily close.)

## Honest strategy study (`--improve`)
`python run.py --improve` runs three checks against real data and reports them straight:
1. **Parameter sweep** — 8/20 … 10/22 neighbours. A real edge is a *plateau*, not a spike.
2. **200-EMA regime filter** — only go long above the 200-day EMA; compares PnL + drawdown.
3. **Weekly timeframe** — same rules, weekly candles (timeframe flips results).

On MNQ the current finding is blunt: 9/21 is a genuine plateau (not overfit), the regime
filter cuts drawdown, but **nothing beats buy-and-hold** — EMA 9/21 is a Bitcoin-shaped
tool and the Nasdaq grinds. Match the strategy to the asset; don't borrow a backtest.

## Tests
Deterministic, no-network unit tests (signals, backtest math, broker safety, mode gating):
```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```
These run in CI (`.github/workflows/ci.yml`) alongside the paper-bot typecheck on every push.

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
