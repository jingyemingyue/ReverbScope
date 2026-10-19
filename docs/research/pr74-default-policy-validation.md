# PR #74 default-policy integration evidence

Subject to GUIDELINES.zh-CN.md §4 C12/C16 and §6. Automated and synthetic
only. Fixed main: `ab3da19618a066460857f0d8c155e4a7dcc3610f`;
source #74: `ebc145752e3851c3d11150dc495634992174a79c`.

Validation remains incomplete: neither local full attempt produced a
complete test/coverage summary. The second execution session disappeared,
with its log stopping at 57%; no pytest completion or exit status was recovered.
The Draft PR's exact-head CI is the pending full-suite acceptance gate.

## Environment and source checks

2026-10-19, Linux x86_64, CPython 3.12.14; NumPy 2.5.4, SciPy 1.18.1,
PySide6 Essentials 6.11.2, pyqtgraph 0.14.0, pytest 9.1.1, pytest-cov 7.1.0,
Ruff 0.17.1, mypy 2.4.0. Fresh dev/gui installation; mypy runs in a separate
dev-only environment, as in CI. No dependency declaration was changed.

An AST audit of existing top-level functions relative to main found only
`_curve_from_truncation` (equivalent guard layout) and
`locate_impulse_response` (M3 suppression) changed. Existing sweep functions
are unchanged; all additional estimators remain separate functions. Relative
to #74, only `core/decay.py` changes under `src/`: method string, two
signature defaults and public docstring. Its entire builder body, including
the guard, is AST-identical to #74. The other experimental source files (`sweep`, `deconvolution`, `modal`,
`bayesian_decay`) remain byte-identical to that source branch; the added
M6 functions in `decay.py` are unchanged.

## Regression and snapshot evidence

- Against original #74, main's noise-policy tests reproduce **6 failed,
  10 passed**; exit 1. The three new default-path cases are deselected only
  for this historical 16-case reproduction. No collection policy changed.
- Candidate related run: **103 passed**, exit 0. Includes the inherited
  16 policy cases unchanged in intent, three added signature/public-IR cases,
  two M3 window cases, research known-answer tests, and existing decay tests.
- Known 0.8 s noiseless, 50 dB cutoff: valid T30 **0.8000399788459893 s**,
  approximately 0.005% high, rather than the original subtracting default's
  approximately 0.7861 s. The 1% assertion is inherited from main, not a
  standards accuracy tolerance.
- All eight snapshot cases match main exactly after replacing only the
  wall-clock `created_at` field with an explicit marker. All numeric arrays,
  validity, metadata other than creation time, serialized curve and method fields
  are compared. The common eight-case JSON projection has SHA256 for both:
  `06de2dcf9028376101a4d68432298f302e7765b22130a8b9f0b0984557fa1a80`.
  Cases: three noiseless cutoffs (45/50/55 dB), imported IR, and four
  synthetic swept-room cases (0.5/2 s duration × zero/1e-5 RMS noise).
- These cases do not expose M3's changed default because their harmonic
  windows do not intersect retained pre-roll. The independent short-window
  regression deliberately does, asserting zeroed samples, unchanged other
  samples, retained location/margin and unchanged input. ADR 0004 explains
  how M3 can affect downstream public outputs. A ninth end-to-end case
  (0.5 s sweep, 100 ms retained pre-roll, default suppression) actually differs
  from main at `placement.candidates` and `reflections.reflections`; all other
  serialized fields, including decay, match. The same reflection stays at
  18.0625 ms; its level changes from -18.774235376788795 to
  -18.77436631040675 dB (about 0.000131 dB), inherited by the placement
  candidate. This establishes a small numerical difference, not an accuracy
  failure or improvement. No general parity claim.

Reproduce snapshots from each selected worktree root, using this candidate's
absolute script path and an external output path:

```bash
PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 python /path/to/candidate/docs/research/pr74_default_snapshot.py /tmp/main.json
# Repeat in the candidate worktree, writing /tmp/candidate.json.
python - <<'PYCODE'
import json
from pathlib import Path
main = json.loads(Path("/tmp/main.json").read_text())
candidate = json.loads(Path("/tmp/candidate.json").read_text())
for name in main:
    if name == "sweep-long-preroll":
        assert [k for k in main[name] if main[name][k] != candidate[name][k]] == [
            "placement", "reflections"
        ]
    else:
        assert main[name] == candidate[name], name
PYCODE
```

Related tests:

```bash
QT_QPA_PLATFORM=offscreen OPENBLAS_NUM_THREADS=1 pytest tests/unit/test_noise_subtraction_policy.py tests/unit/test_research_default_paths.py tests/unit/test_algorithm_methods.py tests/unit/test_decay.py tests/integration/test_decay_validity.py -o addopts= -q --tb=short
```

## Deferred failures: not repaired or accepted

```bash
OPENBLAS_NUM_THREADS=1 pytest docs/research/pr74_deferred_probes.py -o addopts= -q --tb=short
```

**3 failed**, exit 1. Strict probes remain executable and failing; no skip,
xfail, weakened expectation or altered pytest testpaths was introduced.

- M2: `abs(phase_residual) < 1e-8` fails: residual
  **-1.3156552388058116 rad** for the phase identity at the adjusted settings.
- M8, beta 0.9995: known 100 Hz mode estimated **103.31381543868464 Hz**,
  failing the unchanged probe's ±1 Hz expectation.
- M8, beta 0.99: known 0.8 s modal T60 estimated **1.0169171539940518 s**,
  failing the probe's 5% expectation.

These newly added research acceptance probes live with the research record,
outside the existing `tests/` testpaths; no existing failing test was moved.
The main configured regression suite passing does not resolve these failures
or approve the experimental algorithms. Hardware, DAWs, native interaction,
ISO/IEC compliance and an official Codex Security scan were not performed.


## Latest-main refresh and incomplete full-suite evidence

Main advanced to `ab3da19618a066460857f0d8c155e4a7dcc3610f` during validation
(PR #70: beta 4, release notes and obsolete-site documentation). Its core,
models and 16 noise-policy cases are byte-identical to `84764f58`.
This candidate integrates that new main; no local dependency requirement,
GUI or CLI implementation change is added relative to the latest base.
The applicable guidelines are now v2.1.2; their non-site rules are unchanged.

Fresh local related plus release-notes run: **135 passed in 4.89 s, exit 0**.
The refreshed nine-case public comparison retains the same eight equal
cases and M3-only ninth-case differences. Ruff/format, mypy, documentation,
source safety, schema/API and Qt module checks were refreshed on this base.

Local full-suite status: **NOT PASSED / INCOMPLETE**. Attempt 1 exited 1
without a failure summary or traceback; attempt 2's execution session was
lost with output stopping at 57% and no completion status. No OOM was
recorded; the nearby averaging file independently passed 20 tests in 17.67 s.
No implementation, assertion, skip/xfail or 85% coverage-gate change was
made in response. The first exit's cause remains undetermined.

[Command transcript and failures](pr74-validation.txt) and
[unmodified incomplete verbose stdout](pr74-local-full-incomplete.txt.gz)
retain these attempts. Full pytest and >=85% coverage acceptance remain
pending the exact-head remote CI; they are not inferred from partial runs.
The branch must stay Draft and unmerged.


The beta-4 refresh briefly exposed duplicate beta-3/beta-4 installed metadata
in the task environment (`test_version_matches_pyproject`: b3 != b4).
Removing only the stale generated beta-3 dist-info restored metadata agreement;
the source assertion was unchanged. Refreshed schema/API run: 30 passed,
exit 0. Full-suite and coverage acceptance remain pending remote CI.
