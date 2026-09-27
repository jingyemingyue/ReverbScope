# Hardware testing: help RoomScope meet real interfaces

RoomScope's analysis is covered by a synthetic test suite that passes on
Linux, macOS and Windows. What it has **not** had yet is a person running it
with a real audio interface, a real loudspeaker and a real microphone. That is
the most useful contribution right now, and you do not need to write code.

A test takes about 15 minutes. A failure report is just as valuable as a
success.

## What you need

* RoomScope installed (see the [README](../README.md#install)).
* An audio interface, or your computer's built-in audio.
* A loudspeaker (your monitors) and a microphone. A measurement microphone is
  best; any omnidirectional condenser works for a compatibility test.
* Optional: a DAW, if you want to test Universal DAW Mode.

## Safety first

Turn the monitor level **down** before the first sweep. RoomScope plays a sine
sweep that covers 20 Hz–20 kHz; it never changes your system volume, and in
Standalone Mode levels above −12 dBFS need `--acknowledge-level`. Protect
your ears and your tweeters: start quiet and raise the level between takes.

## The tests

Run what applies to you. Each one is independent.

### 1. Device list (1 minute)

```bash
roomscope devices
```

Does your interface appear with the right number of inputs and outputs?

### 2. Standalone measurement (5 minutes)

```bash
roomscope -v measure --out test-standalone/ --input-device <idx> --output-device <idx>
```

`-v` logs buffer under/overflows. Did the sweep play, did the take finish,
does the report show a plausible impulse response ("direct-sound confidence
high")?

Optional variations: `--sample-rate 44100` or `96000`; an input or output
channel above 2 (`--input-channel 3`); an electrical loopback cable on a
second input (`--input-channels 1,2 --loopback-channel 2`). Stop test: in
the desktop app, press **Stop** while a sweep plays; the output should go
silent right away. Ctrl+C in the terminal should also end the take. Report
how quickly each one went quiet.

### 3. Universal DAW Mode (5–10 minutes)

```bash
roomscope sweep --out sweep.wav
# play sweep.wav in your DAW, record the microphone, export recording.wav
roomscope analyze --recording recording.wav --sweep sweep.wav --out test-daw/
```

Did RoomScope find the sweep in your export without trimming?

### 4. Desktop app (optional)

`roomscope gui`: does it start, list your devices, and complete a measurement?

## What to report

Open a **[Hardware compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml)**.
The form asks for:

| Field | Example |
| --- | --- |
| RoomScope version | `roomscope --version` → `roomscope 0.4.1` |
| Operating system | macOS 15.1 (Apple silicon) / Windows 11 23H2 / Ubuntu 24.04 |
| Python version | `python --version` → 3.12.7 |
| Audio interface | Focusrite Scarlett 2i2 (4th gen), built-in audio, ... |
| Driver / host API | Core Audio, ASIO, WASAPI, ALSA, PipeWire (shown in `roomscope devices`) |
| Microphone | Behringer ECM8000, or "vocal condenser (not a measurement mic)" |
| DAW (if used) | REAPER 7.2, Logic Pro 11, ... or "none" |
| Sample rate / buffer size | 48 kHz / 256 samples |
| Loopback cable used? | yes / no |
| Which tests you ran, and the result | PASS / FAIL / partly, per test |
| Logs | output of the `-v` run, any error message |

Attach a session bundle if you can. It is the fastest way for us to reproduce
a problem:

```bash
roomscope session bundle test-standalone/ --out report.zip            # includes the WAVs
roomscope session bundle test-standalone/ --no-audio --out report.zip  # results only
```

Only attach recordings of your own room. Do not include other people's
performances without permission.

## Compatibility matrix

Results from reports land here once a maintainer has read the attached logs.
Every cell that nobody has run is **Not tested**; nothing is filled in from the
synthetic backend.

| Interface | OS | Driver / host API | Standalone | Universal DAW Mode | Loopback | Reported by / issue |
| --- | --- | --- | --- | --- | --- | --- |
| *(none yet: be the first)* | Not tested | Not tested | Not tested | Not tested | Not tested | — |

| Platform | Device list | Standalone measurement | DAW round trip | Stop during playback |
| --- | --- | --- | --- | --- |
| macOS | Not tested | Not tested | Not tested | Not tested |
| Windows | Not tested | Not tested | Not tested | Not tested |
| Linux | Not tested | Not tested | Not tested | Not tested |

The release-gate checklist (the stricter per-platform list that must pass
before 1.0) is [HARDWARE_TESTS.md](HARDWARE_TESTS.md). The measurement
accuracy campaign against a reference instrument is
[VALIDATION.md](VALIDATION.md).

## Known issues

* Desktop bundles are unsigned: macOS Gatekeeper and Windows SmartScreen warn
  on first start ([user guide](user-guide/en.md#install)).
* On Linux, Standalone Mode needs the system PortAudio library
  (`libportaudio2`).
* The Windows ASIO host API depends on how `sounddevice` was built; if your
  ASIO driver is missing from `roomscope devices`, report which host APIs you
  do see.
