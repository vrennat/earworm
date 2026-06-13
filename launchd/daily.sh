#!/usr/bin/env bash
# Daily episode producer — composed entirely from the stock earworm CLI. The
# com.earworm.daily launchd agent runs this once a day. It reproduces the
# intended "ensure a topic, then run one" behavior WITHOUT any custom CLI flag:
#
#   1. reset-stale   requeue any topic stuck 'running' from a killed prior run
#   2. autogen       propose a small batch ONLY when the queue has no pending topic
#   3. run           drain exactly one pending topic -> one script
#
# The always-on `watch` daemon renders + publishes the resulting script, so this
# yields exactly one new episode per day. Surplus topics autogen proposes carry
# over as buffer and are consumed on later days (autogen only fires when dry, so
# the queue stays bounded).
set -u

EARWORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EARWORM="$EARWORM_DIR/.venv/bin/earworm"
DB="$EARWORM_DIR/earworm.db"

cd "$EARWORM_DIR" || exit 1

# 1. Crash recovery: a SIGKILLed prior run leaves its topic 'running' and
#    next_pending() ignores 'running' rows, so it would be orphaned. Requeue it.
"$EARWORM" reset-stale

# 2. Top up ONLY when the queue is dry, so the buffer can't grow unbounded.
#    sqlite3 ships with macOS; the db path is fixed by project_root() (repo root).
pending="$(/usr/bin/sqlite3 "$DB" "SELECT COUNT(*) FROM topics WHERE status='pending';" 2>/dev/null || echo 0)"
if [ "${pending:-0}" -eq 0 ]; then
    echo "[daily] queue empty -> autogen --count 3"
    "$EARWORM" autogen --count 3
else
    echo "[daily] $pending pending topic(s) in queue -> draining one"
fi

# 3. Drain exactly one. A non-zero exit (pipeline error, or a still-empty queue
#    if autogen produced nothing) is surfaced to launchd and logged to daily.log.
exec "$EARWORM" run
