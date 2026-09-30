# Measurement methodology

Every quantity RoomScope reports is listed here with its algorithm source,
unit, computation conditions, validity rule and known limitations. All DSP is
an independent implementation from the cited publications and standards
(see CODE_PROVENANCE.md). Bibliographic details were verified against the
publishers' records on 2026-09-17; items that could only be confirmed through
secondary sources are marked.

## 1. Excitation: exponential sine sweep (ESS)

**Source.** Farina (2000) [1], Farina (2007) [2], Müller & Massarani (2001) [3];
ISO 18233:2006 [11] endorses swept-sine excitation for room acoustics.

**Formula** (`core/sweep.py`). With `L = T / ln(f2/f1)`:

```
x(t) = sin( 2*pi*f1*L * (exp(t/L) - 1) ),    0 <= t < T
f(t) = f1 * exp(t/L)
```

Defaults: 48 kHz, 20 Hz–20 kHz, 10 s, peak −12 dBFS, sin²/cos² fades of
50 ms / 10 ms, 1 s of silence before and 3 s after. Supported sample rates:
44.1, 48, 88.2, 96, 176.4, 192 kHz. The user chooses duration, start/end
frequency, fades, level and silences.

**Why these defaults.** Müller & Massarani recommend short half-cosine fades
to avoid switching noise while keeping ripple < 0.1 dB, and starting below /
ending above the band of interest [3]. Farina (2007) shows most pre-ringing
comes from the fade-out and band limiting [2]; a very short fade-out is a
compromise between his "no fade-out, sweep to Nyquist" advice and DAW
compatibility (a file that ends at Nyquist is resampled unpredictably by
some DAWs). The silence after the sweep captures the decay; the silence
before it is the quiet segment for the noise analysis.

**Level safety.** The default is conservative and RoomScope never changes
system volume. Standalone Mode defaults to −20 dBFS and needs an explicit
acknowledgement above −12 dBFS.

## 2. Inverse filter and deconvolution

**Analytic inverse** (`core/sweep.py::inverse_filter`, Farina [1] §5):
the time-reversed sweep with an amplitude envelope `exp(-t/L)` (−6 dB per
octave), which compensates the −3 dB/octave energy spectrum of the log sweep
[3]. Both inverse filters are scaled so that the *in-band magnitude* of the
sweep convolved with its inverse is 1 (median of `|X(f)·I(f)|` over the inner
part of the excitation band). A perfect loopback therefore has a 0 dB
frequency response. The time-domain peak of the resulting band-limited pulse
is *not* 1: it is roughly `2 · bandwidth / fs` (about 0.82 for the default
48 kHz sweep) and drops further when the direct sound falls between samples.
Levels are read from the frequency response, not from `peak_value`.

**Spectral inverse** (`inverse_filter_spectral` / `design_spectral_inverse`):
when the reference is an arbitrary WAV without a RoomScope sweep definition,
a Kirkeby-type regularised spectral division is used (Farina 2007 [2]
§3.1). `H_inv = conj(X) / (|X|² + β(f))` with a frequency-dependent
`β(f) = P_ref(f) · 10^(b(f)/10)`, where `P_ref(f)` is the pink trend of the
reference and `b(f)` is small inside the estimated excitation band
(`SPECTRAL_REG_IN_BAND_DB`) and large outside it
(`SPECTRAL_REG_OUT_OF_BAND_DB`), with sin² transitions in log frequency.
Same in-band normalisation as the analytic inverse. A constant `β` would
boost the inverse just below `f1` and above `f2`.

**Deconvolution** (`core/deconvolution.py`): full linear convolution of the
whole recording with the inverse filter (FFT). Because the convolution is
zero-padded (linear, not circular), harmonic distortion products of the
loudspeaker land *before* the linear response at `Δt_k = L·ln(k)` for the
k-th harmonic [1][3] and are never wrapped into the IR.

**Impulse-response location.** The direct sound is taken as the strongest
sample of the deconvolved signal. The IR keeps `ir_pre_delay_ms` (5 ms)
before it and up to `ir_max_length_s` (6 s) after it, limited by how much
recording exists after the sweep (`valid_length_s`). The *pre-peak margin*
(dB between the peak and the strongest content in the 0.5 s window ending
2 ms before it) is reported and mapped to a confidence: high ≥ 20 dB,
medium ≥ 10 dB, low otherwise. A low margin means distortion pre-responses,
noise or a wrong reference; findings and reflection notes say so.

**Sample rates.** If the recording's rate differs from the sweep definition,
the reference is regenerated at the recording's rate (this is what the DAW
effectively played) and a warning is recorded. A WAV-only reference is
resampled with `scipy.signal.resample_poly`.

