#!/bin/bash
# Install the ensemble runtime + LaunchAgent + Desktop shortcut.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$HOME/.ensemble/app"
PLIST="$HOME/Library/LaunchAgents/local.ensemble.web.plist"
LABEL="local.ensemble.web"
UID_NUM="$(id -u)"
WEBLOC="$HOME/Desktop/Ensemble.webloc"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.ensemble" "$RUNTIME/web"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME/web"
cp "$ROOT/ensemble.py" "$ROOT/serve.py" "$RUNTIME/"
cp "$ROOT/web/index.html" "$ROOT/web/app.css" "$ROOT/web/app.js" "$RUNTIME/web/"

cat > "$RUNTIME/serve.sh" <<'SERVE'
#!/bin/bash
export PATH="$HOME/.local/bin:$HOME/.kimi-code/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
export ENSEMBLE_HOME="${ENSEMBLE_HOME:-$HOME/.ensemble}"
cd "$HOME/.ensemble/app" || exit 2
exec "$HOME/.ensemble/app/ensemble.py" web --port 8765 --no-open
SERVE
chmod 755 "$RUNTIME/serve.sh" "$RUNTIME/ensemble.py"

python3 - "$RUNTIME" "$HOME" "$PLIST" <<'PY'
import plistlib, sys
runtime, home, path = sys.argv[1], sys.argv[2], sys.argv[3]
data = {
    "Label": "local.ensemble.web",
    "ProgramArguments": ["/bin/bash", f"{runtime}/serve.sh"],
    "WorkingDirectory": runtime,
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 5,
    "StandardOutPath": f"{home}/.ensemble/web.log",
    "StandardErrorPath": f"{home}/.ensemble/web.log",
    "EnvironmentVariables": {
        "PATH": f"{home}/.local/bin:{home}/.kimi-code/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONUNBUFFERED": "1",
    },
}
with open(path, "wb") as fh:
    plistlib.dump(data, fh)
PY
chmod 644 "$PLIST"

launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl enable "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" 2>/dev/null || true
launchctl kickstart -k "gui/$UID_NUM/$LABEL" 2>/dev/null || true

for _ in $(seq 1 60); do
  curl -fsS -m 1 "http://127.0.0.1:8765/api/health" >/dev/null 2>&1 && break
  sleep 0.25
done

python3 - "$WEBLOC" <<'PY'
import plistlib, sys
with open(sys.argv[1], "wb") as fh:
    plistlib.dump({"URL": "http://127.0.0.1:8765"}, fh)
PY
xattr -cr "$WEBLOC" 2>/dev/null || true

"$ROOT/desktop/install-dock.sh"

if curl -fsS -m 1 "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
  echo "installed  $WEBLOC"
  echo "runtime    $RUNTIME"
  echo "agent      $PLIST"
else
  echo "runtime installed, but the server did not come up; see ~/.ensemble/web.log" >&2
  exit 1
fi
