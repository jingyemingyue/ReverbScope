# Measuring through your DAW

**English** | [简体中文](daw-setup.zh-CN.md)

Universal DAW Mode is designed for any DAW that can play one WAV file and
record another at the same time. RoomScope never talks to the DAW: it only needs the
recording, exported whole. This page lists what every DAW has to get right,
then the steps in the DAWs most studios use. The Chinese translation is
[daw-setup.zh-CN.md](daw-setup.zh-CN.md).

> **Documented workflow, not yet tested in a DAW.** The steps and menu names
> below are written from each vendor's current documentation, with a numbered
> source per step (the few third-party sources are marked). None of them has
> been run with RoomScope in a real DAW yet: the DAW matrix in
> [HARDWARE_TESTS.md](../HARDWARE_TESTS.md) is empty. If you run one, or your
> version differs, please open a
> [DAW compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml).

## What every DAW must do

1. **Same sample rate.** The sweep sample rate is the only RoomScope
   session setting that must follow the DAW project you are using.
   `roomscope daw` lists declared or fake projects; if none or more than
   one is in play, RoomScope asks and will not guess.
   `roomscope sweep --follow-daw --daw REAPER` (or `--daw NAME --sample-rate`
   when none is detected) writes the sweep at that project's rate. In the
   GUI, use **Choose DAW to follow...** before saving the test signal.
   You can still set the rate yourself:
   `roomscope sweep --sample-rate 44100 --out sweep_44k.wav`, or pick
   the rate in the GUI's Step 1. A 48 kHz file played unconverted in a
   44.1 kHz project runs 8 % slow and cannot be deconvolved; RoomScope reports
   *"a file generated at 48000 Hz was played at 44100 Hz"* when that happens,
   provided the `.roomscope-sweep.json` sidecar is next to the WAV (keep it
   there). Exporting the recording at another rate is harmless: the DAW
   converts on export and RoomScope follows the file's rate. RoomScope
   does not query a running host; this documentation VM has no DAW.
2. **No time-stretching.** Warp, Flex Time, Follow Tempo, elastic audio and
   stretch modes must be off for the test-signal clip, and the tempo must not
   change after import. RoomScope reports *"the DAW time-stretched it"* when
   the sweep runs off speed by more than the estimate's own spread (about
   1.3 % for the default 10 s sweep, 2.4 % for 3 s, 5.5 % for 1 s) and the
   sidecar is used; a smaller stretch still spoils the measurement (low direct-sound confidence,
   unreliable decay) without a named cause, so check the clip rather than
   rely on the report.
3. **A clean playback path.** Bypass every plug-in on the test-signal track,
   on the buses it passes and on the master: limiters, clippers, "loudness"
   or tape plug-ins, and **room-correction** plug-ins (SoundID Reference,
   ARC and the like) unless you mean to measure the corrected system. No
   fades, clip gain or automation on the test signal. A fader or clip gain
   below 0 dB is fine.
4. **One loudspeaker.** Route the test-signal track to the one loudspeaker
   you are measuring (pan hard or use a mono output). Two loudspeakers
   playing the same sweep interfere and the result describes neither.
5. **Record the microphone on its own mono track**, input monitoring off
   (otherwise the microphone feeds back to the loudspeaker), with no
   plug-ins, sends or gate on it. Start recording before the test signal
   starts, or record the whole clip in one pass: the file begins with one
   second of silence for exactly this. Record one pass only: turn loop /
   cycle recording off. If you pull the microphone channel's fader down to
   silence monitoring, set it back to 0 dB before an export that renders
   through the channel (a stem or track export).
6. **Export the recorded track or clip whole** at the project sample rate as
   WAV (Broadcast WAV, RF64 and Wave64 are fine), AIFF, CAF or FLAC, 24-bit or
   32-bit float, **without normalising** (normalising hides the noise floor
   level you compare between takes). Mono or stereo both work; with a stereo
   file pick the microphone channel in the GUI or with `--channel`. Do not
   trim: RoomScope finds the sweep, and the silence after it is the decay.
