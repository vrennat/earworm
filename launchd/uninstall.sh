#!/usr/bin/env bash
# Unload + remove the earworm launchd agents.
set -euo pipefail
UID_NUM="$(id -u)"
LA="$HOME/Library/LaunchAgents"
# Includes the retired autogen/run agents so an uninstall from an older install
# still cleans up fully.
for label in com.earworm.watch com.earworm.daily com.earworm.autogen com.earworm.run; do
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    rm -f "$LA/$label.plist"
    echo "removed $label"
done
echo "done."
