# Hardware test matrix

**English** | [简体中文](HARDWARE_TESTS.zh-CN.md)

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

## Step by step for testers

About an hour for one interface on one computer; any subset helps. Report
what happened, including failures and checks you skipped: a "Fail" or "Not
run" with a reason is as useful as a "Pass".

**Before you start**

1. Turn the monitors or headphones **down**. The test signal is a sine sweep
   from 20 Hz to 20 kHz; start low and raise it until the sweep is clearly
   audible at the microphone, never loud. RoomScope refuses levels above
   −12 dBFS unless you confirm it.
2. Install RoomScope from the latest release (the
   [user guide](user-guide/en.md#install) has the steps per system). The
   builds are not signed yet: on macOS open it once with **System Settings ▸
   Privacy & Security ▸ Open Anyway**; on Windows click **More info ▸ Run
   anyway** in SmartScreen; on Linux install `libportaudio2` first. On macOS,
   allow microphone access when asked (**System Settings ▸ Privacy &
   Security ▸ Microphone**).
3. Connect the interface, set it up in its own control panel as you
   normally use it, and write down the driver version and the buffer size
   set there.
4. Copy **Help ▸ Environment Report for Bug Reports** after pressing **Probe
   sample rates** (or run `roomscope doctor --probe`). Nothing is played.
   Paste it into the report; it names the version, build commit, OS, audio
   systems and devices, with your home folder shown as `~`.

**Interface checks** (one answer per row of the form)

| Row | What to do | Pass when |
| --- | --- | --- |
| Device list | Open Standalone Mode (or run `roomscope devices`) | The interface is listed with the right number of inputs and outputs |
| Full take at 44.1 / 48 / 96 kHz | Standalone Mode, pick the interface for input and output, set the rate, press Start; repeat per rate the interface offers | A result opens, the direct-sound confidence is not "low", and no warning says the rate is unsupported or that the recording has dropouts |
| Channels beyond 1–2 | Choose an input or output above channel 2 | The sweep comes out of, and is recorded from, the channels you chose |
| Loopback capture | Cable one output back to one input and choose it as the loopback channel | The result says the loopback was compensated |
| Stop during playback | Press Stop while the sweep plays | The sound stops at once, no tone keeps playing, no result is saved |
| No buffer under/overflow | A full take at your usual settings | No "buffer problem(s) … may contain dropouts" warning in the result or in `roomscope.log` |
| Interface unplugged | Monitors down; unplug the cable during a take | RoomScope reports an error and saves nothing; it does not hang or crash |
| Full Standalone measurement | Microphone and loudspeaker in a room | You get a result you can read |
| Same signal through one DAW | Universal DAW Mode with the same interface | See the DAW steps below |

Buffer and latency: RoomScope uses the interface's driver settings. If a
take reports dropouts, raise the buffer size in the interface's control
panel, close other audio programs, and try again; say both settings in the
report. The developer edition (a source install, or **File ▸ Settings ▸ Show
developer tools** and a restart) also offers **Latency: Low / High** and, per system, WASAPI
exclusive mode (Windows) or letting RoomScope set the device rate (macOS);
record them if you change them. ASIO is not used by the bundles.

**DAW check** (one DAW, one take)

1. Follow [user-guide/daw-setup.md](user-guide/daw-setup.md) for your DAW
   exactly as written; note any menu that differs in your version.
2. Generate the sweep at the project's sample rate, play it through the
   loudspeaker, record the microphone, export the recording, and analyse it
   in Universal DAW Mode.
3. Pass when the direct-sound confidence is "high" and no sample-rate or
   time-stretch finding appears. Then, if you can, the two negative checks in
   the DAW matrix above: they pass when RoomScope names the problem.

**What to send**

The `audio stream:` line in `roomscope.log` records the settings of the
opened stream: device IDs, requested/reported Hz, channel counts, block size
and input/output latency in seconds. Attach that line together with any
buffer warning. The reported latency can differ from the requested low/high
class. The reported rate is PortAudio's value, not an independent clock
measurement: when the host cannot report the hardware rate, it repeats the
requested rate ([sounddevice stream properties](https://python-sounddevice.readthedocs.io/en/0.5.6/api/streams.html)).
A difference greater than 0.5 Hz is flagged because WAV/session rates are
integer Hz. Takes with timing warnings retain diagnostic numbers but mark
their decay/energy metrics unreliable and withhold the estimated RT60;
resolve the device problem and repeat the measurement.

* The form: [audio interface test report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml)
  or [DAW compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml).
* The environment report (step 4 above).
* For any failure, `roomscope.log` from the data folder (`~/.roomscope/`, or
  **Environment Report ▸ Open Data Folder**), and if a result was saved, a
  session bundle made with `roomscope session bundle <session folder>
  --no-audio` (leave out `--no-audio` only if you are happy to share the
  recording of your room).
