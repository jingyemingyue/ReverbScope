# Align the research integration with main's noise policy

This decision follows GUIDELINES.zh-CN.md §2.4, §3 D11, §4 C12/C16 and §6.
Status: draft integration candidate; not approval to merge PR #74.

## Baselines and decision

Remote main `ab3da19618a066460857f0d8c155e4a7dcc3610f` contains PR #72
and PR #88 (`5582943a1a72d05bf6a0a31c5a74ce479f202f91`). The research
head is PR #74 `ebc145752e3851c3d11150dc495634992174a79c`.
This independent branch integrates that head into main without writing to
`feat/all-algorithm-methods`.

Resolve only the conflicting default noise policy: both `schroeder_curve`
and `_curve_from_truncation` default to `subtract_noise=False`, and
`DECAY_METHOD` and the public docstring match main. Preserve PR #74's
existing finite-floor, no-problem, strictly `>40.0` dB condition verbatim.
There is no second guard implementation or changed validity threshold.
ADR 0003's known noiseless 0.8 s decay motivates this policy; convergence
and a large range cannot distinguish late signal from noise.

## Audit of default public paths relative to main

| Path | Integration difference and rationale |
| --- | --- |
| `schroeder_curve`, `analyze_band`, decay sensitivity | Same defaults, integration, compensation and reported method as main. The equivalent guard is flattened in #74; opt-in output is covered by exact energy-sum tests. |
| `generate_ess`, `measurement_signal`, inverse filters | Existing functions unchanged. M1 pre-emphasis and M2 synchronization are separate explicit calls, not selected by the pipeline. |
| `analyze_impulse_response` | No sweep-rate harmonic windows; unchanged default analysis path. Known-answer and snapshot comparisons cover this entry point. |
| `locate_impulse_response` | #74 adds `suppress_harmonics=True`: intersecting harmonic windows are zeroed in the retained IR; main retains those samples. Preserve the research proposal in this candidate, with a regression explicitly exposing the difference. This is a remaining review decision, not default parity. |
| `analyze` with settings/reference metadata | Reaches that harmonic-window default; downstream IR, plots, saved waveform, placement or reflections can therefore differ. Harmonic levels use original `h_full`; margin and location precede cleaning. Long sweeps can conceal the difference when windows fall outside pre-roll. |
| `analyze` with an audio-only reference | A plain audio-only reference is prepared with `sweep_rate_s=None`; no harmonic windows are produced and this path is unchanged. |
| M4 selection, M6 model truncation, M7 NLS/BIC, M8 modal API | Added opt-in functions only; existing pass selection, Lundeby estimator, result format, GUI and CLI selection are unchanged. |

The remaining harmonic default is documented rather than silently disabled
or generalized into a refactor. This candidate cannot be described as fully
main-equivalent, or as accepting M3 accuracy. It retains all experimental
methods for separate review.

For a 0.5 s synthetic sweep with 100 ms pre-roll, the public `analyze`
snapshot differs from main in `placement.candidates` and
`reflections.reflections`; all other serialized fields, including decay,
match. Decay uses the original `h_full` through `_analyze_decay_of_pass`;
this integration does not silently replace that input with the cleaned IR.

## Evidence and remaining blockers

Main's 16 noise-policy cases are inherited without weaker assertions.
Additional tests pin both signature defaults, public IR analysis versus an
explicitly unsubtracted builder, and the precise samples affected by M3.
[Validation record](../research/pr74-default-policy-validation.md) records
snapshot comparisons and the actual commands/results.

The separate [deferred probes](https://github.com/jingyemingyue/ReverbScope/blob/67643f0d5c9324cf59c9848a89da02a2b47b3a88/docs/research/pr74_deferred_probes.py) are
executable strict acceptance tests outside pytest's existing `tests/`
testpaths. Run them explicitly; they intentionally fail on the unchanged
M2/M8 implementation. They are new evidence, not existing tests moved out
of the suite; no skip, xfail, collection setting or coverage gate changed.
M2 phase synchronization and M8 weighted modal recovery remain blockers to
algorithm acceptance. General noisy-room accuracy, native platforms,
hardware, DAWs and standards compliance remain unverified.
