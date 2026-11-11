#!/bin/bash
# Builds Tsubasa.app and Tsubasa-mac-arm64.dmg on an Apple-silicon Mac (or the macOS arm64 GitHub runner).
#
#   bash mac/build_app.sh            -> mac/build/Tsubasa.app and mac/build/Tsubasa-mac-arm64.dmg
#
# The bundle carries its own relocatable Python 3.12 (python-build-standalone, fetched by uv) with mlx-lm (the MLX
# engine) and the document worker's packages, so nothing is installed on the Mac itself. Needs: uv
# (https://docs.astral.sh/uv/) and the Xcode command line tools (sips, iconutil, hdiutil, codesign).
# The app is ad-hoc signed only: the first start needs right-click > Open (no Apple Developer ID).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This build needs macOS on Apple silicon (arm64)." >&2; exit 1
fi
command -v uv >/dev/null || { echo "Install uv first: https://docs.astral.sh/uv/" >&2; exit 1; }

VERSION=$(sed -n "s/^VERSION = '\(.*\)'/\1/p" core/config.py)
OUT="mac/build"; APP="$OUT/Tsubasa.app"; RES="$APP/Contents/Resources"
rm -rf "$OUT"; mkdir -p "$APP/Contents/MacOS" "$RES"

echo "== Python runtime"
uv python install 3.12 --install-dir "$OUT/py"
PYDIR=$(find "$OUT/py" -maxdepth 1 -type d -name 'cpython-3.12*' | head -n 1)
[[ -n "$PYDIR" ]] || { echo "uv did not provide a Python 3.12" >&2; exit 1; }
cp -R "$PYDIR" "$RES/python"; rm -rf "$OUT/py"
PY="$RES/python/bin/python3"
uv pip install --python "$PY" --break-system-packages mlx-lm -r tools/file-worker-requirements.txt
"$PY" -c "import mlx_lm, pymupdf, docx, openpyxl; print('packages ok, mlx-lm', mlx_lm.__version__)"

echo "== App files"
mkdir -p "$RES/app"
cp app.py LICENSE README.md MAC.md THIRD-PARTY-NOTICES.txt CHANGELOG.md "$RES/app/"
for d in core web tools vendor library licenses; do cp -R "$d" "$RES/app/$d"; done
find "$RES" -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "== Icon"
"$PY" mac/make_icns.py web/tsubasa.ico "$OUT/icon.png"
ICONSET="$OUT/Tsubasa.iconset"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$OUT/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); sips -z $d $d "$OUT/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$RES/Tsubasa.icns"; rm -rf "$ICONSET" "$OUT/icon.png"

echo "== Bundle"
cat > "$APP/Contents/MacOS/Tsubasa" <<'EOF'
#!/bin/bash
# Tsubasa launcher: the bundled Python runs the local server, which opens the window and starts the MLX engine.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec "$RES/python/bin/python3" -B "$RES/app/app.py" --start-engine
EOF
chmod +x "$APP/Contents/MacOS/Tsubasa"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Tsubasa</string>
  <key>CFBundleDisplayName</key><string>Tsubasa</string>
  <key>CFBundleIdentifier</key><string>io.github.alexandergubric.tsubasa</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleExecutable</key><string>Tsubasa</string>
  <key>CFBundleIconFile</key><string>Tsubasa</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>13.5</string>
  <key>LSArchitecturePriority</key><array><string>arm64</string></array>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>© 2026 Alexander Gubric</string>
</dict></plist>
EOF
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "note: ad-hoc signing skipped"

echo "== Disk image"
DMGROOT="$OUT/dmg"; mkdir -p "$DMGROOT"
cp -R "$APP" "$DMGROOT/"; ln -s /Applications "$DMGROOT/Applications"
hdiutil create -volname "Tsubasa ${VERSION}" -srcfolder "$DMGROOT" -ov -format UDZO "$OUT/Tsubasa-mac-arm64.dmg" >/dev/null
rm -rf "$DMGROOT"
du -sh "$APP" "$OUT/Tsubasa-mac-arm64.dmg"
echo "Built Tsubasa ${VERSION}: $OUT/Tsubasa-mac-arm64.dmg"
