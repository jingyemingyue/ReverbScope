# License decision: Apache License 2.0

Decided 2026-09-17 for the v0.1 foundation, after the dependency audit
(DEPENDENCIES.md) and the reference-repository audit (THIRD_PARTY_REVIEW.md).
Changing the license requires the project owner's explicit approval.

## Candidates considered

| | MIT | BSD-3-Clause | Apache-2.0 |
| --- | --- | --- | --- |
| Commercial use | yes | yes | yes |
| Attribution required | yes | yes | yes (+ NOTICE) |
| Explicit patent grant from contributors | no | no | **yes** (§3) |
| Patent retaliation clause | no | no | yes |
| Explicit contribution terms | no | no | yes (§5) |
| Compatible with all ReverbScope dependencies | yes | yes | yes |
| Can be combined into GPL-3.0 works | yes | yes | yes |
| Can be combined into GPL-2.0-only works | yes | yes | no |
| Common in the Python DSP ecosystem | very (pyroomacoustics, pyfar) | very (NumPy, SciPy, python-acoustics) | common (packaging, pip-audit, many Apache projects) |

## Why Apache-2.0

1. **Patents are a real concern in this domain.** The methodology audit
   found a densely patented neighbourhood (room correction: Dirac,
   Sonarworks, Audyssey, DTS, Harman) and two in-force patents adjacent to
   measurement (US 9,959,883, US 10,816,391). Apache-2.0 gives every user an
   explicit patent license from every contributor for what they contribute,
   and terminates it for anyone who sues over the project's patents. MIT and
   BSD are silent on patents.
2. **Legal clarity was ranked second only to correctness in the project
   brief.** Apache-2.0 spells out contribution terms (§5), trademark
   exclusion (§6) and NOTICE handling (§4d), which removes ambiguity for
   commercial adopters and corporate contributors.
3. **Dependency compatibility.** All runtime dependencies are permissive
   (BSD-3, MIT, MIT-0, PSF-style, Apache-2.0/BSD dual) or LGPL used
   dynamically (Qt/PySide6, libsndfile). Apache-2.0 code may be combined with
   all of them. Nothing forces copyleft on ReverbScope as long as the LGPL
   components stay replaceable shared libraries (see DEPENDENCIES.md).
4. **Community.** Apache-2.0 is an OSI/FSF-approved, GPLv3-compatible
   license accepted by all major distributions and package indexes.

## Costs accepted

* Apache-2.0 cannot be incorporated into GPL-2.0-*only* projects. No such
  downstream use is planned; GPL-3.0 users are unaffected.
* Contributors must keep the NOTICE file and add attribution notices when
  they adapt third-party permissive code (recorded in CODE_PROVENANCE.md).
* The license text is longer than MIT/BSD. The short SPDX identifier
  `Apache-2.0` is used in packaging metadata.

## How it is applied

* `LICENSE`: the verbatim Apache License 2.0 text (SHA-256
  cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30, as
  published at https://www.apache.org/licenses/LICENSE-2.0.txt).
* `NOTICE`: project copyright line and a pointer to the dependency notices.
* `pyproject.toml`: `license = "Apache-2.0"`, `license-files = ["LICENSE", "NOTICE"]`.
* Source files carry no per-file header in v0.1; the package-level license
  applies. Adding SPDX headers is an accepted future change.

## Re-evaluation triggers

Re-open this decision if: a copyleft dependency becomes unavoidable in the
core; a GPL-2.0-only integration is required; or a contributor cannot accept
the Apache-2.0 patent terms.
