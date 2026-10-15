# Public beta: download, verify, try

**English** | [简体中文](PUBLIC_TESTING.zh-CN.md)

Checked **2026-10-15** against [GitHub Releases](https://github.com/jingyemingyue/ReverbScope/releases).
The newest public pre-release is **[v0.5.0b1](https://github.com/jingyemingyue/ReverbScope/releases/tag/v0.5.0b1)**,
published on 2026-10-01 under the former **RoomScope** name. rc1, rc2, b2 and b3
are Draft releases; visitors cannot download them. No stable release is available.
The [audit snapshot](evidence/oss-readiness-2026-10-15.json) records asset names,
sizes and GitHub SHA256 digests. Recheck Releases before following a later version.

## 1. Download one edition

Open **Assets** on v0.5.0b1. Bundles need neither Python nor Git.

| Computer | Desktop: GUI + CLI | Terminal: CLI only |
| --- | --- | --- |
| Apple silicon, macOS 14+ | `RoomScope-Desktop-macOS-arm64.dmg` | `RoomScope-Terminal-macOS-arm64.tar.gz` |
| Intel Mac, macOS 14+ | `RoomScope-Desktop-macOS-x86_64.dmg` | `RoomScope-Terminal-macOS-x86_64.tar.gz` |
| Windows 10/11 x64 | `RoomScope-Desktop-Windows-x64-Setup.exe` or `RoomScope-Desktop-Windows-x64.zip` | `RoomScope-Terminal-Windows-x64.zip` |
| Linux x86_64, glibc 2.39+ | `RoomScope-Desktop-Linux-x86_64.tar.gz` | `RoomScope-Terminal-Linux-x86_64.tar.gz` |

These are build targets, not verified interface/driver combinations. Also download
`SHA256SUMS` from **the same release**. `cyclonedx.sbom.json` and
`generated-bundle.lock` describe that release's dependencies. Do not substitute
the current source lock or a Draft release's checksum.

## 2. Verify before opening

For the file you chose, compare the full hash with its line in `SHA256SUMS`:

```bash
shasum -a 256 RoomScope-Desktop-macOS-arm64.dmg
sha256sum RoomScope-Desktop-Linux-x86_64.tar.gz
```

Windows PowerShell:

```powershell
Get-FileHash .\RoomScope-Desktop-Windows-x64-Setup.exe -Algorithm SHA256
```

A mismatch means stop, download again and report the release URL and filename.
Checksums establish file integrity; they are not a signing/notarization claim.

## 3. Install and run a silent demo

- **Mac Desktop:** open the DMG, drag **RoomScope** into Applications, eject the
  DMG, then open the app from Applications. For an unsigned-app warning, use
  System Settings → Privacy & Security → Open Anyway after the initial attempt.
  No Gatekeeper or SIP change is needed. Allow microphone access when you later
  perform a real measurement. The app has **not** been Apple-notarized.
- **Windows Desktop:** run Setup, then Start → RoomScope; or extract the entire
  ZIP and start `roomscope-gui.exe`. SmartScreen may show More info → Run anyway;
  if policy blocks it, report the block rather than disabling the policy.
  These builds have no Authenticode signature.
- **Linux Desktop:** extract the entire archive, install PortAudio and the Qt
  system libraries listed in the [versioned installation guide](https://github.com/jingyemingyue/ReverbScope/blob/v0.5.0b1/docs/INSTALLATION.md),
  then run `./roomscope/roomscope-gui`. A CJK font is needed for Chinese charts.
- **Terminal:** extract all files. On Mac/Linux run
  `./roomscope-terminal/roomscope demo`. On Windows open **RoomScope Terminal.cmd**,
  then run `roomscope.exe demo`. If macOS blocks the unsigned terminal executable,
  use the Desktop Edition or the [versioned installation guide](https://github.com/jingyemingyue/ReverbScope/blob/v0.5.0b1/docs/INSTALLATION.md#terminal-edition).

In Desktop choose **Demo (no interface)** (Chinese: **演示（无需音频接口）**).
It uses **Synthetic / Demo** data and plays nothing. It demonstrates software
flow only; it does not test your interface, room or DAW. Neither edition adds
the command to PATH. For the Mac Desktop CLI, for example:

```bash
/Applications/RoomScope.app/Contents/MacOS/RoomScope demo
```

For Python 3.12+ users, download `roomscope-0.5.0b1-py3-none-any.whl` and
`generated-bundle.lock` from that same release, create a fresh virtual
environment, then install the release's runtime pins together with the local wheel.
An unconstrained GUI extra can resolve newer Qt versions that the old beta
was never tested with (6.12.0 is excluded by current source due to suite aborts):

```bash
python -m pip install -r generated-bundle.lock "./roomscope-0.5.0b1-py3-none-any.whl[gui]"
roomscope --help
roomscope demo
```

There is no claimed PyPI release. Public beta 1 lacks newer fixes and GUI work;
its documentation is [pinned to that tag](https://github.com/jingyemingyue/ReverbScope/tree/v0.5.0b1/docs).
The current source uses **ReverbScope / `reverbscope`** instead.

## 4. Report what happened

Follow [Community testing](COMMUNITY_TESTING.md). State the exact asset, hash,
version and build; failures and NOT RUN rows are useful. Start playback only
after lowering monitor volume and checking routing. No physical interface or
DAW PASS is recorded yet. The draft rc2 may be tested if the maintainer shares
that exact build; do not report it as a public release or as beta 1.
