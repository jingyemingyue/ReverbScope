# Optional local decay model

The experimental decay fitter estimates one or two exponential components
and a stationary noise floor from an impulse response's block-averaged
squared amplitude. A small bundled neural model can supply starting values
for the physical fit. It runs locally on the CPU with NumPy; it needs no
LLM, cloud service, GPU, extra inference framework or downloaded weights.

This is a separate result alongside the existing EDT, T20, T30 and
estimated RT60. It does not change those measurements or turn an invalid
ISO-range result into a valid one. A component's 60 dB decay time is a
parameter of the fitted exponential, not another name for a measured T30.

## Choose a mode

`--decay-fit` accepts three modes:

| Mode | Behaviour |
| --- | --- |
| `off` | Default. Keep the existing analysis without the experimental fit. |
| `physical` | Use deterministic starting values for the constrained physical fit. |
| `neural` | Add starting values from the bundled small neural model before the same physical fit. |

For an existing **synthetic** IR WAV, use the same declared excitation band
for both modes. Imported WAV analysis does not open an audio device:

```bash
roomscope --backend fake analyze-ir --ir synthetic-room.wav --band 20 20000 --decay-fit physical --out decay-physical
roomscope --backend fake analyze-ir --ir synthetic-room.wav --band 20 20000 --decay-fit neural --out decay-neural
```

`synthetic-room.wav` must exist before these commands run. The `fake`
backend is explicit so the examples remain suitable for offline
validation. Declaring a band describes the input; it does not establish
that the WAV contains useful energy throughout that band.

## What is fitted

The expected squared response is

```text
p(t) = N + sum_i A_i * exp(-k*t/T_i),   k = 6*ln(10)
```

Here `N` is stationary noise power, `A_i` is a non-negative component
amplitude, and `T_i` is its positive 60 dB energy-decay time in seconds.
The prediction is averaged over each complete analysis block before
comparison with measured block power. Evaluating only the block centre
would bias its instantaneous component amplitudes when the time constant
is comparable to the block width. Free fitted amplitudes can absorb that
factor, so this alone does not imply a bias in the fitted time constants.

One-component and two-component candidates are fitted with physical
constraints. Residual error and a BIC-based heuristic help choose the
candidate; BIC is not a calibrated probability that the room has two
physical decay processes. Adjacent blocks of a filtered response can be
correlated, so the usual independent-observation interpretation is only
an approximation.

For nearly exact fits, the residual variance used only by BIC has a
data-scaled floating-point resolution floor. This prevents solver and
rounding differences from inventing evidence for a second component.
Reported residuals and conditional standard deviations retain their
actual values.

The reported uncertainty is conditional on the selected model and its
noise assumptions. It is not an uncertainty budget for microphone
calibration, source position, room variability, filtering, or departures
from exponential decay. Very similar time constants, a weak second
component or a component hidden below the floor can be unidentifiable
even when the curve residual is small.

This fit uses **raw block power**. The finite-window energy-decay-function
formula in the DecayFitNet paper applies after backward integration and
contains a terminal exponential correction and a linear noise term. That
formula is not used here, and the fitter does not reinterpret the existing
Lundeby-truncated, compensated Schroeder curve as raw data.

## The bundled neural model

The independently implemented network has 64 inputs, one hidden layer of
32 units and 5 outputs: **2,245 weights and biases** in total. Its outputs
provide initial estimates for the fast and slow times, their amplitudes,
and stationary noise power. The physical optimizer produces the reported
parameters; the network prediction alone is never presented as a
measurement.

The shipped [JSON artifact](../src/roomscope/model_data/decay_initializer_v1.json)
is `roomscope-decay-initializer-v1`, **51,257 bytes**, with SHA-256:

```text
2ba0004247ce90ff70e92fb0e97ae14f59d12d92e6029732224c853fecc12234
```

Training uses the project's own analytic synthetic block-power curves and
Gaussian noise. The model artifact contains JSON arrays and metadata;
inference does not deserialize executable objects. Results record the
model identity, parameter count and artifact SHA-256 so another run can
identify the weights used. No third-party source, pretrained model or
measured dataset was imported.

Git preserves LF line endings for the model JSON on every platform, and
the wheel test checks the documented hash so Windows checkout conversion
cannot silently change the artifact fingerprint.

Synthetic training and held-out tests establish behaviour within the
generated examples. They do not establish the real-room performance
reported for the original DecayFitNet, which uses a different, much larger
network and measured evaluation datasets.

The artifact's training domain is dimensionless: times are divided by
the duration of the blocks presented to the model, and powers by the
first observed block. It covers the following generated examples:

