# Contributing to RoomScope

Thank you for helping build a measurement tool people can trust. You do not
need to write code to make a real difference.

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security reports go
through [SECURITY.md](SECURITY.md), not public issues.

## Ways to help

| You have... | Most useful contribution |
| --- | --- |
| An audio interface and 15 minutes | A [hardware compatibility report](docs/HARDWARE_TESTING.md): the biggest gap right now |
| A DAW you know well | Notes on routing the sweep and exporting the take in that DAW (user guide, `good first issue`) |
| A result that looks wrong | A [measurement problem](.github/ISSUE_TEMPLATE/measurement.yml) issue with a session bundle |
| Another language | Translations: the catalog is `src/roomscope/locale/zh_CN/LC_MESSAGES/roomscope.po` |
| Python / DSP experience | Bug fixes, tests, and review of the methodology |

## Development setup (5 minutes)

```bash
git clone https://github.com/jingyemingyue/RoomScope.git
cd RoomScope
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
roomscope demo                                          # sanity check, no hardware needed
```

On Linux, Standalone Mode and the GUI tests also need PortAudio and a few Qt
platform libraries (CI installs them automatically):

```bash
sudo apt-get install -y libportaudio2 libegl1 libgl1 libxkbcommon0 libxcb-cursor0
```

The `gui` extra installs **PySide6_Essentials** (LGPL-3.0), not the PySide6
meta-package, so GPL-only Qt modules never land in a developer environment.

## Checks before a pull request

All of these run locally in a few minutes. Please run them before you push:
CI repeats them on every push, and its minutes are limited.

```bash
QT_QPA_PLATFORM=offscreen pytest   # unit + integration + robustness + offscreen GUI tests
ruff check . && ruff format --check .
mypy                               # strict
```

Useful while working:

```bash
roomscope demo                                           # CLI end to end on a simulated room
roomscope gui                                            # the desktop app
python examples/synthetic_measurement.py out/            # the Python API end to end
python scripts/check_doc_links.py                        # relative links under docs/
python scripts/smoke_bundle.py --no-gui --out /tmp/smoke-session   # fake-backend measure
QT_QPA_PLATFORM=offscreen python scripts/render_readme_assets.py  # README screenshots
```

GitHub Actions runs the suite on Ubuntu (Python 3.12, 3.13, 3.14), macOS and
Windows (3.12), plus lint, mypy, schema and packaging jobs. Tests that need
audio hardware are not part of the suite; synthetic signals are used instead.

## What a good pull request looks like

* One logical change, with a description that says **why**.
* Tests: every DSP change has a synthetic test with a known expected result;
  every bug fix has a test that failed before the fix.
* `CHANGELOG.md` updated under `[Unreleased]`.
* User-visible text goes through `_()` and has a Simplified Chinese entry in
  the catalog (a test checks that every message has one; ask in the pull
  request if you cannot write the translation).
* If the report or the GUI changes visibly, regenerate the README images with
  `scripts/render_readme_assets.py`.
* The pull-request template's checklist is filled in; CI is green before merge.

## Ground rules

These exist so that every number RoomScope prints stays defensible.

1. **Correctness before features.** A metric that cannot be computed reliably
   is reported as `insufficient_decay_range` / `unreliable`, never as a
   plausible-looking number.
2. **Cite the method.** Any new DSP function states its algorithm source
   (paper, standard) in the module docstring and in
   `docs/MEASUREMENT_METHODOLOGY.md`, with units and validity conditions.
3. **Clean-room by default.** Implement from the published equations. Do not
   paste code from other repositories, Stack Overflow, blog posts or AI
   answers. If adapting third-party code is unavoidable, first record it in
   `docs/THIRD_PARTY_REVIEW.md` and `docs/CODE_PROVENANCE.md` and keep the
   upstream copyright notice. Code from repositories without a clear license
   is never used.
4. **License review before dependencies.** Every new package (runtime or dev)
   gets a row in `docs/DEPENDENCIES.md` with its upstream license, bundled
   native libraries and obligations. Copyleft (GPL/AGPL/LGPL/MPL) dependencies
   need an explicit discussion in the pull request.
5. **Core stays pure.** `roomscope.core` takes and returns NumPy arrays and
   dataclasses; no Qt, no device access, no file I/O. Front ends only call
   `roomscope.core.pipeline.analyze`.
6. **Honest units.** dBFS unless calibrated. No "room score".
7. **Safety.** Nothing changes system volume, audio configuration or DAW
   settings. Default playback levels stay conservative.
8. **Only LGPL Qt modules** (QtCore, QtGui, QtWidgets). Never import
   GPL-only modules such as QtCharts, QtDataVisualization or QtGraphs.
9. **No invented evidence.** Never mark a hardware cell PASS from the fake
   backend, and never present synthetic data as a real measurement.

## Tests

* `tests/conftest.py` has helpers for synthetic rooms and exponential decays.
* Keep tests fast: use short sweeps (2 s) and 48 kHz unless the test is about
  sample rates.
* Never rely on a real room recording as the only evidence.
* Inverse filters are normalised to **unit in-band gain** (0 dB loopback
  frequency response). The time-domain IR peak of a loopback is not 1.0; assert
  against `reference_pulse(settings)` or against the frequency response.

## Adding a recording profile

Implement `RecordingProfile` (see `src/roomscope/interpretation/profiles.py`),
register it in `_PROFILES`, add a synthetic test in
`tests/unit/test_interpretation.py`, and document the thresholds in
`docs/MEASUREMENT_METHODOLOGY.md` §8. Do not put advice inside `roomscope.core`.

## Commit and release policy

* Do not create tags/releases, change the license, or delete remote branches
  without maintainer approval.
* A change to `pyproject.toml` also runs the release workflow (bundles on
  three operating systems); keep such changes for release pull requests
  where possible.
* How a version is cut: [docs/RELEASE_PLAN.md](docs/RELEASE_PLAN.md) and
  [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Reporting measurement problems

Please attach: the sweep sidecar JSON, the recorded WAV (or a link), the
`result.json`, your DAW/interface and sample rate, and what you expected.
`roomscope session bundle <session> --out report.zip` collects the files.
