# Release checklist: first public alpha

This page turns [RELEASE_PLAN.md](RELEASE_PLAN.md) into the concrete next
release. RELEASE_PLAN.md stays authoritative for the version ladder and the
gates; this page covers what users will see on the Releases page and on PyPI.

## 1. Where the Releases page stands (checked 2026-09-27)

* One **draft pre-release** named `v0.4.1`, created by `release.yml`, with
  unsigned bundles attached. Its body is the CHANGELOG `[0.4.1]` section,
  which says "still private" (the repository is public now), lists internal
  fixes by issue number, and predates `roomscope demo` and the new README.
* **No tags, no published release, nothing on PyPI.** The name `roomscope`
  was still free on PyPI on 2026-09-27 (`https://pypi.org/pypi/roomscope/json`
  returned 404); that can change until it is registered.

A visitor who opens Releases today sees "There aren't any releases here". That
reads as "not usable yet" even though the software runs end to end.

## 2. Recommendation: cut v0.4.2 as the first public alpha

1. **Delete the `v0.4.1` draft** (Releases → the draft → Delete). It was never
   published, so no tag or download disappears. Its notes are outdated.
2. **Prepare the release commit** (one pull request, so the release workflow
   runs once on it and once on `main`):
   * `pyproject.toml`: `version = "0.4.2"` plus the metadata in §5 below.
     A `pyproject.toml` change triggers `release.yml`, which builds bundles on
     three OSes; that is why the metadata was not changed in the
     presentation pull request.
   * `CHANGELOG.md`: rename `[Unreleased]` to `[0.4.2] - <date>`.
   * `docs/STATUS.md`: a dated snapshot of what was run.
3. **After merge**, `release.yml` opens a `v0.4.2` draft with the bundles.
   Replace the draft's body with the notes in §4 (they are written for users;
   the CHANGELOG stays the detailed record).
4. **Publish it as a pre-release** (keep "Set as a pre-release" ticked). The
   title should say what it is: `v0.4.2 — first public alpha`.

Publishing is the maintainer's decision (RELEASE_PLAN.md §3). Nothing on this
page creates a tag.

## 3. Release notes template

Use this structure for every 0.x release body. Keep it honest: say what was
verified and what was not.

```markdown
**RoomScope <version> — <alpha | beta | release candidate>**

Open-source, DAW-independent room acoustics analysis for recording engineers.

## Try it
<install command> · `roomscope demo` works without any audio hardware.

## What's new
- <user-visible change, one line each>

## Verified for this release
- Synthetic test suite: <N> tests on Linux (3.12–3.14), macOS and Windows (3.12)
- Bundles: built and smoke-tested (fake backend + offscreen GUI) on <OSes>
- Real audio hardware: <"not tested yet" | list of confirmed reports with issue links>

## Known limitations
- <unsigned bundles; not on PyPI; no hardware validation; ...>

## Downloads
<bundle>: <what it is; Gatekeeper / SmartScreen note for unsigned builds>

Full details: CHANGELOG.md
```

## 4. Draft notes for v0.4.2

```markdown
**RoomScope 0.4.2 — first public alpha**

Open-source, DAW-independent room acoustics analysis for recording engineers:
reverberation (RT60), early reflections, frequency response, noise floor and
low-frequency resonances, plus a comparison of two microphone positions.

## Try it
    pip install "roomscope[gui] @ git+https://github.com/jingyemingyue/RoomScope.git@v0.4.2"
    roomscope demo        # no audio hardware needed: a simulated room, clearly labelled

or download a desktop bundle below.

## What's new since the first draft (0.4.1)
- `roomscope demo`: try the whole workflow (sweep → recording → analysis →
  comparison) on a simulated room, without an interface or a microphone.
- Reports start with an "At a glance" summary; comparisons show one row per
  band and explain each value that could not be compared.
- Cleaner CLI: grouped `--help` with defaults, a single-line progress bar,
  colour only on terminals (`--no-color`, `NO_COLOR`), `roomscope` alone
  prints a quick start.
- The desktop app shows the report in a fixed-width font.
- `roomscope gui` on a CLI-only install explains how to add the desktop app
  instead of crashing.
- Piping a report to a file on Windows no longer crashes on "Δ" or "→".
- A hardware testing guide and a "Hardware compatibility report" issue form.
- 0.4.1 fixes (loopback time origin, PortAudio callback, comparison smoothing,
  complete Chinese catalog, ...) are included; see CHANGELOG.md.

## Verified for this release
- Synthetic test suite on Linux (Python 3.12–3.14), macOS and Windows (3.12).
- Bundles built and smoke-tested by the release workflow (fake backend,
  offscreen GUI).
- **Real audio hardware: not tested yet.** Please help:
  docs/HARDWARE_TESTING.md.

## Known limitations
- Alpha: the Python API and JSON schemas may change before 1.0.
- Bundles are unsigned: macOS Gatekeeper and Windows SmartScreen will warn.
- Not on PyPI yet.
- Levels are dBFS unless calibrated; no dB SPL.
```

