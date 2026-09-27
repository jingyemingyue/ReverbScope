# GitHub settings only the maintainer can change

The repository's About box, topics and features cannot be edited from a pull
request, and the tools used to prepare this change have no write access to
them. Nothing below has been applied yet. State checked on 2026-09-27:
description **empty**, website **empty**, topics **none**, Issues **on**,
Discussions **off**, Wiki **off**, one **draft** pre-release `v0.4.1`, no tags.

## 1. About box (repository home page → ⚙ next to "About")

**Description** (GitHub search indexes it; keep it under ~200 characters):

```text
DAW-independent room acoustics analyzer for recording engineers. Measure RT60, early reflections, frequency response and noise floor, and compare microphone positions.
```

**Website:** until a docs site is published, point it at the user guide:

```text
https://github.com/jingyemingyue/RoomScope/blob/main/docs/user-guide/en.md
```

(`scripts/build_docs_site.py` can build a static site from `docs/`. Publishing
it on GitHub Pages needs a Pages workflow, which costs Actions minutes on
every push to `main`; worth it only once there are users to read it.)

**Topics** (all describe what the project actually does; GitHub allows 20):

```text
audio  audio-engineering  recording  recording-studio  acoustics
room-acoustics  dsp  impulse-response  rt60  reverberation  daw
microphone  audio-analysis  sine-sweep  measurement  python  pyside6
```

Tick **Releases** and uncheck **Packages** and **Deployments** under "Include
in the home page" (there are no packages or deployments; empty sections look
unfinished).

## 2. Features (Settings → General → Features)

| Feature | Recommendation | Why |
| --- | --- | --- |
| Issues | **On** (already) | Bug, measurement, feature and hardware-report forms are set up |
| Discussions | **Turn on** | Questions ("is my result plausible?") and show-and-tell do not belong in the issue tracker. Suggested categories: *Q&A*, *Show and tell* (share your room's results), *Ideas*, *Announcements* |
| Wiki | Off | Docs live in `docs/` and are reviewed in pull requests |
| Projects | Off unless you use it | An empty Projects tab looks abandoned |
| Sponsorships | Optional | Only if you want it; nothing in the repo depends on it |

When Discussions is on, add this to `.github/ISSUE_TEMPLATE/config.yml` under
`contact_links` so questions go there instead of into issues:

```yaml
  - name: Questions and results
    url: https://github.com/jingyemingyue/RoomScope/discussions
    about: Ask how to measure, or share and discuss a result.
```

## 3. Labels (Issues → Labels)

The hardware form applies `hardware-report`; GitHub silently drops a label
that does not exist, so create it first.

| Label | Colour (suggested) | Used for |
| --- | --- | --- |
| `hardware-report` | `#0e8a16` | Hardware compatibility reports |
| `measurement` | `#1d76db` | Measurement-problem form (check it exists) |
| `good first issue` | GitHub default | Small, well-described tasks, e.g. DAW notes in the user guide |
| `help wanted` | GitHub default | Especially: hardware testers per platform |
| `documentation` | GitHub default | Docs-only changes |

## 4. Social preview (Settings → General → Social preview)

Upload `docs/assets/social-preview.png` (1280×640). It is generated from the
synthetic demo by `scripts/render_readme_assets.py` and labelled as synthetic.
Links shared on Reddit, Hacker News, Slack or WeChat show this image.

## 5. A pinned "call for hardware testers" issue

Create an issue and pin it (issue page → "Pin issue"). Suggested text:

> **Title:** Call for hardware testers (macOS, Windows, Linux)
>
> RoomScope's synthetic test suite passes on all three platforms, but nobody
> has confirmed it on a real audio interface yet. If you have an interface, a
> microphone and 15 minutes, please follow
> [docs/HARDWARE_TESTING.md](https://github.com/jingyemingyue/RoomScope/blob/main/docs/HARDWARE_TESTING.md)
> and file a *Hardware compatibility report*. Failures are as useful as
> successes. Results go into the compatibility matrix with your name (if you
> want it there).

## 6. Releases

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). In short: the existing
`v0.4.1` draft's notes still say "still private" and predate `roomscope demo`
and the new README. The recommendation is to delete that draft and cut
`v0.4.2` as the first public alpha pre-release.

## 7. Security and branch protection (from ARCHITECTURE_V1.md §9.1)

* Settings → Code security → **Private vulnerability reporting: on**
  (`SECURITY.md` points reporters there).
* Settings → Branches → protect `main`: require the CI checks to pass and a
  pull request before merging.
