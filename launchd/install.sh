#!/usr/bin/env bash
# Install the earworm launchd agents: substitute paths into the plist templates,
# copy to ~/Library/LaunchAgents, and (re)load them.
#
#   bash launchd/install.sh
#
# Re-run any time after moving the repo or editing a template. Uninstall with
# launchd/uninstall.sh. Logs land in <repo>/logs/.
set -euo pipefail

EARWORM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LA="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
PATH_VAL="$EARWORM_DIR/.venv/bin:$HOME/.local/bin:/opt/homebrew/bin:$HOME/.bun/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$LA" "$EARWORM_DIR/logs"

for label in com.earworm.watch com.earworm.autogen com.earworm.run; do
    src="$EARWORM_DIR/launchd/$label.plist"
    dst="$LA/$label.plist"
    sed -e "s#__EARWORM_DIR__#$EARWORM_DIR#g" \
        -e "s#__PATH__#$PATH_VAL#g" \
        -e "s#__HOME__#$HOME#g" \
        "$src" > "$dst"
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_NUM" "$dst"
    echo "loaded $label"
done

launchctl kickstart -k "gui/$UID_NUM/com.earworm.watch" 2>/dev/null || true
echo
echo "Installed. The renderer (watch) is running now; autogen fires Mon 07:00,"
echo "run drains the queue weekdays 07:30. Logs: $EARWORM_DIR/logs/"
echo "Verify with: launchctl list | grep earworm"
