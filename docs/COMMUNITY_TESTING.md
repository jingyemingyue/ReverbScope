# Community testing: one computer, one interface, one report

**English** | [简体中文](COMMUNITY_TESTING.zh-CN.md)

Start with the [public-beta installation guide](PUBLIC_TESTING.md) or a specific
candidate supplied by the maintainer. Record its asset SHA256 and build commit.
The [hardware matrix](HARDWARE_TESTS.md) remains **NOT RUN** until a physical
run is reported. Missing equipment is a reason to skip, not to simulate a pass.
No audio device, measurement microphone, speaker or DAW is available in the
2026-10-15 cloud audit environment.

## Evidence labels

| Status | Meaning | Evidence |
| --- | --- | --- |
| Automated PASS | A named automated check passed on a specified commit/environment | Command, exit status, log/CI run; synthetic inputs labelled Synthetic / Demo |
| Hardware PASS | A person executed that row on physical equipment | Date, version/SHA, machine, interface/driver, routing/rate/buffer, attachments, issue |
| FAIL | The check ran and its expected outcome was not met | Actual outcome, message, reproduction and scope (automated or physical) |
| NOT RUN | Not executed, unsupported by available equipment, or missing evidence | Reason; never infer PASS from another rate, OS or DAW |

An environment report or accepted-rate probe cannot prove a full take. A DAW
manual is a procedure source, not a compatibility test. A reported driver
latency is not an independently measured round-trip latency. The existing
matrix's `PASS` cells mean physical Hardware PASS; link the original report.

## Prepare one report per run

From a checkout, Python 3.12+ (standard library only):

```bash
python scripts/prepare_test_report.py --out test-reports/mac-48k --probe --daw "Fender Studio Pro: fill version"
```

If the app is not on PATH, add `--executable` followed by its executable path.
Mac Desktop candidate example:

```bash
python scripts/prepare_test_report.py --out test-reports/mac-candidate --executable /Applications/ReverbScope.app/Contents/MacOS/ReverbScope --probe
```

Public beta 1 uses `/Applications/RoomScope.app/Contents/MacOS/RoomScope` or
`--executable roomscope`; do not collect a source install's environment while
testing a bundle. `--language zh-CN` creates the Chinese form; `--skip-environment`
creates a blank form on a computer without the app. `--probe` briefly asks
devices about rates but never plays/records audio. Nothing is uploaded.

The tool creates `report.md`, `run.json`, `environment.json`, `commands.txt` in
a **new** directory. It refuses an existing directory to preserve prior results.
Every physical check starts NOT RUN even when environment collection succeeds.
Paths/settings and raw error strings are omitted from the collected JSON;
device names remain and may identify people. Review all files before sharing.
Collection failures are recorded as FAIL without copying private exception text.

