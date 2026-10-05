#!/bin/sh
# Sign, notarize and staple a ReverbScope disk image, then check that
# Gatekeeper accepts both the image and the app inside it
# (docs/RELEASE_PLAN.md §3b, steps 3-5). Run only with a Developer ID;
# the app inside must already be signed with sign_app.sh --identity.
#
#   notarize_dmg.sh DMG
#
# Environment:
#   MACOS_SIGNING_IDENTITY   "Developer ID Application: NAME (TEAMID)"
#   APPLE_API_KEY_P8_BASE64  App Store Connect API key (.p8), base64
#   APPLE_API_KEY_ID         its Key ID
#   APPLE_API_ISSUER_ID      the Issuer ID shown on the same page
#   RUNNER_TEMP              a scratch directory (set by GitHub Actions)
set -eu
DMG="${1:?usage: notarize_dmg.sh DMG}"
: "${MACOS_SIGNING_IDENTITY:?}" "${APPLE_API_KEY_P8_BASE64:?}" "${APPLE_API_KEY_ID:?}"
: "${APPLE_API_ISSUER_ID:?}" "${RUNNER_TEMP:?}"

WORK="$(mktemp -d "$RUNNER_TEMP/notarize.XXXXXX")"
MOUNT="$WORK/mount"
KEY="$WORK/AuthKey_$APPLE_API_KEY_ID.p8"
cleanup() {
  if [ -d "$MOUNT" ]; then hdiutil detach "$MOUNT" -quiet || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT HUP INT TERM
umask 077
printf '%s' "$APPLE_API_KEY_P8_BASE64" | base64 --decode > "$KEY"

# 3. Sign the disk image itself, with a secure timestamp.
codesign --sign "$MACOS_SIGNING_IDENTITY" --timestamp --force "$DMG"
codesign --verify --strict --verbose=2 "$DMG"

# 4. Notarize. The log is printed even when the submission is accepted:
#    warnings there become errors in later notarization rules.
set -- --key "$KEY" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER_ID"
xcrun notarytool submit "$DMG" "$@" --wait --timeout 45m --output-format json > "$WORK/submit.json"
cat "$WORK/submit.json"
ID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["id"])' "$WORK/submit.json")"
STATUS="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["status"])' "$WORK/submit.json")"
xcrun notarytool log "$ID" "$@" || true
if [ "$STATUS" != "Accepted" ]; then
  echo "notarization of $DMG ended with status $STATUS" >&2
  exit 1
fi

# 5. Staple the ticket so the image opens offline, then ask Gatekeeper.
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"
spctl -a -t open -vvv --context context:primary-signature "$DMG"
mkdir "$MOUNT"
hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MOUNT" -quiet
spctl -a -t exec -vvv "$MOUNT/ReverbScope.app"
codesign --verify --deep --strict --verbose=2 "$MOUNT/ReverbScope.app"
echo "notarized and stapled: $DMG"
