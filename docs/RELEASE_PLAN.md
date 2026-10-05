# ReverbScope release plan

**English** | [简体中文](RELEASE_PLAN.zh-CN.md)

Status: adopted 2026-09-24. This document says which versions ReverbScope
will cut, what each one must prove before it is cut, and how a release is
mechanically produced. It does not change the scope contract in
[ARCHITECTURE_V1.md](ARCHITECTURE_V1.md) §3; it schedules it. A Chinese
digest is in [RELEASE_PLAN.zh-CN.md](RELEASE_PLAN.zh-CN.md); the English
text is authoritative.

No dates. The exit criteria are the schedule (ARCHITECTURE_V1.md §10).

## 1. Where the project stands (2026-09-24)

* `main` carries the v0.1 foundation plus milestones 0.2 (reopen and
  compare), 0.3 (trust the chain), 0.4 (for everyone) and the 1.0-rc
  *software* items (Placement tab, validation protocol, packaging
  scaffolding, robustness). They were reviewed and merged on 2026-09-24
  (PRs #5, #6, #7, #8); the review findings are GitHub issues #9–#16.
* No tag and no published Release exist yet (v0.4.1 is a draft). The
  repository has been public since 2026-09-24. **Update (2026-09-27):**
  v0.4.1 is prepared as the first *public* pre-release for early testers:
  README and [INSTALLATION.md](INSTALLATION.md) lead with the download, the
  release notes open with *Choose your edition* and *Known limitations*,
  and the release-candidate artifacts were checked (§3c). **Update
  (2026-09-29):** every platform ships a Desktop Edition and a Terminal
  Edition ([EDITIONS.md](EDITIONS.md)), and the `[Unreleased]` entries of
  `CHANGELOG.md` are folded into `[0.4.1]`, so the draft's notes describe
  everything the pre-release contains. It becomes public when the
  maintainer publishes the draft; nothing here publishes it. **Update
  (2026-09-30):** the release candidate is on `main`: PR #24 → #22 → #21,
  merged with merge commits (no squash, no rebase), `main` = `c5fe692`,
  whose tree is #24's head. CI #81 and Release #34 are green on it, and
  Release #34 refreshed the v0.4.1 draft with that commit's 14 files
  (STATUS snapshot 32). PR #23 was closed as superseded by #24. The draft is
  still unpublished. **Close-out update (2026-09-30):** PRs #25 and #26
  are also merged. CI #87 and Release #38 passed on `d97822a`, and the same
  draft was refreshed with that commit's 14 files and corrected testing
  limitations (STATUS snapshot 33). It remains unpublished. **Published
  (2026-09-30):** the draft was published as a pre-release, not as the latest
  release. Tag `v0.4.1` points at `d97822a` and the 14 assets stayed. An
  install on a person's own computer (checklist step 3) is still open.
* **Software beta (2026-10-01):** `0.5.0b1` packages what landed after 0.4.1
  (early/late energy, profile clarity notices, the placement picture, the
  desktop and command-line polish). It does **not** meet the 0.5.0 row:
  no hardware cell is PASS, so 0.5.0 itself is not cut. Publishing
  `v0.5.0b1` does not republish `v0.4.1`.
* **Update (2026-09-24, later the same day):** the review follow-ups
  #9–#17 (#17, the QML part of the bundle gate, was found after this plan
  was written) are fixed on the branch `v0.4.1-review-followups`, which
  sets the version to 0.4.1. Because #17 had to be closed before any
  bundle is published (§4), 0.4.0 is not expected to get a Release of its
  own: once that pull request is merged with CI green, the first draft
  Release is v0.4.1. Nothing else in this plan changes.
* Everything that requires a person in a real room is **not** done: the
  hardware matrix ([HARDWARE_TESTS.md](HARDWARE_TESTS.md)) has no PASS cell
  and the validation campaign ([VALIDATION.md](VALIDATION.md)) has not been
  run. The maintainer has no measurement hardware available in the near
  term, so those items are scheduled last and may be filled by
  contributors after the repository opens.
* Signing identities, the PyPI project name and trusted publishing are
  maintainer decisions and are still open (ARCHITECTURE_V1.md §13); the
  public flip was made on 2026-09-24.

## 2. Version ladder