**Limitations.** A strong reflection louder than the direct sound (rare, but
possible with the microphone close to a wall and far from the source) would
be taken as t = 0; the confidence margin does not catch that case. Clock
mismatch between separate playback and recording devices smears high
frequencies [2]; Standalone Mode uses one full-duplex device, Universal DAW
Mode inherits whatever clocking the DAW/interface provides.

**Imported impulse responses** (`analyze_impulse_response`,
`roomscope analyze-ir`). An IR WAV from another tool skips deconvolution,
the sweep-position checks, the distortion indicators and the noise section;
no sweep-pass search is made (a one-sample reference has no passes). The
strongest sample is the direct sound, with the same pre-peak margin as
above except that the excluded stretch before the peak is
max(2 ms, 2 / declared upper band edge), so that the rise of a
band-limited direct sound (a sub-woofer IR low-passed at 80 Hz rises for
~25 ms) is not counted. A file whose peak stands less than 10 dB
(`IMPORTED_IR_MIN_MARGIN_DB`) above the content before it — a sweep
recording, music, noise, or an IR whose direct sound is weaker than a later
arrival, which cannot serve as time zero — is refused rather than analysed.
A file that starts at its peak cannot be checked and is analysed with
confidence "low".
Band metrics are computed only inside an excitation band the caller
declares (`--band LO HI`); without one they are `not_computed`. Fed the
`impulse_response.wav` of a sweep analysis with that analysis's band, the
imported path reproduces its RT60 (±1 %), band T values (±2 %), reflection
delay (±0.05 ms) and level (±0.2 dB) and its resonance candidates
(`tests/integration/test_analyze_ir.py`).

## 2b. Was the sweep played at the speed it was generated at?

A DAW can play the test file at the wrong speed: a file generated at one
sample rate placed in a project at another without conversion (a 48 kHz
sweep in a 44.1 kHz project runs at 91.9 %), or a time-stretch (Warp, Flex
Time, Follow Tempo, elastic audio). Exporting the recording at another rate
than the project ran at is not a cause: the DAW converts on export, and the
reference sweep is regenerated at the recording's rate. The inverse filter of the generated sweep then no longer
collapses the recording to an impulse; the pre-peak margin collapses and all
the pipeline could say before 0.4.1 was that the direct sound is not
identified.

When direct-sound detection confidence is low (a sweep played even 2 % off
leaves a pre-peak margin of a few dB, while a medium margin means the
generated sweep did deconvolve the recording) and the sweep definition is
known, `roomscope.core.playback_speed` measures the sweep rate
in the recording itself. An ESS passes frequency `f` at
`t(f) = L · ln(f / f1)` [1], a straight line of slope `L` against `ln f`.
In a short-time spectrum of the recording (Hann window of about 40 ms, 87.5 %
overlap), each frequency bin between 200 Hz and min(16 kHz, 0.85 · Nyquist)
is loudest in the frame where the sweep passed it — reverberation only adds
later and weaker energy — and bins whose maximum is at least 20 dB above
their median over time are kept. A Theil–Sen line [23, 24] through
`(ln f, t)` of at least 12 such bins spanning at least 1.5 octaves gives the
measured `L'`, and `speed = L / L'`. A speed within the estimate's own
spread of 1 is "as generated": `max(1.25 %, 5.5 % / T^0.75)` for a sweep of
`T` seconds (9.3 % at 0.5 s, 5.5 % at 1 s, 2.4 % at 3 s, 1.6 % at 5 s,
1.25 % from about 9 s). Otherwise, when `speed × generated rate` is within
2.5 % of a common sample rate (22.05 to 192 kHz; ratios between them differ
by at least 8 %), the result names a sample-rate mismatch and the rate the
file was played at, else a time-stretch.

The spread was measured on correctly played sweeps in synthetic rooms (RT60
1–4 s, diffuse level 0.05–0.3, 72 rooms per sweep length): worst case 8.2 %
at 0.5 s, 4.5 % at 1 s, 1.9 % at 3 s, 1.4 % at 5 s and 0.9 % at 10 s, with
either sign; the tolerance stays about 20 % above it
(`tests/integration/test_playback_speed.py`). A smaller stretch is not
named. The estimate is a diagnosis only: it
explains a failed measurement, marks the decay unreliable and is stored in
`impulse_response.playback_speed`, but RoomScope never re-analyses with the
measured speed. Tests: `tests/integration/test_playback_speed.py`.

## 2a. Loopback reference channel

An optional electrical return of the same interface output that drives the
loudspeaker (`core/loopback.py`). Both channels share one converter clock;
nothing here estimates or corrects drift.

