#!/usr/bin/env bash
# Install the earworm launchd agents: substitute paths into the plist templates,
# copy to ~/Library/LaunchAgents, and (re)load them.
#
#   bash launchd/install.sh
#
# Agents installed:
#   com.earworm.watch  always-on renderer (renders inbox scripts -> mp3 -> publish)
#   com.earworm.daily  07:00 daily producer (launchd/daily.sh): one episode/day
#
# Re-run any time after moving the repo or editing a template. Uninstall with
# launchd/uninstall.sh. Logs land in <repo>/logs/.
set -euo pipefail

EARWORM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LA="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
PATH_VAL="$EARWORM_DIR/.venv/bin:$HOME/.local/bin:/opt/homebrew/bin:$HOME/.bun/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$LA" "$EARWORM_DIR/logs"

# Retire the old split agents (weekly autogen + weekday run). The single daily
# producer below supersedes them; left loaded they would double up.
for old in com.earworm.autogen com.earworm.run; do
    launchctl bootout "gui/$UID_NUM/$old" 2>/dev/null || true
    rm -f "$LA/$old.plist"
done

# The daily agent runs this wrapper directly.
chmod +x "$EARWORM_DIR/launchd/daily.sh"

for label in com.earworm.watch com.earworm.daily; do
    src="$EARWORM_DIR/launchd/$label.plist"
    dst="$LA/$label.plist"
    sed -e "s#__EARWORM_DIR__#$EARWORM_DIR#g" \
        -e "s#__PATH__#$PATH_VAL#g" \
        -e "s#__HOME__#$HOME#g" \
        "$src" > "$dst"
    # bootout is async: the label can linger mid-teardown and make an immediate
    # bootstrap fail with EIO (error 5). Wait for it to clear, then retry.
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        launchctl print "gui/$UID_NUM/$label" >/dev/null 2>&1 || break
        sleep 1
    done
    for attempt in 1 2 3 4 5; do
        if launchctl bootstrap "gui/$UID_NUM" "$dst" 2>/dev/null; then
            break
        fi
        if [ "$attempt" = 5 ]; then
            echo "ERROR: failed to bootstrap $label after retries" >&2
            exit 1
        fi
        sleep 1
    done
    echo "loaded $label"
done

launchctl kickstart -k "gui/$UID_NUM/com.earworm.watch" 2>/dev/null || true
echo
echo "Installed. The renderer (watch) is running now; the daily producer fires"
echo "every day at 07:00 (one fresh episode/day). Logs: $EARWORM_DIR/logs/"
echo "Verify with: launchctl list | grep earworm"
