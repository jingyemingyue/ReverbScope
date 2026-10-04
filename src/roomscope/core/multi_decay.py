"""Experimental one/two-exponential energy fits, separate from ISO RT metrics.

The model is block-averaged ``sum(A * exp(-6*ln(10)*t/T)) + N``. A small
local network may supply optimizer starting values; the measured power and
the same constrained physical fit decide the result in either mode. These
component times are not EDT/T20/T30 and never repair an invalid ISO metric.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from roomscope.models.audio import FloatArray
from roomscope.models.result import DecayComponent, MultiDecayFit, Validity

METHOD = "experimental block-power exponential-mixture fit (one or two components)"
_DECAY = 6.0 * np.log(10.0)
_MAX_BLOCKS = 128
_MIN_BLOCKS = 12
_MIN_RANGE_DB = 15.0
_MAX_RESIDUAL_DB = 1.5
_MIN_BIC_IMPROVEMENT = 10.0


@dataclass(frozen=True)
class _Candidate:
    values: FloatArray  # [amplitudes..., times..., noise]
    predicted_components: FloatArray
    rms_db: float
    bic: float
    jacobian: FloatArray
    residuals: FloatArray
    converged: bool


def _prediction(values: FloatArray, times: FloatArray, duration: float, count: int) -> FloatArray:
    beta = _DECAY / values[count : 2 * count]
    average = -np.expm1(-beta * duration) / (beta * duration)
    return np.asarray(np.exp(-times[:, None] * beta) * average * values[:count], dtype=np.float64)


def _fit(
    power: FloatArray,
    times: FloatArray,
    duration: float,
    seeds: list[FloatArray],
    count: int,
) -> _Candidate:
    span = len(power) * duration
    lower = np.log([1e-10] * count + [duration / 4.0] * count + [1e-300])
    upper = np.log([100.0] * count + [6.0 * span] * count + [2.0])
    observed = np.log(np.maximum(power, 1e-300))
    # BIC estimates residual variance. Below the relative floating-point
    # resolution of squared log levels, its logarithmic ratio measures solver
    # and rounding differences rather than evidence for another component.
    # Only the BIC variance is bounded; reported residuals and uncertainties
    # retain the actual errors.
    variance_resolution = np.finfo(np.float64).eps * max(1.0, float(np.mean(observed**2)))

    def residual(log_values: FloatArray) -> FloatArray:
        values = np.exp(log_values)
        prediction = _prediction(values, times, duration, count).sum(axis=1) + values[-1]
        return np.asarray(np.log(prediction) - observed, dtype=np.float64)

    best: _Candidate | None = None
    for seed in seeds:
        initial = np.clip(np.log(np.maximum(seed, 1e-300)), lower + 1e-8, upper - 1e-8)
        fitted = least_squares(residual, initial, bounds=(lower, upper), max_nfev=150)
        errors = np.asarray(fitted.fun, dtype=np.float64)
        rss = float(errors @ errors)
        bic_variance = max(rss / len(power), variance_resolution)
        candidate = _Candidate(
            values=np.asarray(np.exp(fitted.x), dtype=np.float64),
            predicted_components=_prediction(np.exp(fitted.x), times, duration, count),
            rms_db=float(np.sqrt(rss / len(power)) * 10.0 / np.log(10.0)),
            bic=float(len(power) * np.log(bic_variance) + (2 * count + 1) * np.log(len(power))),
            jacobian=np.asarray(fitted.jac, dtype=np.float64),
            residuals=errors,
            converged=bool(fitted.success),
        )
        if best is None or candidate.rms_db < best.rms_db:
            best = candidate
    assert best is not None
    return best


def _quality(candidate: _Candidate, duration: float, count: int) -> tuple[str | None, list[float]]:
    if not candidate.converged:
        return "the physical optimizer did not converge", []
    if candidate.rms_db > _MAX_RESIDUAL_DB:
        return (
            f"the exponential model does not explain the decay ({candidate.rms_db:.2f} dB RMS)",
            [],
        )
    values = candidate.values
    rt = values[count : 2 * count]
    if min(rt) <= duration * 0.255 or max(rt) >= 5.9 * len(candidate.residuals) * duration:
        return "a fitted decay time reaches the search bounds", []
    if count == 2 and max(rt) / min(rt) < 1.5:
        return "the two decay time constants cannot be separated", []
    for index in range(count):
        component = candidate.predicted_components[:, index]
        others = candidate.predicted_components.sum(axis=1) - component
        # A component must remain visible above noise and competing components
        # over an observed 10 dB decline. One impulse in a single block fails.
        visible = np.flatnonzero(component >= np.maximum(10.0 * values[-1], 0.2 * others))
        if len(visible) < 4 or 60.0 * (visible[-1] - visible[0]) * duration / rt[index] < 10.0:
            return (
                "a decay component has fewer than four visible blocks or less than 10 dB observed decay",
                [],
            )
    # An unmeasurably small noise term need not invalidate identifiable decay
    # times. Otherwise it participates in the local uncertainty calculation.
    jac = candidate.jacobian
    columns = list(range(2 * count))
    if float(np.max(np.abs(jac[:, -1]))) > 0.05:
        columns.append(2 * count)
    reduced = jac[:, columns]
    singular = np.linalg.svd(reduced, compute_uv=False)
    if singular[-1] <= 1e-4 * singular[0]:
        return "the decay parameters are not identifiable in this recording", []
    variance = float(candidate.residuals @ candidate.residuals) / max(1, len(jac) - len(columns))
    covariance = np.linalg.inv(reduced.T @ reduced) * variance
    deviations = [
        float(rt[i] * np.sqrt(max(0.0, covariance[count + i, count + i]))) for i in range(count)
    ]
    if any(std > 0.25 * time for std, time in zip(deviations, rt, strict=True)):
        return "the fitted decay-time uncertainty exceeds 25 percent", []
    return None, deviations


def _physical_seeds(
    power: FloatArray, times: FloatArray, duration: float
) -> tuple[FloatArray, list[FloatArray]]:
    noise = max(float(np.median(power[-max(3, len(power) // 5) :])), 1e-300)
    levels = 10.0 * np.log10(np.maximum(power, 1e-300))
    mask = (power > 10.0 * noise) & (levels <= 0.0) & (levels >= -30.0)
    rt = len(power) * duration
    if np.count_nonzero(mask) >= 3:
        slope = float(np.polyfit(times[mask], levels[mask], 1)[0])
        if slope < 0.0:
            rt = -60.0 / slope
    rt = float(np.clip(rt, duration, 3.0 * len(power) * duration))
    amplitude = float((_DECAY * duration / rt) / -np.expm1(-_DECAY * duration / rt))
    single = np.array([amplitude, rt, noise], dtype=np.float64)
    # Different physically plausible basins prevent the network from being a
    # prerequisite for discovering a weak slow component.
    double = [
        np.array([amplitude, amplitude * fraction, rt / ratio, rt * 1.5, noise])
        for fraction, ratio in ((0.01, 3.0), (0.1, 2.0))
    ]
    return single, double


def fit_multi_decay(
    signal: FloatArray,
    sample_rate: int,
    *,
    start_index: int = 0,
    time_origin_index: int = 0,
    initializer: str = "physical",
) -> MultiDecayFit:
    """Fit decay components with conservative observability and model checks.

    ``start_index`` excludes the direct pulse; all reported times use
    ``time_origin_index``. Component weights sum to one, excluding noise;
    noise power is relative to the first measured block. Uncertainty is a
    local regression estimate, not calibrated coverage on real rooms.
    """
    if initializer not in ("physical", "neural"):
        raise ValueError("initializer must be 'physical' or 'neural'")
    start = (start_index - time_origin_index) / sample_rate if sample_rate > 0 else 0.0
    end = start
    actual_initializer = "physical"
    model_id: str | None = None
    parameter_count: int | None = None
    model_sha: str | None = None
    fallback: str | None = None

    def result(
        validity: Validity,
        reason: str | None = None,
        *,
        components: tuple[DecayComponent, ...] = (),
        noise_relative_power: float | None = None,
        residual_rms_db: float | None = None,
        bic_difference: float | None = None,
    ) -> MultiDecayFit:
        if fallback:
            reason = f"{reason}; {fallback}" if reason else fallback
        return MultiDecayFit(
            method=METHOD,
            validity=validity,
            fit_start_s=start,
            fit_end_s=end,
            initializer=actual_initializer,
            initializer_model=model_id,
            initializer_parameters=parameter_count,
            initializer_sha256=model_sha,
            components=components,
            noise_relative_power=noise_relative_power,
            residual_rms_db=residual_rms_db,
            bic_difference=bic_difference,
            reason=reason,
        )

    samples = np.asarray(signal, dtype=np.float64)
    if sample_rate <= 0 or samples.ndim != 1 or not np.all(np.isfinite(samples)):
        return result(
            Validity.NOT_COMPUTED, "a finite mono signal and positive sample rate are required"
        )
    if start_index < 0 or start_index >= len(samples):
        return result(Validity.NOT_COMPUTED, "the fit start index is outside the signal")
    tail = samples[start_index:]
    block = max(8, round(0.01 * sample_rate), int(np.ceil(len(tail) / _MAX_BLOCKS)))
    count = len(tail) // block
    duration = block / sample_rate
    end = start + count * duration
    if count < _MIN_BLOCKS:
        return result(Validity.INSUFFICIENT_RANGE, "at least 12 averaged blocks are required")
    # Scale before squaring so finite but very large inputs cannot overflow.
    scale = float(np.max(np.abs(tail)))
    if scale <= 0.0:
        return result(Validity.INSUFFICIENT_RANGE, "the signal contains no measurable decay energy")
    power = np.asarray(((tail[: count * block] / scale) ** 2).reshape(count, block).mean(axis=1))
    if power[0] <= 0.0 or np.any(power <= 0.0):
        return result(
            Validity.INSUFFICIENT_RANGE, "empty energy blocks prevent a continuous decay fit"
        )
    power /= power[0]
    early = float(np.median(power[:3]))
    late = float(np.median(power[-max(3, count // 5) :]))
    if 10.0 * np.log10(early / late) < _MIN_RANGE_DB:
        return result(
            Validity.INSUFFICIENT_RANGE,
            "less than 15 dB observed decay; stationary noise or a rising response cannot establish a decay time",
        )
    times = np.arange(count, dtype=np.float64) * duration
    single_seed, double_seeds = _physical_seeds(power, times, duration)
    single_seeds = [single_seed]
    if initializer == "neural":
        try:
            from roomscope.core.decay_model import neural_initial_guess

            seed = neural_initial_guess(power, duration)
            fast, slow, a_fast, a_slow, noise = seed.values
            proposed = np.asarray([a_fast, a_slow, fast, slow, noise], dtype=np.float64)
            if not np.all(np.isfinite(proposed)) or np.any(proposed <= 0.0):
                raise ValueError("the local model returned nonpositive or nonfinite parameters")
            double_seeds.insert(0, proposed)
            single_seeds.insert(0, np.array([a_fast + a_slow, slow, noise]))
            actual_initializer = "neural"
            model_id, parameter_count, model_sha = seed.model_id, seed.parameter_count, seed.sha256
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            fallback = f"local model initialization failed ({exc}); used physical initialization"
    try:
        one = _fit(power, times, duration, single_seeds, 1)
        two = _fit(power, times, duration, double_seeds, 2)
        difference = one.bic - two.bic
        two_problem, two_std = _quality(two, duration, 2)
        if difference > _MIN_BIC_IMPROVEMENT and two_problem is not None:
            return result(
                Validity.UNRELIABLE,
                f"a second decay is favored but cannot be reliably resolved: {two_problem}",
                residual_rms_db=two.rms_db,
                bic_difference=difference,
            )
        chosen, components_count, deviations = one, 1, []
        if difference > _MIN_BIC_IMPROVEMENT and two_problem is None:
            chosen, components_count, deviations = two, 2, two_std
        problem, std = _quality(chosen, duration, components_count)
        deviations = deviations or std
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
        return result(Validity.UNRELIABLE, f"the constrained decay fit failed: {exc}")
    if problem is not None:
        return result(
            Validity.UNRELIABLE, problem, residual_rms_db=chosen.rms_db, bic_difference=difference
        )
    amplitudes = chosen.values[:components_count]
    rt = chosen.values[components_count : 2 * components_count]
    components = tuple(
        DecayComponent(float(rt[i]), float(amplitudes[i] / amplitudes.sum()), deviations[i])
        for i in np.argsort(rt)
    )
    return result(
        Validity.VALID,
        components=components,
        noise_relative_power=float(chosen.values[-1]),
        residual_rms_db=chosen.rms_db,
        bic_difference=difference,
    )
