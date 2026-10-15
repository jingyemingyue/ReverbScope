# Agent instructions

The execution standard is [docs/GUIDELINES.zh-CN.md](docs/GUIDELINES.zh-CN.md)
(v2.1.1). [docs/GUIDELINES.md](docs/GUIDELINES.md) is an English summary. If
this file and the guidelines disagree, the guidelines win. This file is the
working copy of Appendix J. How AI help is used is
[docs/AI_ASSISTANCE.md](docs/AI_ASSISTANCE.md).

Notes for the maintainer are in Chinese. Commit messages stay in the
repository's English style.

## Before editing

Read §0, §2, §3, §4, §6, and Appendix J of the Chinese guidelines, and the
chapters the task names. If those files are not in the checkout and the user
did not attach them, stop. Do not work from memory.

Use the current GitHub history. Do not work from an old RoomScope checkout.

## One task

One task, one branch, one pull request. Claim it first: tool, task, and
expected finish. Do not open a second full GUI redesign. The branches that
already exist for this purpose are `main`, `release/0.5.0`, and
`gui/redesign`. Do not commit on those three. Do not push onto someone
else's branch.

The pull request names the guidelines section and the task, for example
"§5 S1: land the execution guidelines".

## Eight steps

Stop at the three points below unless the user said, for this task only,
that the stops are not required.

1. Read the chapters above. List what was read.
2. Restate the task: goal, in scope, out of scope, done when, cited sections.
   **Stop** until the user replies that the restatement is confirmed.
3. Look, read-only. List the files to change and any conflict with the
   guidelines.
4. Write the change plan: each file, the tests, the checks. **Stop** until
   the user says to start.
5. Change only the files in the plan. Run the related tests as you go. If
   another file has to change, stop and say why.
6. Run the checks in §6 item 8. Record pass, fail, or not run. A skip needs
   a reason.
7. Commit on the task branch. Show the diff summary. **Stop** until the user
   says to push.
8. Push, open a draft pull request, and write the handoff. Then stop.

## Stop and ask

Stop immediately when:

- The guidelines cannot be found.
- The task conflicts with the guidelines, or the guidelines do not cover it.
- A change would touch `core/`, `models/`, `interpretation/`, `health.py`, a
  file format, CLI output, a dependency, `.github/`, or the license, and
  that was not the task.
- A test fails and the failure does not look caused by this task.
- A test, a check, or a CI gate would be deleted or weakened.
- The git action is one listed under "Do not" below.
- The work needs an account, a token, an email address, or an organization id.
- The same error is still failing after two attempts to fix it.
- The checkout is an old RoomScope tree, or the branch was not cut from the
  current target branch.

Say where it is stuck, the options and their effects, and which option you
recommend. Then wait.

## Do not

- `git push --force` (including `--force-with-lease`), `git reset --hard`
  onto someone else's commit, rebase a pushed branch, delete a remote
  branch, delete a remote-tracking branch, create a tag, or amend a commit
  that was already pushed.
- Merge, close, or release with the GitHub CLI or API. No write call that
  edits the repository settings.
- Commit or push on `main`, `release/0.5.0`, or `gui/redesign`.
- Widen the task: no drive-by refactor, rename, format sweep, dependency
  bump, or unrelated bugfix. Record it under "seen, not done" in the handoff.
- Add a dependency, icon, font, or palette without the C7 audit.
- Change a test's expected value, add a skip, add an expected failure, or
  lower a coverage gate so the suite goes green.
- Edit the guidelines or their version. A disagreement is a
  guidelines-change proposal.
- Call a check passed without the command and the result. Do not invent star
  counts, download counts, user counts, coverage, or timings.
- Call an offscreen screenshot, the fake backend, CI, or a synthetic demo a
  hardware or DAW test.
- Write an email address, an organization id, or a token anywhere.

## Checks

From the repository root, as in §6 item 8:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,gui]" build
ruff check . && ruff format --check .
mypy --platform linux
python scripts/check_doc_links.py && python scripts/check_cli_docs.py && python scripts/check_src_safety.py
QT_QPA_PLATFORM=offscreen pytest --cov=reverbscope.core --cov=reverbscope.models --cov-fail-under=85
```

`ruff format` also formats Python inside Markdown fences. On macOS, plain
`mypy` reports an extra unreachable branch because of `sys.platform`; CI on
Linux uses `--platform linux`.

## Commit and handoff

Commit subject in English, at most 72 characters, saying what changed. The
body says why, and names a source pull request when a change is ported
(`Ported from #63`). The last line is `Assisted-by: <tool>`.

The handoff, also the end of the pull-request body:

- Task, with the guidelines section.
- Branch and short SHA.
- Files and what each change does.
- Each check: command, then pass, fail, or not run.
- Evidence level actually reached: automated, synthetic demo, or hardware.
- Not done.
- Seen but not done.
- Suggested next step.
- The AI tool, and that a maintainer must review before merge.

Default to a draft pull request.
