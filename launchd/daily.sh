#!/usr/bin/env bash
# Daily episode producer — composed entirely from the stock earworm CLI. The
# com.earworm.daily launchd agent runs this once a day. It reproduces the
# intended "ensure topics, then run a few" behavior WITHOUT any custom CLI flag:
#
#   1. reset-stale   requeue any topic stuck 'running' from a killed prior run
#   2. autogen       top the queue up to EPISODES_PER_DAY pending topics
#   3. run x N       drain exactly EPISODES_PER_DAY pending topics -> N scripts
#
# The always-on `watch` daemon renders + publishes the resulting scripts, so this
# yields EPISODES_PER_DAY new episodes per day. The queue is topped up to exactly
# the day's quota and then drained to it, so the buffer stays bounded near zero.
set -u

# How many episodes to produce per daily run.
EPISODES_PER_DAY=3

EARWORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EARWORM="$EARWORM_DIR/.venv/bin/earworm"
DB="$EARWORM_DIR/earworm.db"

cd "$EARWORM_DIR" || exit 1

# 1. Crash recovery: a SIGKILLed prior run leaves its topic 'running' and
#    next_pending() ignores 'running' rows, so it would be orphaned. Requeue it.
"$EARWORM" reset-stale

# 2. Top up to the day's quota. autogen only fires for the shortfall, so the
#    buffer can't grow unbounded. sqlite3 ships with macOS; the db path is fixed
#    by project_root() (repo root).
pending="$(/usr/bin/sqlite3 "$DB" "SELECT COUNT(*) FROM topics WHERE status='pending';" 2>/dev/null || echo 0)"
need=$(( EPISODES_PER_DAY - ${pending:-0} ))
if [ "$need" -gt 0 ]; then
    echo "[daily] $pending pending, need $EPISODES_PER_DAY -> autogen --count $need"
    "$EARWORM" autogen --count "$need"
else
    echo "[daily] $pending pending topic(s) in queue (>= $EPISODES_PER_DAY) -> draining $EPISODES_PER_DAY"
fi

# 3. Drain exactly EPISODES_PER_DAY, one at a time. Each `earworm run` takes the
#    oldest pending topic. A failed run (pipeline error or a dry queue if autogen
#    produced nothing) is logged and counted; we keep going and surface a non-zero
#    exit to launchd if any of them failed.
failed=0
for i in $(seq 1 "$EPISODES_PER_DAY"); do
    echo "[daily] run $i/$EPISODES_PER_DAY"
    if ! "$EARWORM" run; then
        echo "[daily] run $i/$EPISODES_PER_DAY failed" >&2
        failed=$(( failed + 1 ))
    fi
done

if [ "$failed" -gt 0 ]; then
    echo "[daily] $failed of $EPISODES_PER_DAY run(s) failed" >&2
    exit 1
fi
echo "[daily] produced $EPISODES_PER_DAY script(s)"
