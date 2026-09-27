# RoomScope user guide

RoomScope measures a recording room so you can hear what the room is doing to
close-miked sources. It does not score the room and it does not correct it.

This page is the English guide. The Chinese translation is
[zh-CN.md](zh-CN.md).

## Install

**From Python.** RoomScope is not on PyPI yet, so install it from GitHub into
a virtual environment (Python 3.12 or newer):

```bash
python3 -m venv roomscope-env
source roomscope-env/bin/activate          # Windows: roomscope-env\Scripts\activate
pip install "roomscope[gui] @ git+https://github.com/jingyemingyue/RoomScope.git"
```

Leave out `[gui]` for the command line only. With pipx:
`pipx install git+https://github.com/jingyemingyue/RoomScope.git`.
`pip install -e ".[dev,gui]"` is the developer install from a clone
(CONTRIBUTING.md). `pip install roomscope` from PyPI is planned, not available yet.

**Unsigned desktop bundle.** The `release.yml` workflow builds one-directory
bundles for macOS, Windows and Linux; they appear on the Releases page once
the maintainer publishes a release (none has been published yet). Until the
maintainer holds signing identities they are **unsigned**:

* **macOS:** right-click the app → Open, or System Settings → Privacy & Security
  after Gatekeeper blocks it. Grant microphone access when asked
  (`NSMicrophoneUsageDescription` is in the bundle Info.plist).
* **Windows:** SmartScreen may warn; choose “More info” → “Run anyway”.
* **Linux:** extract the directory and run `roomscope`. An AppImage may follow.

The About dialog and `THIRD_PARTY_LICENSES/` list Qt, libsndfile and the other
bundled licenses.

## Try it without hardware

```bash
roomscope demo
```

The demo writes a sweep and two **simulated** recordings of one made-up room
(a position close to a desk and a side wall, and one moved back), analyses
both and compares them. It uses no audio device and plays nothing. The files
land in `roomscope-demo/`; every saved session is marked
`"mode": "synthetic_demo"` so it cannot be mistaken for a measurement. Open
them with `roomscope show roomscope-demo/position-a`,
`roomscope compare roomscope-demo/position-a roomscope-demo/position-b --same-input-gain`
or in the desktop app.

## Universal DAW Mode

1. `roomscope sweep --out sweep.wav` (or the GUI “Universal DAW Mode” generate
   button). Keep the `.roomscope-sweep.json` sidecar next to the WAV.
2. Import the WAV on a new DAW track. Route it to the monitors.
3. Arm a second track with the measurement microphone. Do not trim the bounce.
4. Optional loopback: bounce a two-channel export (microphone + electrical
   return) and pass `--channel 0 --loopback-channel 1`.
5. `roomscope analyze --recording take.wav --sweep sweep.wav --out session/`
   or drop the files in the GUI.

Per-DAW notes from users belong in issues labelled `good first issue`.

## Standalone Mode and the loopback cable

`roomscope devices` lists interfaces. `roomscope measure --out session/` plays
the sweep and records. `--input-channels 1,2 --loopback-channel 2` records an
electrical return on input 2.

Start at a low monitor level. Levels above −12 dBFS need `--acknowledge-level`
every time; that confirmation is never saved.

**Demo** (GUI, `roomscope demo`, or `roomscope --backend fake measure`) runs
the same flow on a synthetic room. Nothing is sent to a loudspeaker.

## Reading a result

Each metric has a validity flag. `insufficient_decay_range` means the number is
withheld, not that it is zero. There is no single score.

Core diagnostics (`warnings`, `notes`, `reason`) stay in English in
`result.json` so bug reports compare across languages. The UI shows them
verbatim under a heading that says so.

The Results page has seven tabs:

| Tab | What it shows |
| --- | --- |
| Overview | Broadband and octave-band EDT / T20 / T30 / RT60 with validity; the text report; core diagnostics (always English). |
| Impulse Response | The deconvolved IR. The peak is the direct sound; it is not normalised to 1.0. |
| Frequency Response | Raw (dotted) and smoothed (solid) magnitude. A dashed curve is the electrical loopback when compensation ran. 0 dB is the interface, not “flat in the room”. |
| Decay | Schroeder / energy-decay curves. Broadband is a solid line; octave bands use changing dash patterns so colour is not the only cue. |
| Noise | Quiet-segment spectrum and 50/60 Hz hum candidates. |
| Early Reflections | ETC peaks (delay ms, level dB re direct). Open markers for candidates. |
| Placement | Excess path, and — only with a tape-measured loudspeaker distance — loudspeaker height, the plane above both devices, and horizontal separation. No wall is named. |

Low-frequency resonance candidates stay in the Overview text report (and in
`resonances.csv` after `roomscope export`). They are not a separate tab.

## Placement

The Results page has a Placement tab. Without a tape-measured loudspeaker
distance RoomScope only reports each arrival's excess path. With the
distance (and, for the vertical axis, the microphone height) it reports
loudspeaker height, the plane above both devices and the horizontal
separation. It never names a wall or gives room length or width.

Enter the tape numbers in Universal DAW Mode or Standalone Mode before
Analyze, or pass `--speaker-distance` / `--mic-height` / `--temperature`
on the CLI.

## Comparing two positions

`roomscope compare baseline/ candidate/ --same-input-gain` (or the GUI Compare
page). A decay delta is only VALID when both sides are VALID. The noise delta
needs an explicit “input gain unchanged” declaration. A change is never called
significant; ISO 3382-1’s just-noticeable difference for T is quoted as context.

The Compare page lists matched early reflections (delay ±0.5 ms) and
low-frequency resonances (within 1/6 octave, with decay-distinguishable
flags). `roomscope compare … --out comparison.json` writes the numbers only;
`roomscope show comparison.json` prints the report again and **re-derives**
findings (they are never stored in the file).

## Projects and averaging

A project folder holds `project.json` and ordinary session folders.
`roomscope project init --out room/ --name Booth` then
`roomscope project add room/ session/ --position desk`.
`roomscope project average room/` averages VALID T values only, never decay
curves, and names the ISO 3382-2 class the position counts reach.

## Export and language

`roomscope export session/ --format csv --out curves/` writes every curve.
`--lang zh_CN` (or Settings → Language, or `ROOMSCOPE_LANG`) translates
findings, the text-report labels, the GUI and CLI help (`roomscope --help`
and every subcommand). Units stay untranslated; digits stay ASCII.
Core diagnostic strings from `roomscope.core` stay English.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Direct-sound confidence not high | Wrong sweep sidecar; loudspeaker distortion; trim the recording? Do not trim. |
| Wrong reference | The `.roomscope-sweep.json` next to the WAV must be the file RoomScope wrote for *this* sweep (same duration, band and fades). A sweep from another session, or the recording used as the reference, will mis-locate the IR. |
| Multiple passes in one bounce | Play the sweep once. Two passes in the same WAV look like two IRs; RoomScope keeps the strongest peak and the rest becomes “room”. Bounce a single take. |
| Clipping warning | Lower playback or input gain. |
| Insufficient decay range | Longer sweep, slightly louder playback, or a quieter room. |
| Device rate mismatch | The GUI shows the device rate next to the requested one; pick a supported rate. |
| Loopback refused | The return must look like an electrical pulse, not a room. If the second channel is another microphone, compensation is refused and the analysis continues uncompensated. |

## Bug-report bundle

`roomscope session bundle session/ --out report.zip` zips the folder.
`--no-audio` leaves the WAVs out if you do not want to share a recording of
the room. Attach the zip to a measurement issue. Settings and the rotating
log live under `$ROOMSCOPE_HOME` (`~/.roomscope` by default).
