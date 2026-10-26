# Public beta: download, verify, try

**English** | [简体中文](PUBLIC_TESTING.zh-CN.md)

Checked **2026-10-21** against [GitHub Releases](https://github.com/jingyemingyue/ReverbScope/releases).
The newest public pre-release is **[v0.5.0b6](https://github.com/jingyemingyue/ReverbScope/releases/tag/v0.5.0b6)**
(beta 6), published on 2026-10-21 and the first public build with the
**ReverbScope** names. The older v0.5.0b1 and v0.4.1 pre-releases are still
public under the former RoomScope name. b2–b5, rc1 and rc2 are Draft releases;
visitors cannot download them. No stable release is available. Recheck
Releases before following a later version.

## 1. Download one edition

Open **Assets** on v0.5.0b6. Bundles need neither Python nor Git.

| Computer | Desktop: GUI + CLI | Terminal: CLI only |
| --- | --- | --- |
| Apple silicon, macOS 14+ | `ReverbScope-Desktop-macOS-arm64.dmg` | `ReverbScope-Terminal-macOS-arm64.tar.gz` |
| Intel Mac, macOS 14+ | `ReverbScope-Desktop-macOS-x86_64.dmg` | `ReverbScope-Terminal-macOS-x86_64.tar.gz` |
| Windows 10/11 x64 | `ReverbScope-Desktop-Windows-x64-Setup.exe` or `ReverbScope-Desktop-Windows-x64.zip` | `ReverbScope-Terminal-Windows-x64.zip` |
| Linux x86_64, glibc 2.39+ | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | `ReverbScope-Terminal-Linux-x86_64.tar.gz` |

These are build targets, not verified interface/driver combinations. Also download
`SHA256SUMS` from **the same release**. `cyclonedx.sbom.json` and
`generated-bundle.lock` describe that release's dependencies. Do not substitute
the current source lock or a Draft release's checksum.

## 2. Verify before opening

For the file you chose, compare the full hash with its line in `SHA256SUMS`:

```bash
shasum -a 256 ReverbScope-Desktop-macOS-arm64.dmg
sha256sum ReverbScope-Desktop-Linux-x86_64.tar.gz
```

Windows PowerShell:

```powershell
Get-FileHash .\ReverbScope-Desktop-Windows-x64-Setup.exe -Algorithm SHA256
```

A mismatch means stop, download again and report the release URL and filename.
Checksums establish file integrity; they are not a signing/notarization claim.

## 3. Install and run a silent demo

- **Mac Desktop:** open the DMG, drag **ReverbScope** into Applications, eject the
  DMG, then open the app from Applications. For an unsigned-app warning, use
  System Settings → Privacy & Security → Open Anyway after the initial attempt.
  No Gatekeeper or SIP change is needed. Allow microphone access when you later
  perform a real measurement. The app has **not** been Apple-notarized.
- **Windows Desktop:** run Setup, then Start → ReverbScope; or extract the entire
  ZIP and start `reverbscope-gui.exe`. SmartScreen may show More info → Run anyway;
  if policy blocks it, report the block rather than disabling the policy.
  These builds have no Authenticode signature.
- **Linux Desktop:** extract the entire archive, install PortAudio and the Qt
  system libraries listed in the [versioned installation guide](https://github.com/jingyemingyue/ReverbScope/blob/v0.5.0b6/docs/INSTALLATION.md),
  then run `./reverbscope/reverbscope-gui`. A CJK font is needed for Chinese charts.
- **Terminal:** extract all files. On Mac/Linux run
  `./reverbscope-terminal/reverbscope demo`. On Windows open **ReverbScope Terminal.cmd**,
  then run `reverbscope.exe demo`. If macOS refuses the unsigned terminal executable
  from a downloaded folder, follow the
  [versioned installation guide](https://github.com/jingyemingyue/ReverbScope/blob/v0.5.0b6/docs/INSTALLATION.md#terminal-edition).

The desktop window has no demo button. Run `demo` from the command line once:
it writes a **Synthetic / Demo** session for two simulated positions and plays
nothing. Then choose **Open Session…** in the sidebar and pick `position-a` in
the demo folder. This demonstrates software flow only; it does not test your
interface, room or DAW. Neither edition adds the command to PATH. For the Mac
Desktop CLI, for example:

```bash
/Applications/ReverbScope.app/Contents/MacOS/ReverbScope demo
```

For Python 3.12+ users, download `reverbscope-0.5.0b6-py3-none-any.whl` and
`generated-bundle.lock` from that same release, create a fresh virtual
environment, then install the release's runtime pins together with the local wheel.
An unconstrained GUI extra can resolve newer Qt versions that this beta was
never tested with:

```bash
python -m pip install -r generated-bundle.lock "./reverbscope-0.5.0b6-py3-none-any.whl[gui]"
reverbscope --help
reverbscope demo
```

There is no PyPI release: `pip install reverbscope` does not install this
project. The documentation for this beta is
[pinned to its tag](https://github.com/jingyemingyue/ReverbScope/tree/v0.5.0b6/docs).
Beta 1 used **RoomScope / `roomscope`** names; its own
[pinned documentation](https://github.com/jingyemingyue/ReverbScope/tree/v0.5.0b1/docs)
still applies to those files.

## 4. Report what happened

Follow [Community testing](COMMUNITY_TESTING.md). State the exact asset, hash,
version and build; failures and NOT RUN rows are useful. Start playback only
after lowering monitor volume and checking routing. No physical interface or
DAW PASS is recorded yet. A Draft build may be tested if the maintainer shares
that exact build; do not report it as a public release.