Without Python, copy the table below and **Help → Environment Report for Bug
Reports** (or run the tested app's `doctor --probe`). The legacy beta app uses
the RoomScope name. Add the same fields manually; both routes are valid.

## Short Apple Silicon Mac acceptance

Use the arm64 Desktop bundle on the actual Mac, not Rosetta, an offscreen Qt
session or a source-only launch. Allow microphone access. Connect one physical
interface and a microphone/speaker; note OS, interface/driver, input/output
numbers, buffer, and any Core Audio rate-setting option. Start at **−20 dBFS**
with monitor gain low. Disable direct/software monitoring of the microphone
into the speaker, processing and loopback feedback. A measurement mic is needed
for a defensible frequency-response claim; record an ordinary mic as a limitation.

| Step | Action and acceptance | Initial status |
| --- | --- | --- |
| 1 | Verify asset hash; install, launch natively, switch EN/zh-CN, resize; essential controls and Stop remain reachable | NOT RUN |
| 2 | Enumerate devices; verify counts; select actual input/output; test another channel above 2 if available | NOT RUN |
| 3 | At 44.1, 48 and 96 kHz, separately complete playback + recording + analysis. Record actual reported rate, no dropout warning; unsupported rate = NOT RUN with reason | NOT RUN |
| 4 | During a new sweep press Stop. Output must become silent immediately, UI recover, cancelled take must not appear as a successful result. Human observation cannot prove the one-callback timing bound | NOT RUN |
| 5 | Turn monitor gain down; unplug interface during a take. Error/cancellation, no hang/crash or successful phantom take. Reconnect, refresh devices and complete another take | NOT RUN |
| 6 | Copy the `audio stream:` line and buffer warnings after a complete take. Report `latency_s`, block size and requested/reported Hz; no invented measured latency | NOT RUN |
| 7 | With suitable **line-level** output-to-input cabling and no feedback, select a distinct loopback input. Complete a take; confirm compensation status/reason. No cable/input = NOT RUN | NOT RUN |
| 8 | Save the successful measurement, note displayed values/validity, quit, relaunch and reopen that saved session. Values, validity and plots agree; preserve audio/sidecar as expected | NOT RUN |

Steps 1–3, Stop and save/reopen are the first useful report; finish the remaining
rows before calling the Mac checklist complete. No equipment means NOT RUN for
all physical rows. Avoid absolute SPL/accuracy claims without calibration/reference.

## Fender Studio Pro / Studio One: first DAW report

Use **Universal DAW Mode**. Current source/candidate buttons are **Save Test Signal WAV...**,
**Choose Recording...**, **Choose Reference Sweep...** and **Analyze**;
newer Draft GUI branches can differ. Capture
actual labels/version rather than silently following a different PR's screenshots.
The detailed [vendor-sourced DAW guide](user-guide/daw-setup.md#fender-studio-pro-formerly-presonus-studio-one)
is the menu reference; the following is a test, and has **NOT RUN** status here.

1. Create an empty session/song at **48 kHz** using the same physical interface.
   Disable stretch-to-session-tempo. Generate a 48 kHz sweep and retain its JSON
   sidecar. Import it on a playback track; route only to the chosen speaker.
2. Track Inspector: **Tempo → Don't Follow**; Event Speedup 1, Transpose/Tune 0,
   Normalize off. No inserts, master processing, auto-EQ or room correction.
3. Arm a separate mono microphone track; switch its Monitor off after arming
   (and disable interface direct monitoring). Record pre-silence, the complete
   sweep and the full decay tail without looping or trimming the sweep.
4. Export **only the microphone recording**, using Export Selection or Export
   Stems for that track. WAV, session rate, preferably 32-bit float, no normalize,
   stretch, gain changes or effects. Keep the original capture and sidecar.
5. Import the exported recording with the sweep definition; Analyze. Record
   direct-sound confidence and all health/validity warnings. A physical roundtrip
   passes when analysis completes with high direct-sound confidence and no
   unintended rate/stretch finding. A warning is evidence to investigate, not a
   reason to replace the result with a demo. Save, quit and reopen this session.
6. Optional negative controls: deliberately play a 48 kHz sweep unconverted in
   a 44.1 kHz project, then separately stretch a clip to 97%. Record actual DAW
   conversion behavior and diagnosis. A DAW that resamples correctly need not
   produce a mismatch finding. Restore the clean setup for subsequent takes.

## Reuse the report for another DAW

| DAW | Setup reference and required details | Initial status |
| --- | --- | --- |
| Pro Tools | [Guide](user-guide/daw-setup.md#avid-pro-tools); exact version, session rate, SRC choice, mic monitoring off, selected recording export | NOT RUN |
| Logic Pro / GarageBand | [Guide](user-guide/daw-setup.md); exact version, Flex/Smart Tempo choices, no normalization, exported mic track and tail | NOT RUN |
| REAPER | [Guide](user-guide/daw-setup.md#cockos-reaper); exact version, project/device rate, timebase, rate 1.0, mic-only render | NOT RUN |
| Any other DAW | Same sweep → physical capture → unprocessed mic export → sidecar analysis, plus actual import/stretch/export settings | NOT RUN |

Use one report directory per DAW/version/routing setup. `--daw` only records a
label; it never launches or controls a DAW or marks it compatible.

## Attach, triage, reproduce, retest

Attach the edited report, reviewed `environment.json`, asset hash, relevant
`audio stream:` line/warnings, result screenshot and DAW export/stretch screenshots.
Prefer a session bundle made with `session bundle <session> --no-audio --out report.zip`;
even without audio, review room labels, paths and JSON metadata. Share a recording
only with consent and no private speech. The generated `commands.txt` lists commands
for the tested executable. Do not upload entire private DAW projects.

Submit [hardware](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware.yml)
or [DAW](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw.yml)
reports (Chinese forms also available). A maintainer records exact build and
scope, reproduces failures, adds the smallest non-private regression fixture,
fixes on the appropriate line, and asks the reporter to rerun the new build.
Only after review does a dated row with an issue link enter the matrix. Earlier
FAIL/NOT RUN evidence remains visible; a fix is not Hardware PASS until retested.
