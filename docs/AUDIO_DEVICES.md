# Audio devices and host APIs

**English** | [简体中文](AUDIO_DEVICES.zh-CN.md)

Last checked: 2026-09-24. This page covers **Standalone Mode**: ReverbScope
plays and records through PortAudio with python-sounddevice 0.5.6, whose
Windows and macOS wheels bundle PortAudio v19.7.0; on Linux it loads the
distribution's `libportaudio2` [14][15]. PortAudio behaviour was read in the
v19.7.0 source [9]–[12]. In Universal DAW Mode the DAW owns the device path
and the same rules apply ([user-guide/daw-setup.md](user-guide/daw-setup.md)).

## 1. Why the device path matters

A sweep measurement treats loudspeaker, room and microphone as a linear,
time-invariant system (ISO 18233 sets requirements for both [8]) and
deconvolves the recording with the generated sweep. Whatever the device path
adds is measured as if it were the room.

* **One sample clock.** Playback and recording should share one clock, or
  synchronised clocks [7]. Two clocks drift apart (§3).
* **No sample-rate conversion.** A converter is a low-pass filter with a
  delay; PipeWire documents its resampler's cutoff, window and latency [35].
  A mixer running at 48 kHz cannot carry the part of a 96 kHz sweep above
  24 kHz. A converter that follows another clock (drift correction, adaptive
  resampling) changes its ratio during the take: a time variance, which
  sweeps tolerate far better than MLS, but not completely [2, §2.4][5].
* **No processing.** Equalisers, automatic gain control, echo cancellation
  and other effects loaded by the operating system [21], and other
  applications mixed into the output [18], end up in the result. A limiter or AGC is a
  non-linearity, and a sweep cannot move every distortion artefact out of the
  causal part of the response [3].
* **Unchanged level.** Nothing should rescale the signal. A sweep's crest
  factor is 3.01 dB, so it can run near full scale where MLS needs 5–8 dB of
  headroom [2, §2.2]; ReverbScope still starts at −20 dBFS to protect the
  loudspeaker (`audio/backend.py`).
* **Stable latency, no dropouts.** The deconvolved time origin includes the
  round-trip latency; only a loopback gives electrical time zero
  ([MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) §2a). An output
  underflow inserts a gap, an input overflow discards samples [9]; ReverbScope
  counts these flags and keeps them with the take: they appear in the
  result's warnings and as a "measure again" finding (`audio/portaudio.py`,
  `AudioSignal.device_warnings`). The take is analysed, not refused, until
  real interfaces show whether some host APIs report them spuriously.

## 2. Host APIs per platform

Each PortAudio device belongs to one host API [9][13], so an interface
appears once per host API it is reachable through (`reverbscope devices` shows
the host API in brackets). Rank 1 is best. "Default latency" is PortAudio's
default suggestion (low / high), not a measured round trip.

### Windows

| Rank | Host API (PortAudio name) | Sample-rate conversion | Mixing / processing | Default latency |
| --- | --- | --- | --- | --- |
| 1 | `Windows WASAPI`, exclusive | none: the hardware must support the format [16] | none: bypasses the audio engine [23] | device minimum / default period [10] |
| 2 | `ASIO` | the driver's rates (`ASIOCanSampleRate`) [12] | vendor driver, bypasses the engine [23] | preferred / maximum driver buffer [12] |
| 3 | `Windows WDM-KS` | none: the driver pin must support the rate [12] | below the system mixer; locks other users out [12] | 10 / 40 ms (WaveRT), 10 / 85 ms (WaveCyclic) [12] |
| 4 | `Windows WASAPI`, shared | PortAudio accepts only the shared-mode rate unless `auto_convert` is set [10] | audio engine: mixing and APOs [18][21] | as exclusive; engine buffers default to 10 ms [23] |
| 5 | `Windows DirectSound` | automatic [16] | audio engine [19]; deprecated API [22] | 120 / 240 ms [12] |
| 6 | `MME` | automatic [16] | audio engine [19] | 90 / 180 ms [12] |