7. **Latency does not matter.** RoomScope finds the sweep wherever it is in
   the recording, so plug-in delay compensation and interface latency need no
   setting.
8. **Optional loopback.** Record the interface's electrical return (an output
   cabled back to a spare input) on a second track in the same pass. Export
   both tracks as one two-channel file (`--channel 0 --loopback-channel 1`)
   or as two files (`--loopback return.wav`).

Then analyse:

```bash
roomscope analyze --recording "Mic_01.wav" --sweep sweep_44k.wav --out session/
```

or choose the files in the GUI's Universal DAW Mode.

## Avid Pro Tools

* **Sample rate:** set when the session is created; Session Setup shows it
  [P1, p. 1814]. Generate the sweep at that rate.
* **Import:** File ▸ Import ▸ Audio [P1, p. 641]. If the Import Audio dialog's
  comments field warns that the file's rate differs from the session's
  [P1, p. 643], generate the sweep at the session rate instead of enabling
  *Apply SRC*.
* **Time-stretching:** leave Elastic Audio off: the track's Elastic Audio
  selector reads *None – Disable Elastic Audio* [P1, p. 1317]. Import with
  File ▸ Import rather than by dragging from the desktop, or set the
  preference *Drag and Drop From Desktop Conforms to Session Tempo* to
  *None*: with *All Files*, dragged files become tick-based Elastic Audio
  that follows the session tempo [P1, p. 647].
* **Record:** a new mono audio track with the microphone input,
  record-enabled. With TrackInput off the track is in Auto Input mode, which
  still plays the input while recording [P1, pp. 768–769]: pull the
  microphone track's fader down, which does not affect the recording.
  Clear the inserts on the sweep track and on the master fader.
* **Export:** select the recorded clip and use *Export Clips as Files* from
  the Clip List menu [P1, p. 649]: WAV, mono, the session rate and bit depth
  (converting 32-bit float to 24-bit adds dither). Pro Tools writes Broadcast
  WAV; RoomScope reads it as is.

## Apple Logic Pro and GarageBand

* **Sample rate:** File ▸ Project Settings ▸ Audio ▸ Sample Rate [G1]. The
  Assets tab of Project Settings has *Convert audio file sample rate when
  importing* [G1]; generating the sweep at the project rate makes it moot.
  GarageBand for Mac has no sample-rate setting in its guide; generate the
  sweep at 44.1 kHz (`--sample-rate 44100`), the rate GarageBand's iPhone/iPad
  guide names for imports [G9].
* **Import:** Logic: File ▸ Import ▸ Audio File, or drag the WAV to a track
  [G2]. GarageBand: drag the WAV onto a track [G8].
* **Time-stretching:** Logic 12.3: in the Region inspector untick *Flex* and
  set *Smart Tempo* to *Off* [G3] (Logic 12.2 and earlier: *Flex & Follow* =
  *Off* [G4]; the *Smart Tempo* pop-up is new in 12.3 [G14]); in File ▸ Project Settings ▸ Smart Tempo set *Set Imported Files To*
  to *Flex Off* and untick *Trim start of new regions* [G5]. GarageBand: in the
  audio editor untick *Follow Tempo and Pitch* and leave *Enable Flex* off
  [G10].
* **Record:** a mono audio track with the microphone input. Logic's software
  monitoring is on by default and plays the input of a recording track [G6]:
  turn it off (Settings ▸ Audio ▸ General) or pull the track's fader down. Turn
  Cycle off. Logic's recording file (CAF, WAVE/BWF or AIFF) can be analysed
  directly [G7].
* **Export:** Logic: select the recorded region, File ▸ Export ▸ *1 Region as
  Audio File*, WAV or AIFF, *Normalize* Off, *Bypass Effect Plug-ins* on
  [G11]. GarageBand: mute the sweep track, turn *Export projects at full
  volume* off (Settings ▸ Advanced; it normalises the export) [G12] and use
  Share ▸ Export Song to Disk as WAVE or AIFF [G13]. That export trims silence
  at the start and end of the project [G13]; the microphone's room noise before
  the sweep is not digital silence, but check that the exported file starts
  before the sweep.

