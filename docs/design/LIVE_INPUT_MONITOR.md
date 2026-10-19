# Live input monitor (Signal and level)

Draft, branch `gui/realtime-meter-analyzer` on top of the focused desktop
(`gui/photoshop-focused`, PR #71). GUI display layer only: no change to
`core/`, `models/`, `interpretation/`, `health.py`, file formats, the CLI or
dependencies.

## What it is

Step 2 of Standalone Mode ("Signal and level" / “信号与电平”) shows a live
**peak/RMS level meter** and a **live spectrum** of the input chosen in the
Connection step, so the input gain can be set before a take.

It is a display, not a measurement (guidelines C1): nothing it shows is
stored, exported or analysed, and the panel says so under the chart, with
every display transform it applied (Hann window, analysis length and bin
width, averaging time, fractional-octave smoothing, “uncalibrated dBFS”).
Levels are dBFS only (C4). On the fake backend (Demo, tests, screenshots) the
input is synthetic pink noise plus tones and the panel shows “Synthetic demo
data” (C9).

## It never plays sound

* The monitor opens an **input-only** stream (`sounddevice.InputStream`). It
  never opens an output, never plays a test tone, and nothing plays when a
  step is entered. A test asserts that only `InputStream` is opened.
* A sweep plays only on an **interface output the user picked by hand** in
  the Connection step. “System default” (PortAudio's default output, usually
  the computer's own speakers) and an output the list merely preselected are
  refused with an inline reason and a warning before any device check; there
  is no fallback to the default output. The fake backend, which plays
  nothing, is exempt.

Finding, not changed here (outside the GUI): `audio/inventory.preflight`,
the PortAudio backend and the CLI treat `output_device=None` as PortAudio's
default output, and the interactive CLI says it plays “through the default
output device”. The same rule for the CLI needs its own task.

## Capture path

The measurement backend (`audio/portaudio.py`) has no listen-only call, so
the GUI adds a thin source in `ui/live_input.py` with the library the backend
already uses (python-sounddevice via `audio.devices.sounddevice_module()`),
the device, 1-based input channels (microphone, then loopback if set),
sample rate and host-API options (`StreamOptions`, `host_api_settings`) of
the Connection step, and the backend's `CALLBACK_BLOCK` (256 frames).

As in the backend, the audio callback only copies the selected columns into
a single-producer/single-consumer ring buffer and advances a counter. It
never touches Qt and takes no lock. A `QTimer` (30 ms, about 33 frames/s) in
`ui/live_monitor.py` reads the newest frames, updates the meter and the
spectrum, and draws with pyqtgraph `setData`.

When it listens: only while the Standalone page and step 2 are visible, the
window is open and no take or analysis is running. It closes when the step
or the task is left, when a take starts (before the preflight touches the
device), on Esc or Pause (until Resume), and when the window closes. A change
of input device, channel, host API or rate reopens it.

Errors (no device, permission denied, device busy, backend unavailable, a
stream that stops) are shown inline; the page keeps working. On macOS a
missing microphone permission gives silence rather than an error, so two
seconds of exact digital silence show a hint.

## Constants (`display/live.py`)

| | value |
| --- | --- |
| meter scale | −60 … 0 dBFS, ticks 0, −3, −6, −12, −18, −24, −36, −48, −60 |
| attack | immediate (the frame that holds the peak) |
| release | 20 dB/s (bar and released hold marker) |
| peak hold | 1.5 s, then falls at the release rate, never below the bar |
| RMS window | 0.3 s |
| clip latch | a sample ≥ −0.1 dBFS (the health check's full-scale line); click the meter to clear |
| hot zone | above −1 dBFS (`health.HEADROOM_DB`) |
| marker | −12 dBFS (`SAFE_MAX_LEVEL_DBFS`, the level from which a sweep needs the acknowledgement) |
| spectrum | 20 Hz … 20 kHz or Nyquist, log axis, −120 … 0 dBFS |
| analysis length | 2048 / 4096 / 8192 (default) / 16384, periodic Hann, coherent-gain corrected (a sine on a bin reads its peak level) |
| averaging | none / 0.1 / 0.3 (default) / 1 s, exponential on power, frame-rate independent |
| smoothing | none (default) / 1/3 / 1/6 / 1/12 octave, mean power, display only |
| display points | about one per 1.5 px; unsmoothed points take the largest bin in their log cell so tones keep their height |
| peak-hold trace | holds 1 s, then falls 12 dB/s |

The synthetic input's pink filter uses Paul Kellet's published economy
filter coefficients (music-dsp, public domain).

## Evidence

Automated and synthetic only (C16): unit tests for dBFS, ballistics, clip
latch, bin/log mapping, smoothing and a 1 kHz sine at −6 dBFS; offscreen Qt
tests for the lifecycle with fake sources, the error messages, input-only
streams and the output rule; offscreen screenshots fed by the synthetic
input. **No sound card was opened.** Latency, drop-outs, permission prompts
and device-busy behaviour must be checked on hardware:

1. macOS + interface: enter step 2 → meter moves with the microphone; no
   sound from any output; the permission prompt appears once.
2. Deny the microphone permission → silence hint, no crash.
3. Open the interface in another program in exclusive mode (Windows WASAPI)
   → “device busy” message.
4. Unplug the interface while listening → message, no crash.
5. Start a take from step 3 and from the strip → monitor closes first; the
   take is not disturbed; Esc stops a take, and outside a take pauses the monitor.
6. Leave “System default” or the preselected output → Run refuses with the
   reason; pick the interface output → the sweep plays only there.
7. Compare the meter with the interface's own meter (peak within about 1 dB).
