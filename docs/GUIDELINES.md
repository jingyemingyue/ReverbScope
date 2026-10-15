# ReverbScope execution guidelines (English summary)

**English summary** | [简体中文（以此为准）](GUIDELINES.zh-CN.md)

This file is a summary of
[GUIDELINES.zh-CN.md](GUIDELINES.zh-CN.md) **v2.1.1** (2026-10-15).
The Chinese text is the only execution standard for the project. If this
summary and the Chinese text differ, follow the Chinese text. Do not treat
this page as a second authority, and do not change the Chinese document's
version number without the maintainer.

The Chinese text's own snapshot of the repository (stars, forks, open pull
requests, release state) is dated 2026-10-15. This summary does not refresh
those numbers. Anything not re-checked is not stated here as a new fact.

Appendix F of the Chinese text (maintainer confirmations) is **not** filled
in by putting these files in the repository. Items marked "pending" below
stay pending until the maintainer writes a choice.

## What the project is trying to do

Make ReverbScope installable, usable, and used, with the maintainer in
charge. Then apply to OpenAI's Codex for Open Source programme with evidence
that can be checked. The GUI redesign serves that goal. It is not a separate
goal, and it does not block the application (decision D14).

Order of work, from the Chinese text:

1. Close the loop: one standard, a disposition for each open pull request.
2. Publish a public preview whose name is ReverbScope and that a stranger can
   install.
3. Record one real-hardware run and one DAW round trip.
4. Get a first outside tester, and treat their report as a bug to reproduce.
5. Apply only after that, and only the maintainer submits the form.

Suggested dates are in §5 of the Chinese text. The maintainer can move them.

## What stays the same

Every number carries a validity flag. Levels are dBFS. There is no overall
score. The app stays offline. Only LGPL Qt modules are used. The command
line and the GUI use the same numbers and the same words. English and
Simplified Chinese. Safety: Stop and Esc silence playback immediately, and
the level is confirmed before every measurement. Synthetic data is marked on
every screen.

## What this project will not do

Buy, trade, or ask for stars. Count the maintainer, CI, or a draft asset's
downloads as users. Describe synthetic data, CI, or the fake audio backend as
a hardware or DAW test. Submit the Codex application on the maintainer's
behalf. Put an email address, an OpenAI organization id, or any token in the
repository or in an AI session's output (constraints C15–C18).

## One standard, one line of work

Other design notes and pull-request descriptions are inputs. They are not
competing standards. At any time there is one development branch (`main`),
one release-candidate branch (`release/0.5.0`), and one GUI integration
branch (`gui/redesign`). A new session claims one task from §5. It does not
open another full redesign.

When opinions conflict, decide in this order:

1. A choice the maintainer wrote on a pull request or issue (record it in
   Appendix F).
2. The product principles in `ARCHITECTURE_V1.md`, and the hard constraints
   below.
3. Evidence that can be repeated: a passing test, a CI link, a screenshot, a
   hardware report. Then an argument in a document. Then a claim in a pull
   request.
4. The decision table.
5. The smaller change that can be reviewed and reverted.
6. Still tied: the maintainer decides. An AI session does not pick.

Which tool wrote a change is not a reason to prefer it.

## Decision table

"Adopted" means the Chinese text already uses it. "Pending" means follow the
suggestion until the maintainer confirms or rejects it. A rejection updates
the table and the chapters that depend on it. This landing does not check
any box in Appendix F.