## Steinberg Cubase and Nuendo

* **Sample rate:** Project ▸ Project Setup [C1].
* **Import:** File ▸ Import ▸ Audio File [C2]. The import options dialog
  (shown when Preferences ▸ Editing ▸ Audio ▸ *On Import Audio Files* is set to
  *Open Options Dialog*) offers *Convert to Project Settings* when the file's
  rate or bit depth differs [C2]; generate the sweep at the project rate so no
  rate conversion is needed.
* **Time-stretching:** keep *Musical Mode* off for the sweep clip (Sample Editor
  or Pool; ACID-tagged files switch it on automatically) [C3].
* **Record:** a mono audio track with the microphone input. Every Auto
  Monitoring mode except *Manual* (Preferences ▸ VST) switches monitoring on
  while a track is record-enabled [C4]: set it to *Manual*. Check that the
  Control Room has no insert or room-correction plug-in on the monitor path,
  or bypass it [C5].
* **Export:** File ▸ Export ▸ Selected Events with *Processing* = *Dry* [C6];
  or set the locators to the take and use File ▸ Export ▸ Audio Mixdown with
  *Channel Selection* = *Single*, the microphone channel [C7]. (Audio ▸ Bounce
  Selection also works; it writes the new file into the project's Audio
  folder and applies event fades and volume [C8].)

## Fender Studio Pro (formerly PreSonus Studio One)

Studio One became Fender Studio Pro with version 8 (January 2026), and
"Song" became "Session" [S1, S2]; the older menu names are in brackets.

* **Sample rate:** Session ▸ Session Setup (Song ▸ Song Setup before v8)
  [S2, S6]. When creating the session, leave *Stretch Audio Files to Session
  Tempo* off [S9]; with it on, *Timestretch* becomes the default Tempo mode of
  new audio tracks [S5].
* **Import:** drag the WAV from the Browser to an audio track [S3].
* **Time-stretching:** in the **Track** Inspector set the track's *Tempo* mode
  to *Don't Follow*: events on that track "are never moved or stretched
  automatically" [S4]. In the Event Inspector keep *Speedup* at 1,
  *Transpose* and *Tune* at 0 and *Normalize* off. A gear-wheel icon on an
  event means time-stretching is on, its sample rate differs from the
  session's, or its transpose or tune was changed [S2].
* **Record:** a mono track with the microphone input. Monitoring switches on
  automatically when Record is enabled [S5]: switch the Monitor button off
  after arming.
* **Export:** right-click the recorded event ▸ *Export Selection* [S7], or
  Session ▸ Export Stems (Song ▸ Export Stems before v8) with only the
  microphone track selected; a stem includes the track's inserts, so remove
  or bypass them first [S7]. WAV, the session rate, no normalisation. *Use
  Dithering for Playback and Audio File Export* (Options ▸ Advanced ▸ Audio)
  is on by default and dithers whenever an export reduces the bit depth:
  export 32-bit float, or switch it off [S8].

## Ableton Live

* **Sample rate:** Settings (Options ▸ Settings on Windows, Live ▸ Settings on
  macOS) ▸ Audio ▸ *In/Out Sample Rate* [L1]. Live converts a file at another
  rate in real time, which its Audio Fact Sheet calls non-neutral [L2]: one
  more reason to generate the sweep at the Set's rate.
* **Import:** drag the WAV to an audio track in the Arrangement View.
* **Time-stretching:** open the clip and switch **Warp off** in the Clip
  View [L3]. *Auto-Warp Long Samples* (Settings ▸ Record, Warp & Launch) is on
  by default [L4], so a long test file is warped unless you switch it off.
* **Record:** a second audio track, *Audio From* the microphone input
  (mono), Monitor *Off*, armed; record in the Arrangement [L5].
