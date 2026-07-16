#!/usr/bin/env bash
# Schedule the MNQ memory bot to run --scan once a day on macOS (via launchd).
# Usage:  bash schedule/install-macos.sh [HOUR]
#   HOUR = local hour to run, 0-23 (default 17 = 5pm, after the futures daily close).
set -euo pipefail

HOUR="${1:-17}"
LABEL="com.valy.mnqbot"
BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"      # .../trading/backtest-bot
PY="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$BOT_DIR/data/bot.log"

mkdir -p "$HOME/Library/LaunchAgents" "$BOT_DIR/data"

# certifi path if available, so the scheduled (minimal-env) run can verify HTTPS.
CERT="$("$PY" -m certifi 2>/dev/null || true)"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$BOT_DIR/run.py</string>
    <string>--scan</string>
  </array>
  <key>WorkingDirectory</key><string>$BOT_DIR</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
$( [ -n "$CERT" ] && printf '  <key>EnvironmentVariables</key>\n  <dict><key>SSL_CERT_FILE</key><string>%s</string></dict>\n' "$CERT" )
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✅ Scheduled '$LABEL' to run --scan every day at ${HOUR}:00 local time."
echo "   Working dir : $BOT_DIR"
echo "   Log file    : $LOG"
echo
echo "   Watch it live : tail -f \"$LOG\""
echo "   Run once now  : launchctl start $LABEL"
echo "   Stop & remove : bash schedule/uninstall-macos.sh"
echo
echo "Tip: run 'python3 run.py --forward --days 650' first to seed the bot's memory"
echo "     with what it has already learned from real MNQ history."
