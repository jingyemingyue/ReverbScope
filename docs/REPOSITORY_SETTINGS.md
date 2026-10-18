# Repository settings handoff

Audited 2026-10-15. About Description, Topics and Homepage are empty. Pages is
disabled and `https://jingyemingyue.github.io/ReverbScope/` returned HTTP 404.
Do not set that URL as Homepage. No website was created or published here.

The connected GitHub account reports repository admin permission, but the
available connector exposes no repository-metadata/topic write operation.
The shell has no authenticated `gh` session. This is an operation-access gap,
not a claim that the owner lacks admin rights. Run the following with an
already-authenticated maintainer GitHub CLI; no secret belongs in this file:

```bash
gh repo edit jingyemingyue/ReverbScope --description 'Open-source room acoustics analyzer for recording engineers. Analyze impulse responses, reverberation, reflections and microphone positions through a DAW or standalone capture.' --add-topic room-acoustics,audio-analysis,impulse-response,recording-studio,acoustics,python
gh repo view jingyemingyue/ReverbScope --json description,repositoryTopics,url
```

Leave Homepage unset. Before setting a future URL, retrieve it anonymously and
verify it serves the intended project page rather than a 404, sign-in or redirect
to unrelated content. The standalone website plan was cancelled on 2026-10-17;
`site/` and `.github/workflows/pages.yml` were deleted from `main`.

For labels referenced by the issue forms/backlog, check the current labels first:

```bash
gh label list --repo jingyemingyue/ReverbScope
```

Create only missing labels; these commands do not create issues or imply reports:

```bash
gh label create hardware-report --repo jingyemingyue/ReverbScope --description 'Evidence from a physical interface test' --color 0E8A16
gh label create daw-report --repo jingyemingyue/ReverbScope --description 'Evidence from a physical DAW capture/export test' --color 1D76DB
gh label create 'good first issue' --repo jingyemingyue/ReverbScope --description 'A small scoped task with a concrete acceptance check' --color 7057FF
gh label create 'help wanted' --repo jingyemingyue/ReverbScope --description 'Maintainer is seeking a real contribution or test' --color 008672
```

Review main/release branch rules (PR required, no force-push/delete, required
checks), private vulnerability reporting, and a reachable private Code of Conduct
contact in Settings. Their state was not verified through this connector; do not
check them off from the presence of SECURITY/CODE_OF_CONDUCT alone. Do not publish
personal contact details without the maintainer choosing them.
