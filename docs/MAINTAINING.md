# Maintaining ReverbScope

A runbook for the person who keeps the project going: which branch is which,
what the automation does on its own, what only a maintainer can do, and what
to do when something is red. It assumes no assistant and no memory of how the
pieces were built; every step names the file or page it lives in. Pair it with
[RELEASE_PLAN.md](RELEASE_PLAN.md) (why the lines exist, how a release is
produced, the 0.5.0 gate), [CONTRIBUTING.md](../CONTRIBUTING.md) (the rules a
change must follow, the loop from a report to a regression test),
[OFFLINE_CHECKS.md](OFFLINE_CHECKS.md) (what can be checked without hardware)
and [API_STABILITY.md](API_STABILITY.md) (what must not change silently).

中文读者：[MAINTAINING.zh-CN.md](MAINTAINING.zh-CN.md) 是本文的中文版。

## 1. The two lines

| Line | Branch | Version in `pyproject.toml` | What lands there |
| --- | --- | --- | --- |
| Beta (development) | `main` | `0.5.0b2`, then `0.5.0b3`, … | Everything: fixes, features, UX, docs |
| Release candidate | `release/0.5.0` | `0.5.0rc1`, then `rc2`, … until `0.5.0` | Only correctness, crash, packaging, cross-platform, hardware/DAW compatibility, documentation, localization and release-engineering fixes, each with a regression test where one can express it ([RELEASE_PLAN.md §2a](RELEASE_PLAN.md#2a-two-lines-beta-and-release-candidate-2026-10-06)) |

Rules that keep them consistent:

* A fix that applies to both lines is committed once and reaches the other
  line by `git merge` or `git cherry-pick -x` of the same commit, never
  retyped. Fix the candidate first when the bug is in the candidate; the
  forward-port to `main` follows in the same session.
* Nothing goes from `main` to the candidate except through that rule. A new
  feature, a command-line redesign, an algorithm experiment or a dependency
  upgrade stays on `main` until the next candidate series is cut.
* Published history is never rewritten: no force-push to `main`,
  `release/**` or a published tag; merges are merge commits (the per-PR
  merge commit is the record of how conflicts were resolved).
* The candidate becomes `0.5.0` only when the gate in
  [RELEASE_PLAN.md §2b](RELEASE_PLAN.md#2b-the-050-gate) is met on real
  machines and the maintainer publishes it.

## 2. What runs on its own

Both workflows live in `.github/workflows/`; every action is pinned to a
commit SHA with its version in a comment.

**CI** (`ci.yml`), on every pull request and on pushes to `main` and
`release/**`, nine jobs that must all be green before a merge:

| Job | What it proves |
| --- | --- |
| Lint and type-check | `ruff check`, `ruff format --check`, strict `mypy` (with the `dev` extra only, so PySide6's stubs are absent: code that type-checks only with them fails here), `scripts/check_doc_links.py`, `scripts/check_cli_docs.py`, the docs-site build, `scripts/check_src_safety.py` (no network imports, no shell-outs under `src/`), `scripts/check_action_pins.py` (every pinned action is a commit its repository has; the one check that needs the network) |
| JSON Schemas | the schema tests, and that `reverbscope schema <name>` prints exactly the shipped files |
| Tests (Ubuntu 3.12 / 3.13 / 3.14, macOS 3.12, Windows 3.12) | the full suite offscreen; on Ubuntu 3.12 with the 85 % branch-coverage gate on `core` and `models`; then the fake-backend Standalone flow and `examples/synthetic_measurement.py` |
| sdist and wheel | `python -m build`, the wheel installs, `reverbscope --help` runs |
| License bundle and GPL-module gate | `scripts/build_license_bundle.py` resolves every package; the installed PySide6 is Essentials only (no GPL-only Qt module) |

**Release** (`release.yml`), on pushes to `main` and `release/**` that touch a
release file (`pyproject.toml`, `packaging/`, the bundle scripts, the
workflow itself, `requirements/`), on `v*` tags, on pull requests that touch
those files, and by hand (**Actions → Release → Run workflow**). It runs the
quality job, builds sdist and wheel, the four platform bundles (Linux,
macOS arm64, macOS x86_64, Windows; Desktop and Terminal Edition each),
smoke-tests every bundle (`scripts/smoke_bundle.py`), installs, smokes and
uninstalls the Windows installer, builds and checks both DMGs, writes the
SBOM, checks the exact file set (`scripts/release_draft.py stage`) and, on
`main` or `release/**` while no tag `v<version>` exists, opens or refreshes
the **draft** release `v<version>` with exactly 14 files. A pull request run
drafts nothing. A documentation-only push builds nothing.

**Pages** (`pages.yml`) publishes `site/` once Pages is enabled in the
repository settings.

**Dependabot** (`.github/dependabot.yml`) opens pull requests for the pinned
GitHub Actions. Take them one at a time: a major version of
`upload-artifact` / `download-artifact` changes how the Release workflow
passes files between jobs, so merge such a bump only after its pull request
has had a green *Release* run (the workflow runs on pull requests that change
it) and the draft refreshed from `main` afterwards still holds 14 files.

## 3. What only a maintainer does

* **Publish a release.** Open the draft `v<version>` on the Releases page,
  read the notes, download at least one bundle and start it on a real
  machine, then **Publish release** (as a *pre-release* for a beta or a
  candidate). Publishing creates the tag; the tag run repeats the gates and
  uploads to PyPI only when the repository variable `REVERBSCOPE_PUBLISH_PYPI`
  is `true` and the `pypi` environment exists ([RELEASE_PLAN.md §3](RELEASE_PLAN.md#3-how-a-release-is-produced)).
  Never publish a draft whose target commit is not the head of its line:
  the draft is rebuilt by the next Release run, and a docs-only push does
  not start one, so run the workflow by hand when the draft lags.
* **Cut the next candidate** (`rc2`, …) on `release/0.5.0`: one commit that
  sets `project.version`, renames the CHANGELOG section, adds a STATUS
  snapshot; push; the Release run opens the new draft. Merge the same commit
  into `main` only if it carries a fix; the version bump itself stays on the
  candidate line.
* **Cut the next beta** on `main`: the same commit shape with `0.5.0b3`;
  move the `[Unreleased]` entries under the new heading.
* **Repository settings** (not reachable from the command line or a
  workflow): the `main` ruleset (require the nine CI jobs, block force
  pushes and deletions, require a pull request with 0 approvals while there
  is one maintainer), the same for `release/**`, Pages, description, topics,
  homepage; the macOS Developer ID secrets ([RELEASE_PLAN.md §3b](RELEASE_PLAN.md#3b-macos-signing-today-and-with-a-developer-id)).
* **Close or merge pull requests**, decide on reports (§5), fill the results
  log in [HARDWARE_TESTS.md](HARDWARE_TESTS.md) from issues only.

## 4. Before every push

Run what CI runs (one or two minutes without the suite, about ten with it):

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,gui]" build
ruff check . && ruff format --check .
mypy
python scripts/check_doc_links.py && python scripts/check_cli_docs.py && python scripts/check_src_safety.py
python scripts/check_action_pins.py   # needs the network; run it after touching a workflow
python scripts/build_docs_site.py --out /tmp/reverbscope-site
QT_QPA_PLATFORM=offscreen pytest --cov=reverbscope.core --cov=reverbscope.models --cov-fail-under=85
python -m build
```

Then push once. Every push to a pull request costs one CI run (about 15
runner-minutes, macOS counted) and, when a release file changed, one
Release run (about 40 runner-minutes); pushes a few minutes apart are
cancelled in favour of the newest, pushes to `main` and tags are not.

When a check is red:

| Red check | Usually | Do |
| --- | --- | --- |
| Lint and type-check, mypy only | a `type: ignore` that is needed with PySide6 stubs but not without, or the reverse | make the code typecheck in both environments (declare the attribute, return the value) instead of ignoring; `pip install -e ".[dev]"` in a second venv reproduces the CI job |
| Lint and type-check, action pins | a pin that is 40 hex digits but not a commit of the action's repository (a job would fail at start with "Unable to resolve action"; `pages.yml` did) | the message names file, line and repository; take the commit of the release tag with `git ls-remote --tags https://github.com/<owner>/<repo>` (the peeled `^{}` line for an annotated tag) and put the version in the comment; a network error is retried three times, so a second failure is GitHub being unreachable, not the pin |
| Lint and type-check, Ruff | formatting | `ruff format .` |
| Documentation links / CLI examples | a moved file or an example that the parser no longer accepts | fix the document; `check_cli_docs.py` names file, line and parser message |
| Tests on one OS only | path, encoding or line-ending assumptions | the job log names the test; reproduce with `PYTHONIOENCODING=cp1252` or a Windows path in a unit test, fix the code, keep the test |
| Tests everywhere, coverage line | the suite passed but `core`/`models` coverage fell under 85 % | add the synthetic test the new branch needs; never lower the gate |
| Tests on every OS, every test passed, then the process died at interpreter exit (`QObject: shared QObject was deleted directly`, exit 134 / 139 on Linux, 127 on Windows) | a new PySide6 release changed what Qt tolerates at shutdown; the `gui` extra has an upper bound for that reason (`docs/DEPENDENCIES.md` §4) and `tests/conftest.py` tears Qt down in a known order when the session ends | reproduce in a venv with the new PySide6 on `tests/ui` (each module alone passes, the directory does not); extend the session-end teardown in `tests/conftest.py` first, then lift the bound on both lines as a release-engineering change, never by skipping the GUI tests |
| Release, a bundle job | PyInstaller lock, a native library without a licence, a GPL-only Qt module | `requirements/bundle.lock` (`scripts/compile_bundle_lock.py`), `packaging/licenses/native/`, `packaging/pyinstaller_filters.py`; the gate scripts say which file |
| Release, draft job | two drafts, a tag on another commit, an asset attached by hand | `scripts/release_draft.py` refuses to guess; remove the stray draft or file and re-run |

A failing test is never a flake to be re-run until green: find the cause.
Never skip, disable or delete a test to pass.

## 5. A report arrives

Issue forms (`.github/ISSUE_TEMPLATE/`, English and Chinese pairs) collect
the environment report (`reverbscope doctor --probe --out report.txt`), the
version and build commit, the files and the expectation. Then, in order
([CONTRIBUTING.md](../CONTRIBUTING.md#from-a-community-report-to-a-regression-test)):

1. Reproduce from the attached files. Cut them down to the smallest file
   that still fails and add it to the regression corpus
   (`tests/corpus/manifest.json`, generated by `tests/corpus/generate.py`),
   or write the synthetic test (`tests/conftest.py` has rooms and decays).
2. Fix on the line where the bug is reported; for a candidate bug, on
   `release/0.5.0` first, then merge or cherry-pick the same commit to
   `main`. Add the CHANGELOG line in the same commit.
3. Record the outcome in the issue, and a PASS / FAIL row in
   [HARDWARE_TESTS.md](HARDWARE_TESTS.md) or [VALIDATION.md](VALIDATION.md)
   only for a run on real equipment, with the issue number. Synthetic and
   CI results never fill those tables.
4. If the fix changes a stored number or a file key, follow
   [API_STABILITY.md](API_STABILITY.md) (additive change, `schema_version`
   when a reader must change, deprecation before removal).

## 6. Where things are

| Need | Place |
| --- | --- |
| What is implemented, what was run, where | [STATUS.md](STATUS.md) (dated snapshots), `CHANGELOG.md` |
| Every number's algorithm, units, validity | [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) |
| Which checks need hardware | [OFFLINE_CHECKS.md](OFFLINE_CHECKS.md), [HARDWARE_TESTS.md](HARDWARE_TESTS.md), [VALIDATION.md](VALIDATION.md) |
| Dependencies and licences | [DEPENDENCIES.md](DEPENDENCIES.md), [THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md), `scripts/build_license_bundle.py` |
| Build a release without Actions minutes | [RELEASE_PLAN.md §3a](RELEASE_PLAN.md#3a-without-github-actions-minutes), `scripts/build_release.py` |
| Timings and memory | [PERFORMANCE.md](PERFORMANCE.md), `scripts/benchmark.py`, `scripts/bench_dsp.py` |
| Translations | `src/reverbscope/locale/zh_CN/LC_MESSAGES/reverbscope.po`; `tests/unit/test_i18n_catalog.py` fails on any untranslated string |