* **Export:** select the whole take in the Arrangement, File ▸ Export
  Audio/Video, *Rendered Track* = the microphone track, *Include Return and
  Main Effects* off, WAV or AIFF, the Set's sample rate, *Normalize* off [L6].
  *Create Fades on Clip Edges* adds fades of at most 4 ms [L2]; the test file
  starts and ends with silence, so they do not touch the sweep.

## Cockos REAPER

* **Sample rate:** File ▸ Project Settings ▸ tick *Project sample rate*
  [R1, p. 32] (unticked, REAPER uses the hardware rate), and in Preferences ▸
  Audio ▸ Device tick *Request sample rate* with the same rate [R1, p. 21].
  REAPER resamples items at another rate during playback, with the project's
  *Playback resample mode* [R1, p. 32].
* **Import:** Insert ▸ Media file [R1, p. 90].
* **Time-stretching:** in the Item Properties (F2) keep *Playback rate* at 1.0
  (*Preserve pitch* only acts when the rate changes) and remove stretch
  markers [R1, p. 134]. The default project timebase is *Beats (position,
  length, rate)* [R1, p. 33]: do not change the tempo after importing, or set
  the item's *Item timebase* to *Time* in the same dialog [R1, p. 134].
* **Record:** arm a track with the microphone as mono input, record
  monitoring off.
* **Export:** File ▸ Render, *Source* = *Selected media items* (or
  *Stems (selected tracks)*), WAV, the project rate; normalisation stays off
  unless set under *Postprocess…* [R1, pp. 411–415]. Default item fades
  (Preferences ▸ Project ▸ Item Fade Defaults) fall on the silence at both ends
  of the test file.

## Image-Line FL Studio

* **Sample rate:** Options ▸ Audio settings (F10) ▸ *Sample Rate*, the mixer's
  playback rate [F1]; exports use this rate [F5].
* **Import:** drag the WAV into the Playlist as an audio clip.
* **Time-stretching:** in the clip's channel settings keep the *Time* knob at
  *(none)*, the default when a sample is dropped on the Playlist; the clip then
  keeps its pitch and duration whatever the project tempo [F2]. If a clip is
  stretched anyway, switch off General settings ▸ *Read sample tempo
  information*, which applies tempo data stored in WAV files [F6]. The default
  declicking adds a 10 ms fade-out [F2], which falls on the test file's
  closing silence.
* **Playback path:** since FL Studio 20.7 the default template is "Basic 808
  with limiter" [F3]; bypass the limiter on the Master insert for the
  measurement.
* **Record:** route the microphone input to a free Mixer insert. Live inputs
  are routed to the Master and back to the outputs by default [F4], so set the
  insert's *Monitor external input* to *Off* (it can feed back otherwise) and
  switch *Loop record* off, which is on by default and stacks takes [F4].
  Arm the insert and record audio into the Playlist.
* **Export:** File ▸ Export ▸ Wave file with *Split mixer tracks*, and use
  the file of the microphone's insert (muted tracks are skipped) [F5]. WAV,
  the project rate.

## Bitwig Studio

* **Sample rate:** Dashboard ▸ Settings ▸ Audio [B1].
* **Import:** drag the WAV to an audio track in the Arranger. Dashboard ▸
  Settings ▸ Behavior ▸ Audio Import: set *Stretch behavior* to *Original
  speed [Raw]* and *Start clip from* to *Sample Start* [B1].
* **Time-stretching:** in the Inspector set the clip's *Stretch* ▸ *Mode* to
  *Raw*, which ignores stretch data and plays the file at its original speed
  [B2]. (There is no *Off* mode.)
* **Record:** an audio track with the microphone input, monitoring off.
* **Export:** File ▸ Export Audio with only the microphone track selected,
  WAV, sample rate *Current* (no conversion) [B3].

## MOTU Digital Performer

Menu names are from the Digital Performer 12 User Guide [M1]; the Digital
Performer 11 guide describes the same commands [M2].