## 5. PyPI readiness

Checked locally on 2026-09-27 with the 0.4.1 sources plus this change:

| Check | State |
| --- | --- |
| `uv build` → sdist + `py3-none-any` wheel | OK |
| `twine check` (metadata and README rendering) | PASSED for both |
| Wheel contents: package, JSON schemas, `.po` and compiled `.mo`, new `demo.py` / `cli/style.py` | OK |
| Fresh CLI-only install from the wheel: `roomscope demo` in English and `--lang zh_CN` | OK |
| License metadata (`license = "Apache-2.0"`, `license-files`) | OK (PEP 639) |
| Python versions (`requires-python >= 3.12`, classifiers 3.12–3.14) | OK, matches CI |
| Trusted publishing, `pypi` environment, `ROOMSCOPE_PUBLISH_PYPI` | **Not set up** (maintainer, RELEASE_PLAN.md §5) |
| README on PyPI | **Needs a fix before the first upload:** relative links and images (`docs/assets/...`) do not resolve on pypi.org. Either make them absolute (`https://github.com/jingyemingyue/RoomScope/blob/main/...`, images via `raw.githubusercontent.com`) or rewrite them at build time |
| sdist size | ~1 MB, mostly `docs/assets` screenshots. Harmless; exclude `docs/assets` from the sdist if it matters |

Proposed `pyproject.toml` metadata for the version bump (search-friendly,
nothing claimed that is not true):

```toml
description = "DAW-independent room acoustics analyzer for recording engineers: RT60, early reflections, frequency response, noise floor and microphone-position comparison."
keywords = [
  "room acoustics", "acoustics", "recording", "recording studio",
  "audio engineering", "microphone placement", "impulse response",
  "sine sweep", "RT60", "reverberation", "early reflections",
  "frequency response", "noise floor", "DAW", "audio interface",
]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Console",
  "Environment :: X11 Applications :: Qt",
  "Intended Audience :: End Users/Desktop",
  "Intended Audience :: Education",
  "Intended Audience :: Science/Research",
  "Operating System :: MacOS",
  "Operating System :: Microsoft :: Windows",
  "Operating System :: POSIX :: Linux",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
  "Topic :: Multimedia :: Sound/Audio :: Analysis",
  "Topic :: Multimedia :: Sound/Audio :: Capture/Recording",
  "Topic :: Scientific/Engineering :: Physics",
  "Typing :: Typed",
]

[project.urls]
Homepage = "https://github.com/jingyemingyue/RoomScope"
Documentation = "https://github.com/jingyemingyue/RoomScope/blob/main/docs/user-guide/en.md"
Changelog = "https://github.com/jingyemingyue/RoomScope/blob/main/CHANGELOG.md"
Issues = "https://github.com/jingyemingyue/RoomScope/issues"
"Hardware testing" = "https://github.com/jingyemingyue/RoomScope/blob/main/docs/HARDWARE_TESTING.md"
```

`Development Status :: 3 - Alpha` matches the README badge: the software runs
end to end and is tested synthetically, and no hardware result exists yet.
Move to `4 - Beta` when the 0.5.0 exit criteria (one executed hardware
platform) are met.
