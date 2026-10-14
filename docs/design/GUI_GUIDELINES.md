# Desktop GUI execution guidelines: English summary

The authoritative text is [GUI_GUIDELINES.zh-CN.md](GUI_GUIDELINES.zh-CN.md),
version 1.0, 2026-10-14. This summary does not introduce new decisions.
Product principles in [ARCHITECTURE_V1.md](../ARCHITECTURE_V1.md) take
precedence; historical GUI 2 design documents are subordinate.

## Product and interaction direction

One measurement-project window answers: can I record here, what is wrong
at this position, and did moving improve it? A project/position/measurement
tree sits beside a conclusion-first result area: conclusion, four key
metrics, interactive charts, tables, then the complete report. Measurement
uses stepped DAW, interface and impulse-response import flows.
Use at most eight primary views. Conditions, paths and validity details
belong in a normally closed detail drawer. A task bar appears during work,
with an always-visible Stop while measuring. Use system fonts, generated
token styles, semantic components, accessible keyboard navigation, and
short localized copy. Every number retains its units and validity.

## Non-negotiable constraints

- GUI and display code perform presentation transforms, not acoustic analysis.
- No overall room score, uncalibrated SPL claims, network imports in `src/`,
  GPL-only Qt modules, or measurement-format changes.
- Confirm playback level for every take; Stop and Esc immediately silence
  output; measuring locks device settings and allows view changes.
- Preserve behavioral tests, generation guards and thread shutdown.
- Mark synthetic data on every screen and in image exports and captions.
- Share numerical precision and terminology with CLI presentation; do not
  silently change CLI goldens or pending terminology decisions.
- Audit new dependencies, icons, fonts and colour maps before bundling.
- No CLI flags, internal filenames, documentation paths or full paths in
  routine GUI copy; paths may appear in the detail drawer or tooltips.

## Branch and phase gates

The maintainer approved #58 as the baseline, freezing 3D/scan features in
developer experiments, keeping an example project, adopting an audited
Lucide subset, and one `gui/redesign` integration branch on 2026-10-14.
See the [decision and evidence ledger](GUI_REDESIGN_STATUS.zh-CN.md) for the
exact scope. The maintainer subsequently approved the recommended terminology
and retaining PySide6 6.6 with a fallback for tabular numerals; use the Qt 6.7
font feature when available. No old PR is closed by this approval.

Work proceeds through Phase 0 baseline/decisions, Phase 1 design tokens and
component gallery, Phase 2 shell/navigation, Phase 3 result/chart views,
Phase 4 measurement flows, Phase 5 comparison/projects, Phase 6 remaining
pages/states, and Phase 7 native acceptance. Each task uses a branch from
`gui/redesign` and a reviewable PR back to it. Integration into `main` is a
maintainer decision after the final gate; GUI redesign never enters the
release-candidate branch.

## Evidence required

Run Ruff, formatting, strict mypy, documentation checks, source safety,
and the offscreen suite with 85% core/models branch coverage. Screenshot
matrices cover English/Chinese, light/dark, the four specified sizes and
1x/2x scale, using isolated settings and synthetic data. Distinguish source
startup timings from packaged cold start. Native Mac/Windows, real audio,
DAW and VoiceOver checks remain separate manual evidence.

Each GUI PR cites guideline sections, includes before/after screenshots,
all relevant empty/loading/error/disabled states, changelog notes and actual
validation. The section 16.2 rubric requires at least 20/24 with no zero in
mandatory items, plus an independent maintainer or second-session review.
Report skipped or unrun checks explicitly. Do not edit the authoritative
guidelines without maintainer approval and a versioned change record.