* **Sample rate:** the *Sample Rate* setting in the Control Panel sets the
  project's rate [M1, p. 222]; the interface is chosen under Setup ▸ Configure
  Audio System ▸ Configure Hardware Driver [M1, p. 260]. Generate the sweep at
  that rate and do not change the project rate afterwards. Before recording,
  set Preferences ▸ Audio Files to Broadcast WAVE and 24-bit or 32-bit float;
  these settings apply to newly recorded files [M1, p. 84].
* **Import:** File ▸ Import Audio, or drag the WAV onto a mono audio track
  [M1, pp. 40–42]. DP does not play a file at another rate at the wrong speed:
  the soundbite gets an "X" in the Soundbites window and does not play
  [M1, pp. 43, 50], or, with *Enable Automatic Conversions* on and *Convert
  sample rate* set to *On import* (Preferences ▸ Automatic Conversions), DP
  converts it on import [M1, p. 97]. Generate the sweep at the project rate so
  neither happens. Leave the soundbite's gain at 0 dB and add no soundbite
  volume automation [M1, p. 400].
* **Time-stretching:** untick *Stretch* in the Track Settings menu of the sweep
  track and of the microphone track; with it unchecked nothing is stretched
  automatically [M1, p. 170] (Preferences ▸ Pitch and Stretch sets this for new
  tracks [M1, p. 104]). A WAV with embedded tempo conforms to the sequence
  tempo [M1, p. 44] and a take carries the tempo map it was recorded with
  [M1, p. 713], so do not change the tempo after recording and do not use
  Audio ▸ Soundbite Tempo ▸ *Adjust Soundbites to Sequence Tempo*; setting
  the soundbite's *Time Compress/Expand* to *Don't Time Scale* keeps that
  command off it [M1, pp. 399, 717].
* **Record:** Project ▸ Add Track ▸ mono audio track [M1, p. 140], the
  microphone as its input, record-enabled [M1, p. 260]. Record-enabling turns
  input monitoring on whatever the monitor button shows [M1, p. 265]: set
  Studio ▸ Audio Patch Thru to *Off* [M1, p. 266]. Leave *Memory Cycle* and
  *Overdub* off so one pass is recorded [M1, p. 273]. Bypass the inserts on the
  sweep track and the master.
* **Export:** the take is a file named after the track and take number in the
  project's *Audio Files* folder [M1, p. 261]; load that file into RoomScope:
  it is the recording itself, without fader, inserts or automation. Or select
  the take from before the sweep to the end of the decay and use File ▸
  Bounce to Disk [M1, p. 1017] with *Source* = the microphone track
  [M1, p. 1021], *Channels* = *Match Track Format* (a mono file from a mono
  track) and *Sample Format* = *Project Default*, 24-bit or 32-bit float
  [M1, pp. 1020–1021]. A bounce includes the track's volume automation,
  mute/solo state and active inserts [M1, pp. 1017–1018]; its settings have no
  sample-rate, normalise or dither option [M1, pp. 1018–1021].

## Audacity

* **Sample rate:** *Project Sample Rate* in the *Quality* section of Audio
  Setup ▸ Audio Settings [A1].
* **Import:** File ▸ Import ▸ Audio [A2].
* **Record:** in Transport ▸ Transport Options turn *Hear other tracks during
  recording* on and *Enable audible input monitoring* off (*Overdub* and
  *Software Playthrough* in older versions) [A3]. Set Audio Setup ▸ Recording
  Channels to 1 (Mono), put the cursor at the start and use **Record New
  Track** (Shift+R): plain Record starts at the end of the selected track,
  after the sweep [A4].
* **Export:** select the recorded track and use File ▸ Export Audio… with
  *Export Range* = *Current Selection*, WAV, *Signed 24-bit PCM* or *32-bit
  float* [A5]. (*Export Selected Audio* was removed in Audacity 3.4 [A6].)

## Any other DAW

