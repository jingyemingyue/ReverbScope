# OSS readiness local validation

Date: 2026-10-15. Base: `3567da03ea415fc48b870035fe3502234a471514`.
Scope: the OSS-readiness patch on `oss/application-readiness`, not any GUI Draft.
Environment: Linux x86_64, Python 3.12.14; offscreen Qt 6.11.2.
Results are recorded after each command finishes. This file is not a live CI badge.

## Report-tool regression evidence

The first focused run had **2 failed, 30 passed**. It caught the public beta's
legacy `roomscope` environment key being rejected, and distinguished an in-archive
Windows launcher from a separately downloadable asset. The key compatibility was
fixed without rewriting the beta version; the asset check now distinguishes the
known in-archive launcher. The focused rerun passed 32 tests. A later docs-site regression test first failed
because JSON evidence links pointed to missing generated files; it passed after
linking JSON attachments to repository source. The final targeted group passed
89 tests. Its 128 matplotlib CJK glyph warnings are recorded, not suppressed;
the visible Chinese Qt screenshot was separately checked after adding a local
Noto CJK font. No font file is shipped by this patch.

## Validation ledger

| Check | Status | Evidence / scope |
| --- | --- | --- |
| Public beta wheel integrity | Automated PASS | Downloaded from v0.5.0b1; SHA256 matches GitHub digest and its SHA256SUMS: `bbb7c1f15998550cec5093cd830af1230222be43e03c54fcc4b53ee359f92b84` |
| Public beta wheel entry points | Automated PASS | Inspected installed artifact metadata: `roomscope`, `roomscope-gui`; clean lock-constrained install, help, demo, offscreen gui --smoke, and legacy doctor report collection succeeded |
| Focused pytest | Automated PASS | 89 passed, 128 matplotlib font warnings; docs site, report tool, issue/language pairs, release text, screenshot generator |
| Ruff / formatting | Automated PASS | ruff check .; ruff format --check . (275 files) |
| Mypy | Automated PASS | strict mypy: 87 source files, with Qt installed |
| Docs / CLI / safety / docs site | Automated PASS | link check (docs + 7 root documents), 102 CLI commands parsed only, src safety, 53-page site; every generated link gate in targeted tests passes |
| Full local pytest + coverage | FAIL / INCOMPLETE | First completed run: 1912 passed, 1 skipped, 1 session-guard error from concurrent QA smoke, coverage 93.38%; rerun lost its execution-server session after 1444 test indicators, with no completion summary. Head-specific PR CI must settle the full-suite gate; do not call either local attempt green |
| License bundle / Essentials gate | Automated PASS | build_license_bundle.py: no unresolved packages; installed PySide6 Essentials gate passes |
| sdist / wheel / metadata / clean install smoke | Automated PASS (initial build) | python -m build --no-isolation; twine check both files; isolated wheel + runtime-lock install; pip check, help, fake take, saved-result show and offscreen gui --smoke; a later refresh of sdist/wheel and twine check also passed; final head is independently rebuilt by PR CI |
| Real hardware, native macOS GUI and actual DAWs | NOT RUN | No equipment or DAW in this cloud environment |

No table row implies independent adoption, physical audio compatibility, notarization
or a published candidate. Temporary logs and generated reports stay outside the repo;
commands and bounded results here are sufficient to reproduce them.


## Reproduce the relevant checks

Use a Python 3.12 virtual environment with the existing `dev,gui` extras and
`build`/`twine` for packaging. The full numerical suite is bounded to one BLAS
thread here because the first attempt lost its execution-server connection
before completing. That incomplete attempt is not a PASS and supplied no final
coverage figure.

```bash
ruff check .
ruff format --check .
mypy
python scripts/check_doc_links.py
python scripts/check_cli_docs.py
python scripts/check_src_safety.py
python scripts/build_docs_site.py --out /tmp/reverbscope-readiness-site
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 QT_QPA_PLATFORM=offscreen pytest --cov=reverbscope.core --cov=reverbscope.models --cov-fail-under=85 --cov-report=term
python -m build --no-isolation
python -m twine check dist/*
python scripts/build_license_bundle.py --out /tmp/reverbscope-readiness-licenses
```

`check_action_pins.py` was not rerun: no workflow or action pin changed. No
manual Release workflow or bundle-matrix rerun was requested. CI will run once
for the PR; the existing Release path filter should skip this docs/test/tool
patch. Offscreen GUI/synthetic tests never count as native desktop acceptance.

## Why these changes exist and how to accept them

