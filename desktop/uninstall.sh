#!/bin/bash
set -u
UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM/local.ensemble.web" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/local.ensemble.web.plist"
rm -f "$HOME/Desktop/Ensemble.webloc"
rm -rf "$HOME/Applications/Ensemble.app"
rm -rf "$HOME/.ensemble/app"
if command -v dockutil >/dev/null 2>&1; then
  dockutil --remove Ensemble --no-restart >/dev/null 2>&1 || true
  killall Dock 2>/dev/null || true
fi

python3 - <<'PY'
import plistlib, subprocess, os
tmp = "/tmp/ensemble-dock-export.plist"
try:
    subprocess.run(["defaults", "export", "com.apple.dock", tmp], check=True, capture_output=True)
    with open(tmp, "rb") as fh:
        data = plistlib.load(fh)
    target = "file://" + os.path.expanduser("~/Applications/Ensemble.app") + "/"
    apps = data.get("persistent-apps") or []
    kept = [entry for entry in apps if (entry.get("tile-data", {}).get("file-data", {}) or {}).get("_CFURLString") != target]
    if len(kept) != len(apps):
        data["persistent-apps"] = kept
        with open(tmp, "wb") as fh:
            plistlib.dump(data, fh)
        subprocess.run(["defaults", "import", "com.apple.dock", tmp], check=True)
        subprocess.run(["killall", "Dock"], check=False)
except Exception:
    pass
PY
echo "removed Desktop shortcut, launch agent and runtime copy (runs left intact)"