For a DAW not listed above (Studio One before version 8, Cakewalk by BandLab
or Cakewalk Sonar, Ardour, Harrison Mixbus, Tracktion Waveform, Reason, LUNA
and others), look up each point in its manual. Each follows from
[What every DAW must do](#what-every-daw-must-do).

1. **Rate first.** Set the project rate before importing anything and generate
   the sweep at that rate. Some DAWs play a file at another rate unconverted,
   at the wrong speed (Pro Tools [P1, p. 636], Logic [G1]); others convert it
   on import (Cakewalk [CW1], Ardour [AR2]), which puts the DAW's resampler
   into the measurement. After importing, check the clip's rate in the file
   list or pool.
2. **Import to an ordinary audio track on the timeline**, not into a sampler,
   clip launcher or loop browser. Switch off every tempo feature for the sweep
   clip and the microphone track (warp, flex, elastic, musical mode, follow
   tempo, stretch to tempo, tempo detection on import) and do not change the
   tempo afterwards. The clip must last exactly as long as the WAV file.
3. **Leave the clip as it is:** no clip gain envelope, fades, crossfades,
   normalising, transpose or tune, and no automatic trim to the first
   transient.
4. **A clean playback path:** bypass plug-ins on the sweep track, its buses and
   the master (a default template may hold a limiter), and any room-correction
   plug-in; route the sweep to one loudspeaker.
5. **Record one mono pass:** a mono track without plug-ins, input monitoring
   off, loop / cycle / take recording off, started before the sweep and
   stopped after the decay.
6. **Export the take, not a mix:** best is the recorded file itself from the
   project's audio folder. Otherwise export the clip or track dry, at the
   project rate, as 24-bit or 32-bit float WAV, AIFF or FLAC, with no
   normalising, dither or bit-depth reduction, no master-bus processing and no
   trimming of silence or the tail.

**Ardour.** Session ▸ Import opens the *Add Existing Media* dialog [AR1]; a
file whose rate differs from the session's is shown in red and "must be
resampled before importing" [AR2]. Generate the sweep at the session rate
instead. An Editor region is stretched only when you use the Stretch Mode
tool [AR3]; clips in Cue slots have their own stretch modes [AR4], so put the
sweep on the Editor timeline.

**Cakewalk by BandLab / Cakewalk Sonar.** File ▸ Import Audio converts a file
at another rate to the project rate; leave *Bit Depth* at *Original*, the
default [CW1, CW2]. Clips with stretching enabled follow the project tempo,
clips without it do not; keep AudioSnap *Follow Project Tempo* and the Groove
Clip *Stretch to Tempo* option off for the sweep [CW3].

## When the report says something is wrong

| RoomScope says | What happened in the DAW | Fix |
| --- | --- | --- |
| *"a file generated at 48000 Hz was played at 44100 Hz"* | The project runs at another rate than the sweep and played it without conversion | Generate the sweep at the project rate |
| *"the DAW time-stretched it"* | Warp / Flex / Follow Tempo / stretch on the sweep clip, or a tempo change after import | Switch stretching off for the clip |
| *"the recording starts ... after the sweep began"* | Recording started late, or the export was trimmed | Record from before the sweep; export the whole clip |
| *"harmonic ... was folded back"* | A limiter, clipper or overloaded bus in the playback path | Bypass master and track plug-ins; lower the sweep track |
| *"flat-topped peaks ... probable clipping"* | Microphone preamp too hot | Lower the input gain |
| *"the recording contains N sweep passes"* | Loop / cycle recording, or the sweep placed twice | Record one pass |
| *"recording is silent"* | Wrong input or a muted track | Check the input and which track you exported |
| *"the recording has no background noise at all"* (an RT60 of a few hundredths of a second, no reflections) | The test-signal track was exported instead of the microphone, or a gate / noise reduction is on the microphone track | Export the microphone track, dry |
| *"direct-sound detection confidence is low"* with none of the above | Wrong reference sweep, a small time-stretch (below the spread above) or Warp / Flex left on, a very noisy room, or a loudspeaker far into distortion | Use the sweep you played; check stretching; lower the playback level |

## Sources

Menu names and defaults above were read in these pages (2026-09); none of
the steps has been run in the DAW with RoomScope yet:

* [P1] Avid, Pro Tools Reference Guide 2026.4 — https://resources.avid.com/SupportFiles/PT/Pro_Tools_Reference_Guide_2026.4.pdf
* [G1] Apple, Logic Pro User Guide, Set the project sample rate — https://support.apple.com/guide/logicpro/set-the-project-sample-rate-lgcpce0958b8/mac
* [G2] Apple, Logic Pro User Guide, Add and delete audio files — https://support.apple.com/guide/logicpro/add-and-delete-audio-files-lgcp1bb0ad7d/mac
* [G3] Apple, Logic Pro User Guide, Choose the Smart Tempo setting — https://support.apple.com/guide/logicpro/choose-the-smart-tempo-setting-lgcpb7abb9cc/mac
* [G4] Apple, Logic Pro 12.2 User Guide, Flex & Follow — https://support.apple.com/guide/logicpro/lgcpb7abb9cc/12.2/mac/15.6
* [G5] Apple, Logic Pro User Guide, Smart Tempo project settings — https://support.apple.com/guide/logicpro/smart-tempo-project-settings-lgcp6ad7156e/mac
* [G6] Apple, Logic Pro User Guide, General settings (software monitoring) — https://support.apple.com/guide/logicpro/general-settings-lgcp0ed343a9/mac
* [G7] Apple, Logic Pro User Guide, Recording settings — https://support.apple.com/guide/logicpro/recording-settings-lgcp411dd5c8/mac
* [G8] Apple, GarageBand for Mac User Guide, Import audio and MIDI files — https://support.apple.com/guide/garageband/import-audio-and-midi-files-gbndd01649ed/mac
* [G9] Apple, GarageBand for iPhone User Guide (imports converted to 44.1 kHz) — https://support.apple.com/guide/garageband-iphone/
* [G10] Apple, GarageBand for Mac User Guide, Intro to the Audio Editor — https://support.apple.com/guide/garageband/intro-to-the-audio-editor-gbndca7725e3/mac
* [G11] Apple, Logic Pro User Guide, Export regions as audio files — https://support.apple.com/guide/logicpro/export-regions-as-audio-files-lgcp8e5ce2d3/mac
* [G12] Apple, GarageBand for Mac User Guide, Change Advanced settings — https://support.apple.com/guide/garageband/change-advanced-settings-gbnded6e79bc/mac
* [G13] Apple, GarageBand for Mac User Guide, Export songs to disk — https://support.apple.com/guide/garageband/export-songs-to-disk-or-icloud-gbnd7cbf5ed9/mac
* [G14] Apple, Logic Pro for Mac release notes (12.3: Smart Tempo pop-up) — https://support.apple.com/en-us/109503
* [C1]–[C8] Steinberg, Cubase Pro / Nuendo 15 help (steinberg.help): Project Setup; Import Options dialog (`importing_audio_and_midi_open_options_dialog_r`); Musical Mode; Auto Monitoring (Preferences ▸ VST); Control Room; Export Selected Events (`parts_and_events_export_selected_events_r`); Export Audio Mixdown options (`export_audio_mixdown_options_r`); Bounce Selection (`parts_and_events_from_events_new_files_creating_t`) — https://steinberg.help/r/cubase-pro/15.0/en/
* [S1] synthanatomy.com, report on the Fender Studio Pro 8 release (January 2026; third-party)
* [S2]–[S7] Fender Studio Pro 8.1 manual: Events; The Browser ▸ Files tab; Timestretching and Track/Event Inspectors; Audio Tracks; Session Setup; Exporting Audio and MIDI Files — https://fenderstudiopromanual.fender.com/en/Content/ (Studio One 5 Reference Manual for pre-v8 names)
* [S8] Fender Studio Pro manual, Advanced Options — https://fenderstudiopromanual.fender.com/en/Content/Setup_Topics/Advanced_Options.htm
* [S9] Fender Studio Pro manual, Creating a New Session — https://fenderstudiopromanual.fender.com/en/Content/Setup_Topics/Creating_a_New_Session.htm

* [L1] Ableton, Live 12 manual, First Steps — https://www.ableton.com/en/live-manual/12/first-steps/
* [L2] Ableton, Live 12 manual, Audio Fact Sheet — https://www.ableton.com/en/live-manual/12/audio-fact-sheet/
* [L3] Ableton, Live 12 manual, Clip View — https://www.ableton.com/en/live-manual/12/clip-view/
* [L4] Ableton, Live 12 manual, Audio Clips, Tempo, and Warping — https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/
* [L5] Ableton, Live 12 manual, Routing and I/O — https://www.ableton.com/en/live-manual/12/routing-and-i-o/
* [L6] Ableton, Live 12 manual, Managing Files and Sets — https://www.ableton.com/en/live-manual/12/managing-files-and-sets/
* [R1] Cockos, REAPER User Guide 7.80 — https://www.reaper.fm/userguide/ReaperUserGuide780.pdf
* [F1] Image-Line, FL Studio manual, Audio Settings — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_audio.htm
* [F2] Image-Line, FL Studio manual, Sampler channel settings — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/chansettings_sampler.htm
* [F3] Image-Line, FL Studio 20.7 release notes — https://www.image-line.com/fl-studio-news/fl-studio-207-released
* [F4] Image-Line, FL Studio manual, Recording audio — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/recording_audio.htm
* [F5] Image-Line, FL Studio manual, Export — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/fformats_save_export.htm
* [F6] Image-Line, FL Studio manual, General Settings — https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/envsettings_general.htm
* [B1] Bitwig Studio user guide, The Dashboard — https://www.bitwig.com/userguide/latest/the_dashboard/
* [B2] Bitwig Studio user guide, Inspecting audio clips — https://www.bitwig.com/userguide/latest/inspecting_audio_clips/
* [B3] Bitwig Studio user guide, Exporting audio — https://www.bitwig.com/userguide/latest/exporting_audio/
* [A1] Audacity manual, Audio Settings Preferences — https://manual.audacityteam.org/man/audio_settings_preferences.html
* [A2] Audacity manual, File Menu — https://manual.audacityteam.org/man/file_menu.html
* [A3] Audacity manual, Transport Options — https://manual.audacityteam.org/man/transport_menu_transport_options.html
* [A4] Audacity manual, Recording — https://manual.audacityteam.org/man/transport_menu_recording.html
* [A5] Audacity manual, Export dialog — https://manual.audacityteam.org/man/file_export_dialog.html
* [A6] Audacity forum, "What happened to Export Selected Audio?" — https://forum.audacityteam.org/t/what-happened-to-export-selected-audio/88742 (forum)
* [M1] MOTU, Digital Performer 12 User Guide (2026) — https://cdn-data.motu.com/manuals/software/dp/v1200/Digital%20Performer%20User%20Guide.pdf
* [M2] MOTU, Digital Performer 11 User Guide — https://cdn-data.motu.com/manuals/software/dp/v11/Digital+Performer+User+Guide.pdf
* [AR1] Ardour manual, Adding Pre-existing Material — https://manual.ardour.org/adding-pre-existing-material/
* [AR2] Ardour manual, Import Dialog — https://manual.ardour.org/adding-pre-existing-material/import-dialog/
* [AR3] Ardour manual, Stretching — https://manual.ardour.org/editing/editing-regions-and-selections/stretching/
* [AR4] Ardour manual, Clip stretch options (Cues) — https://manual.ardour.org/cue/setting-up-cues/clip-stretch-options/
* [CW1] Cakewalk documentation, Import Audio dialog — http://legacy.cakewalk.com/Documentation?product=Cakewalk&language=3&help=0x200FB
* [CW2] Cakewalk Sonar documentation, Import Audio dialog — https://legacy.cakewalk.com/Documentation?product=CakewalkSonar&language=3&help=0x200FB
* [CW3] Cakewalk documentation, How tempo changes affect audio clips — https://legacy.cakewalk.com/Documentation?product=Cakewalk&language=3&help=Tempo.02.html
