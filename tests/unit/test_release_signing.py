"""The Developer ID path in the release workflow stays off until the
maintainer sets every signing secret, never runs on pull requests, and hands
secrets only to the steps that need them (docs/RELEASE_PLAN.md §3b)."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
SECRETS = {
    "MACOS_CERTIFICATE_P12_BASE64",
    "MACOS_CERTIFICATE_PASSWORD",
    "MACOS_SIGNING_IDENTITY",
    "APPLE_API_KEY_P8_BASE64",
    "APPLE_API_KEY_ID",
    "APPLE_API_ISSUER_ID",
}
GATE = "if: steps.devid.outputs.enabled == 'true'"


def _bundle_steps() -> dict[str, str]:
    job = WORKFLOW[WORKFLOW.index("\n  bundle:") : WORKFLOW.index("\n  sbom:")]
    blocks = re.split(r"\n      - ", job)[1:]
    steps: dict[str, str] = {}
    for block in blocks:
        match = re.search(r"name: (.+)", block)
        if match:
            steps[match.group(1).strip()] = block
    return steps


def test_secrets_reach_only_the_gate_and_the_gated_steps() -> None:
    steps = _bundle_steps()
    using = {name: body for name, body in steps.items() if "secrets." in body}
    assert set(using) == {
        "Developer ID signing configured?",
        "Developer ID signature",
        "Notarize and staple the disk image",
    }
    for name, body in using.items():
        assert set(re.findall(r"secrets\.(\w+)", body)) <= SECRETS
        if name != "Developer ID signing configured?":
            assert GATE in body
    # No other job reads a signing secret.
    outside = WORKFLOW
    for body in using.values():
        assert body in outside
        outside = outside.replace(body, "")
    assert not SECRETS & set(re.findall(r"secrets\.(\w+)", outside))


def test_the_gate_needs_all_six_secrets_and_skips_pull_requests() -> None:
    gate = _bundle_steps()["Developer ID signing configured?"]
    assert set(re.findall(r"secrets\.(\w+)", gate)) == SECRETS
    assert '"$set_count" -ne 6' in gate and "exit 1" in gate
    assert '"$GITHUB_EVENT_NAME" = pull_request' in gate
    assert "enabled=false" in gate and "enabled=true" in gate


def test_notarization_runs_before_the_dmg_check_and_the_checksums() -> None:
    names = list(_bundle_steps())
    order = [
        "Check macOS .app and its licenses",
        "Rehearse the Developer ID layout (hardened runtime, ad hoc)",
        "Developer ID signature",
        "macOS disk image",
        "Notarize and staple the disk image",
        "Check macOS disk image",
        "Remove the signing keychain",
        "Checksums of distributable files",
    ]
    assert [names.index(n) for n in order] == sorted(names.index(n) for n in order)
    cleanup = _bundle_steps()["Remove the signing keychain"]
    assert "always()" in cleanup


def test_signing_scripts_refuse_to_run_without_their_inputs() -> None:
    importer = Path("packaging/macos/import_certificate.sh").read_text(encoding="utf-8")
    notarize = Path("packaging/macos/notarize_dmg.sh").read_text(encoding="utf-8")
    for name in ("MACOS_CERTIFICATE_P12_BASE64", "MACOS_CERTIFICATE_PASSWORD"):
        assert f"{name}:?" in importer
    for name in ("MACOS_SIGNING_IDENTITY", "APPLE_API_KEY_P8_BASE64", "APPLE_API_KEY_ID"):
        assert f"{name}:?" in notarize
    assert "Developer ID Application" in importer
    assert '"$STATUS" != "Accepted"' in notarize
    assert "stapler staple" in notarize and "stapler validate" in notarize
    assert "spctl -a -t exec" in notarize