| Area / files | Problem addressed | Acceptance / reproducible evidence |
| --- | --- | --- |
| READMEs, PUBLIC_TESTING, installation/version notices, site copy | Visitor was told to download unpublished renamed candidates | Compare the frozen public asset list, download/hash/install beta wheel, run silent demo; asset-name regression |
| docs/images via existing render_readme_assets.py | Existing image footer showed 0.5.0b1 while main is b3 | Regenerate on this branch, inspect b3 footer, source caption and Synthetic / Demo stamp; screenshot-generator tests |
| COMMUNITY_TESTING + HARDWARE_TESTS | Empty matrix lacked a short Mac/Fender run with save/reopen and explicit scope | Both languages contain the same manual sequence and NOT RUN defaults; human execution remains required |
| prepare_test_report.py + its tests | Inconsistent report setup, stale reruns and private paths | Actual current/legacy doctor capture; tests cover timeout/errors, skipped collection, no-overwrite, path omission and no inferred Hardware PASS |
| Paired issue forms, CONTRIBUTING and runbooks | Reports could mix synthetic/physical results or omit asset/save-reopen evidence | Existing EN/zh structure, required-field, command/evidence and link tests pass |
| Roadmap, task backlog, OSS audit/application + GitHub snapshot | Claims/next steps were scattered or stale | Exact SHA/run/visibility links, separated official facts/recommendations, public asset check, 500-character field tests |
| build_docs_site.py + regression | Newly linked JSON evidence was not copied to the generated site | Pre-fix assertion fails; post-fix nested/root JSON href tests and all generated-link checks pass |

Runtime sources, schemas, DSP, GUI code, license, version, dependency locks and
workflow files are unchanged. Candidate publication and GUI integration are
separate maintainer decisions.


## Published metadata cross-check

The public beta SHA256SUMS, generated-bundle.lock and CycloneDX SBOM were also
actually downloaded. Their hashes match the corresponding GitHub asset digests.
All 11 SHA256SUMS entries match the asset metadata; all 19 runtime lock versions
are present with matching versions in the public SBOM (49 components, CycloneDX
1.6, RoomScope component 0.5.0b1). This is a metadata/integrity check, not an
independent assertion that every frozen bundle contains exactly those bytes.
The public SBOM has no root metadata.component; component presence was checked
in its component list rather than assuming a root name.


## PR ancestry evidence

Fetched the 17 exact PR heads into this isolated checkout, then used
`git merge-base --is-ancestor` (exit 0/1), without merging any branch.
Confirmed: #56 → #57 → #58; #58 → #59/#61/#62. Not ancestry:
#55 → #56, #54 → #57, #63 → #64, #57/#58 → #64.
The JSON snapshot records these edges. Base-branch names alone would miss that
#57 already contains #56, despite both PRs targeting main.


## Isolation correction during this audit

The first completed full run executed 1912 tests successfully (one font-related
skip, coverage 93.38%) but **failed the session-scoped real-data-directory guard**
at teardown. It is not recorded as a successful full run. Concurrent install
smokes had been invoked without an isolated REVERBSCOPE_HOME; their synthetic
session path was confirmed in the default recent-session list. The WAV test
named by teardown passed independently (1 passed). No test/guard was weakened.
The full suite was rerun with those external app invocations finished, but the execution-server connection was lost again; any later
smoke must use its own data directory. The complete suite will be verified by the original PR CI jobs rather than claiming an interrupted local run passed.

QA runtime versions: Python 3.12.14, numpy 2.5.4, scipy 1.18.1, Qt Essentials
6.11.2, pytest 9.1.1, ruff 0.17.0, mypy 2.4.0, hatchling 1.32.4. Clean published
and new-wheel installations separately used their pinned runtime graph (numpy
2.5.3, Qt 6.11.2). These environments are deliberately distinguished.


Chinese chart rendering was additionally run with a fresh, task-local
MPLCONFIGDIR after installing a local Noto CJK font: the existing CJK-font
regression passed (1 passed). This distinguishes a cached missing-font skip
from actual rendering with an available font; it is still an offscreen check.


## Final cross-platform test detail

All new report tests read UTF-8 artifacts explicitly, including Chinese reports
and the UTF-8 GitHub snapshot, so Windows locale defaults cannot turn a valid
file into a decode failure. The final focused report/docs run passed **24 tests in 1.40 s** after this UTF-8
change; the earlier broader targeted run passed 89 tests. Updated issue form examples
were rechecked with the existing language/form gates: 31 passed.

Head-specific CI is requested exactly once by the readiness PR. The local full
run limitation is disclosed above; the original multi-platform pytest, type,
license, schema and package jobs are not disabled, replaced or weakened.


The existing Pages workflow is a separate deployment prerequisite: source-site
copy in this PR does not enable Pages. Merging that file on main while Pages
remains disabled triggers a failed deployment; the settings handoff records
how to configure it or keep the site-copy change pending. No deployment was run.