* **WASAPI shared** is what ReverbScope opens by default (no host-specific
  settings, `audio/portaudio.py`); `reverbscope measure --wasapi-exclusive`
  opens exclusive mode instead (below). The engine runs at the shared-mode format
  chosen in the Sound control panel (device ▸ Properties ▸ Advanced ▸
  *Default Format*) [16]; PortAudio reports that rate as the default and
  refuses others [10]. `WasapiSettings(auto_convert=True)` would insert a
  channel matrixer and sample-rate converter
  (`AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM`) [14][20]; ReverbScope therefore does
  not offer it. Set the
  Default Format to the measurement rate and disable enhancements
  (Enhancements tab, or Advanced tab) [24]. Endpoint effects apply even to
  raw streams [21], and the codec or a DSP may process in hardware [22].
* **WASAPI exclusive** (`WasapiSettings(exclusive=True)` [14]; ReverbScope:
  `--wasapi-exclusive`) needs *Allow
  applications to take exclusive control of this device* (on by default) and
  silences other applications [17]; PortAudio quotes ~3 ms, shared ≥ 20 ms [10].
* **ASIO** DLLs are removed from ReverbScope's bundles for licensing
  ([DEPENDENCIES.md](DEPENDENCIES.md) §3); sounddevice loads its ASIO DLL only
  with `SD_ENABLE_ASIO` set [14]. One ASIO device serves both directions [12].
* **Microphone privacy:** Settings ▸ Privacy & security ▸ Microphone ▸
  *Microphone access* and *Let desktop apps access your microphone* [25].

### macOS

Core Audio is the only host API (rank 1). Use one interface set to the
measurement rate, or an aggregate device (§3).

* **Nominal rate.** A device runs at one nominal sample rate
  (`kAudioDevicePropertyNominalSampleRate`) [29], set in Audio MIDI Setup ▸
  *Format* [26]; PortAudio reports it as the default rate [11].
* **Conversion.** By default PortAudio "plays nice": the AUHAL converts
  output and an AudioConverter converts input, at maximum quality, instead of
  changing the device [11]. `CoreAudioSettings(change_device_parameters=True)`
  lets PortAudio set the nominal rate (possibly disrupting other programs,
  even when only querying); `fail_if_conversion_required=True` then refuses
  any conversion [11][14]. ReverbScope passes no CoreAudioSettings by default:
  set the rate in Audio MIDI Setup; the GUI flags a device rate that differs
  (`ui/pages.py`). `reverbscope measure --coreaudio-set-rate` passes
  `change_device_parameters=True, fail_if_conversion_required=True`, so the
  take runs at the requested rate or fails instead of converting.
* **Latency.** Default low = the device's fixed latency + 64 frames; high =
  fixed latency + current buffer size; 10 / 100 ms if unreadable [11].
* **Microphone permission:** System Settings ▸ Privacy & Security ▸
  Microphone [30]; a packaged app must declare `NSMicrophoneUsageDescription`
  [31]. Without it ReverbScope reports *"recording is silent"*
  ([user guide](user-guide/en.md)).

### Linux

| Rank | Host API / device | Sample-rate conversion | Mixing / processing | Default latency |
| --- | --- | --- | --- | --- |
| 1 | `ALSA`, `hw:X,Y` | none: "raw communication without any conversions" [32] | none [32] | (512−128)/fs / (2048−512)/fs: 8 / 32 ms at 48 kHz, if the hardware allows [12] |
| 2 | `JACK Audio Connection Kit` | none: one server rate, other rates refused [12][37] | the JACK graph | port latency ÷ rate [12] |
| 3 | `ALSA`, `plughw:` | only when rate, format or channels are not native [32] | none | as `hw:` |
| 4 | `ALSA`, `default` / `dmix` / `pulse` / `pipewire` | yes: dmix defaults to 48 kHz [33]; PipeWire resamples to its graph rate, 48 kHz by default [34][35]; PulseAudio runs at its default or alternate rate [36] | dmix mixes streams [32]; PipeWire's adapter converts format, rate and channel layout [35] | set by the server |
| 5 | `OSS` | driver; PortAudio accepts a rate within 1 % [12] | ALSA's OSS emulation, if used [38] | not assessed |

* PortAudio names ALSA hardware `card: device (hw:X,Y)` and also lists
  plug-in and server PCMs (`default`, `pulse`, `pipewire`, ...);
  `PA_ALSA_PLUGHW=1` makes it open `plughw:` instead of `hw:` [12].
