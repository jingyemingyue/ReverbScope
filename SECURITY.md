# Security Policy

**English** | [简体中文](SECURITY.zh-CN.md)

## Supported versions

RoomScope is a pre-release (0.4.x, see [docs/RELEASE_PLAN.md](docs/RELEASE_PLAN.md)).
Only `main` and the newest 0.4.x version are maintained. The repository is
public; releases are pre-releases on GitHub Releases, and nothing is on
PyPI.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting on this repository
(**Security → Report a vulnerability**). Do not open a public issue for a
report that could be abused.

If private reporting is not enabled yet, contact the repository owner through
GitHub. You should hear back within a few days.

## What is not a security issue

Wrong RT60 figures, surprising validity flags, GUI layout bugs and similar
analysis or usability problems are ordinary bugs. Please open a
[measurement](.github/ISSUE_TEMPLATE/measurement.yml) or
[bug](.github/ISSUE_TEMPLATE/bug.yml) issue and attach the files listed in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Files from other people

Session folders, bundles, `comparison.json`, `project.json`, sweep sidecars
and WAV files are treated as untrusted data. RoomScope never unpickles or
evaluates them, caps JSON size and nesting, is meant to turn malformed content
into a `RoomScopeError` rather than a crash (`tests/robustness/`), and reads a
session's `result.json` and
`impulse_response.wav` only from inside that session's folder (a path in
`session.json` that is absolute or leads out of the folder is refused).
Saving an opened session into another folder copies its sweep sidecar and
recording only from inside its own folder.
`roomscope session bundle` leaves out any file that links out of the session
folder, so a session from someone else cannot put one of your files into the
zip you attach to a public issue. A
`project.json` is different by design: it lists session folders, which may
live anywhere, so opening someone else's project opens the session folders it
names — look at it first. Apart from that, a way to make RoomScope read or
write outside the files you opened is a security issue.

## Safety of Standalone Mode

RoomScope plays a test sweep through a loudspeaker. Defaults stay conservative
(−20 dBFS in Standalone Mode; −12 dBFS for generated sweep files). By default
nothing in this project changes system volume, audio-device configuration, or
DAW settings. The one opt-in exception is `roomscope measure
--coreaudio-set-rate` (the matching Standalone checkbox in the developer
edition): it lets PortAudio set the selected macOS device's nominal sample
rate for the take, which can disturb other programs using that device.
Whether the previous rate is restored afterwards has not been checked; Audio
MIDI Setup shows the device's rate. Please report any other change as a
security issue.