**Validation.** The loopback recording is deconvolved with the same inverse
filter as the microphone. The result must be an electrical pulse: high
direct-sound confidence, no clipping, 99 % of the energy after the peak
arriving within `MAX_ELECTRICAL_SETTLE_MS` (10 ms), and the strongest sample
5–80 ms later at least `MIN_LATE_PEAK_DROP_DB` (25 dB) down. The energy is
summed from the peak to the end of the *valid* record (where the
deconvolution still fully overlaps the recording) with the noise power
subtracted from every sample; the noise power is the median of the squared
samples in the last quarter (at least 100 ms, starting no earlier than
200 ms after the peak) of that valid record, divided by 0.4549 (the median
of a χ²₁ variable). Before v0.4.1 the whole record, noise included, was
integrated, so a clean loopback with a long post-roll could be refused
(#12); a first fix that looked only at the first 80 ms let a close
microphone in a live room pass and was replaced before release. What
remains length-dependent is the random fluctuation of the subtracted noise
(it grows with the square root of the record length): on synthetic data a
clean loopback is accepted at a peak-to-noise ratio of 60 dB and more for
post-rolls from 1.5 to 12 s, and starts to be refused at random around
54 dB; real interface loopbacks are normally far cleaner. A channel that
still carries room energy is refused with that reason and the analysis
continues uncompensated (`LoopbackResult.compensation_applied = false`); on
synthetic rooms (RT60 0.3–4 s, weak and strong diffuse tails) the verdicts
are those of 0.4.0. Evidence is synthetic only
(`tests/unit/test_loopback.py`); no hardware loopback has been recorded yet
(HARDWARE_TESTS.md).

**Compensation.** A short FIR around the loopback peak is divided out of
the microphone's deconvolved response by regularised spectral division
`H_room = H_mic · conj(H_lb) / (|H_lb|² + ε(f))`, with the same in-band /
out-of-band regularisation shape as `design_spectral_inverse` (Kirkeby et
al. [22]; Müller & Massarani [3] §"reference measurement"). The FIR is cut
from 5 ms before to 15 ms after the loopback peak, and the peak is its time
origin: the samples before the peak (converter pre-ringing) are placed at
negative time, and the FFT frame is padded by four FIR lengths on each side
of the microphone response so the division is linear, not circular.
Compensation therefore removes the interface *response* without moving the
acoustic time origin: the microphone's direct sound, the reported sweep
start in the recording and the reflection delays stay within one sample of
the uncompensated analysis. (Before v0.4.1 the FIR's first sample was used
as its origin, which advanced the compensated response by the 5 ms pre-roll,
circularly; #12.) On a synthetic interface the
median absolute frequency-response error against the dry room, over the
normalisation band, is required to stay below `COMPENSATION_TOLERANCE_DB`
(1.0 dB). `FrequencyResponseResult.reference` then reads
`relative dB (0 dB = the interface loopback)`.

**Time origin.** `path_delay_ms` is the microphone peak minus the loopback
peak. `distance_upper_bound_m = c · path_delay` is a bound: loudspeaker DSP
latency only adds delay, so the true loudspeaker-to-microphone distance is
at most this value. A tape-measured `placement_distance_m` that exceeds the
bound marks the placement figures unreliable.

## 3. Reverberation: EDT, T20, T30, estimated RT60

**Source.** Schroeder (1965) [4] for backward integration; Lundeby et al.
(1995) [5] for noise truncation and compensation (step list as reproduced by
Karjalainen et al. 2002 [15]); ISO 3382-1:2009 [9] / ISO 3382-2:2008 [10] for
evaluation ranges and the noise margin; Jacobsen & Rindel (1987) [6] for
time-reversed filtering.

**Procedure** (`core/decay.py`):

1. Band filtering: Butterworth band-pass (3 poles per skirt, second-order
   sections) for octave bands 63 Hz–8 kHz (base-2 edges `fc·2^(±1/2)`,
   IEC 61260-1 [12]), applied *time-reversed* so that the filter's own decay
   precedes the room decay. The filters are not certified IEC 61260 class 1.
2. Lundeby truncation (iterative, max 6 passes): 20 ms local averages, noise
   from the last 10 %, regression from the peak to noise + 10 dB, cross-point,
   new interval (5 intervals per 10 dB, clamped 1–50 ms), noise re-estimated
   from 7.5 dB of decay after the cross-point (at least the last 10 %), late
   slope over 15 dB starting 7.5 dB above noise, repeat until the cross-point
   moves < 1 ms. These parameter values are RoomScope's choices within the
   ranges published by Lundeby (10–50 ms; 3–10 intervals/10 dB; 5–10 dB;
   10–20 dB).
3. Schroeder curve: `EDC(t) = Σ_{τ≥t} h²(τ)` from the decay start (peak of the
   smoothed energy) to the truncation point, plus the late-decay
   compensation `C = p(t_c)·(−10 / (slope·ln 10))` (energy of the extrapolated
   exponential tail). Normalised to 0 dB at the start.
4. Least-squares line fits over the ISO 3382-1 ranges and extrapolation to
   60 dB: EDT 0…−10 dB (×6), T20 −5…−25 dB (×3), T30 −5…−35 dB (×2). The
   ISO "degree of non-linearity" `ξ = 1000·(1 − r²)` (‰) is reported.
5. **Validity.** A metric is reported only when the available decay range
   (peak level of the smoothed energy minus the estimated noise floor, in dB)
   is at least `|lower limit| + 10 dB`: 20 dB for EDT, 35 dB for T20, 45 dB
   for T30 (ISO 3382: the evaluation range must lie ≥ 10 dB above the noise
   [9][10], restated by Hak et al. 2012 [17]). Otherwise the metric is
   `insufficient_decay_range` with the numbers in `reason`.
6. **B·T check.** With time-reversed filtering the bandwidth × reverberation
   time product should exceed about 4 (about 16 with forward filtering) [6];
   below 4 the band's metrics are marked `unreliable` and a warning explains
   why. The numbers 16 / 4 are confirmed only through works citing [6].
7. **Estimated RT60** is T30 when valid, else T20, else none; the basis is
   always reported. Curvature `C = 100·(T30/T20 − 1)` % is given when both
   exist.

**Units.** Seconds; the Schroeder curve in dB relative to its start.

**Limitations.** One source and one microphone position do not reach the
ISO 3382-2 *survey* class (Table 1 asks for at least two microphone
positions and two source–microphone combinations). `average_decay` (SHOULD)
spatially averages VALID T values only; see §3a. Very
short decays in low bands are limited by the filters (B·T rule). The
truncation parameters differ from those in other packages (ODEON, ITA
Toolbox), so small systematic differences to other tools are expected [19].

### 3a. Spatial averaging of T values (SHOULD)

**Source.** ISO 3382-2:2008 [10], 4.3.1, Table 1 "Minimum numbers of
positions and measurements" (source–microphone combinations, source
positions and microphone positions for survey / engineering / precision
accuracy), and the rule that one averages *T values*, not decay curves
(ARCHITECTURE.md §5).

**Procedure** (`core/averaging.py`). `average_decay(results)` takes the
arithmetic mean of EDT, T20 and T30 per band over the metrics marked VALID
only, with the count, the spread (max − min) and the contributing session
labels. Decay curves (`edc_db`) are never averaged. The output names the
ISO 3382-2 accuracy class reached by the source positions, microphone
positions and source–microphone combinations; every row of the table must
be met. `roomscope project average` counts one microphone position per
position label of the project (repeated takes at a position add sessions,
not positions; sessions without a position are averaged but not counted),
takes the source count from `--sources` (default 1) and counts at most one
combination per labelled session.

**Table 1** (ISO 3382-2:2008, 4.3.1; read from the standard's own text in
the publisher's preview pages, retrieved 2026-09-24):

| Class | Source–microphone combinations | Source positions | Microphone positions |
| --- | --- | --- | --- |
| survey | 2 | ≥ 1 | ≥ 2 |
| engineering | 6 | ≥ 2 | ≥ 2 |
| precision | 12 | ≥ 2 | ≥ 3 |

Anything below the survey row is labelled `below_survey`. Two footnotes of
the table are not implemented: an engineering result used as a correction
term for other engineering-level measurements needs only one source and
three microphone positions, and the interrupted-noise method may use a
rotating microphone boom. The table's fourth row (decays per position) is
for the interrupted-noise method; RoomScope uses the integrated impulse
response. Before v0.4.1 the code carried an unsourced transcription that
asked for ≥ 3 / ≥ 6 microphone positions for engineering / precision and did
not check the microphone count for engineering, and `project average`
counted sessions as microphone positions (#15).

RoomScope measurements are one source unless the caller passes
`n_source_positions`. The class is a label, not a claim of compliance: the
standard's other clause 4 conditions (distances between positions and from
surfaces, source height and so on) are not checked.
Multi-position *placement* stays out of 1.0 (MEASUREMENT_METHODOLOGY.md §7a).

## 4. Frequency response

**Source.** Standard FFT of the impulse response; fractional-octave
smoothing as power averaging in a `±1/(2n)`-octave window (a common
engineering definition; no standard governs it).

**Procedure** (`core/frequency_response.py`). Optional gating window
`fr_window_s` (default: the whole valid IR, 5 ms half-cosine end taper when
gated); FFT length chosen for ≥ 1 Hz resolution; magnitude in dB relative to
the loopback reference (0 dB = flat). The raw curve is always stored; the
smoothed curve (default 1/6 octave, configurable, 0 = off) is stored
separately and labelled.

**Limitations.** Relative dB only; the absolute gain of loudspeaker, mic and
preamp is included. No phase display in v0.1.

## 5. Background noise

**Source.** AES17-2020 [18] for the dBFS definition (0 dBFS = RMS of a
full-scale sine); Welch (1967) for the PSD estimate.

**Procedure** (`core/noise.py`). Quiet segment = recording from 50 ms after
the start to 100 ms before the detected sweep start (≥ 0.5 s), else the file
tail 3 s after the sweep end (flagged as possibly containing reverberation),
else none. Reported: RMS in dBFS (sine reference), peak dBFS, octave-band RMS
levels (zero-phase filtered), Welch PSD (Hann, 2 Hz resolution), and mains
hum candidates: for 50 Hz and 60 Hz, harmonics up to 1 kHz whose PSD peak
(±2 Hz) exceeds the median of the ±15 % neighbourhood by ≥ 10 dB; "detected"
means ≥ 2 such harmonics.

**Units.** dBFS and dB re FS²/Hz. **Never dB SPL** without calibration, which
v0.1 does not support.

**Limitations.** The pre-sweep segment is only as quiet as the DAW routing
allows (e.g. monitor bleed); the hum thresholds are engineering choices.

## 6. Early reflections

**Source.** Energy-time-curve inspection after Heyser (1971) [16]; onset
detection considerations from Defrance et al. (2008) and Usher (2010).

**Procedure** (`core/reflections.py`). Hilbert envelope with a 0.1 ms
peak-hold, expressed in dB relative to the direct sound; a 6 ms moving
average of the dB envelope models the local diffuse level; peaks between
0.8 ms and 80 ms after the direct sound, above −20 dB re direct and at least
6 dB above the local trend, are reported as candidates `(delay_ms,
relative_db)`.

**Limitations.** Candidates, not identified surfaces. In a dense early
diffuse tail some candidates are statistical. Delays are relative to the
detected direct sound (see confidence above).

## 7. Potential low-frequency resonances

**Source.** Decay-time-versus-frequency reasoning after Karjalainen et al.
(2002) [15] and Mäkivirta et al. (2003); no standard exists. The related
Genelec patent US 7,742,607 expired in 2022 (see §10).

**Procedure** (`core/resonance.py`). Below 300 Hz, peaks of the 1/24-octave
smoothed response that stand ≥ 6 dB above the 1-octave smoothed baseline are
candidates. For each, a 1/3-octave band-pass (2 poles per skirt,
time-reversed) is applied and the time for the band envelope to fall 20 dB
is compared with the same measure for the filter alone; the decay is called
distinguishable only when it is ≥ 2× the filter ringing.

**Limitations.** "Potential resonance" only. Identifying a room mode needs
room dimensions and several positions; RoomScope does not claim it.

## 7a. Placement geometry

**Source.** The image-source construction for a plane reflector is standard
(Allen & Berkley 1979 [20] is the canonical *forward* method). The identity
used here is elementary algebra from it and was implemented clean-room; no
code was taken from any image-source library (see `docs/CODE_PROVENANCE.md`).
The published route to *full* room geometry from echoes — room-shape-from-
echoes / echo sorting, Dokmanić et al. (2013) [21] and the echo-labelling
work following it — requires a microphone array or several positions and is
deliberately **not** implemented (§9).

**What is identifiable.** With `s` and `r` the perpendicular distances of
loudspeaker and microphone from a plane, `d` their straight-line separation,
`u = s + r` and `v = s − r`, a first-order arrival of excess path `c·δ` gives

    L² − d² = u² − v² = 4·s·r ,   so   P := s·r = c·δ·(2d + c·δ)/4

exactly, with no assumption about room shape. Four independent arrival
equations constrain six unknowns: the deficit is **three** without a measured
`d` and **two** with it. The residual freedom is exactly the *direction* of
the loudspeaker-to-microphone vector, and every direction reproduces the
measured arrival times, so no coordinate, room length, room width or wall
distance is derivable from one omnidirectional microphone at one position.
The rank of the observation map is asserted in
`tests/unit/test_placement.py::test_single_position_identifiability_is_what_the_docstring_claims`
rather than only stated here.

**Procedure** (`core/placement.py`), one code path degrading by tier:

* **Tier 0** (temperature only): each candidate's excess path in metres,
  `c = 331.3·√(1 + T/273.15)` (343.2 m/s at 20 °C; numerically the ISO 9613-1
  form). 20 °C is assumed when none is given, and `temperature_assumed`
  records that it was.
* **Tier 1** (`--speaker-distance`): per candidate `P`, its square root
  `√P` — the geometric mean of the two perpendicular distances, so the nearer
  of the pair is at most `√P` and the farther at least `√P` — the exact
  two-sided bracket `[√P, L/2]` on their *arithmetic* mean, and the specular
  ceiling `20·log₁₀(d/L)`.
* **Tier 2** (`--mic-height`): `s = P/h`, the plane above both devices
  `H = (u + √(L_upper² − d² + v²))/2`, and `q = √(d² − v²)`.

The tier-2 question is phrased as *the first solid horizontal surface below
the microphone* — the desk top at a desk, otherwise the floor. That dissolves
the desk-versus-floor ambiguity by definition; no acoustic evidence from one
omnidirectional microphone could resolve it.

**Thresholds by tier of justification.** Tier 1, no free choice: the specular
ceiling. Tier 2, physical plausibility deliberately wide: loudspeaker
0.10–3.00 m, plane above 1.80–6.00 m with 0.30 m clearance. Tier 3,
RoomScope engineering choices calibrated against synthetic arrivals, not
standards: `MAX_SURFACE_ATTENUATION_DB = 12`,
`SPECULAR_EXCESS_TOLERANCE_DB = 2`, `HEIGHT_AGREEMENT_M = 0.08`,
`CEILING_AGREEMENT_M = 0.12`, `MAX_HYPOTHESIS_CANDIDATES = 8`.

The level screen is **tier 3, not geometry**: it assumes a point source in a
free field, an infinite rigid plane, and that a broadband peak-held envelope
peak may be compared with an on-axis level. It is used only to *withhold* an
attribution, never to assert what an arrival is.

**Refusals.** Unique-or-refuse throughout: when two arrivals both survive the
gates and disagree by more than the agreement threshold, every competing value
is listed and none is chosen — picking the earliest is wrong exactly in the
commonest setup (a desk edge arrives before the desk top) and picking the
loudest is wrong whenever the lower plane is carpeted. Nothing at all is
reported when direct-sound confidence is not `high`, because every delay is
measured from that origin.

**Limitations.** The reported `input_uncertainty_m` propagates the stated
tape, temperature and peak-location uncertainties **only**; model error
(flatness, rigidity, first-order specularity, and the user having measured to
a different plane than the one that reflected) is excluded and is usually
larger. The reflection search resolves arrivals no closer than 0.3 ms, so a
microphone near the vertical midpoint of a room produces one merged peak
instead of a floor and a ceiling arrival; when no separate upper plane is
found and a plausible one would have merged with the arrival used, the height
is marked `unreliable` and the user is told to move the microphone 20–30 cm
and measure again. A truncated search window does not drop arrivals at
random — it drops the longest paths first — so any height derived from what
remains is biased low, and that is stated rather than implied.

## 8. Interpretation layer

Findings are produced from the result by a recording profile
(`interpretation/profiles.py`), never by the DSP. The interface is fixed in
v0.1 so profiles can be added without touching the DSP; every profile shares
the measurement-integrity checks — low direct-sound confidence, clipping,
insufficient decay range — and the low-band / mid-band imbalance rule
(low bands decaying > 1.5× slower than mid bands), and keeps its own
thresholds and wording for reflections, decay, noise and resonances.
Thresholds are coarse engineering choices and are stated in each finding's
evidence.

The seven profiles and their section thresholds:

| Profile | Reflection (≥ dB re direct, ≤ ms) | RT60 notice / warning (s) | Notes |
| --- | --- | --- | --- |
| generic | −10 / 30 | 0.6 / 1.0 | Default; any close-miked recording |
| vocal | −12 / 25 | 0.5 / 0.8 | Close-miked lead or backing vocals; noise advice assumes compression |
| voiceover | −14 / 20 | 0.4 / 0.7 | Voice-over, narration, audiobook; flags the weakest reflections |
| acoustic_guitar | −10 / 30 | 0.7 / 1.1 | Comb filtering from early reflections |
| drums | −6 / 20 | 0.8 / 1.2 | Only a hard slap is reported; noise findings skipped (the kit masks the floor) |
| room_mic | −5 / 40 | 0.9 / 1.4 | The room is the instrument; long decay is not automatically a defect |
| choir | −12 / 30 | 0.8 / 1.3 | Ensembles: decay helps ambience but blurs diction |

The default is `generic`; `roomscope analyze --profile vocal` and the GUI
profile selector pick another. The report prints the profile name
(`Interpretation (vocal profile):`) so the advice is never mistaken for
room-agnostic truth.

## 9. Things RoomScope deliberately does not do

No room score, no auto-EQ or correction, no dB SPL without calibration, no
room-mode identification, no plug-in hosting. Spatial averaging of T values
is offered as a SHOULD (`average_decay`); it never averages decay curves.

No room geometry beyond the vertical axis of §7a: no coordinates, no room
length or width, and no wall is ever named. The published method for the full
problem — room shape from echoes / echo sorting, Dokmanić et al. (2013) [21] —
needs a microphone array or several measurement positions, which RoomScope
does not require of its users. Two microphone positions with a fixed
loudspeaker would be *exactly* determined (twelve equations, twelve unknowns),
which means a zero residual would prove nothing about whether the surfaces
were assigned correctly; any future multi-position support must therefore ship
with a redundant third position, not with two.

## 10. Patents

A Google Patents search (2026-09-17, not a legal opinion) found no in-force
patent claiming ESS generation with inverse-filter deconvolution, Schroeder
integration, ISO 3382 evaluation, ETC-based reflection detection or
decay-versus-frequency resonance detection as such; these methods are
published 1965–2003 prior art. Two in-force patents to stay clear of by
design: US 9,959,883 B2 (automatic two-sweep pass-band scheme) and
US 10,816,391 B2 (clock-drift correction between unsynchronised emitter and
receiver devices). Room-*correction* filter design is densely patented
(Dirac, Sonarworks, Audyssey/Sound United, DTS, Harman); RoomScope measures
and reports only.

## 11. Comparing two sessions

`roomscope.core.compare.compare` takes two `AnalysisResult` objects and
returns a `ComparisonResult`. It is a pure function: it never changes either
result. Findings are re-derived by `interpret_comparison` and are not stored
as truth.

Comparability. The common excitation band is the intersection of both
`excitation_band` ranges. Sample rates may differ. Different sweep durations
or levels are allowed and noted. The pair is refused when the common band is
narrower than one octave (`CompareSettings.min_common_band_octaves`, default
1.0).

Decay. A delta exists only when *both* metrics are VALID; otherwise the
delta is `not_comparable` and carries both reasons. A band that exists on
one side only is listed as `not_comparable` ("band missing from the
candidate" / "... from the baseline"), whichever side lacks it. The report
quotes the
just-noticeable difference for T that ISO 3382-1 gives (about 5 %; clause
not verified against the standard text) and never calls a change
"significant" on its own: single-position repeatability is not established
by one pair.

Frequency response. Each raw magnitude curve is first smoothed on its own
(linear, sub-hertz) frequency grid with the coarser of the two
`smoothing_fraction` values — or, when neither result was smoothed, over
one step of the comparison grid (1/24 octave by default) — and only then
sampled on a shared logarithmic grid (`log_grid_points_per_octave`, 24)
inside the common band. The order matters: sampling the raw spectrum first
point-samples its comb-filter ripple (the grid step is ~300 Hz at 10 kHz),
so two takes of the same room would differ by several dB of sampling noise
(v0.4.0 did this; #9). The difference curve is candidate minus baseline.
Mean absolute difference is reported per IEC 61260-1 octave band that
overlaps the common range. On synthetic rooms that differ only in the
random diffuse tail, the 4 / 8 / 16 kHz octave MADs are below 1.2 / 1.0 /
0.6 dB (they were about 3 dB before), and a linear-phase +6.02 dB shelf is
recovered within 0.3 dB (`tests/unit/test_compare.py`).

Early reflections. Matched by delay within ±0.5 ms
(`CompareSettings.reflection_match_ms`). Unmatched arrivals are listed as
appeared or disappeared. Both sides must have high direct-sound confidence.

Noise. RMS and band deltas are VALID only if both sessions have a verified
quiet segment *and* the caller declares the input gain unchanged
(`CompareSettings.same_input_gain`). Otherwise the delta is UNRELIABLE with
the reason "gain not declared equal".

Resonances. Matched within 1/6 octave
(`CompareSettings.resonance_match_octaves`). The decay-distinguishable flags
are compared, not a decay-time delta.

Placement. Tier-2 heights are compared when both results are tier 2;
otherwise the placement deltas are `not_comparable`.

Loopback. `path_delay_ms` is compared only when both results applied
loopback compensation.

## References

1. A. Farina, "Simultaneous Measurement of Impulse Response and Distortion with a Swept-Sine Technique," AES 108th Convention, Paris, 2000, preprint 5093. (confirmed, primary text)
2. A. Farina, "Advancements in Impulse Response Measurements by Sine Sweeps," AES 122nd Convention, Vienna, 2007, paper 7121. (confirmed, primary text)
3. S. Müller, P. Massarani, "Transfer-Function Measurement with Sweeps," J. Audio Eng. Soc. 49(6), 443–471, 2001. (confirmed)
4. M. R. Schroeder, "New Method of Measuring Reverberation Time," J. Acoust. Soc. Am. 37(3), 409–412, 1965. doi:10.1121/1.1909343 (confirmed)
5. A. Lundeby, T. E. Vigran, H. Bietz, M. Vorländer, "Uncertainties of Measurements in Room Acoustics," Acustica 81(4), 344–355, 1995. (confirmed via secondary sources; algorithm as summarised in [15])
6. F. Jacobsen, J. H. Rindel, "Time reversed decay measurements," J. Sound Vib. 117(1), 187–190, 1987. doi:10.1016/0022-460X(87)90444-5; F. Jacobsen, "A note on acoustic decay measurements," J. Sound Vib. 115(1), 163–170, 1987. (bibliography confirmed; B·T limits confirmed only through citing works)
7. G.-B. Stan, J.-J. Embrechts, D. Archambeau, "Comparison of Different Impulse Response Measurement Techniques," J. Audio Eng. Soc. 50(4), 249–262, 2002. (confirmed)
8. A. Novak, P. Lotton, L. Simon, "Synchronized Swept-Sine: Theory, Application, and Implementation," J. Audio Eng. Soc. 63(10), 786–798, 2015. doi:10.17743/jaes.2015.0071 (confirmed)
9. ISO 3382-1:2009, Acoustics — Measurement of room acoustic parameters — Part 1: Performance spaces. (confirmed; clause numbers not read from the standard text)
10. ISO 3382-2:2008 + Cor 1:2009, Part 2: Reverberation time in ordinary rooms. (confirmed; 4.3.1 Table 1 read from the standard's preview pages, https://cdn.standards.iteh.ai/samples/36201/4a4d0dc848ac4d40bfe46e36c531afb5/ISO-3382-2-2008.pdf, on 2026-09-24; the rest of the text was not read)
11. ISO 18233:2006, Acoustics — Application of new measurement methods in building and room acoustics. (confirmed)
12. IEC 61260-1:2014 / ANSI/ASA S1.11-2014/Part 1, Electroacoustics — Octave-band and fractional-octave-band filters — Part 1: Specifications. (confirmed)
15. M. Karjalainen, P. Antsalo, A. Mäkivirta, T. Peltonen, V. Välimäki, "Estimation of Modal Decay Parameters from Noisy Response Measurements," J. Audio Eng. Soc. 50(11), 867–878, 2002. (confirmed)
16. R. C. Heyser, "Determination of Loudspeaker Signal Arrival Times, Parts I–III," J. Audio Eng. Soc. 19(9–11), 1971. (confirmed)
17. C. C. J. M. Hak, R. H. C. Wenmaekers, L. C. J. van Luxemburg, "Measuring Room Impulse Responses: Impact of the Decay Range on Derived Room Acoustic Parameters," Acta Acustica united with Acustica 98(6), 907–915, 2012. doi:10.3813/AAA.918574 (confirmed)
18. AES17-2020, AES standard method for digital audio engineering — Measurement of digital audio equipment. (confirmed via AES publications; defines 0 dB FS as the RMS of a full-scale sine)
19. D. Cabrera, J. Xun, M. Guski, "Calculating Reverberation Time from Impulse Responses: A Comparison of Software Implementations," Acoustics Australia 44(2), 369–378, 2016. doi:10.1007/s40857-016-0055-6 (confirmed)
20. J. B. Allen and D. A. Berkley, "Image method for efficiently simulating small-room acoustics," J. Acoust. Soc. Am. 65(4), 943-950, 1979. (confirmed, primary text) — forward image-source model; cited as the origin of the construction, not as a method for the inverse problem. (Numbered [17] before v0.4.1, which collided with Hak et al.)
21. I. Dokmanić, R. Parhizkar, A. Walther, Y. M. Lu and M. Vetterli, "Acoustic echoes reveal room shape," PNAS 110(30), 12186-12191, 2013. (confirmed, primary text) — the canonical published route to full room geometry from echoes; named here because RoomScope declines it, see §9. (Numbered [18] before v0.4.1, which collided with AES17.)
22. O. Kirkeby, P. A. Nelson, H. Hamada and F. Orduña-Bustamante, "Fast deconvolution of multichannel systems using regularization," IEEE Trans. Speech and Audio Processing 6(2), 189–194, 1998. (bibliographic record; the regularised-inversion form `conj(H) / (|H|² + ε(f))` used in §2 and §2a is the one Farina 2007 [2] §3.1 quotes from it; the primary text was not re-read for v0.4.1)
23. H. Theil, "A rank-invariant method of linear and polynomial regression analysis," Proc. Koninklijke Nederlandse Akademie van Wetenschappen 53, 386–392, 521–525, 1397–1412, 1950. (bibliographic record; used through `scipy.stats.theilslopes`)
24. P. K. Sen, "Estimates of the regression coefficient based on Kendall's tau," J. Am. Stat. Assoc. 63(324), 1379–1389, 1968. (bibliographic record; used through `scipy.stats.theilslopes`)

Additional supporting references (A. Mäkivirta et al. 2003; G. Defrance et
al. 2008; J. Usher 2010; M. Guski & M. Vorländer 2014; C. L. Christensen et
al. 2013) are listed with their confirmation status in
`docs/research/literature.md`.