* **PipeWire** resamples when a stream's rate differs from the graph rate
  and adapts device clocks to the graph clock; in the *Pro Audio* profile,
  nodes of one device are assumed to share a clock and are not resampled
  [35]. Graph-rate switching (`default.clock.allowed-rates`) is off by
  default [34].

## 3. Separate input and output devices

A PortAudio full-duplex stream needs both devices in one host API [9]; ASIO
needs one device [12]; Core Audio joins two devices with a ring buffer
between two callbacks [11]. Two devices have two clocks: with a relative rate
error ε the recording slips by ε·T over a sweep of length T (for
illustration, 50 ppm over 10 s is 0.5 ms, 24 samples at 48 kHz).

* **Effect.** A small mismatch usually leaves the IR clean; a larger one
  "skews" it, low frequencies arriving before high ones. A skewed IR still
  gives usable room parameters, but in Farina's example correcting it gained
  12.45 dB of peak-to-noise ratio [1, §3.4]. Drift convolves the IR with an
  all-pass filter that follows the sweep's frequency trajectory, its group
  delay proportional to the sweep length [6]. Harmonic responses, placed by
  the sweep rate [4], move too; averaging [7] and MLS [5] suffer as well.
* **Correction** needs the drift rate (from a loopback or repeated
  excitation), then resampling or a compensation filter [6][7], or a
  reference-based inverse filter or a stretched inverse sweep [1, §3.4].
  ReverbScope does not estimate drift (`core/loopback.py`).
* **Recommendation.** Use one interface for both directions. On macOS, if
  two devices are unavoidable, build an aggregate device, make the device
  with the most reliable clock the clock (sync) source and enable drift
  correction (resampling) for the others, or lock them by word clock and
  leave it off [27][28] (HAL: `kAudioSubDevicePropertyDriftCompensation`
  [29]). PipeWire outside the Pro Audio profile resamples devices to its graph
  clock [35]: drift is hidden, at the cost of resampling.
* **A loopback shows it.** Feed the output device into a second input of the
  input device; the loopback shows the same skew. ReverbScope refuses a
  loopback with less than 99 % of its energy within 10 ms after the peak, and
  its compensation window spans 5 ms before to 15 ms after the peak
  (`core/loopback.py`), so it cannot absorb a larger skew. ReverbScope warns if
  playback and recording are different physical devices (`audio/inventory.py`).

## 4. How ReverbScope probes devices

* **Listing:** `sd.query_devices()`, `sd.query_hostapis()` [14]. The default
  rate is PortAudio's `defaultSampleRate`: the mix rate on WASAPI [10], the
  nominal rate on Core Audio [11], the server rate on JACK, on ALSA the
  device default or the rate nearest 44.1 kHz without resampling [12].
* **Rate check:** `check_sample_rate()` (`audio/devices.py`) calls
  `sd.check_input_settings()` / `sd.check_output_settings()`, i.e.
  `Pa_IsFormatSupported` [9][14]. The GUI checks the chosen rate on the
  selected devices before a take, the CLI on `--input-device` /
  `--output-device`, and the inventory (`audio/inventory.py`) checks 44.1,
  48, 88.2, 96, 176.4 and 192 kHz for **one channel** (`channels=1`); without
  a channel count sounddevice fills in the device's maximum, and a rate the
  device supports only with fewer channels would then fail [11][14]. Latency
  `'high'` and no host settings (WASAPI shared, Core Audio "play nice") are
  used for the check [14].
* **No stream is started**, but ALSA opens the PCM and applies hardware
  parameters and Core Audio opens and closes a stream to answer [11][12].
  The suggested latency is ignored [9].
* **"Supported" is not "native".** MME and DirectSound accept rates Windows
  converts [16] (PortAudio's DirectSound code does not check the rate at
  all [12]); WASAPI shared accepts only the engine rate but still
  processes [10][21]; Core Audio converts by default [11]; ALSA `plughw:`,
  `default`, `pulse` and `pipewire` convert [32][35]; ALSA and OSS accept a
  rate within 1 % [12]. Only `hw:`, WDM-KS, WASAPI exclusive, ASIO and JACK
  answer for the rate the hardware or server actually runs at.
