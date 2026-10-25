#!/bin/bash
# Ensure the launchd-managed ensemble server is up, then let the caller open the UI.
set -u
UID_NUM="$(id -u)"
URL="http://127.0.0.1:8765"

health() {
  curl -fsS -m 1 "$URL/api/health" >/dev/null 2>&1
}

if ! health; then
  launchctl enable "gui/$UID_NUM/local.ensemble.web" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/$UID_NUM/local.ensemble.web" >/dev/null 2>&1 || true
  for _ in $(seq 1 40); do
    health && break
    sleep 0.25
  done
fi

if health; then
  echo "ok"
else
  echo "failed"
  exit 1
fi
