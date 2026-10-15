# Codex for Open Source application draft

Prepared **2026-10-15**. **Not submitted.** Refresh facts from [OSS readiness](OSS_READINESS.md)
and the [official form](https://openai.com/form/codex-for-oss/) before sending.
The primary maintainer must verify their role and enter legal name, account email,
public GitHub profile and OpenAI organization ID privately. No account identifiers
or commitments on someone else's behalf belong in this repository.

## Project narrative

ReverbScope is an Apache-2.0 Python application for evaluating recording spaces
and microphone positions. A recording student, independent engineer or small studio
can generate a test sweep, record it through a familiar DAW, and import the
microphone capture for impulse-response and reverberation analysis. A standalone
capture path is also implemented. Results carry validity/confidence information,
with explicit limitations when the measurement cannot support a conclusion.
English and Simplified Chinese interfaces, CLI reports and portable session data
help make the workflow inspectable and repeatable.

The workflow emphasis is the handoff alongside a DAW, recording profiles,
position comparison and shareable analysis evidence. These are design choices,
not demonstrated superiority, feature parity or accuracy advantages over general
acoustic-analysis software. Current algorithm evidence uses synthetic/reference
cases and scripted device stand-ins. Hardware and DAW compatibility remain unproven.

The maintainer's responsibilities include issue/reproduction handling, reviewing
AI-assisted changes, bilingual documentation, packaging and release decisions.
Main (`3567da03ea41`) and candidate (`03a32f640bcd`) have passing CI and Release
runs linked in the audit. Tests cover Linux Python 3.12/3.13/3.14, macOS 3.12 and
Windows 3.12, with wheel/source and four bundle targets. There are two public
pre-releases, still named RoomScope; newer ReverbScope candidates are Draft.
There are no verified external users, case studies, monthly-download figures or
physical test reports to cite. Self/AI-authored PR activity is not independent adoption.

Codex and API support would be used for reproducible defect reduction: reviewed
synthetic cases, regression minimization, cross-platform packaging investigation,
clear installation/reporting instructions and triage of real community reports.
The maintainer remains responsible for reviewing patches and release evidence.
Physical acceptance remains human work. No automatic merging, release publication
or unsupported compatibility badge is part of the proposed use.

## Copy-ready form fields

Each answer below is at most 500 characters, matching the form inspected on the
preparation date. The application form can change; recheck it before submission.

### Why does this repository qualify?

ReverbScope is an Apache-2.0 room-acoustics tool for recording students and independent engineers. It connects DAW sweep capture to validity-aware impulse-response analysis and microphone-position comparisons. I maintain its Python CLI/GUI, bilingual docs, CI and release workflow. It is early stage: no verified external adoption or hardware/DAW test reports yet. I am applying on its practical value to the open-source recording workflow, not a claim of broad usage.

### How will you use API credits for your project?

Use Codex/API resources to reproduce reported bugs, generate reviewed synthetic regression cases, diagnose cross-platform installation and packaging failures, improve English/Chinese docs, and triage tester reports. Run locally first, reuse existing CI, and require maintainer review before merges or releases. Prioritize real tester failures and measurable reliability work; AI-generated signals will never be presented as physical hardware evidence.

### Anything else we should know?

Current public download is the legacy-named RoomScope v0.5.0b1. ReverbScope rc2/b3 packages remain Draft. Main and candidate have passing CI/release runs, but real interface/DAW validation, signed distribution and independent adoption evidence remain open. Next goals: one documented Apple Silicon interface run, one Fender Studio Pro/Studio One roundtrip, one independent tester report, and a verified public candidate installation path.

## Proposed next milestones (targets, not completed results)

| Goal | Completion evidence |
| --- | --- |
| One Apple Silicon interface report | Exact asset SHA, dated device/driver/rate/Stop/unplug/save-reopen checklist and linked issue; missing loopback stays NOT RUN |
| One Fender Studio Pro / Studio One roundtrip | Version, sweep sidecar, microphone export settings, result/validity and reviewed attachments |
| One independent tester report | A real person's consented install/test issue and follow-up; do not guarantee recruitment or invent users |
| One reviewable public candidate route | Maintainer-approved pre-release, anonymous download, hash verification and native launch report on the exact published SHA |
| Each confirmed non-hardware-only bug gets a regression | Issue, minimal non-private fixture, test that fails before the patch and passes after, appropriate CI plus reporter retest where possible |

These goals are practical readiness improvements, **not official eligibility thresholds**.
The official program assesses maintenance, usage/adoption or ecosystem importance;
no star minimum or approval probability is inferred. Nothing here claims OpenAI
endorsement, selection, granted credits or an approved security-access request.
