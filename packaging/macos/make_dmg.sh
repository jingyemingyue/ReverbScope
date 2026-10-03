#!/bin/sh
# Wrap ReverbScope.app in an unsigned UDZO disk image (ARCHITECTURE_V1.md §6.2).
set -eu
APP="${1:-dist/ReverbScope.app}"
OUT="${2:-dist/ReverbScope-Desktop-macOS-$(uname -m).dmg}"
if [ ! -d "$APP" ]; then
  echo "missing $APP" >&2
  exit 1
fi
rm -f "$OUT"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT HUP INT TERM
ditto "$APP" "$STAGE/ReverbScope.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname ReverbScope -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "wrote $OUT"