| Version | Purpose | Must be true before it is cut | Not claimed |
| --- | --- | --- | --- |
| **0.4.0** | First pre-release: everything on `main` today, as a draft Release with unsigned bundles for the maintainer's own testing | CI green on Linux / macOS / Windows and Python 3.12–3.14; `ruff`, `mypy`, the schema job and the bundle gates pass; the license bundle carries the verbatim LGPL-3.0 / GPL-3.0 / PortAudio texts; `CHANGELOG.md` has a `[0.4.0]` section; `docs/STATUS.md` has a dated snapshot | Any hardware result; a person installing a bundle on macOS / Windows; PyPI; public availability |
| **0.4.x** | Software readiness before community hardware validation (the maintainer's phase definition, 2026-09-24): the review follow-ups #9–#17 (all closed in 0.4.1), packaging, device diagnostics, the GUI, the DAW guide and the community report templates | CI and the Release workflow green on the release commit; every new behaviour has a synthetic or scripted test; `CHANGELOG.md` names what changed; no hardware or DAW claim | Any hardware or DAW result; signing; PyPI |
| **0.5.0b1** | Software beta: ship the single-microphone algorithm and the desktop presentation that landed after 0.4.1, still without a hardware claim | CI and the Release workflow green on the release commit; every new behaviour has a synthetic test; CHANGELOG names the version; the notes say this is not 0.5.0 | Any hardware or DAW result; the 0.5.0 exit criteria; signing; PyPI |
| **0.5.0** | "Trusted by a human": the first version whose Standalone Mode and DAW workflow were run on real hardware at least once | One dated PASS row per cell of the hardware matrix on at least one platform (device enumeration, sample-rate negotiation, channel mapping, loopback capture, Stop during playback, a full Standalone measurement, the same signal through one DAW); #12 and #13 (loopback time origin, real-time callback) closed; #14 (zh-CN catalog complete, safety warning translated) closed; #15 (ISO 3382-2 table source) closed | The validation campaign; API / schema freeze; signing |
| **1.0.0rc1** | Freeze and prove (ARCHITECTURE_V1.md §10, row 1.0-rc) | No open MUST item of §3.1: hardware matrix executed at least once per platform (M10); validation campaign published with its data (M11); signed bundles or an explicit maintainer decision to ship unsigned (M9); public-repository checklist executed (M13, §9.1); API and schema integers frozen; SECURITY / CONTRIBUTING / STATUS updated for the freeze; PyPI pre-release if trusted publishing is configured | — |
| **1.0.0** | Release | Fixes from the candidate only; release notes name the validation results and the known limitations | — |

Minor releases between these rows are allowed whenever a MUST or SHOULD
item lands and CI is green on every platform; patch releases are for fixes
only (ARCHITECTURE_V1.md §9.2).

## 3. How a release is produced

The pipeline is `.github/workflows/release.yml`
([source](../.github/workflows/release.yml)). It is driven by the version
in `pyproject.toml`, and the maintainer keeps the last word.

> **Workflow status (2026-09-24).** The version-driven workflow has been on
> `main` since PR #18; the v0.4.1 draft Release was opened from it and is
> refreshed whenever `pyproject.toml`, the workflow, `packaging/`,
> `scripts/smoke_bundle.py`, `scripts/release_draft.py`,
> `scripts/inno_chinese_messages.py` or `src/reverbscope/__main__.py` change
> on `main` while `v0.4.1` has no tag. The
> Windows job builds and installs `ReverbScope-Desktop-Windows-x64-Setup.exe` on every run,
> and every job also builds the Terminal Edition of its platform. Check
> the latest `main` run and the draft's assets before publishing.
>
> **How the draft is refreshed** (`scripts/release_draft.py`, tested in
> `tests/unit/test_release_draft.py`). Each refresh replaces *every* asset,
> the notes, the tag name and the target commit, so the draft holds exactly
> the 14 files of one successful run of the commit it targets (nine downloads
> of the two editions, wheel, sdist, one `SHA256SUMS`, the SBOM and the lock). Files an older
> workflow attached under names no longer produced (`ReverbScope.dmg`,
> `SHA256SUMS-macOS`, ...) are removed. The job stops without changing
> anything when `v<version>` is already published, when two drafts match,
> when a tag `v<version>` points at another commit, or when the draft holds
> a file it does not know (for example one attached by hand: remove it, or
> publish without re-running the workflow). A change under `src/` alone does
> not start the Release workflow; run it by hand (**Actions → Release → Run
> workflow** on `main`) so the draft is rebuilt from the newest commit.
> The first `main` run of this refresh was Release #34 on `c5fe692`
> (2026-09-30): it updated the existing draft 395349087 in place (four files
> replaced, the six earlier names removed, 14 files uploaded) and its
> *Verify the draft* step passed. A later commit that touches none of the
> paths above (for example `docs/` only) leaves the draft on `c5fe692`, and
> publishing then tags `c5fe692`, the commit the files were built from.
> PR #26 later changed the release-notes header: Release #38 refreshed this
> same draft from `d97822a`. The docs-only close-out record leaves it on
> `d97822a`, so that is the commit publishing will tag (STATUS snapshot 33).

1. **Prepare the release commit on `main`.** Set `project.version` in
   `pyproject.toml` to the new version (no `.dev` suffix). Move the
   `[Unreleased]` entries of `CHANGELOG.md` under a `## [<version>] -
   <date>` heading. Add a dated snapshot to `docs/STATUS.md` that says what
   was actually run. Re-check `docs/DEPENDENCIES.md` §3–§4 if any dependency
   version changed. Commit and push (or merge the PR).
2. **CI opens a draft.** Because `pyproject.toml` changed on `main` and no
   tag `v<version>` exists, the workflow runs lint, type-check and the
   test suite, builds sdist and wheel, builds the unsigned bundles on the
   three OS runners (license bundle → PyInstaller → strip GPL-only Qt
   modules and ASIO DLLs → bundle gate → smoke test → archive → checksums),
   produces the SBOM and lock file, and opens or refreshes the **draft**
   GitHub Release named `v<version>` with the release notes
   (`packaging/release-notes-header.md` around the CHANGELOG section) as
   its body and the 14 files attached. **No tag exists at this point.** A
   version containing
   `.dev` never opens a draft.
3. **The maintainer decides.** Download the bundles from the draft and try
   them on a real machine (the `docs/user-guide` Gatekeeper / SmartScreen
   steps apply to unsigned builds). Publish the draft to release, or delete
   it to abort. Publishing creates the tag `v<version>` on the release
   commit — that click is the release decision the project brief reserves
   for the maintainer.
   A tag the maintainer pushes by hand takes the same path: the tag run
   builds everything and opens (or updates) the draft for that tag.
4. **The tag run.** Pushing the tag (which publishing does) re-runs the
   quality gates against the tag and, only if the repository variable
   `REVERBSCOPE_PUBLISH_PYPI` is `true` and the `pypi` environment and PyPI
   trusted publisher exist, uploads the wheel and sdist to PyPI. Until the
   maintainer sets that up, nothing reaches PyPI.

Rules that follow from this: the version in `pyproject.toml` is the single
source of truth (`reverbscope.__version__` reads it from package metadata); a
tag whose name does not equal `v<pyproject version>` fails the workflow;
tags come only from publishing a draft or from the maintainer's own push;
published history is never rewritten.

### 3a. Without GitHub Actions minutes

A private repository spends its own Actions minutes, and macOS runners count
ten times. When they run out, jobs fail within seconds without a runner (no
step runs, no log). Three ways on, from cheapest:

1. **Build locally.** `scripts/build_release.py` runs the release workflow's
   bundle job on the machine it is started on and writes the same file names
   to `dist/`. Run it once per platform: on a Mac with Apple silicon
   (`ReverbScope-Desktop-macOS-arm64.dmg`, `ReverbScope-Terminal-macOS-arm64.tar.gz`),
   an Intel Mac if available (`ReverbScope-Desktop-macOS-x86_64.dmg`,
   `ReverbScope-Terminal-macOS-x86_64.tar.gz`), Windows with Inno Setup 6
   installed (`ReverbScope-Desktop-Windows-x64-Setup.exe`,
   `ReverbScope-Desktop-Windows-x64.zip`, `ReverbScope-Terminal-Windows-x64.zip`) and
   Linux x86_64 (`ReverbScope-Desktop-Linux-x86_64.tar.gz`,
   `ReverbScope-Terminal-Linux-x86_64.tar.gz`); add `--python-dist` on one of them for
   the wheel and sdist. The script installs nothing itself: install
   `requirements/bundle.lock`, the `dev` and `gui` extras, `pyinstaller==6.22.3`
   and `build` as the script's docstring shows; it refuses other versions
   unless `--allow-unlocked`. It runs the test suite, the license bundle, the
   `--strip --require-licenses` gate and the smoke test (CLI, fake-backend
   measurement, offscreen GUI, windowed launcher); on macOS it also ad-hoc
   signs the app and mounts, copies and launches it from the DMG. On
   Windows it compiles the installer but does not install, smoke-test and
   uninstall it as the workflow does (that would change the PC); do those
   three steps by hand before publishing a locally built installer.
2. **Publish by hand.** Create or edit the draft `v<version>` on the Releases
   page (tag `v<version>` on the release commit of `main`, *pre-release*),
   paste the notes (`packaging/release-notes-header.md` with `{version}`
   replaced and the CHANGELOG section at `{changes}`), upload every file from
   step 1 and one `SHA256SUMS` made from each machine's `SHA256SUMS-*` lines,
   and publish. The PyPI job needs Actions;
   without it nothing reaches PyPI, as before.
3. **Make the repository public** (§5): standard GitHub-hosted runners are
   free for public repositories, and the workflow then runs as written.
   Done on 2026-09-24; the workflows have run on GitHub's runners since.

A locally built release has had exactly the checks the script ran on that
machine; `docs/STATUS.md` records which machines built which files.

### 3b. macOS signing: today, and with a Developer ID

**Today** the app is signed ad hoc, which only seals the bundle: it is not a
Developer ID signature, it is not notarized, and Gatekeeper blocks it on first
open (the user guide gives the steps). `packaging/macos/sign_app.sh` signs from
the inside out, as Apple asks for distributed code [A1][A2]: every loose
Mach-O file under `Contents/Frameworks`, each nested `.framework` deepest
first, then the app; `codesign --deep` is used only to verify, because Apple
advises against it for signing [A1][A3]. The released app has no hardened
runtime and no entitlements.

**Rehearsed in CI.** On both macOS runners (arm64, x86_64) the release job signs
a copy of the app with `sign_app.sh --runtime`: hardened runtime and
`entitlements-adhoc.plist`. That copy must start (GUI smoke, fake measurement)
and `reverbscope doctor` must be able to create a cffi callback, the mechanism
PortAudio uses to call ReverbScope from the audio thread. The entitlements, per
key:

| Key | Why | Source |
| --- | --- | --- |
| `com.apple.security.device.audio-input` | Core Audio input (the microphone) under the hardened runtime; without it the system terminates the app | [A4][A5] |
| `com.apple.security.cs.allow-unsigned-executable-memory` | python-sounddevice creates its stream callbacks with cffi's `ffi.callback` (ABI mode); cffi's documentation asks for this key on macOS, and Apple's x86_64 libffi maps writable-and-executable memory without `MAP_JIT` | [A6][A7] |
| `com.apple.security.cs.disable-library-validation` (rehearsal file only) | An ad hoc signature has no Team ID, so library validation would refuse the app's own libraries. A Developer ID build signs everything with one Team ID and does not need it | [A8] |

`entitlements.plist` (the Developer ID file) has the first two keys and never
`get-task-allow`, which notarization rejects [A9].

**With a Developer ID Application certificate** (maintainer decision, §5).
The release workflow already contains these steps; they are skipped until
all six repository secrets below exist, so community and fork builds stay
ad hoc. They never run on pull requests, and a partial set of secrets fails
the build instead of silently shipping an ad hoc DMG. **None of them has run
yet**: no certificate exists.

1. `packaging/macos/import_certificate.sh` imports the `.p12` into a
   temporary keychain and refuses anything but a `Developer ID Application`
   identity; the job deletes the keychain at the end, even on failure.
2. `sign_app.sh dist/ReverbScope.app --identity "$MACOS_SIGNING_IDENTITY"`
   re-signs the app: the same inside-out order, `--timestamp` on every item,
   `--options runtime` with `entitlements.plist` on the app [A2][A9]. The
   step checks the runtime flag, the Developer ID authority and a timestamp,
   then smoke-tests the signed app.
3. `packaging/macos/notarize_dmg.sh` signs the DMG with `--timestamp` [A10];
4. submits it with `xcrun notarytool submit --wait` using an App Store
   Connect API key, prints `notarytool log` even on success and fails unless
   the status is `Accepted` [A11][A12];
5. staples the ticket (`stapler staple`, `stapler validate`), then checks
   `spctl -a -t open --context context:primary-signature` on the DMG and
   `spctl -a -t exec` on the mounted app [A12][A13].
6. The SHA-256 sums are computed after stapling (stapling changes the DMG).

| Repository secret | What it holds | Where it comes from |
| --- | --- | --- |
| `MACOS_CERTIFICATE_P12_BASE64` | The Developer ID Application certificate with its private key, exported as `.p12`, base64-encoded (`base64 -i cert.p12 \| pbcopy`) | Apple Developer account ▸ Certificates ▸ `+` ▸ Developer ID Application (Account Holder only); then Keychain Access ▸ export as `.p12` [A14] |
| `MACOS_CERTIFICATE_PASSWORD` | The password chosen for that export | You |
| `MACOS_SIGNING_IDENTITY` | The identity name, e.g. `Developer ID Application: Jane Doe (AB12CD34EF)` | `security find-identity -v -p codesigning` after importing the certificate |
| `APPLE_API_KEY_P8_BASE64` | An App Store Connect API key (`AuthKey_<id>.p8`), base64-encoded | App Store Connect ▸ Users and Access ▸ Integrations ▸ Team Keys ▸ `+` (the `.p8` downloads once) [A15] |
| `APPLE_API_KEY_ID` | That key's Key ID | Same page |
| `APPLE_API_ISSUER_ID` | The Issuer ID shown above the key list | Same page |

A signed and notarized DMG keeps its file name; the release notes, README and
user guide must then drop the Gatekeeper "Open Anyway" steps for that
release (not before a notarized build has been downloaded and opened on a
Mac that never saw it).

**Why two DMGs, not one Universal app.** PyInstaller builds a `universal2`
app only when every collected binary is itself universal2 [A16]. For the
versions pinned in `requirements/bundle.lock` (checked on PyPI 2026-09-27),
NumPy 2.5.3, SciPy 1.18.1, matplotlib 3.11.2, Pillow 12.3.0, contourpy 1.4.0,
cffi 2.1.1 and soundfile 0.14.0 publish only separate `arm64` and `x86_64`
macOS wheels, so the release keeps one DMG per architecture, each built and
tested on a runner of that architecture.

What CI cannot show without the certificate: a Developer ID signature,
library validation with a shared Team ID, secure timestamps, notarization,
stapling, Gatekeeper acceptance, and the microphone permission prompt.

Windows: the installer and executables are not Authenticode-signed; SmartScreen
warns on first run (user guide). This is a known limitation of the 0.x
pre-releases, not an error; signing is the same §5 decision. When a
certificate exists: sign `dist\reverbscope\*.exe` with `signtool sign /fd sha256
/tr <timestamp URL> /td sha256`, then compile the installer with
`iscc "--signtool=signtool=signtool.exe sign … $f" /DSignToolName=signtool`
so that Inno Setup signs the installer and its uninstaller ([W1][W2][W3];
`packaging/windows/reverbscope.iss`). Not run yet.

Sources for §3b (accessed 2026-09-24):

* [A1] Apple, TN2206 "macOS Code Signing In Depth": https://developer.apple.com/library/archive/technotes/tn2206/_index.html
* [A2] Apple, "Creating distribution-signed code for macOS": https://developer.apple.com/documentation/xcode/creating-distribution-signed-code-for-the-mac
* [A3] Apple Developer Forums (DTS), "--deep Considered Harmful": https://developer.apple.com/forums/thread/129980
* [A4] Apple, `com.apple.security.device.audio-input`: https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.device.audio-input
* [A5] Apple, "Requesting authorization to capture and save media": https://developer.apple.com/documentation/avfoundation/requesting-authorization-to-capture-and-save-media
* [A6] cffi documentation, "Callbacks (old style)": https://cffi.readthedocs.io/en/latest/using.html#callbacks
* [A7] Apple, `com.apple.security.cs.allow-unsigned-executable-memory`: https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.allow-unsigned-executable-memory
* [A8] Apple, `com.apple.security.cs.disable-library-validation`: https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation
* [A9] Apple, "Notarizing macOS software before distribution": https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
* [A10] Apple, "Packaging Mac software for distribution": https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution
* [A11] Apple, TN3147 "Migrating to the latest notarization tool": https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool
* [A12] Apple, "Customizing the notarization workflow": https://developer.apple.com/documentation/security/customizing-the-notarization-workflow
* [A13] Apple Developer Forums (DTS), "Testing a Notarised Product": https://developer.apple.com/forums/thread/130560
* [A14] Apple, "Create Developer ID certificates": https://developer.apple.com/help/account/certificates/create-developer-id-certificates/
* [A15] Apple, "Creating API keys for App Store Connect API": https://developer.apple.com/documentation/appstoreconnectapi/creating-api-keys-for-app-store-connect-api
* [A16] PyInstaller manual, "macOS multi-arch support": https://pyinstaller.org/en/stable/feature-notes.html#macos-multi-arch-support
* [W1] Inno Setup Help, `[Setup]: SignTool`: https://jrsoftware.org/ishelp/topic_setup_signtool.htm (and `SignedUninstaller`: https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm)
* [W2] Inno Setup Help, Compiler Command-Line Parameters (`--signtool=<name>=<command>`): https://jrsoftware.org/ishelp/topic_compilercmdline.htm
* [W3] Microsoft Learn, SignTool.exe: https://learn.microsoft.com/en-us/dotnet/framework/tools/signtool-exe

### 3c. Publishing v0.4.1, the first public pre-release

v0.4.1 is the version the README's **Download** button leads to. Its draft
is rebuilt by every `main` run while `v0.4.1` has no tag (§3), so the files
on the draft always come from one run of the newest `main` commit that
touched the Release workflow's paths; the version stays 0.4.1 because
nothing with that number has been published.

**What was checked on the release candidate (2026-09-27, Release run #23,
PR #21 head `b753e17`, build commit `7cb1419`; STATUS snapshot 30).** The file
names are those of that run, before the Desktop and Terminal editions. Later
builds, made from the changed packaging, carry the names in the publish
checklist below; the Terminal Edition archives did not exist at that run.

| File | Check | Result |
| --- | --- | --- |
| All archives | `sha256sum -c` against each `SHA256SUMS-<OS>-<ARCH>` | OK (5 of 5) |
| `reverbscope-0.4.1-py3-none-any.whl` | fresh virtual environment, no editable install: `reverbscope --version`, `--help`, `--backend fake measure`, `sweep`, `analyze`, `show`, `--lang zh_CN show`; with `[gui]`: `gui --smoke` offscreen, `reverbscope-gui` stays running; without `[gui]`: `reverbscope gui` (a traceback, fixed in this release) | OK |
| `reverbscope-0.4.1.tar.gz` | builds a wheel with the same 90 files; `pip install "./reverbscope-0.4.1.tar.gz[gui]"` installs `reverbscope` / `reverbscope-gui` and the compiled zh_CN catalog | OK |
| `twine check` | wheel and sdist metadata | PASSED |
| `ReverbScope-macos-arm64.dmg`, `ReverbScope-macos-x86_64.dmg` | opened on Linux with 7-Zip: `ReverbScope.app` + `Applications` link; Mach-O arm64 / x86_64; `Info.plist` 0.4.1, `LSMinimumSystemVersion` 14.0, microphone usage text; `build_info.json` names the build commit; 313 Mach-O files, no absolute load path outside `/usr/lib` / `/System` | OK; mount, install and launch on macOS were done by the workflow's `check_macos_dmg.py` on macOS 26 / 15 runners, not by a person |
| `reverbscope-windows-x64.zip` | top level `reverbscope-gui.exe` (PE32+ GUI), `reverbscope.exe` (PE32+ console), `_internal\`, `THIRD_PARTY_LICENSES\` | OK; launched only by the workflow on a Windows runner |
| `ReverbScope-setup.exe` | silently installed, smoke-tested and uninstalled by the workflow | OK (runner only) |
| `reverbscope-linux-x86_64.tar.gz` | `smoke_bundle.py --require-gui-launcher --expect-commit 7cb1419…` in an empty environment (no virtualenv on `PATH`) | OK; needs glibc 2.39 |
| Secrets and private paths | token / private-key patterns in the bundles and the sdist (only PEM header strings inside Qt's TLS plug-ins); home-directory paths in the sdist are test fixtures (`/home/me`, `/home/anna`) | none found |
| Version | `pyproject.toml`, `reverbscope --version`, wheel / sdist names, `Info.plist`, `build_info.json` | all 0.4.1 |

These checks cover the files built from `b753e17`. The 14 commits added to
the release candidate after it, up to #24's head `cf27b30` (among them the
command-line presentation `0f5418e` / `f5eb961`, #23's first-run UX folded
in by `cd45bf9`, the Desktop / Terminal split `bcea79a`, the release-file
fixes `cccc682` / `f893cc7` and the exporter fix in `cf27b30`), are covered
by CI and by the Release workflow's own bundle smoke tests on each platform
(last: Release #34 on `c5fe692`, STATUS snapshot 32), not by this download
check: repeat the wheel check and step 3 below on the draft's files before
publishing.

Known and harmless: the bundles carry `reverbscope-0.4.1.dist-info/direct_url.json`
with the CI runner's checkout path (`file:///Users/runner/work/...`), because
the bundle job installs ReverbScope in editable mode; some third-party wheels
contain their own build machines' paths in debug strings. Neither is a
developer's machine or a secret.

**Publish checklist (the maintainer's click):**

1. Merge the release candidate into `main` and wait for **CI** and
   **Release** to be green on that commit. The Release run refreshes the
   v0.4.1 draft with that commit's 14 files and these notes.
2. On the draft, check: target commit = the green `main` commit; the 14
   assets (Desktop Edition: `ReverbScope-Desktop-macOS-arm64.dmg`,
   `ReverbScope-Desktop-macOS-x86_64.dmg`, `ReverbScope-Desktop-Windows-x64-Setup.exe`,
   `ReverbScope-Desktop-Windows-x64.zip`, `ReverbScope-Desktop-Linux-x86_64.tar.gz`;
   Terminal Edition: `ReverbScope-Terminal-macOS-arm64.tar.gz`,
   `ReverbScope-Terminal-macOS-x86_64.tar.gz`, `ReverbScope-Terminal-Windows-x64.zip`,
   `ReverbScope-Terminal-Linux-x86_64.tar.gz`; `reverbscope-0.4.1-py3-none-any.whl`,
   `reverbscope-0.4.1.tar.gz`, `SHA256SUMS`, `cyclonedx.sbom.json`,
   `generated-bundle.lock`); the notes start with *ReverbScope v0.4.1 — Early
   public pre-release for testing*.

   **Steps 1 and 2 were repeated after PRs #25 and #26 on 2026-09-30**
   (STATUS snapshot 33): the release commit is `d97822a`, with CI #87 and
   Release #38 green. The draft targets `d97822a`, holds exactly the 14
   files above, and its notes match that commit's corrected header and
   changelog. The workflow's *Verify the draft* step compared names, sizes
   and digests with this run's files. Later docs-only commits leave this
   target unchanged. Steps 3 to 5 are the maintainer's.
3. Recommended before publishing: download the DMG for your Mac, install it
   as [INSTALLATION.md](INSTALLATION.md) says, and open it once (the
   Gatekeeper steps included). This is the one check no workflow can make.
4. Keep **Set as a pre-release** ticked, leave *Set as the latest release*
   unticked, and click **Publish release**. Publishing creates the tag
   `v0.4.1` on the target commit and starts the tag run; PyPI stays off
   (§3d).
5. Open <https://github.com/jingyemingyue/ReverbScope/releases> in a private
   window: v0.4.1 must be listed with its assets. The README links that page
   rather than `/releases/latest`, because GitHub's *latest* never points at
   a pre-release (with only pre-releases it redirects to `/releases`; the API
   answers 404).

Do not re-run the Release workflow on `main` after publishing to "refresh"
anything: a published version is never turned back into a draft, and a
fix ships as 0.4.2.

### 3d. PyPI readiness (checked 2026-09-27, not published)

ReverbScope is **not** uploaded to PyPI in 0.4.x; GitHub Releases is the
channel for the first public testers. What is ready and what is not:

| Item | State |
| --- | --- |
| Name `reverbscope` | Free on PyPI on 2026-09-27 (`/pypi/reverbscope/json` answers 404). Not reserved; PyPI can still refuse a name at the first upload. |
| Metadata | `twine check` passes for wheel and sdist; license expression `Apache-2.0` with `LICENSE` / `NOTICE`; `Requires-Python >=3.12`; project URLs set. The classifier still says *Pre-Alpha*. |
| README on PyPI | **Not ready.** `readme = "README.md"` has 38 relative links and the screenshot, which break on pypi.org. Before the first upload, give PyPI a README with absolute links (or a short PyPI-specific description). |
| Wheel / sdist | Pure-Python wheel, built by the Release workflow's `package` job; the sdist rebuilds the same wheel (§3c). |
| Trusted Publishing | Wired in `release.yml` (`pypi` job: `environment: pypi`, `id-token: write`, `pypa/gh-action-pypi-publish` pinned by SHA), gated on a `v*` tag **and** `vars.REVERBSCOPE_PUBLISH_PYPI == 'true'`. Missing: the PyPI trusted publisher, the `pypi` environment with a required reviewer, the variable. |
| Provenance | `pypa/gh-action-pypi-publish` uploads PEP 740 attestations by default under trusted publishing; nothing to add. |

Until a version is on PyPI, no document may tell users to run
`pip install reverbscope`; INSTALLATION.md says so explicitly, and
`reverbscope gui` without PySide6 advises `pip install "PySide6_Essentials>=6.6"`
instead of the extra of a package that is not on PyPI.

## 4. Gates that apply to every release

* CI (`ci.yml`) green on the release commit: lint, mypy, docs link check,
  docs site build, `check_src_safety.py`, schema job, the test matrix
  (Ubuntu 3.12 / 3.13 / 3.14, macOS 3.12, Windows 3.12), the 85 % coverage
  gate on `core` and `models`, the package job, the installed-Essentials
  GPL gate.
* Release workflow green: bundle gate with `--strip --require-licenses`,
  smoke test (`--version`, fake-backend measurement, offscreen GUI) on
  each OS.
* No `UNKNOWN / NEEDS REVIEW` item in `DEPENDENCIES.md` §6 that affects
  the binary being shipped; the license bundle lists `unresolved: none`.
* `docs/STATUS.md` states what was run and what was not. Nothing is
  marked PASS that was not run; hardware cells stay empty until a person
  fills them with a date and an interface name.
* `CHANGELOG.md` has the version's section; overclaims found in review
  are corrected in the same release (for 0.4.0: the zh-CN catalog covered
  three of seven profiles, see #14; closed in 0.4.1).

## 5. Maintainer decisions still open

| Decision | Needed by | State |
| --- | --- | --- |
| Public flip of the repository (ARCHITECTURE_V1.md §9.1 checklist: description and topics, branch protection on `main`, CODEOWNERS present, private vulnerability reporting, labels, Discussions, pinned roadmap) | 1.0.0rc1 (recommended at the first candidate so it gets outside testing) | Repository public since 2026-09-24; CODEOWNERS is present; the other checklist items are repository settings not checked here (the issue templates use the labels `hardware-report` and `daw-report`, which GitHub adds only if they exist) |
| Apple Developer ID + notarization, Windows Authenticode; or ship 1.0 unsigned with documentation | 1.0.0rc1 | Open; 0.x bundles are unsigned by design |
| PyPI: register `reverbscope`, configure trusted publishing, create the `pypi` environment with required reviewers, set `REVERBSCOPE_PUBLISH_PYPI=true`; give PyPI a README with absolute links | First version the maintainer wants on PyPI (earliest 0.5.0) | Open; readiness in §3d; the workflow stays off until then |
| Publish the v0.4.1 draft as the first public pre-release | Done | Published 2026-09-30 as a pre-release (not latest), tag `v0.4.1` on `d97822a`, 14 assets. Own-machine install (checklist step 3) is still open |
| Validation campaign: rooms, reference instrument (REW as a comparison instrument only), who runs it | 1.0.0rc1 | Open; no hardware available near-term |
| DCO sign-off requirement | Public flip | Open |
| Dependabot PRs #3 / #4 (actions/checkout 4→7, actions/setup-python 5→7) | After v0.4.1 is published | Left alone while v0.4.1 is being finished, so the release workflow does not change major versions under it; then merge when Dependabot has rebased them onto the SHA-pinned workflows and CI is green |

## 6. Review follow-ups (2026-09-24)

Opened while merging the milestone PRs; none blocks 0.4.0, several block
0.5.0 (see §2). All nine are fixed in 0.4.1 (CHANGELOG `[0.4.1]`); an issue
is closed when that pull request is merged.

| Issue | Area | Severity | 0.4.1 |
| --- | --- | --- | --- |
| #9 | `compare`: frequency-response delta interpolates the raw spectrum before smoothing | medium | smoothed on the native grid first |
| #10 | `analyze_impulse_response` / `analyze-ir` untested | medium | tested; a quadratic pass search and non-IR input fixed on the way |
| #11 | session loader follows absolute member paths | low (security) | members confined to the session folder |
| #12 | loopback FIR window advances the compensated response by ~5 ms | medium | FIR origin at its peak, linear division, settling net of noise over the valid record |
| #13 | PortAudio: progress inside the real-time callback; swallowed callback errors | medium | progress polled, errors fail the take, channels validated first |
| #14 | zh-CN catalog incomplete; safety warning untranslated; `.mo` not shipped | high for the i18n claim | all profiles, contexts, hashed `.mo` in the wheel |
| #15 | ISO 3382-2 Table 1: source unnamed; engineering class ignores microphone count | medium | Table 1 read from the standard, every row checked |
| #16 | `check_src_safety.py` gaps; coverage figure unrecorded | low | aliases / dynamic imports; 90.20 % recorded |
| #17 | bundle gate misses the virtual-keyboard QML plugins | must close before any bundle is published | QML matched by directory; any QML tree fails |

## 7. What this plan does not do

It does not make the repository public, create a numbered Release, change
the license, push a tag, rewrite history, or claim any hardware result.
Each of those is either a maintainer click or a person in a room.
