# Hardware test matrix

ARCHITECTURE_V1.md §7.3: executed at least once per platform before 1.0
(M10) and recorded here with the date, the RoomScope version and the
interface. Community results are accepted through the
[Hardware compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml)
issue form, ideally with a session bundle attached. How to take part is in
[HARDWARE_TESTING.md](HARDWARE_TESTING.md).

Nothing below is marked PASS that was not run on real hardware. This file
is the started matrix for milestone 0.3; the cells are empty on purpose.

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

Record a row as `PASS YYYY-MM-DD, RoomScope x.y.z, <interface name>` or
`FAIL` with an issue link. Do not fill a cell from the fake backend.

What the automated tests do and do not show: `tests/unit/test_audio_backend.py`
runs the synthetic `fake` backend, and `tests/unit/test_portaudio_backend.py`
drives `PortAudioBackend`'s real callback code through a scripted stand-in
for `sounddevice` (progress from the waiting thread, callback exceptions,
early stream end, Stop, status flags). Neither touches PortAudio or an
interface, so neither fills a cell above; the Stop test in particular sets
the cancel flag itself (#13).
