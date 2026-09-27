# Hardware test matrix

ARCHITECTURE_V1.md §7.3: executed at least once per platform before 1.0
(M10) and recorded here with the date, the RoomScope version and build
commit, the operating system and the interface.

Nothing below is marked PASS that was not run on real hardware: a physical
machine, a physical interface and its actual driver, with real playback and
capture where the check needs them. The Demo mode, the `fake` backend, the
synthetic and scripted-PortAudio tests, and CI runners do not count. The
cells are empty on purpose; no check has been run on real hardware yet.

**Contributing a result.** Open an
[Audio interface test report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml)
or a [DAW compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml)
issue. Both ask for the environment report
(**Help → Environment Report for Bug Reports**, or `roomscope doctor`; the
interface report with probed sample rates, `roomscope doctor --probe`),
which names the version, build commit, OS, host APIs and devices. The
interface report asks Pass / Fail / Not run for each row of the table below.
A maintainer copies the result into a cell below with a link to the issue.

| Check | macOS | Windows | Linux |
| --- | --- | --- | --- |
| Device enumeration | | | |
| Sample-rate negotiation 44.1 kHz | | | |
| Sample-rate negotiation 48 kHz | | | |
| Sample-rate negotiation 96 kHz | | | |
| Channel mapping beyond 1–2 | | | |
| Loopback capture | | | |
| Stop during playback (output silent within one callback) | | | |
| Full take without a logged buffer under/overflow (`roomscope -v measure`) | | | |
| Device unplugged during a take is reported as a failure, not a recording | | | |
| Full Standalone measurement | | | |
| Same signal through one DAW (Universal DAW Mode) | | | |

Record a cell as `PASS YYYY-MM-DD, RoomScope x.y.z (commit), <OS version>,
<interface and driver>, #issue` or `FAIL ... #issue`. Do not fill a cell from
the fake backend, a CI runner or a test.

## DAW matrix

One Universal DAW Mode measurement per DAW, following
[user-guide/daw-setup.md](user-guide/daw-setup.md) as written: the sweep
generated at the project rate, recorded and exported with the listed menus,
analysed with `direct_sound_confidence` high. A cell also checks that the
notes are right for that DAW version; correct the guide in the same pull
request when they are not. Two negative checks per DAW confirm the diagnosis:
a 48 kHz sweep in a 44.1 kHz project with the DAW's import conversion off
(expect the sample-rate finding; a DAW that resamples during playback, such
as Live or REAPER, should instead give a valid result, and Digital Performer
refuses to play the file: record which happened), and, where the DAW
stretches, the clip stretched (for example to 97 %) or the tempo changed after
import (expect the time-stretch finding).

| DAW (version) | macOS | Windows | Linux | Sample-rate finding | Time-stretch finding |
| --- | --- | --- | --- | --- | --- |
| Pro Tools | | | n/a | | |
| Logic Pro | | n/a | n/a | | |
| GarageBand | | n/a | n/a | | |
| Cubase / Nuendo | | | n/a | | |
| Fender Studio Pro (Studio One) | | | | | |
| Ableton Live | | | n/a | | |
| REAPER | | | | | |
| FL Studio | | | n/a | | |
| Bitwig Studio | | | | | |
| Digital Performer | | | n/a | | |
| Audacity | | | | | n/a |

What the automated tests show instead: `tests/integration/test_daw_exports.py`
analyses the same take written as Broadcast WAV (with `bext`, `iXML` and
`JUNK` chunks), WAVE_FORMAT_EXTENSIBLE, RF64, Wave64, AIFF, CAF and FLAC at
16 / 24 / 32-bit PCM and 32-bit float, and stereo bounces of a mono
microphone; `tests/integration/test_playback_speed.py` plays a synthetic sweep
unconverted at 44.1 / 88.2 / 96 kHz and time-stretched by ±3 % and checks
the diagnosis. None of them runs a DAW, so none fills a cell above.

What the automated tests do and do not show: `tests/unit/test_audio_backend.py`
runs the synthetic `fake` backend, and `tests/unit/test_portaudio_backend.py`
drives `PortAudioBackend`'s real callback code through a scripted stand-in
for `sounddevice` (progress from the waiting thread, callback exceptions,
early stream end, Stop, status flags). Neither touches PortAudio or an
interface, so neither fills a cell above; the Stop test in particular sets
the cancel flag itself (#13).
