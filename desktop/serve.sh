#!/bin/bash
# Foreground server process managed by launchd.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:$HOME/.kimi-code/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
export ENSEMBLE_HOME="${ENSEMBLE_HOME:-$HOME/.ensemble}"
cd "$ROOT" || exit 2
exec "$ROOT/ensemble.py" web --port 8765 --no-open
