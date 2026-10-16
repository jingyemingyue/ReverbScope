# Roadmap

**English** | [简体中文](ROADMAP.zh-CN.md)

Status checked 2026-10-15. Dates are evidence dates, not delivery promises.
[OSS readiness](OSS_READINESS.md) contains exact commits/workflows; the
[release plan](RELEASE_PLAN.md) owns stable-version gates.

| State | Work | Evidence / exit criterion |
| --- | --- | --- |
| Implemented in source | ESS/IR analysis, decay validity, noise/reflections, position comparison, sessions/projects | `src/reverbscope/`; methodology and synthetic/unit/integration tests |
| Implemented in source | CLI/GUI, EN/zh-CN, environment report and two capture routes | Main 0.5.0b3 source; not all features are in public beta 1 |
| Implemented automation | CI, wheel/source, Windows/macOS arm64/macOS x86_64/Linux bundles, license/SBOM/checksum staging | Audit-linked successful main/candidate runs; Automated PASS only |
| Public, early testing | RoomScope v0.5.0b1 and v0.4.1 | Public Release assets; unsigned, no recorded hardware/DAW PASS |
| Under validation | ReverbScope rc2/b3 and installed first launch | Draft only; exact-asset checks and native launch report before publishing |
| Under validation | Hardware and DAW paths | NOT RUN until linked physical reports; see community testing |
| Under review | Competing GUI branches, especially #64 | Choose one route, resolve current failures, review integrated diff, native test; no merged/public claim |
| Planned | First independent testers and regression feedback loop | Real issue with reproducible environment and follow-up; no adoption count until evidenced |
| Planned | Signing/notarization and stronger build reproducibility | Maintainer credentials/decision; verify signed artifacts, hash-lock toolchain proposal; no existing certification claim |
| Planned | Website and repository settings | Set About/Topics; Homepage only after HTTP success; verify rules/private reporting/contact |
| Planned | Stable 0.5.0 | Full release-plan hardware/DAW gate and explicit maintainer decision |
| Planned | PyPI and 1.0 validation | Separate release-plan gates; not implied by a successful source install |

Join via [community testing](COMMUNITY_TESTING.md) or [contributor tasks](COMMUNITY_TASKS.md).
Neither star targets nor source-line targets are milestones.
