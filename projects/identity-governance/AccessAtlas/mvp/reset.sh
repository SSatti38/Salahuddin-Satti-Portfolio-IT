#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
rm -f -- "$HERE/data/workspace.sqlite3" "$HERE/data/workspace.sqlite3-wal" "$HERE/data/workspace.sqlite3-shm"
printf '%s\n' 'Removed AccessAtlas local SQLite database and sidecars. The next run starts empty.'
