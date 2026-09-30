#!/bin/sh
# Sign RoomScope.app from the inside out (Apple TN2206; "Creating
# distribution-signed code for macOS"): every loose Mach-O file under
# Contents/Frameworks, then each nested .framework deepest first, then the
# app, which signs Contents/MacOS/RoomScope. codesign --deep is used only to
# verify: Apple advises against it for signing, because it applies one set
# of options to every nested item. Entitlements go on the app only.
#
#   sign_app.sh APP                 ad hoc, as released today (no Developer ID
#                                   exists); no hardened runtime, no entitlements
#   sign_app.sh APP --runtime       ad hoc with the hardened runtime and
#                                   entitlements-adhoc.plist: a CI rehearsal of
#                                   the Developer ID layout (see RELEASE_PLAN.md)
#   sign_app.sh APP --identity "Developer ID Application: NAME (TEAMID)"
#                                   hardened runtime, secure timestamp and
#                                   entitlements.plist, ready for notarization
#                                   (not run yet: no certificate)
set -eu
APP="${1:?usage: sign_app.sh APP [--runtime | --identity IDENTITY]}"
shift
HERE="$(cd "$(dirname "$0")" && pwd)"
IDENTITY="-"
RUNTIME=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --runtime) RUNTIME=1 ;;
    --identity) shift; IDENTITY="${1:?--identity needs a value}"; RUNTIME=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
if [ ! -d "$APP/Contents/MacOS" ]; then
  echo "not an app bundle: $APP" >&2
  exit 1
fi

# Nested code: identity, --force, and a secure timestamp for Developer ID.
# No entitlements and no hardened runtime on libraries (Apple: "Don't apply
# entitlements to library code").
if [ "$IDENTITY" = "-" ]; then
  set -- --sign - --force
else
  set -- --sign "$IDENTITY" --force --timestamp
fi

FRAMEWORKS="$APP/Contents/Frameworks"
if [ -d "$FRAMEWORKS" ]; then
  find "$FRAMEWORKS" -type f ! -path '*.framework/*' | while IFS= read -r file; do
    case "$(file -b "$file")" in
      Mach-O*) codesign "$@" "$file" ;;
    esac
  done
  find "$FRAMEWORKS" -type d -name '*.framework' | awk -F/ '{ print NF "\t" $0 }' |
    sort -rn | cut -f2- | while IFS= read -r framework; do
      codesign "$@" "$framework"
    done
fi

if [ "$RUNTIME" = 1 ]; then
  if [ "$IDENTITY" = "-" ]; then
    # An ad hoc signature has no Team ID, so library validation would refuse
    # the app's own libraries; only this rehearsal file disables it.
    ENTITLEMENTS="$HERE/entitlements-adhoc.plist"
  else
    ENTITLEMENTS="$HERE/entitlements.plist"
  fi
  codesign "$@" --options runtime --entitlements "$ENTITLEMENTS" "$APP"
else
  codesign "$@" "$APP"
fi
codesign --verify --deep --strict --verbose=2 "$APP"
