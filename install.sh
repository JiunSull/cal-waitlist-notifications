#!/bin/bash
# Runs the watcher in the background whenever you're logged in (macOS launchd).
#
#   bash install.sh                 # install or update
#   NTFY_TOPIC=your-topic bash install.sh   # also push to your phone via ntfy
#   bash install.sh --uninstall     # stop and remove
set -euo pipefail
LABEL="local.waitlist-watch"
DEST="$HOME/.waitlist_watch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Stopped and removed. (Files left in $DEST; delete them if you like.)"
  exit 0
fi

if [ ! -f "$HERE/config.json" ]; then
  echo "No config.json yet. Run: cp config.example.json config.json  (then edit it)" >&2
  exit 1
fi

PY="$(command -v python3)"
mkdir -p "$DEST" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cp "$HERE/waitlist_watch.py" "$HERE/config.json" "$DEST/"

ENV_BLOCK=""
if [ -n "${NTFY_TOPIC:-}" ]; then
  ENV_BLOCK="<key>EnvironmentVariables</key><dict><key>NTFY_TOPIC</key><string>${NTFY_TOPIC}</string></dict>"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DEST/waitlist_watch.py</string></array>
  $ENV_BLOCK
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/waitlist_watch.out</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/waitlist_watch.out</string>
</dict></plist>
EOF
chmod 600 "$PLIST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Running. You should get a 'Now watching' notification in a few seconds."
echo "Log: tail -f ~/Library/Logs/waitlist_watch.log"
