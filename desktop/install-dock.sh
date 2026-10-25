#!/bin/bash
# Build ~/Applications/Ensemble.app (minimal shell app) and pin it to the Dock.
set -euo pipefail
APP="$HOME/Applications/Ensemble.app"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
command -v dockutil >/dev/null 2>&1 || { echo "dockutil is required: brew install dockutil" >&2; exit 1; }
mkdir -p "$HOME/Applications"

python3 - "$WORK" <<'PY'
import sys
from PIL import Image, ImageDraw
work = sys.argv[1]
size = 1024
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((32, 32, size - 32, size - 32), radius=210, fill=(17, 27, 41, 255))
colors = [(91, 91, 214), (139, 92, 246), (47, 107, 255), (11, 143, 106)]
cell, gap = 300, 32
start = (size - (cell * 2 + gap)) // 2
for index, color in enumerate(colors):
    x = start + (index % 2) * (cell + gap)
    y = start + (index // 2) * (cell + gap)
    d.rounded_rectangle((x, y, x + cell, y + cell), radius=58, fill=color + (255,))
img.save(f"{work}/icon_1024.png")
PY
mkdir -p "$WORK/Ensemble.iconset"
for s in 16 32 64 128 256 512; do
  sips -z "$s" "$s" "$WORK/icon_1024.png" --out "$WORK/Ensemble.iconset/icon_${s}x${s}.png" >/dev/null
done
sips -z 32 32 "$WORK/icon_1024.png" --out "$WORK/Ensemble.iconset/icon_16x16@2x.png" >/dev/null
sips -z 64 64 "$WORK/icon_1024.png" --out "$WORK/Ensemble.iconset/icon_32x32@2x.png" >/dev/null
sips -z 256 256 "$WORK/icon_1024.png" --out "$WORK/Ensemble.iconset/icon_128x128@2x.png" >/dev/null
sips -z 512 512 "$WORK/icon_1024.png" --out "$WORK/Ensemble.iconset/icon_256x256@2x.png" >/dev/null
cp "$WORK/icon_1024.png" "$WORK/Ensemble.iconset/icon_512x512@2x.png"
iconutil -c icns "$WORK/Ensemble.iconset" -o "$WORK/Ensemble.icns"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$WORK/Ensemble.icns" "$APP/Contents/Resources/Ensemble.icns"

cat > "$APP/Contents/MacOS/Ensemble" <<'SHELL'
#!/bin/bash
UID_NUM="$(/usr/bin/id -u)"
URL="http://127.0.0.1:8765"
if ! /usr/bin/curl -fsS -m 1 "$URL/api/health" >/dev/null 2>&1; then
  /bin/launchctl enable "gui/$UID_NUM/local.ensemble.web" >/dev/null 2>&1 || true
  /bin/launchctl kickstart -k "gui/$UID_NUM/local.ensemble.web" >/dev/null 2>&1 || true
  i=0
  while [ "$i" -lt 40 ]; do
    /usr/bin/curl -fsS -m 1 "$URL/api/health" >/dev/null 2>&1 && break
    /bin/sleep 0.25
    i=$((i + 1))
  done
fi
if /usr/bin/curl -fsS -m 1 "$URL/api/health" >/dev/null 2>&1; then
  /usr/bin/open "$URL"
else
  /usr/bin/osascript -e 'display alert "Ensemble did not start" message "Check ~/.ensemble/web.log." as critical' >/dev/null 2>&1
fi
SHELL
chmod 755 "$APP/Contents/MacOS/Ensemble"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleDisplayName</key><string>Ensemble</string>
  <key>CFBundleExecutable</key><string>Ensemble</string>
  <key>CFBundleIconFile</key><string>Ensemble</string>
  <key>CFBundleIdentifier</key><string>local.ensemble.launcher3</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>Ensemble</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
codesign --force --deep --sign - "$APP" >/dev/null 2>&1

dockutil --remove Ensemble --no-restart >/dev/null 2>&1 || true
dockutil --add "$APP" --label Ensemble --no-restart >/dev/null
killall Dock 2>/dev/null || true
echo "pinned $APP to the Dock"