| ID | Decision | Status |
| --- | --- | --- |
| D1 | The only target shape is a measurement-project window: a measurement list on the left, a conclusion-first result in the centre, charts as views, a detail drawer closed by default, and a stepped wizard for a new measurement. No permanent measure strip, no permanent inspector, no navigation rail. | Adopted |
| D2 | Prefer PR #58's head `2560124` as the base of `gui/redesign`, but only if that line's CI is green during Phase 0. If it is still red on 2026-10-29, base the work on `main` and port `display/` and the chart pieces. Do not merge #55, #63, or #64 as a whole. | Pending |
| D3 | Charts use pyqtgraph 0.14.0. matplotlib stays for static export and README screenshots during the transition. QtCharts, QtGraphs, and QtDataVisualization stay forbidden. | Adopted |
| D4 | UI technology stays Qt Widgets, custom painting, and QSS generated from tokens. No move to QML. | Adopted |
| D5 | Freeze the 3D room, image source, and scan import. Move them to a developer-only experimental menu. Do not delete the code. Entering the product requires an ADR that changes ARCHITECTURE_V1 §3.3. | Pending |
| D6 | Keep the demo as a read-only example project, marked synthetic on every screen. | Pending |
| D7 | Icons are the Lucide subset that the UI actually uses (ISC), rendered with QtSvg and tinted from tokens. Audit them in DEPENDENCIES, the license bundle, and `GUI_REFERENCE_AUDIT.md`. | Pending |
| D8 | Copy runs conclusion, then reason, then action. The GUI does not show command-line flags, internal filenames, document paths, section numbers, or full paths. Some terms in §16.3 are still pending. | Adopted |
| D9 | System UI fonts. macOS: SF Pro and PingFang. Windows: Segoe UI and Microsoft YaHei UI. Linux: Noto Sans and Noto Sans CJK SC. Digits are tabular. Charts use the same family as the UI. | Adopted |
| D10 | Severity, validity, and verdict colours mean one thing everywhere. "Valid" is not coloured. Green is only for improvement and for good. The theme follows the system. Not dark-first. | Adopted |
| D11 | One task, one pull request, with before and after screenshots for GUI work. A GUI change does not change the numbers from core, models, interpretation, or health. A core change is its own pull request and an ADR. | Adopted |
| D12 | The GUI redesign lands on `main` only. The 0.5.0 candidate keeps the current GUI. Cherry-pick only correctness fixes, under MAINTAINING. | Adopted |
| D13 | One GUI integration branch, `gui/redesign`. Closing the superseded pull requests is the maintainer's action. | Pending |
| D14 | Before an application: close-out and a public build, then hardware evidence, then an outside user, then the GUI redesign. The redesign blocks none of those. | Adopted |
| D15 | Publish a public pre-release named ReverbScope (rc3) from `release/0.5.0`. Pre-release, not stable. | Pending |
| D16 | Publish that preview on PyPI as `pip install --pre reverbscope`. | Pending |
| D17 | Apply after S1–S3, with S4 started. Fallback date 2026-12-15 even if there is still no outside user. Do not apply on the current evidence. | Pending |
| D18 | The silent replacement of an unsaved measurement (found on #63) is a data-loss bug. Fix it in a small pull request to `main` with a regression test. Cherry-pick onto `release/0.5.0` only if the maintainer says so. | Adopted (cherry-pick pending) |
| D19 | Evidence rules from #65: an unrun check is written "not run"; official statements and our suggestions stay separate; the maintainer's own activity and an AI session are not "adoption"; downloads of draft assets are not users. | Adopted |
| D20 | GitHub Pages: configure Pages before merging a `site/index.html`, or split that file out of #65. A 404 home page is worse than no site. | Pending |

## Hard constraints

A change that breaks one of these is not merged.

| ID | Constraint |
| --- | --- |
| C1 | Every measurement number on screen comes from core, models, health, or interpretation. `ui` and `display` only transform for display, and the figure says so. |
| C2 | Every number has a unit and a validity. An invalid value is not drawn as a normal number. "For reference only" has a legend. |
| C3 | No score and no combined grade. Verdicts are per aspect: reverberation, clarity, early reflections, noise floor, low end. |
| C4 | Levels are dBFS, uncalibrated. No dB SPL numbers in the UI. |
| C5 | Offline. No network imports under `src/`. An external link opens in the system browser through `QDesktopServices`, and only because the user clicked. |
| C6 | Qt is PySide6 Essentials only. No QtCharts, QtGraphs, QtDataVisualization, QtWebEngine, or other Addons or GPL modules. |
| C7 | A new dependency, icon, font, or palette needs a license audit in `docs/DEPENDENCIES.md`, the license-bundle script, and `GUI_REFERENCE_AUDIT.md`. |
| C8 | Confirm the level before every measurement, and do not remember that confirmation. Stop and Esc silence immediately. Switching views does not stop a measurement, and Stop stays visible while one is running. Device settings cannot be edited during a measurement. |
| C9 | Synthetic data is marked on every screen, in screenshots, in alternative text, and on exported charts. |
| C10 | Every visible string goes through `_()` or `N_()`. The Chinese token gate passes. The Chinese UI does not contain the word "Ctrl". A new term enters the glossary first. |
| C11 | The command line and the GUI share precision, validity words, and verdict words, through `presentation/` once it exists. |
| C12 | Existing behaviour tests are invariants: unsaved-measurement protection, dropping a late result (generation), thread lifetime, the Chinese gate, comparison verdicts. Move them. Do not delete them. |
| C13 | Do not change the `session.json`, `result.json`, or `project.json` formats. UI state lives under `REVERBSCOPE_HOME` and can be deleted without losing a measurement. |
| C14 | Commit only on the branch for that line of work. No force-push, no deleting a remote branch, no release, no tag, no license change, unless the maintainer has agreed in writing. |
| C15 | Do not fake a signal of adoption. |
| C16 | Name the evidence level whenever something is called "tested": hardware or DAW, then automated (CI, fake backend, offscreen screenshot), then synthetic demo. Unrun means "not run". |
| C17 | Only the maintainer submits the application. No name beyond the public GitHub account, no email, no organization id, and no token in the repo or in an AI session's output. |
| C18 | AI output is merged only after the maintainer reviews it. No auto-merge. An AI session does not merge, publish, tag, or close a pull request. |
| C19 | A pull request that conflicts with the guidelines is not merged. Register the disagreement (Appendix H, procedure §2.4) and let the maintainer decide. Change the guidelines only with the maintainer's agreement. |

## Roadmap

Two tracks. The S track decides whether an application is honest. The G
track is the GUI redesign and, by D14, blocks nothing on the S track.

| Stage | What it is | Who |
| --- | --- | --- |
| S0 | Maintainer confirms this standard and writes a disposition on each open pull request. | Maintainer (an AI session may draft the comments) |
| S1 | Merge the small, reviewable pull requests; port the pieces Appendix H accepts; land these guidelines; About and Topics; a few good-first issues. | Maintainer merges; AI prepares |
| S2 | A public ReverbScope preview (rc3), checked against the asset list. PyPI only if D16 is accepted. A clean-machine install, recorded. | Maintainer publishes |
| S3 | One Apple Silicon interface report and one Studio One round trip, dated, with hashes. Unrun cells stay "not run". | Maintainer runs the hardware |
| S4 | Recruit testers for reports, not stars. Reproduce, fix, ask them to retest. | Maintainer replies; AI may reproduce |
| S5 | Refresh the evidence snapshot. Draft three texts of at most 500 characters. The maintainer rewrites them and submits. | Maintainer submits |
| S6 | If accepted: read-only review, regression tests, packaging, triage. Monthly notes in `docs/STATUS.md`. The credits are the maintainer's. | Maintainer |

GUI phases 0–7 each branch from `gui/redesign` and merge back to it. They
reach `main` only after Phase 7, and only when the maintainer says so. Phase
0's exit is a filled decision table, green CI on `gui/redesign`, and archived
baseline screenshots. Later phases build the design system, the shell, the
conclusion and charts, the measurement wizard, compare and project, welcome
and settings, then a hardware acceptance pass. The page-by-page specification
is §§11–20 of the Chinese text.

Suggested pull-request dispositions are Appendix G. They are suggestions
until the maintainer writes them on the pull requests. Merging and closing
stay with the maintainer (C18).

## Where the rest of the specification lives

§§8–20 and appendices A–J are in the Chinese text only. In short:

| Section | Subject |
| --- | --- |
| §8 | What the program is, who it is for, layering, the two release lines |
| §9 | Why the current GUI feels assembled, including the copy bug in measurement health |
| §10 | The 30-second goal and the design principles |
| §11 | Window structure, words for project / position / measurement, shortcuts |
| §12 | Page specifications, including the wizard rules taken from #63 |
| §13 | Tokens, type, spacing, colour semantics |
| §14 | Component list |
| §15 | Chart behaviour, including the crosshair and box-zoom requirements taken from #64 |
| §16 | Voice, forbidden copy, glossary, number formats |
| §17 | Feedback, unsaved measurements, drag and drop, keyboard |
| §18 | Platform, accessibility, performance budgets |
| §19 | Target directories and the `presentation/` layer |
| §20 | Definition of done and the review sheet for a GUI pull request |
| Appendix J | The eight-step protocol for an AI session |

`AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/` are the working copy of
Appendix J. They point here and at the Chinese text. They do not add product
rules. How AI help is allowed to be used is
[AI_ASSISTANCE.md](AI_ASSISTANCE.md).

## Working on a task

Read §0, §2, §3, §4, §6, and Appendix J of the Chinese text, plus the
sections the task names. Work from the current GitHub history, not from an
old RoomScope checkout. One task, one branch, one pull request. Say which
section of the guidelines the pull request implements.

Do not widen a task into DSP, file formats, CLI behaviour, dependencies,
workflows, or the license. If the guidelines do not cover the case, or they
conflict with the task, stop and write a guidelines-change proposal. Do not
edit the guidelines to match the code.

Local checks are §6 item 8 of the Chinese text. CI runs `mypy` on Linux. On
macOS, run `mypy --platform linux` to match it. Say which commands ran, and
write "not run" for the rest. Commit messages stay in the repository's
English style and end with an `Assisted-by:` line. Notes for the maintainer
are in Chinese.