| Synthetic variable | Training range |
| --- | --- |
| Fast time / duration | 0.025–0.5 |
| Slow time / duration | 0.10–2.0, with slow / fast between 1.8 and 10 |
| Slow / fast instantaneous power | 0.001–1.0 |
| Stationary noise / fast instantaneous power | 1e-9–0.01 |
| Block count | 32, 64, 96, 128 or 192 |
| Independent Gaussian degrees per block | 32–5,000 |

The pressure model is zero-mean Gaussian. Block power fluctuations use
the corresponding chi-square distribution; this does not simulate
measured rooms, coherent echoes, correlated modal tails or transient noise.
Input features interpolate block-centre log powers to 64 points and clip
them to −100…0 dB. The physical optimizer and its deterministic starting
values remain necessary outside the synthetic model's useful range.

## Read the result and its failures

The result JSON stores this analysis separately as
`decay.broadband.multi_decay` and each band's `multi_decay`. Inspect its
validity and reason before using component times, conditional standard
deviations, residual diagnostics or model-selection information. `off`
omits the optional result.

Each component records `rt60_s`, `relative_power` and `rt60_std_s`;
the fit records `noise_relative_power`, `residual_rms_db`,
`bic_difference`, `fit_start_s`, `fit_end_s`, `initializer`,
`initializer_model`, `initializer_parameters`, `initializer_sha256`,
`validity` and `reason`. The standard deviations are local least-squares
estimates conditional on this model, not calibrated confidence intervals.
Component relative powers sum to one after excluding noise;
`noise_relative_power` is relative to the first observed block. The fit
interval is measured from the existing direct-sound time origin.
`initializer: "neural"` means a valid neural starting value participated
alongside the deterministic starting values. It does not say which
starting value led to the selected optimum; a physical starting value can
produce the winning fit.

Insufficient decay range, excessive or unsuitable noise, an unidentified
component, or a failed physical fit must remain a failed or unreliable
result with a stated reason. A small residual cannot certify a useful
parameter, and a fitted second component is not evidence of a particular
room mode, surface, material or coupled room. Unknown excitation of an
imported IR yields `not_computed`; outside-band values are not fitted.
Clipping, untrusted direct-sound detection, wrong playback speed and other
measurement-integrity failures propagate to this separate result too.
The fitter needs at least 12 complete power blocks and 15 dB of observed
early-to-late decline. Each accepted component must remain at least 10 dB
above the floor and contribute at least 0.2 times the other components
over four or more blocks spanning at least 10 dB of its decay. Two times
must be separated by a factor of at least 1.5. The local time standard
deviation must be no more than 25% of the time, and singular parameters
are rejected. The 1.5 dB RMS residual cutoff and BIC-difference threshold
of 10 are engineering heuristics, not probabilities.

When BIC favours two components but their parameters cannot be resolved,
the result is withheld with a reason. It does not substitute a biased
single-component answer. If the local artifact cannot be
loaded or is incompatible, `neural` falls back to physical starting values
and records that reason; it does not fetch replacement weights.

## Reproduce training and run the synthetic benchmark

From a checkout installed into the active Python environment, regenerate
the model to a separate file for review:

```bash
OPENBLAS_NUM_THREADS=1 python scripts/train_decay_model.py --out regenerated-decay-initializer.json --samples 12000 --epochs 120 --seed 20261004
python scripts/benchmark_decay_model.py --out decay-benchmark.json
```

The first command uses minibatch Adam to train the 2,245-parameter network
from synthetic data with seed `20261004`. It evaluates the raw initializer
on 1,000 newly generated examples with seed `20261005`, then prints the
artifact SHA-256 and raw prediction errors. Those errors describe starting
values before physical optimization. Normalization statistics are stored
alongside the network weights in the JSON artifact.

The benchmark evaluates the physical and neural-assisted fitting modes
using the packaged artifact
`src/roomscope/model_data/decay_initializer_v1.json`. Writing a regenerated
file elsewhere does not silently replace that artifact. Read the benchmark
dataset description, validity and rejection counts alongside parameter
errors and timings; do not treat a CPU timing or a passing synthetic fit
as measured-room accuracy.

To check deployment inside an installed CLI or a frozen bundle, run
`python scripts/smoke_decay_model.py --roomscope /path/to/roomscope --out /tmp/decay-model-smoke`.
The check generates a known synthetic IR, runs `analyze-ir` with neural
initialization, checks the two component times and saved JSON, and compares
the model fingerprint with the checkout artifact. The Release workflow runs
this check inside both Desktop and Terminal bundles on every build platform.
Nothing is played or recorded from a physical device.

