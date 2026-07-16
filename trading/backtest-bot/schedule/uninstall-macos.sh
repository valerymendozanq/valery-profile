#!/usr/bin/env bash
# Stop and remove the scheduled MNQ memory bot.
set -euo pipefail
LABEL="com.valy.mnqbot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "🛑 Removed the daily schedule ($LABEL). The bot will no longer run on its own."
echo "   Your memory files (data/ledger.csv, data/learnings.md) are left untouched."
