# TradingView MCP — Setup & Verification Guide (Nasdaq micro)

Copy-paste-ready scaffolding for the **TradingView MCP** workflow from the Copy-Paste Kit,
retargeted to Nasdaq micro futures. This lets Claude read your TradingView charts, build
and inject Pine indicators, and drive analysis — inside your own machine.

> ⚠️ **This part cannot be verified from a remote/headless environment.** The TradingView
> MCP drives the **TradingView Desktop app** over a Chrome DevTools debug port on *your*
> machine. There is no desktop app or display in a cloud session, so `tv_launch` /
> `tv_health_check` must be run **locally by you**. The files here are the exact configs to
> drop in; the steps below are what you run. Nothing here fakes a "connected" result.

## What's in this folder
| File | Where it goes | Purpose |
|------|---------------|---------|
| `mcp.json` | merge into `~/.claude/.mcp.json` | registers the `tradingview` MCP server |
| `rules.json` | `~/tradingview-mcp/rules.json` | your Nasdaq-micro watchlist + rules |
| `settings.snippet.json` | merge into `~/.claude/settings.json` | pre-approves the MCP tools |

## Prerequisites (do these on your own computer)
1. **TradingView Desktop** installed — https://www.tradingview.com/desktop/
2. **Node.js** installed (`node --version`).
3. **Claude Code** — https://www.claude.com/claude-code

## Step-by-step

### 1. Install the MCP server
```bash
git clone https://github.com/tradesdontlie/tradingview-mcp.git ~/tradingview-mcp
cd ~/tradingview-mcp && npm install
# if it already exists: cd ~/tradingview-mcp && git pull && npm install
```

### 2. Register the server with Claude Code
Open `~/.claude/.mcp.json` and merge the `tradingview` entry from **`mcp.json`** into your
existing `mcpServers` object (don't overwrite other servers). Replace `<HOME>` with your
absolute home path — e.g. `/Users/valy/tradingview-mcp/src/server.js`.

### 3. Drop in your rules file
Copy **`rules.json`** to `~/tradingview-mcp/rules.json` and edit the watchlist/risk rules
to taste. It's pre-filled for MNQ/NQ with QQQ and NDX proxies and the EMA 9/21 rule set.

### 4. Pre-approve the tools (optional, recommended)
Merge **`settings.snippet.json`** into `~/.claude/settings.json` (add `mcp__tradingview__*`
to `permissions.allow`). **Fully quit and restart Claude Code** for it to take effect.

### 5. Launch TradingView with the debug port
Use the `tv_launch` tool. If it isn't available yet, launch the desktop app manually with
the remote debug flag:
- **macOS:** `/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222`
- **Windows:** `%LOCALAPPDATA%\TradingView\TradingView.exe --remote-debugging-port=9222`
- **Linux:** `/opt/TradingView/tradingview --remote-debugging-port=9222`

### 6. Verify the connection
Run `tv_health_check`. Expected:
```json
{ "success": true, "cdp_connected": true, "chart_symbol": "...", "api_available": true }
```
If `cdp_connected: false`, TradingView isn't running with the debug port — quit it fully
and relaunch via `tv_launch`. If the MCP returns nothing, restart Claude Code after install.

Then confirm end to end:
- MCP installed and connected: yes/no
- Rules file created at: `~/tradingview-mcp/rules.json`
- TradingView connected on port 9222: yes/no
- Current MNQ (or NQ) price: [number]
- Ready to use: yes/no

## Demo prompts to try once connected
- **Analyst:** "Analyse this MNQ chart and give me the best long and short opportunities
  right now. If you find good setups, ask whether to draw them on the chart."
- **Builder:** "Build me an indicator that plots the 9 and 21 EMA and prints a label on
  each 9/21 crossover. Write the Pine Script, inject it, compile it, fix errors, and save
  it to my account."
- **Assistant:** "Given the current chart, where's the cleanest invalidation if I long
  here, and the first resistance to take partial profit? Use the actual indicators on my
  chart, not general commentary."
- **Automator:** "Scan MNQ, NQ, and QQQ on the daily. Find the ones with the cleanest
  bullish structure (price above the 50 EMA, 9 EMA above 21 EMA). Set a price alert at the
  most recent swing high for each and summarize."

## Credit & links
- Original MCP by **@tradesdontlie**: https://github.com/tradesdontlie/tradingview-mcp
- TradingView Desktop: https://www.tradingview.com/desktop/
- Claude Code: https://www.claude.com/claude-code

*Education, not financial advice. Everything here is for analysis and paper testing.*