## Recorded synthetic results

The shipped model's 1,000 held-out generator examples (seed `20261005`)
give these **raw initial-value errors, before physical fitting**:

| Raw neural prediction | Median error | 90th-percentile error |
| --- | --- | --- |
| Fast component time, absolute relative error | 17.86% | 54.09% |
| Slow component time, absolute relative error | 9.08% | 38.02% |
| Stationary noise power, absolute dB error | 1.165 dB | Not recorded |

These time errors are too large to treat the raw predictions as reported
measurements. They are preserved in the artifact's
`held_out_initializer_evaluation` metadata.

A benchmark run on 2026-10-04 used the artifact hash above and 60
independently sampled Gaussian IR cases at 8 kHz, with generator seed
`20263004`. It includes single time constants 0.2, 0.4, 0.8 and 1.2 s;
fast/slow pairs 0.2/1.1, 0.35/2.0 and 0.6/3.2 s; weak slow-component
powers −12 and −25 dB; stationary noise powers −75 and −60 dB; and three
replicates per configuration. These are synthetic pressure responses,
rather than the analytic chi-square power blocks used for training.

| Final physical fit | `physical` | `neural` |
| --- | --- | --- |
| Accepted with correct component count | 56 / 60 | 56 / 60 |
| Withheld | 4 / 60 | 4 / 60 |
| Accepted with wrong component count | 0 | 0 |
| Accepted-component median relative time error | 0.485% | 0.485% |
| Accepted-component 95th-percentile relative time error | 5.668% | 5.668% |
| Total fit time for 60 cases on this machine | 1.18 s | 1.79 s |

Parameter-error statistics include accepted cases with the correct
component count; withheld cases are not counted as accurate. These
results demonstrate **no accuracy or speed benefit from neural
initialization on this benchmark**. Neural initialization remains an
optional research aid. The new physical capability is the separate
two-component decomposition. Timings are specific to this development
machine and workload.

Four additional negative cases verify withholding: silence, stationary
noise and increasing power yield `insufficient_decay_range`; a noise
floor that changes halfway through the response yields `unreliable`
because the exponential model's residual is 16.84 dB RMS. These cases are
recorded separately from the 60-case parameter benchmark.

## Validation and real hardware still pending

Automated validation uses analytic synthetic curves, stochastic synthetic
responses, fake backends and existing repository fixtures. It checks
parameter recovery, fit selection, input validation, model metadata and
serialization while keeping the established ISO metrics separate. Record
benchmark results from the exact generated dataset and model artifact;
do not infer accuracy from the architecture or from another project's
paper.

Still pending are real-room recordings across source and microphone
positions, repeatability against a reference measurement, real noise and
transient artefacts, and narrow-band modal decays. Audio interfaces,
microphones, loudspeakers, gain, clipping and clocking also require actual
hardware checks. No sound card or lidar is required for the automated
work, and the [hardware matrix](HARDWARE_TESTS.md) remains unchanged.

## References and implementation provenance

The conceptual reference is Götz, Falcón Pérez, Schlecht and Pulkki,
[*Neural network for multi-exponential sound energy decay analysis*,
JASA 152(2), 942–953 (2022)](https://doi.org/10.1121/10.0013416), also
available as [arXiv:2205.09644](https://arxiv.org/abs/2205.09644).
[DecayFitNet](https://github.com/georg-goetz/DecayFitNet/tree/01daf3e7bbfd637aa1269bbca0cab7f445db0d5d)
was reviewed at commit `01daf3e7bbfd637aa1269bbca0cab7f445db0d5d` (MIT).
Its approximately 677,000-parameter network was neither copied nor loaded.
The idea borrowed is synthetic training for parametric decay estimation;
our architecture, data generator, weights and implementation are independent.

[pyrato](https://github.com/pyfar/pyrato/tree/034c8604d4d94915e72cf9091e790d6c1dd64580)
and
[pyroomacoustics](https://github.com/LCAV/pyroomacoustics/tree/ff7d61f219e4eb41489963c4bb5f57bea5bc2c69)
were reviewed through repository metadata, README, LICENSE and
documentation only. Neither is an added dependency. The pinned versions,
license-review limits and inspected materials are recorded in
[THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md); independent implementation
and weight provenance are recorded in [CODE_PROVENANCE.md](CODE_PROVENANCE.md).
See [measurement methodology](MEASUREMENT_METHODOLOGY.md) for the formula
and its relationship to the existing analysis.
