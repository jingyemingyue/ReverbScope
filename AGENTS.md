# ReverbScope contributor agents

Follow `CONTRIBUTING.md` and `docs/MAINTAINING.md`.

Before changing `src/reverbscope/ui/`, `src/reverbscope/display/`, visible
copy or screenshots, read `docs/design/GUI_GUIDELINES.zh-CN.md`, especially
sections 0, 3, 5, the relevant page specification in section 7, and section 17.
The English summary is `docs/design/GUI_GUIDELINES.md`; current decisions and
phase evidence are in `docs/design/GUI_REDESIGN_STATUS.zh-CN.md`.
Product principles in `docs/ARCHITECTURE_V1.md` take precedence over the
guidelines, which take precedence over the historical GUI 2 architecture.

- Start each GUI task from the latest `gui/redesign`; use one
  `gui/p<N>-<topic>` branch and PR for one task. Never push to another
  contributor's branch or merge a PR without maintainer authorization.
- Claim the task in its PR or issue before concurrent component work.
- Preserve DSP, CLI behavior and measurement file formats. Correctness
  fixes outside the GUI need separate PRs.
- Keep existing behavior assertions, including unsaved-take protection,
  generation guards, worker lifetime, stop safety and Chinese-language gates.
- New assets and dependencies require the guideline's license audit. Lucide
  is approved as a design choice, but has not yet been bundled or audited.
- Keep synthetic markers and use an isolated `REVERBSCOPE_HOME` for tests
  and screenshots. Offscreen rendering does not establish native acceptance.
- Commit and push stable changes without force-pushes, remote branch
  deletion, tags or releases. GUI work never targets `release/0.5.0`.
- Record only actual checks and attach the section 16 review evidence.
  A maintainer or another session must independently review GUI changes.
- Explanations to the maintainer are in Chinese; comments and commit
  messages follow the existing English style.
