# Status

Snapshot 1 (2026-09-17, v0.1.0.dev1, foundation) was verified by running it
on macOS (Apple silicon, Python 3.12.14); every later snapshot says where it
ran. Nothing is marked PASS that was not run, and no snapshot includes a
measurement through a real interface or a real DAW
([HARDWARE_TESTS.md](HARDWARE_TESTS.md)).

Snapshot 34: 2026-10-01 — **software beta 0.5.0b1 prepared.** This is not
0.5.0. The release plan's 0.5.0 still needs a dated hardware-matrix PASS, and
every cell is still empty. v0.4.1 stays the published pre-release at
`d97822a`; this snapshot does not republish it.

**What the beta contains, on top of 0.4.1** (CHANGELOG `[0.5.0b1]`): ISO
3382-1 C50, C80, D50 and centre time from the same decay truncation; one
profile notice when broadband C50 or C80 is a poor fit for that recording
(not a grade); the rotatable placement picture; GUI failures, About and the
two-clock warning in the interface language; command-line wrapping, quoting
and colour fixes.

**What was run** (this container: Linux x86_64, CPython 3.12.14, the `dev`
and `gui` extras, no audio device): `ruff check`, `ruff format --check`,
`mypy` (strict, 79 files), `check_doc_links.py`, `check_src_safety.py`.
Pytest of everything except `tests/ui` (this container has no `libEGL.so.1`,
so PySide6 does not import): core + models branch coverage **90%** (required
85%). Five golden demo checks and two PySide6 import checks failed only
because Qt cannot load here; the demo diff starts at the "install PySide6"
next-step line, which CI (where Qt loads) does not print. The GUI suite was
not run in this container. **Not run:** any real audio interface, microphone
or DAW; a bundle on a person's own computer; publishing the `v0.5.0b1` draft
(that is the maintainer's click after CI and Release are green).

Snapshot 33: 2026-09-30 — **v0.4.1 final merge close-out; the draft
contains the testing limitations from PR #26.** PR #25 (`90c316b`) was
merged as `932885e`, then PR #26 (`4f91e62`) as
**`d97822afb4d6f77e81c04e95b040f56680f00cf7`**, using merge commits and
pinning each PR head. Both PRs had green CI and no unresolved review
threads; #26 also had a green Release #37 before merging. The combined
diff against `c5fe692` changes only README, CHANGELOG, the release-notes
header and release/status documentation; no source, tests, dependencies or
workflow changed.

**Checks on the release commit `d97822a`:**
[CI #87](https://github.com/jingyemingyue/ReverbScope/actions/runs/36667088717)
and [Release #38](https://github.com/jingyemingyue/ReverbScope/actions/runs/36667088841)
completed successfully. CI includes the Ubuntu Python 3.12 / 3.13 / 3.14,
macOS Python 3.12 and Windows Python 3.12 test jobs, lint/types, JSON
Schemas, Python distributions and the license/GPL-module gate. The Release
quality job reports **810 passed, 1 skipped** (the runner has no CJK font),
with core + models coverage **90.48 %** (required: 85 %), plus seven
schema/public-API tests passed.
Release
includes the Apple silicon and Intel macOS, Windows and Linux builds of
both editions, the release-file/checksum gate and the draft verification;
PyPI was skipped.

**Draft read-back:** release 395349087 is still the one unpublished
v0.4.1 draft, marked pre-release, targeting `d97822a`. It contains exactly
the 14 expected assets, all uploaded with nonzero sizes and SHA-256 digests.
Its body matches the release notes rendered from this commit's header and
CHANGELOG, including the own-machine-install and Chinese-Windows-installer
limitations and the synthetic-room qualifier. The workflow's *Verify the
draft* step passed. No tag `v0.4.1` exists. A later docs-only close-out
commit does not trigger Release: publishing this draft will tag
`d97822a`, the commit its files were built from.

**Remaining work:** publish the draft using RELEASE_PLAN §3c; real
interface/microphone/DAW and own-machine install testing, including macOS
14 and the Chinese installer screens, remains unperformed. The minor CLI
issues listed in snapshot 32 remain; its two release-wording issues are
fixed by #26. Dependabot #3 / #4 remain open until after v0.4.1 is
published, as the release freeze requires. No local test or real hardware
measurement is claimed by this snapshot.

Snapshot 32: 2026-09-30 — **the v0.4.1 release candidate is on `main`; the
draft Release is refreshed from it and waits for the maintainer.** No code
change in this snapshot; it records the merge and what was run.
**Merges** (GitHub merge commits, no squash, no rebase, each with the head
SHA pinned): PR #24 (`cf27b30`) into `claude/epic-meitner-x0t35f` →
`eda86c7`; CI #79 and Release #32 green on `eda86c7`, then PR #22 marked
ready for review and merged into `claude/publication-ready-level-n3hkor` →
`12fd83e`; CI #80 and Release #33 green on `12fd83e`, then PR #21 merged
into `main` → **`c5fe692`**. The three heads were linear (each an ancestor
of the next), every merge was conflict-free, no file was deleted against
`main`, and `main`'s tree is byte-identical to #24's head (`431cb82`): the
tree that CI #78 and Release #31 had already passed. PR #23 was closed
unmerged as superseded by #24 (its first-run UX lives in `cli/console.py` +
`cli/render.py`; no `cli/style.py`, `cli/report.py` is the 45-line
wrapper). **On `main` (`c5fe692`):** CI #81 green on every job (lint and
type-check, tests on Ubuntu 3.12 / 3.13 / 3.14, macOS 3.12 and Windows
3.12, JSON Schemas, sdist and wheel, license bundle and GPL-module gate);
Release #34 green on every job (validate, lint and test, sdist and wheel,
CycloneDX SBOM, the four `Bundle (<os>)` jobs with both editions, *Check the
release file set*, *Draft GitHub Release*; PyPI skipped, as it runs only on
a tag). Without signing secrets the macOS jobs kept the ad hoc signature;
the hardened-runtime rehearsal, the DMG check and the Windows installer's
install / smoke / uninstall ran on the runners. This was the first run of
`release_draft.py sync` against GitHub: it found the existing draft
395349087, replaced `cyclonedx.sbom.json`, `generated-bundle.lock`, the
wheel and the sdist, removed the six earlier names the draft still held
(`ReverbScope.dmg`, `SHA256SUMS-{Linux,macOS,Windows}`,
`reverbscope-linux-x86_64.tar.gz`, `reverbscope-windows-x64.zip`; snapshot 31
expected seven, but that draft never had a `ReverbScope-setup.exe`), uploaded
the 14 files and printed *draft 395349087 holds 14 files from commit
c5fe692d37152c55b768147c7c0753694b5cb25d*; `release_draft.py verify` then
passed (draft, pre-release, tag name and title `v0.4.1`, target commit
`c5fe692`, body equal to the rendered notes, exactly the 14 names, sizes and
digests). The repository lists one Release (that draft) and no tag
`v0.4.1`. The 14 assets: `ReverbScope-Desktop-macOS-arm64.dmg`,
`ReverbScope-Desktop-macOS-x86_64.dmg`,
`ReverbScope-Desktop-Windows-x64-Setup.exe`,
`ReverbScope-Desktop-Windows-x64.zip`,
`ReverbScope-Desktop-Linux-x86_64.tar.gz`,
`ReverbScope-Terminal-macOS-arm64.tar.gz`,
`ReverbScope-Terminal-macOS-x86_64.tar.gz`,
`ReverbScope-Terminal-Windows-x64.zip`,
`ReverbScope-Terminal-Linux-x86_64.tar.gz`,
`reverbscope-0.4.1-py3-none-any.whl`, `reverbscope-0.4.1.tar.gz`,
`SHA256SUMS`, `cyclonedx.sbom.json`, `generated-bundle.lock`.
**What was run on the final tree** (this container: Linux x86_64, CPython
3.12.3, `dev` and `gui` extras, no audio device; the GUI tests with EGL /
XCB libraries unpacked into a scratch folder, not installed): the CI
coverage-gate command, **811 passed**, core + models 90.48 %; `ruff check`,
`ruff format --check`, `mypy` (strict, 79 files), `check_doc_links.py`,
`check_src_safety.py`, `build_docs_site.py`, the schema tests; the license
bundle and the Essentials-only check. The command line, run as a user would
(bare `reverbscope`, `--help`, `demo`, `doctor`, `export`, `show`, `compare`,
`gui --smoke`) in English and `--lang zh_CN`, at 60 and 80 columns and to a
pipe, with `PYTHONIOENCODING` cp1252 / ascii, the C locale and a pty: no
traceback, exit codes as documented, no escape sequence in a pipe or file,
paths and commands never split, zh_CN output Chinese apart from identifiers
and stored data; `--format json` stdout parses as JSON for `doctor`,
`devices`, `show`, `analyze`, `analyze-ir`, `compare` and `schema`; the
demo's stored files under `--lang zh_CN` contain no Chinese. `gui --smoke`
here prints *The desktop GUI cannot start because PySide6 could not be
loaded (libEGL.so.1 …)* and exits 2 (this container has no EGL); the GUI
itself started only in the GUI tests and on the Release runners. `reverbscope
export`, with and without `-v`, in the editable install and in a fresh
wheel install without `[gui]`: no *name collides* message (`909f332`'s code
prints it on every run; a genuinely colliding third-party exporter is still
reported). In that wheel install `reverbscope gui` prints the install hint in
English and Chinese and exits 2. README, INSTALLATION, EDITIONS, the user
guides and the rendered Release notes name only the 14 real assets
(case-sensitive), no earlier name as a download, Download first, the two
editions separate, no Python needed, and never suggest turning off
Gatekeeper or SIP (156 doc / release / editions tests pass; 60 in-page
anchors resolve). **Known, not blocking, not changed for 0.4.1** (found by
this check, each reproduced independently): at 60 columns the root
`--help` tagline and epilog and the `show` / `gui` descriptions are no
longer wrapped (the only difference from `909f332`; 80 columns is fine);
`demo` clears its progress line with `ESC[2K` on a terminal even under
`--color never` / `NO_COLOR`; suggested next-step commands do not quote a
path that contains a space; `--format json` is ignored without a message by
`export`, `sweep` and `show --list` (as on `909f332`); with cp1252 output at
exactly 80–82 columns one demo line runs two to four cells past the width;
the Release notes list the Windows installer under *English and Simplified
Chinese throughout* without saying its Chinese screens have not been seen
on a Chinese Windows, and CHANGELOG `[0.4.1]` says a short sweep "in a
reverberant room measured up to 4.5 % off" without saying the room was
synthetic. **Not run:** any real audio interface, microphone or DAW; a
bundle on a person's own Mac, Windows PC or Linux desktop (the workflow
installs and launches them on GitHub's runners only); macOS 14; the
Chinese installer on a Chinese Windows. These stay open for community
hardware testing; the hardware and DAW matrices stay empty. Publishing the
draft (which creates the tag `v0.4.1` on `c5fe692`) is the maintainer's
click (RELEASE_PLAN §3c, steps 3–5).