* **One host API per take.** A full-duplex stream needs both devices on one
  host API; `Pa_OpenStream` otherwise fails with `paBadIODeviceCombination`
  [9]. ReverbScope checks this before playing and, when only one device is
  chosen, uses that host API's default device for the other direction
  (`resolve_duplex` in `audio/inventory.py`); on Windows the system default
  is MME's, which would not match a WASAPI choice. Channels beyond the
  device's count are refused before playing (`check_channels`), and only
  then is the sample rate asked of the devices the stream will open, with
  the channel counts it opens (`Pa_IsFormatSupported`). The GUI and
  `reverbscope measure` run the same `preflight`.
* **The take:** one full-duplex `sd.Stream`: float32, 256-frame blocks, the
  device's default high latency, "typically more robust" [14] (`portaudio.py`);
  `--latency low` selects the default low latency instead.

## 5. References

Accessed 2026-09-24. See also [research/literature.md](research/literature.md).

1. A. Farina, "Advancements in Impulse Response Measurements by Sine Sweeps," AES 122nd Convention, Vienna, 2007 May 5–8, paper 7121 (AES E-Library 14106). Author PDF, §3.4 "Clock mismatch": https://www.angelofarina.it/Public/Papers/226-AES122.pdf
2. S. Müller, P. Massarani, "Transfer-Function Measurement with Sweeps," J. Audio Eng. Soc. 49(6), 443–471, 2001 June (AES E-Library 10189). Author copy, §1.7, §2.2, §2.4: https://audioroundtable.com/misc/Mueller.pdf
3. A. Torras-Rosell, F. Jacobsen, "A New Interpretation of Distortion Artifacts in Sweep Measurements," J. Audio Eng. Soc. 59(5), 283–289, 2011 (AES E-Library 15929). https://orbit.dtu.dk/en/publications/a-new-interpretation-of-distortion-artifacts-in-sweep-measurement/
4. A. Novák, P. Lotton, L. Simon, "Synchronized Swept-Sine: Theory, Application, and Implementation," J. Audio Eng. Soc. 63(10), 786–798, 2015. doi:10.17743/jaes.2015.0071; https://hal.science/hal-02504321v1
5. P. Svensson, J. L. Nielsen, "Errors in MLS Measurements Caused by Time Variance in Acoustic Systems," J. Audio Eng. Soc. 47(11), 907–927, 1999 November. https://aes2.org/publications/elibrary-page/?id=10266
6. N. J. Bryan, M. A. Kolar, J. S. Abel, "Impulse Response Measurements in the Presence of Clock Drift," AES 129th Convention, San Francisco, 2010 November 4–7 (AES E-Library 15592). https://ccrma.stanford.edu/groups/chavin/publications/AES129_ClockDrift.pdf
7. H. Gamper, "Clock drift estimation and compensation for asynchronous impulse response measurements," Proc. HSCMA 2017, San Francisco, pp. 186–190. doi:10.1109/HSCMA.2017.7895587; https://www.microsoft.com/en-us/research/wp-content/uploads/2017/03/Clock_drift_estimation_HSCMA_2017.pdf
8. ISO 18233:2006, *Acoustics — Application of new measurement methods in building and room acoustics*. https://www.iso.org/standard/40408.html (scope read in the public preview; its clauses on the measurement system were not checked).
9. PortAudio v19.7.0, `include/portaudio.h` and `src/common/pa_front.c`. https://github.com/PortAudio/portaudio/blob/v19.7.0/include/portaudio.h, https://github.com/PortAudio/portaudio/blob/v19.7.0/src/common/pa_front.c
10. PortAudio v19.7.0, WASAPI: `include/pa_win_wasapi.h`, `src/hostapi/wasapi/pa_win_wasapi.c`. https://github.com/PortAudio/portaudio/blob/v19.7.0/include/pa_win_wasapi.h
11. PortAudio v19.7.0, Core Audio: `include/pa_mac_core.h`, `src/hostapi/coreaudio/pa_mac_core.c`, `pa_mac_core_utilities.c`, `notes.txt`. https://github.com/PortAudio/portaudio/tree/v19.7.0/src/hostapi/coreaudio
12. PortAudio v19.7.0, host APIs `wmme`, `dsound`, `wdmks`, `asio`, `alsa`, `jack`, `oss`. https://github.com/PortAudio/portaudio/tree/v19.7.0/src/hostapi
13. PortAudio, "API Overview". https://portaudio.com/docs/v19-doxydocs/api_overview.html
14. python-sounddevice 0.5.6: platform-specific settings, checking hardware, streams, installation, NEWS. https://python-sounddevice.readthedocs.io/en/0.5.6/api/platform-specific-settings.html, https://python-sounddevice.readthedocs.io/en/0.5.6/api/checking-hardware.html, https://python-sounddevice.readthedocs.io/en/0.5.6/api/streams.html, https://python-sounddevice.readthedocs.io/en/0.5.6/installation.html, https://github.com/spatialaudio/python-sounddevice/blob/0.5.6/NEWS.rst
15. spatialaudio/portaudio-binaries, build workflow (checks out PortAudio v19.7.0). https://github.com/spatialaudio/portaudio-binaries/blob/master/.github/workflows/build-libs.yml
16. Microsoft Learn, "Device Formats." https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-formats
17. Microsoft Learn, "Exclusive-Mode Streams." https://learn.microsoft.com/en-us/windows/win32/coreaudio/exclusive-mode-streams
18. Microsoft Learn, "User-Mode Audio Components." https://learn.microsoft.com/en-us/windows/win32/coreaudio/user-mode-audio-components
19. Microsoft Learn, "About the Windows Core Audio APIs." https://learn.microsoft.com/en-us/windows/win32/coreaudio/about-the-windows-core-audio-apis
20. Microsoft Learn, "AUDCLNT_STREAMFLAGS_XXX Constants." https://learn.microsoft.com/en-us/windows/win32/coreaudio/audclnt-streamflags-xxx-constants
21. Microsoft Learn, "Audio Processing Object Architecture." https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-processing-object-architecture
22. Microsoft Learn, "Windows Audio Architecture." https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/windows-audio-architecture
23. Microsoft Learn, "Low Latency Audio." https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/low-latency-audio
24. Microsoft Support, "Disable Audio Enhancements." https://support.microsoft.com/en-us/topic/disable-audio-enhancements-0ec686c4-8d79-4588-b7e7-9287dd296f72
25. Microsoft Support, "Turn on app permissions for your microphone in Windows." https://support.microsoft.com/en-us/windows/privacy/turn-on-app-permissions-for-your-microphone-in-windows
26. Apple, Audio MIDI Setup User Guide, "Set up audio devices." https://support.apple.com/guide/audio-midi-setup/set-up-audio-devices-ams59f301fda/mac
27. Apple, Audio MIDI Setup User Guide, "Set aggregate device settings." https://support.apple.com/guide/audio-midi-setup/set-aggregate-device-settings-ams094c7edb4/mac
28. Apple Support, "Create an Aggregate Device to combine multiple audio devices." https://support.apple.com/en-us/102171
29. Apple Developer, `kAudioDevicePropertyNominalSampleRate` (CoreAudio `AudioHardwareBase.h`; `kAudioSubDevicePropertyDriftCompensation` in `AudioHardware.h`). https://developer.apple.com/documentation/coreaudio/kaudiodevicepropertynominalsamplerate
30. Apple, macOS User Guide, "Control access to the microphone on Mac." https://support.apple.com/guide/mac-help/control-access-to-your-microphone-on-mac-mchla1b1e1fe/mac
31. Apple Developer, `NSMicrophoneUsageDescription`. https://developer.apple.com/documentation/bundleresources/information-property-list/nsmicrophoneusagedescription
32. ALSA project, alsa-lib, "PCM (digital audio) plugins." https://www.alsa-project.org/alsa-doc/alsa-lib/pcm_plugins.html
33. alsa-lib, `src/conf/alsa.conf` (`defaults.pcm.dmix.rate 48000`). https://github.com/alsa-project/alsa-lib/blob/master/src/conf/alsa.conf
34. PipeWire, pipewire.conf(5). https://docs.pipewire.org/page_man_pipewire_conf_5.html
35. PipeWire, pipewire-props(7), "Resampler Parameters" and `clock.name`. https://docs.pipewire.org/page_man_pipewire-props_7.html
36. PulseAudio, pulse-daemon.conf(5). https://manpages.debian.org/bookworm/pulseaudio/pulse-daemon.conf.5.en.html
37. JACK Audio Connection Kit, API reference, "Controlling & querying JACK server operation" (`jack_get_sample_rate`). https://jackaudio.org/api/group__ServerControl.html
38. Linux kernel documentation, "Notes on Kernel OSS-Emulation." https://www.kernel.org/doc/html/latest/sound/designs/oss-emulation.html
