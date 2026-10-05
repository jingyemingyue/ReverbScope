#!/bin/sh
# Import the Developer ID Application certificate into a temporary keychain
# on a CI runner, so that codesign can use it without a password prompt
# (docs/RELEASE_PLAN.md §3b, step 1). Nothing in the release workflow calls
# this unless every signing secret is set; community builds stay ad hoc.
#
# Environment:
#   MACOS_CERTIFICATE_P12_BASE64  the .p12 export (certificate + private key), base64
#   MACOS_CERTIFICATE_PASSWORD    the password chosen when exporting the .p12
#   RUNNER_TEMP                   a scratch directory (set by GitHub Actions)
#
# Prints the keychain path; delete it afterwards with
#   security delete-keychain "$KEYCHAIN"
set -eu
: "${MACOS_CERTIFICATE_P12_BASE64:?}" "${MACOS_CERTIFICATE_PASSWORD:?}" "${RUNNER_TEMP:?}"

KEYCHAIN="$RUNNER_TEMP/reverbscope-signing.keychain-db"
P12="$RUNNER_TEMP/reverbscope-signing.p12"
# A random password for the throwaway keychain; it never leaves the runner.
KEYCHAIN_PASSWORD="$(openssl rand -base64 24)"

umask 077
printf '%s' "$MACOS_CERTIFICATE_P12_BASE64" | base64 --decode > "$P12"
trap 'rm -f "$P12"' EXIT HUP INT TERM

security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security import "$P12" -k "$KEYCHAIN" -P "$MACOS_CERTIFICATE_PASSWORD" -f pkcs12 \
  -T /usr/bin/codesign -T /usr/bin/security
# Let codesign use the key without a UI prompt.
security set-key-partition-list -S apple-tool:,apple: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN" > /dev/null
# Search the new keychain first, then the existing user keychains.
# shellcheck disable=SC2046
security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')

# The identity must be a Developer ID Application certificate with its key.
if ! security find-identity -v -p codesigning "$KEYCHAIN" | grep -q 'Developer ID Application'; then
  echo "no valid 'Developer ID Application' identity in the imported .p12" >&2
  security delete-keychain "$KEYCHAIN"
  exit 1
fi
echo "$KEYCHAIN"