Snapshot 31: 2026-09-29 — **v0.4.1 release close-out: one changelog section
for the pre-release** (branch `claude/reverbscope-cli-integration-84e5qc`, PR
#24, stacked on #22 and #21). One code fix: `reverbscope export` logged
*ignoring third-party exporter 'csv'; name collides* on every run in every
install, because `pyproject.toml` declares the built-in CSV exporter under
the `reverbscope.exporters` entry-point group too; the registry now recognises
its own declaration (a test covers both cases). The `[Unreleased]` entries
(Desktop and Terminal Editions, `reverbscope demo`, the home screen, "At a
glance", numbered next steps, the error block, workflow-ordered help, the
one `SHA256SUMS`, the download-first README and Release page, the
`PYTHONIOENCODING` fix) are folded into `[0.4.1]`, whose date is now
2026-09-29 and whose introduction names the two editions; the draft
Release's notes are taken from that section, so they now describe everything
the pre-release contains. Stale wording fixed on the way: the release-notes
order in RELEASE_PLAN §1 (+ zh-CN), the Release workflow's trigger paths in
§3, the draft body in §3 step 2, the CHANGELOG's "GUI keeps its own reports"
and "installer edition" sentences, the `ReverbScope-setup.exe` comment in
`packaging/windows/reverbscope.iss`, and COMPATIBILITY's review date;
INSTALLATION (+ zh-CN) now says the `xattr` step for the macOS Terminal
Edition is a stop-gap for the unsigned pre-release builds. A merge-readiness
audit of the stack (PRs #21 → #22 → #24) found the three heads linear (each
an ancestor of the next), both merge orders conflict-free with `main` ending
on the tree of #24's head, PR #23 not part of the chain (21 conflicting
files if merged after #24; superseded), and no second CLI presentation layer
(`cli/report.py` is a 45-line wrapper over `cli/render.py`, no `style.py`).
Release run #30 on `6d8c32e` (job logs): the Apple-silicon app is `Mach-O
thin (arm64)`, the Intel app `Mach-O thin (x86_64)`, both ad hoc signed with
the hardened-runtime rehearsal (`flags=0x10002(adhoc,runtime)`), both DMGs
`hdiutil verify` VALID and mounted, copied and launched; the Windows
installer installed, smoke-tested (`reverbscope.exe`, `reverbscope-gui.exe`,
Start menu entry) and uninstalled with its folder and Start menu entries
gone; every Terminal Edition passed the `--terminal` gate and smoke. A local
`release_draft.py stage` on the Linux files plus stand-ins for the other
runners produced exactly the 14-file set with one `SHA256SUMS`, and refused
a stray file. A zh_CN pass over every command's output (the CLI gates'
allowlist) found no untranslated prose; the three metadata fields the demo
stores in English (room, position, microphone) are shown as stored when a
demo session is reopened, by the language-neutral-files design. **What was
run** (this container: Linux x86_64, CPython 3.12.3, `dev` and `gui` extras,
PortAudio 19.6, no audio device): `ruff check`, `ruff format --check`,
`mypy` (strict, 79 files), `check_doc_links.py`, `check_src_safety.py`,
`build_docs_site.py`; the CI coverage-gate command, **810 passed**, core +
models branch coverage 90.48 %; the schema and public-API tests; `--backend
fake devices` and `measure`; `examples/synthetic_measurement.py`.
`scripts/build_release.py --python-dist` in a second environment pinned to
`requirements/bundle.lock` (PyInstaller 6.22.3) built both Linux editions:
tests skipped there (run separately, above), license bundles, PyInstaller,
the `--strip --require-licenses` gate, the `--terminal` gate, both smoke
tests, `ReverbScope-Desktop-Linux-x86_64.tar.gz` (148.1 MB),
`ReverbScope-Terminal-Linux-x86_64.tar.gz` (57.4 MB), `SHA256SUMS-Linux-X64`
(`sha256sum -c` OK), the wheel and the sdist; both `build_info.json` files
name commit `f893cc7` and their edition; the Terminal archive, extracted
into an empty folder and run under `env -i` (no virtual environment, no
`PYTHON*` variables), printed `--version`, ran `demo` in English and
Chinese, wrote nothing but JSON for `--format json doctor` (no matplotlib,
PySide6 or shiboken6 reported, audio callbacks ok), answered `gui` with the
Terminal Edition sentence and exit code 2 in both languages, and contains no
PySide6, shiboken6, Qt, matplotlib or `reverbscope/ui` file. On GitHub
Actions, CI #76 and Release #29 on `f893cc7` (the commit before this one)
are green on every job, the four `Bundle (<os>)` jobs and *Check the release
file set* included; that check downloaded the 17 files of the run (nine
archives, four `SHA256SUMS-<OS>-<ARCH>`, wheel, sdist, SBOM, lock) and
staged the 14-file Release set. A read-only run of `release_draft.py`'s
planner against the asset names main's last Release run (#10, `909f332`)
attached to the v0.4.1 draft plans the removal of the seven earlier names
(`ReverbScope.dmg`, `ReverbScope-setup.exe`, `reverbscope-linux-x86_64.tar.gz`,
`reverbscope-windows-x64.zip`, `SHA256SUMS-{Linux,macOS,Windows}`) and the
replacement of the four shared ones; a name it does not know stops it. **Not
run:** the draft refresh itself (it runs on `main` after the merge); any
real audio interface, microphone or DAW; a bundle on a person's own Mac,
Windows PC or Linux desktop (the release workflow mounts, installs and
launches them on GitHub's runners only); macOS 14; the Chinese installer on
a Chinese Windows. The hardware and DAW matrices stay empty; a cell is
filled only from a community report on real hardware.

Snapshot 30: 2026-09-27 — **download-first installation and the release
candidate's files checked as a user gets them** (branch
`claude/epic-meitner-x0t35f`, stacked on PR #21). README / README.zh-CN open
with *Download* (the stable Releases page, real file names, first-launch
steps for unsigned builds), new `docs/INSTALLATION.md` (+ zh-CN), release
notes restructured for testers, RELEASE_PLAN §3c (publish checklist) and §3d
(PyPI readiness). **What was run** (Linux x86_64, CPython 3.12.3), on the
files of Release run #23 (PR #21 head `b753e17`, build commit `7cb1419`),
downloaded from the run's artifacts: `sha256sum -c` of all five archives;
the wheel in a fresh virtual environment (not editable): `--version`,
`--help`, `--backend fake measure`, `sweep`, `analyze`, `show`,
`--lang zh_CN show`, then with `[gui]` `gui --smoke` (offscreen) and
`reverbscope-gui` kept running; the sdist rebuilt into a wheel with the same
90 files and installed with `[gui]`; `twine check` on both; both DMGs
opened with 7-Zip (app, Applications link, Mach-O arm64 / x86_64,
`Info.plist` 0.4.1 / `LSMinimumSystemVersion` 14.0, `build_info.json`,
313 Mach-O files without an absolute non-system load path); the Windows ZIP's
layout (`reverbscope-gui.exe` PE32+ GUI, `reverbscope.exe` console,
`_internal`, `THIRD_PARTY_LICENSES`); the Linux bundle through
`smoke_bundle.py --require-gui-launcher --expect-commit` in an empty
environment (it needs glibc 2.39); a token / private-key scan of every
bundle and the sdist (nothing but PEM header strings in Qt's TLS plug-ins).
That found one bug, fixed here: `reverbscope gui` without PySide6 printed a
traceback (the wheel without `[gui]`); a wheel built from this branch now
prints the install hint in English and Chinese and exits 2. On this branch:
the full suite, **695 passed** (679 + 16 new), coverage of core + models
90.28 %; ruff, ruff format, mypy strict, `check_doc_links.py`,
`check_src_safety.py`, `build_docs_site.py`, `uv build` + `twine check`.
`/releases/latest` was checked to redirect to `/releases` while no full
release exists (the API answers 404), which is why the README links
`/releases`. **Not run:** the DMGs on a Mac and the Windows files on a
Windows PC by a person (the release workflow mounts, installs and launches
them on GitHub's runners only), any audio interface or DAW, and the
publication itself (the maintainer's click, RELEASE_PLAN §3c).

Snapshot 29: 2026-09-27 — **command-line presentation** (branch
`claude/publication-ready-level-n3hkor`). One renderer for the terminal
(`cli/console.py`: colour policy with `--color` / `NO_COLOR` / `TERM=dumb`,
status symbols with ASCII fallbacks, display-width-aware wrapping and tables
that turn into blocks on a narrow terminal, a progress line that is a single
stage line in a file) and the command renderers (`cli/render.py`) for
analyze, show, compare, doctor, devices, sweep, measure and errors; grouped
`--help` with examples. The GUI's plain-text reports are unchanged. Found on
the way: `--format json measure` wrote status lines into its JSON stdout, and
`doctor` / `devices` ignored `--format json` (both fixed, with tests). No
new dependency; JSON, schemas, stored files and exit codes unchanged. No
hardware or DAW result (still none).

Snapshot 28: 2026-09-27 — **a complete Simplified Chinese experience**
(branch `claude/publication-ready-level-n3hkor`). Everything a user reads can
be Simplified Chinese: GUI (with Qt's own dialogs), CLI help and argparse
errors, text and environment reports, Device Inspector, charts, the Windows
installer, README, SECURITY, the hardware test guide and the GitHub issue
forms. Result files are unchanged: stored notes stay English (`diag`) and are
translated when shown (`localize`); a run under `--lang zh_CN` writes no
Chinese into `result.json`. The macOS Developer ID signing and notarization
steps are in `release.yml`, off until six repository secrets exist, and have
never run. Locally (Linux, Python 3.12): the full suite passes, including new
zh_CN gates for the GUI pages, dialogs, reports, charts (no missing glyphs
where a CJK font is installed) and every CLI help screen; ruff, mypy strict
(with and without the gui extra), doc links (docs/ and root documents), the
docs site and the sdist / wheel build are clean. **Not run:** any real audio
interface or DAW, and the Chinese Windows installer on a Chinese Windows
(CI compiles and installs it on an English runner).

Snapshot 27: 2026-09-27 — **release hardening before the v0.4.1 pre-release**
(same branch). A final review of the branch against `main` found no blocker
in the code; fixed here:
the draft-release job could not see its own draft (the release action looks
a release up by tag, which misses drafts), so a refresh would have left
`ReverbScope.dmg`, `SHA256SUMS-{Linux,macOS,Windows}` and the first run's notes
next to the new files; `scripts/release_draft.py` now stages and checks the
exact 13-file set and the checksum files, refreshes the single draft and
reads it back, and fails closed on a published release, two drafts, a tag on
another commit or an unknown asset (38 tests with a fake API; a read-only
`sync --dry-run` against the real v0.4.1 draft planned the removal of those
four legacy files and replacement of the other six). Also: Standalone and
demo takes skip the playback-speed check (a biased estimate on a noisy,
reverberant take advised switching off a DAW's time-stretch); host-API
options on another host API are refused; libsndfile's LGPL-2.1 text and
source notes are in the license bundle; the interface report form asks
Pass / Fail / Not run per matrix row; the DAW form asks for the interface,
the direct-sound confidence and the environment report; the README says
"No real hardware validation yet" first and links both forms. Run in this
container (Linux x86_64, Python 3.12, PortAudio 19.6, no audio device):
`ruff check`, `ruff format --check`, `mypy` (strict, 75 files), doc links,
source safety, docs site, 625 tests, core/models branch coverage 90.62 %.
**Not run:** anything on real hardware or in a DAW; the draft refresh
itself (it runs only on `main` after the merge).

Snapshot 26: 2026-09-24 — **software readiness for community testing**
(branch `claude/publication-ready-level-n3hkor`, CHANGELOG `[0.4.1]`). A
seven-part review of the branch against `main` (packaging, Windows
installer, macOS app and DMG, DAW guide, claims, code, community), each
finding checked by an independent verifier, reported 35 findings: 31
confirmed (several found by more than one reviewer) and all fixed, 4
refuted as not defects (three of those were improved anyway). Since snapshot 25: Help ▸ Environment Report for every
edition (`reverbscope doctor --probe`: build commit, settings, home folder as
`~`, probed rates, an audio-callback self-check); issue forms for audio
interface and DAW reports; one Standalone pre-flight shared by the GUI and
`reverbscope measure` (rate asked of the devices the stream opens, with its
channels and host-API options); the GUI keeps the system's default devices;
device buffer under/overflows reach the result as a finding; a recording
of exact digital silence (the sweep track exported instead of the
microphone) is flagged; the speed diagnosis follows the estimate's measured
spread; session bundles leave out links out of the folder; inside-out
macOS signing with a hardened-runtime rehearsal; the Linux tarball uses the
system PortAudio; matplotlib's cache survives launches; macOS 14+ declared
(`LSMinimumSystemVersion`); a Digital Performer section and corrected
sources in the DAW guide, labelled "documented workflow, not yet tested in
a DAW"; translated chart text with a CJK font fallback, metric names instead
of ids on the Compare page, and profiles listed by name.

Evidence on GitHub Actions: CI #56 (`f7c92f1`) green on Ubuntu 3.12–3.14,
macOS and Windows (551 / 552 tests; the same-file copy test ran on APFS and
NTFS). CI #57 (`ad969b0`) failed only in "Lint and type-check" (mypy: no
`shiboken6` without the gui extra), fixed in `e1bc2e5`. Release #15
(`ad969b0`) passed all four bundle jobs: macOS 26.6.2 arm64 and macOS
15.7.9 x86_64 (inside-out ad hoc signature valid; hardened-runtime copy
`flags=0x10002(adhoc,runtime)` started, `doctor` found every library
version, the built commit and working audio callbacks; DMG mounted, copied
and launched with `LSMinimumSystemVersion` 14.0; the font cache built once
per job instead of at every launch), Windows (installer compiled,
installed, installed copy smoke-tested, uninstaller removed the whole
folder) and Linux (system PortAudio, bundle gate, smoke). CI #58
(`e1bc2e5`) failed once on macOS in a progress-callback test: a real race
(a poll between the last block and PortAudio's finished callback could
discard a complete take), reproduced deterministically and fixed in
`65febe5`. Release #16 (`e1bc2e5`) passed all four bundle jobs again with
the reworked checks (entitlements, inert Authenticode hook compiled). CI #59
(`65febe5`) green on every job: Ubuntu 3.12 / 3.13 / 3.14 and macOS 576
passed, Windows 575 passed and 1 skipped (a QML check that does not apply
to that PySide6 build), coverage 90.48 %. CI #61 and Release #18
(`38c4878`, the chart and compare-label translations) green on every job,
the four bundle jobs included.
Locally (Linux, Python 3.12): **579 passed**, coverage gate 90.48 %;
ruff, mypy strict (with and without the gui extra), doc links clean; a
local PyInstaller 6.22.3 Linux bundle loaded `/lib/x86_64-linux-gnu`
PortAudio, ALSA and JACK (LD_DEBUG) and passed the license gate. **Not
run:** any real audio interface or DAW; the hardware and DAW matrices in
HARDWARE_TESTS.md stay empty; nothing was signed with a Developer ID or
Authenticode certificate or notarized.

Snapshot 25: 2026-09-24 — **first all-platform green CI run on this
branch** (the repository is public, so hosted runners are available; `main`
had green CI runs before, e.g. #43). On this branch, CI run #54 (commit `2b54157`) passed every job: Ubuntu
Python 3.12 / 3.13 / 3.14, macOS Python 3.12, Windows Python 3.12 (pytest,
fake-backend Standalone flow, example script), lint + mypy + doc links +
docs site + source safety, JSON schemas, sdist / wheel, license bundle and
installed-Essentials gate. The run before it (#53) had failed on macOS and
Windows only in `test_copy_onto_the_same_file_is_a_no_op`, whose Linux
emulation (a hard link) cannot be created where the file system is
case-insensitive: real evidence for the audit finding, fixed in the test.
Release run #13 (commit `d0895b8`, `workflow_dispatch`, no draft) passed
all four bundle jobs: Linux, macOS arm64, **macOS x86_64 on `macos-15-intel`**
(the Intel DMG built, mounted, copied and launched for the first time) and
Windows (installer built, installed, smoke-tested, uninstalled), plus sdist /
wheel and the SBOM. Since snapshot 24: GUI redesign, audio device inventory
and host-API-safe Standalone takes, `reverbscope doctor`, developer / installer
editions, sourced DAW guide, `docs/AUDIO_DEVICES.md`, `docs/COMPARISON.md`,
`docs/COMPATIBILITY.md`, matplotlib>=3.10 and the cross-platform fixes
(then CHANGELOG `[Unreleased]`, since folded into `[0.4.1]`). Locally (Linux, Python 3.12): **549 passed**,
coverage gate 90.47 %. **Not run:** any real audio interface or DAW; the
hardware and DAW matrices in HARDWARE_TESTS.md stay empty.

Snapshot 24: 2026-09-24 — **v0.4.1 release readiness: desktop launch on
three platforms, Windows installer, Intel macOS, DAW workflow** (branch
`claude/publication-ready-level-n3hkor`; see CHANGELOG `[0.4.1]` DAW
workflow and Packaging). The Windows and Linux bundles gain a windowed
`reverbscope-gui` launcher that opens the GUI without arguments (the Start-menu
shortcut, Explorer double-click, desktop file and AppImage `AppRun` all ran
the console CLI before, which printed its usage and exited); the release
workflow always builds `ReverbScope-setup.exe`, installs it silently,
smoke-tests the installed copy and uninstalls it, and builds an Intel
macOS DMG next to the Apple-silicon one. A sweep the DAW played at the wrong
speed (sample-rate mismatch or time-stretch) is diagnosed; DAW export
containers are tested; a per-DAW guide covers ten DAWs.
**What was run for this snapshot** (Linux x86_64, Ubuntu, CPython 3.12,
the `dev`, `gui` and `i18n-dev` extras): the full suite, **522 passed**; the
CI coverage gate command, **90.47 %**; `ruff check`, `ruff format --check`,
`mypy` (strict, 70 files), `check_doc_links.py`, `check_src_safety.py`,
`build_docs_site.py`; `uv build` of sdist and wheel; a Linux PyInstaller
6.22.3 one-directory build with `reverbscope` and `reverbscope-gui` over one
`_internal/`, which passes `check_bundle_contents.py --strip
--require-licenses` and `smoke_bundle.py --require-gui-launcher`;
`reverbscope-gui` without arguments entered the Qt event loop (offscreen).
On GitHub Actions, the release workflow run #11 on this branch (commit
`3876f21`, `workflow_dispatch`, no draft) passed on Linux, macOS arm64 and
Windows: the Windows job built `ReverbScope-setup.exe` with Inno Setup,
installed it per-user, ran `smoke_bundle.py --require-gui-launcher` on the
installed copy (CLI, fake measurement, offscreen GUI through
`reverbscope-gui.exe`) and uninstalled it. Release run #12 (the Intel macOS job) never started: the
repository's Actions minutes were used up, and every job failed within
seconds without a runner. `scripts/build_release.py` (RELEASE_PLAN.md §3a)
was then run on this Linux machine from `requirements/bundle.lock` with
`--python-dist`: tests, wheel and sdist, license bundle, PyInstaller, gate,
smoke test (CLI, fake measurement, offscreen GUI, `reverbscope-gui`),
`reverbscope-linux-x86_64.tar.gz` and `SHA256SUMS-Linux-X64`, about 4 minutes.
**What was not run:** the Intel macOS build (neither in Actions nor on a
Mac), `build_release.py` on macOS or Windows, and any DAW or hardware cell —
the DAW notes come from the DAWs' documentation and the new DAW matrix in
HARDWARE_TESTS.md is empty.

Snapshot 23: 2026-09-24 — **v0.4.1 workflow verification on PR #18**,
commit `ec9a6b7406e5788830dbe68931899671df0d94d4`.
GitHub Actions CI #43 completed successfully (Ubuntu Python 3.12/3.13/3.14,
macOS Python 3.12, Windows Python 3.12; lint, mypy, schemas, package and
installed-Essentials license gate). Release workflow PR run #1 also completed
successfully: lint/type check, 470 Linux tests and the 85 % coverage gate,
sdist/wheel, SBOM, and **Linux, macOS and Windows frozen bundles** built from
the pinned runtime lock; each passed the `--strip --require-licenses`
bundle gate and a fake-backend/offscreen-GUI smoke test. The macOS `.app`
executable was smoke-tested separately. The workflow uploaded the three
archives, checksums, wheel/sdist and SBOM as **CI artifacts**. Draft Release
and PyPI jobs were skipped on this PR. Windows produced a zip; `iscc` was
not installed, so no Windows setup EXE was produced. No bundle was installed
on a person's desktop and no hardware-matrix cell was executed. The PR
remains unmerged at this snapshot.

Snapshot 22: 2026-09-24 — **v0.4.1, review follow-ups #9–#17** (branch
`v0.4.1-review-followups`, one pull request; see CHANGELOG `[0.4.1]`). Each
issue got a synthetic test that was checked to fail on 0.4.0 and pass
after the fix. **What was run for this snapshot** (Linux x86_64, Ubuntu,
CPython 3.12.3, the `dev`, `gui` and `i18n-dev` extras, PySide6_Essentials
6.11.2, numpy 2.5.3, scipy 1.18.1): the full suite, **470 passed**
(tests/unit 366, tests/integration 54, tests/ui 12 offscreen,
tests/robustness 38), and again on CPython 3.13.13; the CI coverage gate
command (`--cov=reverbscope.core --cov=reverbscope.models`, branch coverage):
**90.20 %** (0.4.0 on the same machine: 87.74 %, 345 tests); `ruff check`,
`ruff format --check`, `mypy` (strict, 69 files, with and without the
PySide6 stubs), `check_src_safety.py`, `check_doc_links.py`,
`build_docs_site.py`, `build_license_bundle.py`; `uv build` of sdist and
wheel (the wheel carries the hashed `.mo`, the sdist only the `.po`) and an
install of that wheel; a Linux PyInstaller 6.22.3 one-directory build from
`requirements/bundle.lock`, which has no `qml/` directory, passes
`check_bundle_contents.py --strip --require-licenses` and
`smoke_bundle.py` (`--version`, fake-backend measurement, offscreen GUI),
and runs a `--lang zh_CN` fake measurement from the `.po` without writing a
`.mo`. An independent review of the patch found a regression in the first
version of the #12 settling fix and two over-strict refusals in #10; they
were fixed before the pull request and are covered by tests. **What was
not run here:** CI on macOS / Windows and Python 3.14 (the pull request's
CI is the record), a macOS or Windows bundle, any hardware cell.

Snapshot 21: 2026-09-24 — **v0.4.0, first pre-release.** Milestones 0.2,
0.3, 0.4 and the 1.0-rc software were reviewed and merged into `main`
(PRs #5–#8; review follow-ups are issues #9–#16, listed in
[RELEASE_PLAN.md](RELEASE_PLAN.md) §6). The release commit adds the
verbatim LGPL-3.0 / GPL-3.0 / PortAudio texts to the license bundle and
the `--strip` bundle gate that also catches `Qt6`-prefixed and versioned
library names; the version-driven release workflow could not be pushed
from the preparing session (no `workflow` permission) and is delivered to
the maintainer (RELEASE_PLAN.md §3). **What was run
for this snapshot:** the new gate and license-bundle tests (9 tests) on
Linux x86_64 / Python 3.11 in a scratch layout; `ruff check` and
`ruff format --check` on the changed files; the numpy macOS wheels were
opened to establish the Accelerate-vs-OpenBLAS layouts. **What was not
run here:** the full suite and mypy on the release commit (CI runs them;
the last full local run is the 339/340 count of snapshot 20 on Linux),
any bundle build (the release workflow builds them), any hardware cell.
The zh-CN catalog covers three of seven profiles (#14); the earlier
"findings translated" wording was an overclaim and is corrected in the
CHANGELOG.

Snapshot 2: 2026-09-22 — recording profiles (vocal, voice-over, acoustic
guitar, drums, room mic, choir) added on top of the foundation; same
verification policy.

Snapshot 3: 2026-09-22 — developer-facing GitHub foundation (CI, issue/PR
templates, code of conduct, security policy). Re-verified on Linux x86_64
(Ubuntu, Python 3.12.3). The `gui` extra now installs PySide6_Essentials
only.

Snapshot 5: 2026-09-22 — v0.2 reopen and compare: Tier 1 lazy exports,
lenient loaders, shipped JSON Schemas, `compare()` / CLI / GUI, and
comparison findings. Hardware validation is still not claimed.

Snapshot 6: 2026-09-22 — 0.2 follow-up after CI on `0ad2a4e`: the
comparison test now requires the ISO 3382-1 "not significant" disclaimer
instead of forbidding the word "significant", and the wheel `force-include`
lists each schema JSON file so `reverbscope/schemas/__init__.py` is not
added twice. Re-verified on Linux x86_64 (Ubuntu, Python 3.12.3).

Snapshot 7: 2026-09-22 — v0.3 trust the chain: loopback compensation,
`AudioBackend` + fake backend, progress and Stop, robustness tests, CI
OS matrix, hardware matrix started. Hardware cells are not marked PASS.
Re-verified on Linux x86_64 (Ubuntu, Python 3.12.3).

Snapshot 8: 2026-09-22 — v0.4 for everyone: gettext + zh-CN, self-contained
sessions and bundles, user settings, projects/averaging (SHOULD), CSV
export, user guide, unsigned-bundle pipeline (`release.yml`, license
bundle, GPL-module gate). Hardware cells are not marked PASS.

Snapshot 20: 2026-09-22 — macOS wheel audit: the wheel-audit test still
failed on the macOS runner. The diagnosis recorded at the time ("RECORD
omitted numpy's hidden `.dylibs/` folder") was wrong; the actual cause,
found on 2026-09-24, is that numpy's `macosx_14_0_arm64` wheel links Apple
Accelerate and bundles no shared library at all (DEPENDENCIES.md §6). The
`_on_disk_natives` merge in `audit_installed` is harmless and stays.
Hardware cells empty.

Snapshot 19: 2026-09-22 — M7 CLI output + README §6.4:
remaining CLI messages (sweep next steps, devices table,
measure/progress, error prefixes, argparse -h/--version) go
through gettext. README names the 1.0 platform set and that
anything else may work and is not tested. Hardware cells empty.

Snapshot 18: 2026-09-22 — wheel-audit test is OS-aware:
macOS/Windows CI failed because the Linux OpenBLAS+quadmath /
empty-ASIO checks ran against installed wheels. The test now
follows DEPENDENCIES.md §6 per platform; `.dylibs/` counts as
a bundled-lib folder. Hardware cells empty.

Snapshot 17: 2026-09-22 — 1.0-rc M7 CLI help / text-report labels:
`--lang zh_CN` translates CLI `--help` and every text-report
heading (ARCHITECTURE_V1.md §5.6). Windows win_amd64 wheels of
numpy/scipy/soundfile/matplotlib/Pillow opened (OpenBLAS +
msvcp140 / libsndfile; no ttconv; Pillow codecs are inside the
`.pyd` files). API/schema not frozen. Hardware cells empty.

Snapshot 16: 2026-09-22 — 1.0-rc M7 chrome / M9 wheel audit:
Linux x86_64 wheels of numpy/scipy/soundfile/sounddevice/
matplotlib/Pillow opened (`scripts/audit_wheel_contents.py`);
Windows sounddevice 0.5.6 wheel listed (ASIO DLLs still a
gate). DAW/Standalone/Results chrome goes through gettext.
API/schema not frozen. Hardware cells empty.

Snapshot 15: 2026-09-22 — 1.0-rc compare / robustness / guide:
`load_comparison` (findings re-derived on `reverbscope show
comparison.json`); Compare GUI lists matched resonances; user
guide names every Results tab plus wrong-reference and
multiple-pass troubleshooting; robustness covers comparison.json,
more WAV/sidecar cases, and a microphone used as loopback;
`reverbscope gui --smoke` is the §6.2 offscreen bundle smoke.
API/schema not frozen. Hardware cells empty.

Snapshot 14: 2026-09-22 — 1.0-rc §8 / M9 packaging remainder:
JSON depth cap, shared untrusted-file reader, src safety script,
unsigned zip/tar/dmg/Inno scaffolding and bundle smoke (fake
measure). API/schema not frozen. Hardware cells empty.

Snapshot 13: 2026-09-22 — 1.0-rc S7 / §5.8 remainder: themed docs
site from `docs/`, dark-mode plot and Qt chrome, device rate next to
the requested rate with `check_sample_rate` before Standalone
measure, compare reflections / loopback / MAD, Help → licenses.
API/schema not frozen. Hardware cells empty.

Snapshot 12: 2026-09-22 — 1.0-rc GUI/supply-chain: keyboard shortcuts
for File and Measure actions, linestyle-coded plots, Actions pinned
by SHA. API/schema not frozen. Hardware cells empty.

Snapshot 11: 2026-09-22 — 1.0-rc quality gates: docs link check, 85 %
coverage on `core`/`models`, `docs/index.md` hub, fixtures README.
API/schema not frozen. Hardware cells empty.

Snapshot 10: 2026-09-22 — 1.0-rc software on top of 0.4: Placement tab
(S5), Python 3.14 in CI (S6), M11 validation protocol with pre-chosen
tolerances, bundle.lock, SBOM/checksums and a trusted-publishing job
that still needs the maintainer `pypi` environment. Re-verified on
Linux x86_64 (Ubuntu, Python 3.12.3): 308 passed. Hardware cells are
not marked PASS. The repository is not public.

Snapshot 9: 2026-09-22 — 0.4 follow-up after the first local suite: `--json`
prints JSON again (deprecation on stderr, not `warnings.warn`); license
discovery follows files under `.dist-info/licenses/`; macOS
`NSMicrophoneUsageDescription` and the audio-input entitlement are in
`packaging/macos/`. Re-verified on Linux x86_64 (Ubuntu, Python 3.12.3).

## Implemented

| Area | What exists |
| --- | --- |
| Excitation | ESS generation (Farina), fades, level, silences; WAV + JSON sidecar; 44.1–192 kHz |
| Inverse filters | Analytic (time-reversed, −6 dB/oct) and regularised spectral division |
| Deconvolution | Whole-recording linear convolution; automatic IR location; pre-peak margin / confidence; sweep-start estimate |
| Reverberation | Schroeder integration, Lundeby truncation + compensation, EDT/T20/T30 with ISO 3382-1 ranges, validity flags, non-linearity, curvature, B·T check; broadband + octave bands 63 Hz–8 kHz (time-reversed Butterworth) |
| Frequency response | FFT with optional gating; raw kept; configurable fractional-octave smoothing |
| Background noise | Quiet-segment selection (pre-sweep / tail), RMS + peak dBFS (AES17), octave-band levels, Welch PSD, 50/60 Hz hum candidates |
| Early reflections | ETC peak candidates (delay ms, level dB re direct) with local-trend prominence |
| Placement geometry | Excess path per candidate; with a tape-measured loudspeaker distance the exact product of perpendicular distances and its two-sided bracket; with a microphone height the vertical axis (loudspeaker height, plane above the devices, horizontal separation). No coordinates, no room length or width, no wall named |
| Low-frequency resonances | Candidate peaks (< 300 Hz) with narrow-band decay vs. filter ringing comparison |
| Models & storage | Validated settings; result model with JSON export and `from_dict` load; MeasurementSession; self-contained session directory (session.json, result.json, IR WAV, optional recording.wav, always-copied sweep sidecar); `load_measurement` / `load_comparison` / `list_sessions` / `bundle_session`; recent list and `settings.json` under `$REVERBSCOPE_HOME`; shipped JSON Schemas; `comparison.json` (findings not stored); `project.json` |
| Interpretation | Finding model (`message_id` / `params` / `locale`); messages through gettext `_()`; RecordingProfile registry + entry points; seven profiles; `interpret_comparison` |
| CLI | `reverbscope sweep / analyze / analyze-ir / show / compare / schema / devices / measure / gui / session bundle / export / project`; global `--lang`, `--format`, `--backend`, `--copy-recording` |
| Public API | Lazy Tier 1 exports from `import reverbscope` (ARCHITECTURE_V1.md §5.1) |
| Loopback | Optional electrical return: pulse validation (99 % energy settling over the valid record, net of noise), regularised compensation with the FIR peak as time origin and linear division, path-delay bound; refused room-like or clipped channels leave the analysis uncompensated |
| Audio backends | `AudioBackend` protocol; PortAudio callback stream (progress polled from the waiting thread, Stop, callback errors and early stream end fail the take, buffer problems logged); `plan_input_channels` (1-based inputs → 0-based columns, validated before playback); fake backend for CI and Demo |
| Averaging | `average_decay`: VALID T values only; ISO 3382-2 class from 4.3.1 Table 1 (combinations, source and microphone positions all checked); `project average` counts distinct position labels |
| Export | CSV exporter for decay, FR, noise PSD, reflections, resonances; `reverbscope.exporters` entry points |
| i18n | stdlib gettext with `pgettext` contexts; `zh_CN` catalog for report labels, GUI chrome, CLI help, the safety warning and the findings of all seven profiles (a test requires a translation with matching placeholders for every extracted message); wheel ships a hashed `.mo`, nothing is written at run time; `--lang` / settings / `REVERBSCOPE_LANG` |
| GUI | PySide6 window: Home, Universal DAW Mode, Standalone Mode, Results (including Placement), session save/open, Compare (difference curve, matched reflections and resonances, loopback deltas), Demo, Stop, Settings, project-folder browser, tape-measure fields, dark-mode plot chrome, device rate vs requested rate, `gui --smoke` |
| Standalone Mode | Device enumeration and play+record through the selected backend with safety defaults |
| Bundles | `scripts/build_license_bundle.py` (verbatim LGPL-3.0 / GPL-3.0 / PortAudio texts from `packaging/licenses/`), `scripts/check_bundle_contents.py` (`--strip`, `--require-licenses`, `--installed-essentials`; GPL-only QML module directories matched, any `qml/` tree in a frozen bundle fails), `packaging/reverbscope.spec`, `release.yml` (the version-driven workflow on `main` since PR #18; it opened the v0.4.1 draft and refreshes it while `v0.4.1` has no tag, see RELEASE_PLAN.md §3), `scripts/smoke_bundle.py` |
| Documentation | Hub at `docs/index.md`; themed HTML site from `scripts/build_docs_site.py` (S7); release plan in `docs/RELEASE_PLAN.md` |

## Tested (all PASS on 2026-09-17 on macOS; profile work re-verified 2026-09-22;
Linux x86_64 re-verified 2026-09-24 for v0.4.1, snapshot 22)

```
pytest      470 passed  (tests/unit 366, tests/integration 54, tests/ui 12 offscreen, tests/robustness 38)
coverage    90.20 % of reverbscope.core + reverbscope.models (branch; gate 85 %)
ruff check  All checks passed  (src, tests, examples, scripts)
ruff format files already formatted
mypy        Success: no issues found in 69 source files (strict)
```

The count above is the full local run of snapshot 22 (Linux, CPython
3.12.3). The previous full local run was 339 tests (snapshot 20); the
v0.4.0 tree gives 345 tests and 87.74 % coverage on the same machine.

The 2026-09-17 macOS log recorded 256 tests. Later DSP work replaced a
peak-normalised inverse with unit in-band gain and consolidated some
assertions; the two loopback tests that still expected a time-domain peak
of 1.0 were updated on 2026-09-22 and pass on Linux. Session-reopen tests
(result `from_dict`, `load_measurement`, recent list, `reverbscope show`,
GUI re-open) plus the 0.2 compare / schema / Tier 1 lock tests brought
the suite to 259. 0.3 added loopback, the backend protocol and robustness
tests (283). 0.4 adds i18n, settings, bundles, averaging, CSV, license
gates and the macOS microphone plist (301). 1.0-rc adds the Placement
tab, the validation-protocol test and the bundle-lock test (304), then
the docs-link and fixtures tests (308), then shortcuts, plot
linestyles and Action SHA pins (311), then the themed docs site,
dark-mode plot chrome, device-rate display and compare tables (316),
then JSON depth, src-safety and unsigned-bundle packaging (322),
then comparison load/show, resonance table, richer robustness and
`gui --smoke` (334), then the Linux wheel audit and DAW/Standalone
gettext chrome (336), then CLI help / text-report labels and the
Windows wheel listing (338), then remaining CLI output
gettext and the README platform statement (339).
GUI tests also check that
matplotlib's QtAgg backend loads against PySide6_Essentials (no Addons).

What the tests prove with synthetic signals (no real-room recording is used
as evidence):

* Sweep instantaneous frequency follows `f1·exp(t/L)` (2 % tolerance);
  levels, fades, silences and lengths are exact; all six sample rates work;
  invalid settings are rejected.
* Sweep ⊛ inverse filter is a band-limited pulse with **unit in-band
  magnitude** (0 dB median over the normalisation band, analytic and
  spectral). The time-domain peak is about `2·bandwidth/fs` (~0.82 at
  48 kHz), not 1.0; everything outside ±2 ms is below −35 dB re that peak.
* Loopback recording → IR peak matches `reference_pulse()` at the expected
  index; delay and gain are recovered; too-short, silent and tail-less
  recordings raise clear errors; clipping is warned.
* Exact exponential decay → EDT/T20/T30 within 1 %; noisy exponential decays
  (RT60 0.25/0.6/1.2 s) within 5 %; octave-band T30 within 10 %; a 30 dB
  decay range yields `insufficient_decay_range` for T20/T30 (no number);
  B·T < 4 is flagged unreliable; Lundeby cross-point lands near the noise
  crossing.
* Frequency response of a delta is 0 dB flat; comb-filter notch/peak depths
  are exact; smoothing preserves constants and reduces spikes.
* Full-scale sine = 0 dBFS RMS (AES17); 60 Hz hum with harmonics is detected
  and 50 Hz is not; white noise triggers no hum.
* Discrete reflections at 18/35 ms with −9/−15 dB are found within 0.1 ms
  and 0.5 dB, also in a band-limited IR with a diffuse tail.
* A ringing 62 Hz mode is reported as a distinguishable resonance candidate;
  a flat response yields none.
* Recording profiles: all seven profiles produce findings with measured
  evidence on a rich synthetic room; voiceover flags a weaker reflection than
  generic; vocal flags a decay that room_mic accepts; drums skips noise
  findings; each profile names its recording kind; CLI `--profile` selects
  the profile and rejects unknown names (added 2026-09-22).
* End-to-end: RT60 0.45 s, reflection 18 ms/−9 dB and noise −77 dBFS are
  recovered from a synthetic room; recordings at 44.1 and 96 kHz against a
  48 kHz sweep definition; stereo channel auto-selection and explicit
  selection; WAV-only reference (spectral inverse) and resampled reference;
  loudspeaker distortion (2nd/3rd order) leaves the linear IR clean; CLI
  round trip incl. JSON; session save/load/re-open (`load_measurement`,
  `reverbscope show`, GUI File → Open and Home recent/browse); two synthetic
  positions compare with a validity on every decay delta and a noise delta
  that stays UNRELIABLE until `same_input_gain` is declared; `reverbscope
  schema` matches the shipped files; the Tier 1 export list matches
  ARCHITECTURE_V1.md §5.1; a synthetic interface FIR is removed to within
  1.0 dB median in-band error; a room-like loopback is refused; Stop on
  the fake backend zeroes the next callback block; `reverbscope --backend
  fake measure` completes a Standalone session; GUI DAW-mode, Demo and
  pick-two compare offscreen.
* Bundle gates (2026-09-24): the GPL gate rejects `QtCharts.abi3.so`,
  `libQt6QuickTimeline.so.6`, `Qt6VirtualKeyboard.dll` and a
  `QtCharts.framework` binary, ignores `.pyi` stubs and the stock
  Essentials `Qt/lib`, `Qt/plugins`, `Qt/qml` trees in
  `--installed-essentials` mode, and `--strip` removes the offenders and
  leaves `libQt6Widgets.so.6` in place; the license bundle ships the
  verbatim LGPL-3.0, GPL-3.0 and PortAudio texts and reports them as
  unresolved when PySide6 is installed and the texts are missing.
* Review follow-ups (2026-09-24, v0.4.1): the bundle gate reports and
  strips the virtual-keyboard / timeline QML plugins of the real
  Essentials 6.11.2 tree by directory and rejects any QML tree in a frozen
  bundle (#17); every message extracted from `src/` has a zh-CN
  translation with matching placeholders and four profiles print no
  English finding text under `--lang zh_CN` (#14); a 31-tap linear-phase
  interface no longer moves the compensated sweep start (5.000 ms before,
  within one sample now), a clean loopback with a 1.5–12 s post-roll and
  60 dB peak-to-noise is accepted, and a close microphone in a live room
  (RT60 1.5 / 4 s) is still refused (#12); progress is reported from the
  waiting thread, callback exceptions and early stream ends fail the take,
  Stop on a stalled device returns after the 0.5 s grace period instead of
  the timeout, a loopback on the microphone input is refused before
  playback (#13; scripted `sounddevice` stand-in, not hardware); two takes
  that differ only in the diffuse tail compare at 0.79 / 0.38 / 0.24 dB MAD
  in the 4 / 8 / 16 kHz octaves (3.30 / 2.81 / 2.44 dB before), and a
  +6.02 dB shelf is recovered within 0.3 dB (#9); a re-imported
  `impulse_response.wav` reproduces the
  sweep analysis (RT60 ±1 %, reflection ±0.05 ms / ±0.2 dB, resonance),
  declared sub-woofer IRs are accepted and noise / sweep files are refused
  (#10); session members outside the
  folder, absolute or via symlink, are refused (#11); the ISO 3382-2 class
  matrix and the project position count follow Table 1 (#15); the safety
  script catches aliases and dynamic imports (#16).
* macOS basic run: `reverbscope sweep`, `reverbscope analyze`,
  `reverbscope devices` (12 Core Audio devices listed), the example script,
  and the GUI (offscreen) ran successfully. **Not run:** a real Standalone
  measurement through loudspeakers/microphone (needs a person in the room to
  set levels) and the on-screen GUI on a display.

**Not run:** no placement result has ever been checked against a real room
with a tape measure. Every placement figure in the test suite comes from
arrivals synthesised by the image-source construction, so the tests prove the
algebra and the refusals, not the acoustics of any real surface.

## Known limitations

* A single session does not reach the ISO 3382-2 "survey" class (Table 1
  needs two microphone positions). `average_decay` means VALID T values
  across a project's positions and names the Table 1 class (read from the
  standard's preview pages; its footnotes and the other clause 4
  conditions are not checked). Decay curves are never averaged. C50, C80,
  D50 and centre time are single-position energy ratios from the same
  truncation as the decay (methodology §3b); they are not spatially averaged
  and they are not a room score. They are withheld below 20 dB of decay range.
  A recording profile may add one notice from broadband C50 or C80
  (methodology §8). That threshold is an engineering choice for the recording,
  not an ISO limit and not a grade.
* Direct sound = strongest deconvolved sample; a reflection stronger than the
  direct sound would be mis-identified (confidence margin does not catch it).
* PortAudio buffer under/overflows are reported (result warning and a
  "measure again" finding), not refused; whether a real interface reports
  them, and whether Stop and an unplugged device behave as the scripted
  stand-in does, is unverified (hardware matrix).
* Loopback validation and compensation have synthetic evidence only.
* An imported impulse response that starts at its peak cannot be checked
  for being an IR and is analysed with direct-sound confidence "low".
* Below about 1 kHz a frequency-response comparison of two positions
  mostly shows real modal differences (2–4 dB MAD for two diffuse
  realisations of the same synthetic room), not a change of treatment.
* Band filters are Butterworth, not certified IEC 61260 class 1; short
  decays in the 63/125 Hz bands are limited by B·T and are flagged.
* Lundeby parameters (20 ms initial blocks, 5 intervals/10 dB, 7.5 dB
  margins) are ReverbScope's choices within the published ranges; other tools
  will differ slightly.
* Reflection and resonance outputs are candidates; in dense diffuse tails
  some reflection candidates are statistical; room modes are not identified.
* Noise levels are dBFS only; no SPL calibration; mains-hum thresholds are
  engineering choices.
* No clock-drift correction between separate playback and recording
  devices (Universal DAW Mode relies on the DAW/interface clocking).
* `result.json` with curves is several MB for long IRs (`--no-curves` to
  shrink); the raw IR WAV is the authoritative record.
* zh-CN: core diagnostics (`warnings`, `notes`, `reason`) and plot titles
  stay English by design; the Chinese text was written by the project, not
  reviewed by a second translator.
* The GUI is functional but plain. Session re-opening, a folder/recent
  list, a two-session comparison, Settings, Demo/Stop, a `project.json`
  folder view and a Placement tab (S5) are in. There is no large session
  database.

## Not implemented (by design for v0.1 or deferred)

VST3/AU/AAX plug-ins, room score, auto-EQ/correction, cloud/accounts, 3D
room modelling, absorption material calculators, dB SPL, room-mode
identification, phase display, signed desktop installers. A themed
documentation site is generated from `docs/` (`scripts/build_docs_site.py`).
Unsigned bundles are built by `release.yml` when the version changes;
a person installing a frozen bundle on macOS/Windows is not claimed.

## Dependencies

Runtime: numpy 2.5.3, scipy 1.18.1, soundfile 0.14.0, sounddevice 0.5.6,
matplotlib 3.11.2; optional GUI extra `gui`: PySide6_Essentials 6.11.2
(Qt 6.11.2, LGPL; Addons not installed). Dev: pytest, pytest-cov, ruff,
mypy, jsonschema, hatchling (the build backend, listed for the build-hook
test). Full table with licenses: DEPENDENCIES.md.

## License status

ReverbScope: Apache-2.0 (LICENSE verbatim from apache.org, NOTICE present;
rationale in LICENSE_DECISION.md). All runtime dependencies are permissive
or LGPL used dynamically; no copyleft obligation reaches ReverbScope's source.
Obligations that apply to a *binary* distribution (Qt LGPL texts and
notices, libsndfile LGPL, FreeType credit, PortAudio/Qhull/Agg notices,
Windows ASIO DLL removal, GPL-only Qt module removal) are listed in
DEPENDENCIES.md §3–§4 and are enforced by `build_license_bundle.py` and
`check_bundle_contents.py --strip --require-licenses` in the release
workflow. They must be re-checked whenever a dependency version changes.

## Third-party provenance

No third-party source files vendored (CODE_PROVENANCE.md). Twenty-one
external repositories were audited (THIRD_PARTY_REVIEW.md); all were used as
conceptual references only. GPL projects (DRC, Aliki) and proprietary REW
were not copied. `packaging/licenses/` holds verbatim license *texts*
(LGPL-3.0, GPL-3.0, PortAudio), not code.

## Known licensing risks

* Frozen desktop builds are unsigned until the maintainer holds signing
  identities; the license bundle now carries the Qt / PySide6 texts and
  Qt stays a set of replaceable shared libraries.
* PySide6_Essentials 6.9+ wheels ship GPL-only Qt libraries
  (`libQt6QuickTimeline.so.6`, the virtual-keyboard and timeline QML
  plugins) that ReverbScope never imports; the release workflow strips them
  from every bundle and the gate fails if one survives, or if a frozen
  bundle contains a QML tree at all (#17). A local Linux PyInstaller build
  contained none of them.
* Windows sounddevice wheels contain ASIO DLLs built with the proprietary
  Steinberg SDK — stripped by the same step.
* numpy's macOS wheels differ by deployment target (Accelerate on
  `macosx_14_0`, OpenBLAS + libgfortran/libquadmath on `macosx_11_0`); the
  license bundle for a macOS build must be generated on the build machine
  (DEPENDENCIES.md §6).
* Two in-force patents adjacent to the field (US 9,959,883; US 10,816,391)
  are noted in MEASUREMENT_METHODOLOGY.md §10 so the design does not drift
  into them. Not a legal opinion.

## Next recommended milestone

See [RELEASE_PLAN.md](RELEASE_PLAN.md): **0.5.0b1** is the software beta
(early/late energy, profile clarity notices, the placement picture). It does
not meet the 0.5.0 exit criteria. **0.5.0** is still the first version with
dated hardware-matrix PASS rows. Then 1.0.0rc1 when every MUST item of
ARCHITECTURE_V1.md §3.1 is closed. API and schema versions stay unfrozen
until then.

Maintainer-only actions that this work does not do: publishing a GitHub
Release (which creates the tag), a PyPI upload, signing, a license change,
or rewriting published history. (The repository was made public by the
maintainer on 2026-09-24.)
