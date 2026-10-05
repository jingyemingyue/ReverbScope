# Contributing to ReverbScope

> 中文用户：欢迎在 issue 中用中文提问、报告问题和提交测试结果（中文表单见“New issue”页面）；本贡献指南只提供英文版。

Thank you for helping build a measurement tool people can trust. The rules
below exist so that every number ReverbScope prints stays defensible.

Please also follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security reports
go through [SECURITY.md](SECURITY.md), not public issues.

## Ground rules

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
5. **Core stays pure.** `reverbscope.core` takes and returns NumPy arrays and
   dataclasses; no Qt, no device access, no file I/O. Front ends only call
   `reverbscope.core.pipeline.analyze`.
6. **Honest units.** dBFS unless calibrated. No "room score".
7. **Safety.** Nothing changes system volume, audio configuration or DAW
   settings unless the user opts in (the only such option today is
   `--coreaudio-set-rate`, see SECURITY.md). Default playback levels stay
   conservative.
8. **Only LGPL Qt modules** (QtCore, QtGui, QtWidgets). Never import
   GPL-only modules such as QtCharts, QtDataVisualization or QtGraphs.

## Development setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,gui]"
pytest                    # unit + integration + offscreen GUI smoke tests
ruff check . && ruff format --check .
mypy
python scripts/build_docs_site.py --out site   # themed docs (S7)
python scripts/smoke_bundle.py --no-gui --out /tmp/smoke-session   # fake measure
# add --no-gui only for a CLI-only install; bundles run gui --smoke offscreen
```

On Linux, Standalone Mode and the GUI tests also need PortAudio and a few Qt
platform libraries (CI installs them automatically):

```bash
sudo apt-get install -y libportaudio2 libegl1 libgl1 libxkbcommon0 libxcb-cursor0
```

All three of pytest / ruff / mypy must pass before a pull request is opened.
GitHub Actions repeats them on Python 3.12, 3.13 and 3.14. Tests that need audio
hardware are not part of the suite; synthetic signals are used instead.

The `gui` extra installs **PySide6_Essentials** (LGPL-3.0), not the PySide6
meta-package, so GPL-only Qt modules never land in a developer environment.

## Tests

* Add a synthetic test with a known expected result for every DSP change
  (`tests/conftest.py` has helpers for synthetic rooms and exponential decays).
* Keep tests fast: use short sweeps (2 s) and 48 kHz unless the test is about
  sample rates.
* Never rely on a real room recording as the only evidence.
* Inverse filters are normalised to **unit in-band gain** (0 dB loopback
  frequency response). The time-domain IR peak of a loopback is not 1.0; assert
  against `reference_pulse(settings)` or against the frequency response.

## Adding a recording profile

Implement `RecordingProfile` (see `src/reverbscope/interpretation/profiles.py`),
register it in `_PROFILES`, add a synthetic test in
`tests/unit/test_interpretation.py`, and document the thresholds in
`docs/MEASUREMENT_METHODOLOGY.md` §8. Do not put advice inside `reverbscope.core`.

## Commit and release policy

* One logical change per commit, with a message that says *why*.
* Do not create tags/releases, change the license, or delete remote branches
  without maintainer approval.
* `CHANGELOG.md` is updated in the same pull request.
* Use the pull-request template; CI must be green before merge.

## Reporting problems and test results

Every issue template asks for the environment report: **Help → Environment
Report for Bug Reports** in the app, or `reverbscope doctor` in a terminal
(`--probe` adds the sample rates each device accepts; nothing is played). It
names the version, the build commit, the OS, the settings and the audio
devices, with your home folder shown as `~`.

* **Bug report**: a crash, an error, or wrong behaviour.
* **Measurement problem**: a number looks wrong. Attach the sweep sidecar
  JSON, the recorded WAV (or a link), `result.json`, or a session bundle
  (`reverbscope session bundle <session> --out report.zip`).
* **Audio interface test report** and **DAW compatibility report**: you ran
  ReverbScope with real hardware or through a DAW. These are the only source of
  the PASS/FAIL cells in [docs/HARDWARE_TESTS.md](docs/HARDWARE_TESTS.md);
  a failed run is as useful as a passed one.
