# OSS application readiness

Audit date: **2026-10-15**. This is an evidence inventory and a preparation gate,
not an application submission, approval prediction or OpenAI endorsement.
[Application draft](OSS_APPLICATION_DRAFT.md) · [Roadmap](ROADMAP.md) ·
[Machine-readable GitHub snapshot](evidence/oss-readiness-2026-10-15.json).
Recheck GitHub and the official program before submitting; this snapshot is dated.

## Official program statements

Sources read on the audit date: [OpenAI program documentation](https://developers.openai.com/community/codex-for-oss)
and [official application form](https://openai.com/form/codex-for-oss/).

- Active open-source maintainers may apply. Usage, adoption, ecosystem importance
  and ongoing maintenance are review signals. No numeric star/download minimum
  or approval probability is stated on these pages.
- The form requests a public GitHub profile and repository, primary/core maintainer
  role, an account email, and a qualification explanation. API-credit requests ask
  for an OpenAI organization ID and a concrete use plan; several text fields have
  a 500-character limit.
- The documented support includes six months of ChatGPT Pro with Codex, API credits
  for OSS maintenance, and conditional Codex Security access. Selection and security
  access are reviewed; none is guaranteed by passing our checklist.

These statements are separate from **our preparation recommendations** below:
installable packages, honest testing evidence, a clear README, approachable tasks,
reproducible bugs and a small reviewed PR backlog. Those are project goals, not
invented official eligibility rules. Read the linked program terms before submission.

## Verified project and maintenance evidence

| Item | Evidence at audit | Limit |
| --- | --- | --- |
| Public Python project | GitHub repository is public; Apache-2.0, LICENSE/NOTICE; Python >=3.12 | No license change in this work |
| Development | `main` = `3567da03ea415fc48b870035fe3502234a471514`, 0.5.0b3 | Development source, not public b3 download |
| Candidate | `release/0.5.0` = `03a32f640bcd8d5d3604ae2b9d122f912cb1796f`, 0.5.0rc2 | Feature-frozen; Draft release |
| Main automated gates | [CI 37944754736](https://github.com/jingyemingyue/ReverbScope/actions/runs/37944754736), [Release 37944754997](https://github.com/jingyemingyue/ReverbScope/actions/runs/37944754997): success on that main SHA | Automated PASS, not physical testing |
| Candidate automated gates | [CI 37934093532](https://github.com/jingyemingyue/ReverbScope/actions/runs/37934093532), [Release 37934093630](https://github.com/jingyemingyue/ReverbScope/actions/runs/37934093630): success on that candidate SHA | New changes require their own checks |
| Maintenance activity | Main merge #53, current correctness PR #60 and GUI PRs; [maintenance runbook](MAINTAINING.md), [contribution process](../CONTRIBUTING.md) | Self/AI-authored work is maintenance activity, not independent review or adoption |
| Core workflows | ESS generation/capture, IR import/analysis, decay validity, reflection/noise diagnostics, compare, session/project persistence, CLI/GUI, EN/zh-CN | [Methodology](MEASUREMENT_METHODOLOGY.md), tests and [offline checks](OFFLINE_CHECKS.md); no hardware accuracy claim |
| Governance | CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CODEOWNERS and paired issue forms present | Private vulnerability reporting/contact reachability and branch rules were not verified through this connector |
| Discoverability | Description, Topics and Homepage empty; Pages false; site URL returns HTTP 404 | Admin metadata write endpoint unavailable here; [exact commands / Pages deployment prerequisite](REPOSITORY_SETTINGS.md) |
| Adoption | 0 stars, 0 forks in the snapshot; no hardware/DAW rows and no open non-PR issues | No verified external users, monthly downloads or case studies. Do not convert maintainer/Draft asset downloads into users |

The intended value is an approachable, scriptable measurement handoff next to a
student/independent engineer's DAW: export the test sweep, capture the microphone,
read validity-aware results, compare positions and share a reproducible session.
It is not presented as more accurate than REW or other mature tools.

## Release and installation audit

| Release | Visibility | Target | Assets |
| --- | --- | --- | --- |
| v0.5.0b1 | Public pre-release, 2026-10-01 | `2efcf42f35e088462b67a6bd8966cc4db15c763a` | 14, old RoomScope names |
| v0.4.1 | Public pre-release, 2026-09-30 | `d97822afb4d6f77e81c04e95b040f56680f00cf7` | 14, old RoomScope names |
| v0.5.0rc2 | Draft pre-release | candidate SHA above | 14, renamed ReverbScope assets |
| v0.5.0b3 | Draft pre-release | main SHA above | 14, renamed ReverbScope assets |
| v0.5.0b2 / v0.5.0rc1 | Older Draft pre-releases | See JSON snapshot | 14 each; do not promote accidentally |

The original README/installation text directed visitors to rc1/rc releases and
ReverbScope filenames absent from the public beta. The corrected entry point is
[Public testing](PUBLIC_TESTING.md), with exact public asset names and the legacy
`roomscope` command. Existing detailed GUI/install guides are scoped to renamed
source/candidate builds. Screenshots are labelled source + Synthetic / Demo.
Historical release-plan paragraphs retain dates and now have a current-status notice.

Public beta wheel was downloaded directly from its Release URL. Its SHA256 is
`bbb7c1f15998550cec5093cd830af1230222be43e03c54fcc4b53ee359f92b84`, matching both
GitHub's asset digest and that release's SHA256SUMS; its entry points are
`roomscope` and `roomscope-gui`. Full local checks are recorded in
[evidence/OSS_LOCAL_CHECKS.md](evidence/OSS_LOCAL_CHECKS.md).

P1 findings, with deliberately bounded claims:

- Four build targets exist: Windows x64, macOS arm64, macOS x86_64 and Linux
  x86_64. Release workflow builds Desktop + Terminal editions, smoke-tests them,
  tests Windows installer install/uninstall and DMG content/architecture, and
  validates the exact 14-asset set. It cannot test personal interfaces or a native
  interactive desktop session. Linux bundles require glibc 2.39+; macOS 14 minimum
  is not a recorded native test.
- Runtime versions are pinned in `requirements/bundle.lock`; the published lock
  and CycloneDX SBOM exist. Pins do not contain artifact hashes, and build tools,
  runner images/native libraries and signing timestamps are not fully fixed.
  **Byte-for-byte reproducibility has not been demonstrated.** A wheel install
  resolving dependencies today is not a reproduction of a frozen Desktop bundle.
- SHA256SUMS covers the 11 executable/source/wheel downloads, not itself, SBOM or
  lock. GitHub metadata supplies SHA256 for all 14 assets; the public wheel,
  checksum file, lock and SBOM were byte-checked in this audit. All 11 checksum
  entries match GitHub digests, and all 19 locked runtime versions match the public
  SBOM. Other bytes are not
  asserted verified here. Metadata presence is not a local binary verification.
- LICENSE/NOTICE and third-party-license gates exist. Local build/license results
  belong to their stated environment; this work does not change legal terms.
- macOS Developer ID signing/notarization is conditional; #64's latest Release
  job **skipped** both. Windows bundles have no claimed Authenticode signature.
  Unsigned-build first-launch instructions remain explicit.

## Candidate checklist: report only, do not publish

Candidate under consideration: **v0.5.0rc2**, target `03a32f640bcd8d5d3604ae2b9d122f912cb1796f`.
This is a Draft/approval report, not authorization to publish or create a tag.

| Gate | Current status | Acceptance / next evidence |
| --- | --- | --- |
| Exact version, target and 14 asset names | Automated PASS (metadata audit + existing staging gates) | Re-read target and SHA before any refresh/publish |
| Source CI and Release at candidate SHA | Automated PASS | Links above; run only necessary local checks for this PR |
| Full local verification of every candidate download | NOT RUN | Download same-run assets, verify SHA256/size, inspect SBOM/lock/license bundle |
| Installed arm64 Mac first launch, native GUI, save/reopen | NOT RUN | Execute short [community guide](COMMUNITY_TESTING.md), attach exact asset hash |
| Real interface: channels, rates, complete take, Stop, unplug, latency, loopback | NOT RUN | Linked dated physical report; never use CI/fake as a substitute |
| Fender Studio Pro / Studio One roundtrip | NOT RUN | Physical sweep + mic export + analysis; report actual DAW version/settings |
| Windows / Intel Mac / Linux personal-machine startup | NOT RUN | Per-platform reports; Windows hardware compatibility remains unverified |
| Known relevant fixes | BLOCKED | #60 awaits maintainer decision; cannot assert rc2 includes its head |
| Release decision | BLOCKED | Maintainer accepts evidence/limitations and publishes a pre-release only after review |

The stable **0.5.0** gate remains [RELEASE_PLAN §2b](RELEASE_PLAN.md#2b-the-050-gate):
real macOS and Windows, two interface models, required rate/Stop/dropout/room checks,
two DAW workflows with applicable negative controls and a reference-instrument
comparison on the same recording. The wider matrix additionally checks loopback.
One Mac report does not satisfy that gate. No stable tag is part of this PR.

## All open PRs: exact-head workflow status

The table records the head SHA, not an older green run or a green base branch.
NOT RUN means no matching workflow run was returned, not that it passed.

| PR | State | Head | Base | CI | Release |
| --- | --- | --- | --- | --- | --- |
| [#64](https://github.com/jingyemingyue/ReverbScope/pull/64) | Draft | `3eb54c866ecf` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38688148737) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38688148752) |
| [#63](https://github.com/jingyemingyue/ReverbScope/pull/63) | Draft | `50c5667963ae` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38625394609) | NOT RUN |
| [#62](https://github.com/jingyemingyue/ReverbScope/pull/62) | Draft | `85c45cde8974` | `gui/redesign` | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/38579136835) | NOT RUN |
| [#61](https://github.com/jingyemingyue/ReverbScope/pull/61) | Draft | `e2e7a2916ae2` | `gui/redesign` | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/38587706515) | NOT RUN |
| [#60](https://github.com/jingyemingyue/ReverbScope/pull/60) | Draft | `9c07f00f2c0a` | `release/0.5.0` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38576861560) | NOT RUN |
| [#59](https://github.com/jingyemingyue/ReverbScope/pull/59) | Draft | `71fef588b1b7` | `gui/redesign` | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/38577932577) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38577932485) |
| [#58](https://github.com/jingyemingyue/ReverbScope/pull/58) | Draft | `2560124b3875` | `grok/gui2-professional-polish` | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/38457543884) | NOT RUN |
| [#57](https://github.com/jingyemingyue/ReverbScope/pull/57) | Draft | `72a773791975` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38273997108) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38273997032) |
| [#56](https://github.com/jingyemingyue/ReverbScope/pull/56) | Draft | `7955e7c2a38a` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38077549803) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38077549796) |
| [#55](https://github.com/jingyemingyue/ReverbScope/pull/55) | Draft | `77e3f6365c94` | `main` | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/38117026198) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38117026220) |
| [#54](https://github.com/jingyemingyue/ReverbScope/pull/54) | Draft | `6321a2f4a406` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/38000859764) | NOT RUN |
| [#41](https://github.com/jingyemingyue/ReverbScope/pull/41) | Open | `0182b71ef125` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/37175525277) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/37175525282) |
| [#37](https://github.com/jingyemingyue/ReverbScope/pull/37) | Draft | `175800fafce6` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/37390143316) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/37390143446) |
| [#31](https://github.com/jingyemingyue/ReverbScope/pull/31) | Open | `399caab6aaed` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/37967707583) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/37967707650) |
| [#30](https://github.com/jingyemingyue/ReverbScope/pull/30) | Open | `07e331b7d1cf` | `main` | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/36820916292) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/36820916262) |
| [#29](https://github.com/jingyemingyue/ReverbScope/pull/29) | Open | `9a30a1128d73` | `main` | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/37815440357) | [success](https://github.com/jingyemingyue/ReverbScope/actions/runs/37815440366) |
| [#28](https://github.com/jingyemingyue/ReverbScope/pull/28) | Open | `734fbfe50dd4` | `main` | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/37815415651) | [failure](https://github.com/jingyemingyue/ReverbScope/actions/runs/37815415740) |

### Recommended integration order (no merges performed)

1. Review this OSS-readiness PR independently against main. It contains no DSP,
   Qt code, version bump, workflow/lock upgrade or GUI redesign. Its README/guide
   edits overlap other PRs and must be kept when resolving later doc conflicts.
2. Treat #60 as a narrow correctness decision on `release/0.5.0`; after explicit
   maintainer approval and merge, forward-port the same commit with `-x` as the
   runbook requires. Do not publish the old rc2 pretending that fix is included.
3. Select one GUI integration route. #58 is stacked on #57; `gui/redesign` points
   to #58's head; #59/#61/#62 target that route. #57 already contains #56
   by ancestry, so do not merge #56 again. #55 is a separate alternative.
   #57's diff includes non-GUI/DSP changes, so it cannot be treated as a cosmetic
   shell to merge wholesale. #54 also includes CLI/model changes and is not an ancestor of #57; overlapping
   changes still need review rather than an assumed integration.
4. #63 and #64 each target main independently. Git ancestry confirms #63 is **not**
   an ancestor of #64. #64 is not an integration of the #57/#58/#59 route either.
   Compare overlapping main_window/pages/theme/tests/docs explicitly; carry any
   desired correctness fixes in reviewed, small commits, then native-test that
   chosen integrated SHA. #64's nine CI jobs and its bundle builds passed, while
   draft publishing and PyPI were skipped. No native/hardware evidence follows.
5. Resolve the latest red CI on #55/#58/#59/#61/#62 before advancing those branches;
   earlier green heads do not excuse current failures. Keep #37's broad changes
   and #41's DSP experiment outside this preparation PR. Dependabot #28/#29 are
   red; #30/#31 are green but need their own review of workflow contracts.

## Minimum before a well-evidenced application

These are **our recommendations**, not additional official application requirements:

1. Merge reviewed readiness fixes, set About/Topics through an authorized admin,
   and verify the public download path anonymously. Keep Homepage empty until live.
2. Finish a dated Apple Silicon physical report and a Fender Studio Pro/Studio One
   roundtrip; preserve failures. Have a maintainer decide which tested candidate
   to share publicly, without calling it stable or universally compatible.
3. Obtain at least one independent tester's consented, reproducible installation
   or measurement report. Link the report and retest; do not solicit fake stars
   or count our own downloads as adoption. Record unavailable adoption honestly.
4. Refresh the snapshot/form text, verify maintainer role/public profile and fill
   account/organization fields privately. Review the official terms and submit
   personally. This work never submits the form or exposes account identifiers.

## Final audit categories

| Category | Result / owner |
| --- | --- |
| DONE | Dated GitHub/source audit, corrected public/source install distinction, bilingual testing flow, safe report preparer, paired forms, task backlog, roadmap, evidence-linked application draft; local check record linked above |
| BLOCKED | About/Topics admin write not exposed; Homepage 404; private reporting/contact and branch rules unverified; candidate publish/GUI integration need maintainer review; no byte-reproducibility proof |
| NEEDS REAL HARDWARE | Installed native Mac GUI, interface/rate/Stop/unplug/loopback/latency/save-reopen and actual DAW reports; Windows/Intel/Linux physical evidence |
| NEEDS COMMUNITY EVIDENCE | Independent testers, usage/adoption, externally reproduced bugs, follow-up reports and case studies; no invented counts |
