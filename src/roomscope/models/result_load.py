"""Rebuild an :class:`AnalysisResult` from the JSON that ``to_dict`` writes.

IR samples live in ``impulse_response.wav`` (see ``load_measurement``); the
JSON copy of the IR is optional. Missing curve arrays become empty so a
``--no-curves`` export can still be opened for the scalar report.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.models.loadutil import read_flag, read_schema_version, record_name
from roomscope.models.result import (
    RESULT_SCHEMA_VERSION,
    AliasedDistortion,
    AnalysisResult,
    BandDecay,
    BoundaryCandidate,
    ClippingCheck,
    DecayMetric,
    DecayResult,
    EnergyMetric,
    ExcitationBand,
    FloatArray,
    FrequencyResponseResult,
    HarmonicDistortion,
    HumCandidate,
    ImpulseResponseResult,
    LoopbackResult,
    NoiseResult,
    PlacementLength,
    PlacementResult,
    PlaybackSpeed,
    Reflection,
    ReflectionsResult,
    ResonanceCandidate,
    ResonanceResult,
    Validity,
)

#: Largest count, index or sample rate read from a file. Every integer up to
#: it is exactly a float, so the times and rates derived from it stay finite.
_MAX_COUNT = 2**53


def _obj(data: Any, name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SessionError(_("{kind} must be a JSON object").format(kind=record_name(name)))
    return data


def _array(values: Any) -> FloatArray:
    if values is None:
        return np.zeros(0, dtype=np.float64)
    curve = np.asarray(values, dtype=np.float64)
    if curve.ndim != 1:
        # A single number loads as a 0-d array that to_dict cannot list.
        raise TypeError(_("expected a list of numbers"))
    return curve


def _int(value: Any, name: str, low: int = 0) -> int:
    """An integer field. ``int()`` takes a 400-digit number, which then fails
    in a float conversion in the report or in ``to_dict``."""
    number = int(value)
    if not low <= number <= _MAX_COUNT:
        raise ValueError(_("{field} is out of range").format(field=name))
    return number


def _pair(values: Any) -> tuple[float, float] | None:
    if values is None:
        return None
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise SessionError(_("expected a pair of numbers"))
    return (float(values[0]), float(values[1]))


def _opt_float(value: Any) -> float | None:
    """An optional number. A string or list fails here (and becomes
    SessionError) instead of in a later comparison or format (#11)."""
    return None if value is None else float(value)


def _opt_int(value: Any, name: str, low: int = 0) -> int | None:
    return None if value is None else _int(value, name, low)


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_bool(value: Any, name: str) -> bool | None:
    return None if value is None else read_flag(value, name)


def _str_tuple(values: Any) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(str(v) for v in values)


def _validity(value: Any) -> Validity:
    try:
        return Validity(str(value))
    except ValueError as exc:
        raise SessionError(_("unknown validity {value}").format(value=repr(value))) from exc


def decay_metric_from_dict(data: Any) -> DecayMetric:
    payload = _obj(data, "decay metric")
    rng = payload.get("evaluation_range_db", (0.0, 0.0))
    return DecayMetric(
        name=str(payload.get("name", "")),
        seconds=_opt_float(payload.get("seconds")),
        validity=_validity(payload.get("validity", Validity.NOT_COMPUTED)),
        evaluation_range_db=(float(rng[0]), float(rng[1])),
        nonlinearity_permille=_opt_float(payload.get("nonlinearity_permille")),
        reason=_opt_str(payload.get("reason")),
    )


def energy_metric_from_dict(data: Any, name: str, unit: str) -> EnergyMetric:
    """An energy parameter; a missing object is an older file that has none."""
    if not isinstance(data, dict):
        return EnergyMetric(name=name, value=None, unit=unit, validity=Validity.NOT_COMPUTED)
    value = data.get("value")
    return EnergyMetric(
        name=str(data.get("name", name)),
        value=None if value is None else float(value),
        unit=str(data.get("unit", unit)),
        validity=_validity(data.get("validity", Validity.NOT_COMPUTED)),
        reason=_opt_str(data.get("reason")),
    )


def band_decay_from_dict(data: Any) -> BandDecay:
    payload = _obj(data, "band decay")
    return BandDecay(
        band_label=str(payload.get("band_label", "")),
        center_hz=_opt_float(payload.get("center_hz")),
        low_hz=_opt_float(payload.get("low_hz")),
        high_hz=_opt_float(payload.get("high_hz")),
        noise_floor_db=_opt_float(payload.get("noise_floor_db")),
        peak_to_noise_db=_opt_float(payload.get("peak_to_noise_db")),
        truncation_time_s=_opt_float(payload.get("truncation_time_s")),
        edt=decay_metric_from_dict(payload.get("edt", {})),
        t20=decay_metric_from_dict(payload.get("t20", {})),
        t30=decay_metric_from_dict(payload.get("t30", {})),
        rt60_estimate_s=_opt_float(payload.get("rt60_estimate_s")),
        rt60_basis=_opt_str(payload.get("rt60_basis")),
        curvature_percent=_opt_float(payload.get("curvature_percent")),
        filter_bt_product=_opt_float(payload.get("filter_bt_product")),
        filter_warning=_opt_str(payload.get("filter_warning")),
        edc_time_s=_array(payload.get("edc_time_s")),
        edc_db=_array(payload.get("edc_db")),
        onset_time_s=_opt_float(payload.get("onset_time_s")),
        mid_band_hz=_opt_float(payload.get("mid_band_hz")),
        warnings=_str_tuple(payload.get("warnings")),
        c50=energy_metric_from_dict(payload.get("c50"), "C50", "dB"),
        c80=energy_metric_from_dict(payload.get("c80"), "C80", "dB"),
        d50=energy_metric_from_dict(payload.get("d50"), "D50", "%"),
        centre_time=energy_metric_from_dict(payload.get("centre_time"), "Ts", "s"),
    )


def decay_result_from_dict(data: Any) -> DecayResult:
    payload = _obj(data, "decay")
    return DecayResult(
        method=str(payload.get("method", "")),
        broadband=band_decay_from_dict(payload.get("broadband", {})),
        bands=tuple(band_decay_from_dict(b) for b in payload.get("bands") or ()),
        notes=_str_tuple(payload.get("notes")),
        time_origin=str(payload.get("time_origin", "")),
    )


def excitation_band_from_dict(data: Any) -> ExcitationBand | None:
    if data is None:
        return None
    payload = _obj(data, "excitation band")
    return ExcitationBand(
        low_hz=float(payload["low_hz"]),
        high_hz=float(payload["high_hz"]),
        source=str(payload.get("source", "")),
        note=_opt_str(payload.get("note")),
    )


def harmonic_from_dict(data: Any) -> HarmonicDistortion:
    payload = _obj(data, "harmonic distortion")
    band = payload.get("band_hz")
    return HarmonicDistortion(
        order=_int(payload["order"], "order"),
        offset_s=float(payload["offset_s"]),
        level_db=_opt_float(payload.get("level_db")),
        floor_db=_opt_float(payload.get("floor_db")),
        band_hz=_pair(band),
        reason=_opt_str(payload.get("reason")),
    )


def aliased_from_dict(data: Any) -> AliasedDistortion:
    payload = _obj(data, "aliased distortion")
    return AliasedDistortion(
        order=_int(payload["order"], "order"),
        band_hz=_pair(payload.get("band_hz")),
        level_db=_opt_float(payload.get("level_db")),
        floor_db=_opt_float(payload.get("floor_db")),
        significant=read_flag(payload.get("significant", False), "significant"),
        reason=_opt_str(payload.get("reason")),
    )


def clipping_from_dict(data: Any) -> ClippingCheck | None:
    if data is None:
        return None
    payload = _obj(data, "clipping")
    return ClippingCheck(
        peak_dbfs=float(payload["peak_dbfs"]),
        runs=_int(payload["runs"], "runs"),
        samples=_int(payload["samples"], "samples"),
        clipped=read_flag(payload["clipped"], "clipped"),
        quantisation_step=_opt_float(payload.get("quantisation_step")),
    )


def impulse_from_dict(data: Any) -> ImpulseResponseResult:
    payload = _obj(data, "impulse_response")
    return ImpulseResponseResult(
        sample_rate=_int(payload["sample_rate"], "sample_rate", low=1),
        samples=_array(payload.get("samples")),
        direct_sound_index=_int(payload["direct_sound_index"], "direct_sound_index"),
        pre_delay_samples=_int(payload["pre_delay_samples"], "pre_delay_samples"),
        peak_value=float(payload["peak_value"]),
        valid_length_s=float(payload["valid_length_s"]),
        pre_peak_margin_db=_opt_float(payload.get("pre_peak_margin_db")),
        direct_sound_confidence=str(payload.get("direct_sound_confidence", "")),
        sweep_start_in_recording_s=float(payload.get("sweep_start_in_recording_s", 0.0)),
        notes=_str_tuple(payload.get("notes")),
        excitation_band=excitation_band_from_dict(payload.get("excitation_band")),
        sweep_passes=_int(payload.get("sweep_passes", 1), "sweep_passes", low=1),
        first_sweep_start_in_recording_s=_opt_float(
            payload.get("first_sweep_start_in_recording_s")
        ),
        harmonic_distortion=tuple(
            harmonic_from_dict(h) for h in payload.get("harmonic_distortion") or ()
        ),
        aliased_distortion=tuple(
            aliased_from_dict(a) for a in payload.get("aliased_distortion") or ()
        ),
        loopback=loopback_from_dict(payload.get("loopback")),
        playback_speed=playback_speed_from_dict(payload.get("playback_speed")),
        direct_level_dbfs=_opt_float(payload.get("direct_level_dbfs")),
    )


def loopback_from_dict(data: Any) -> LoopbackResult | None:
    if data is None:
        return None
    payload = _obj(data, "loopback")
    hz = payload.get("interface_response_hz")
    db = payload.get("interface_response_db")
    return LoopbackResult(
        channel=_opt_int(payload.get("channel"), "channel"),
        compensation_applied=read_flag(
            payload.get("compensation_applied", False), "compensation_applied"
        ),
        reason=_opt_str(payload.get("reason")),
        latency_samples=_opt_int(payload.get("latency_samples"), "latency_samples", -_MAX_COUNT),
        path_delay_ms=_opt_float(payload.get("path_delay_ms")),
        distance_upper_bound_m=_opt_float(payload.get("distance_upper_bound_m")),
        interface_response_hz=None if hz is None else _array(hz),
        interface_response_db=None if db is None else _array(db),
        notes=_str_tuple(payload.get("notes")),
    )


def playback_speed_from_dict(data: Any) -> PlaybackSpeed | None:
    if data is None:
        return None
    payload = _obj(data, "playback_speed")
    played = payload.get("played_rate_hz")
    return PlaybackSpeed(
        speed_ratio=float(payload["speed_ratio"]),
        kind=str(payload["kind"]),
        generated_rate_hz=_int(payload["generated_rate_hz"], "generated_rate_hz", low=1),
        played_rate_hz=_opt_int(played, "played_rate_hz", low=1),
    )


def frequency_response_from_dict(data: Any) -> FrequencyResponseResult:
    payload = _obj(data, "frequency_response")
    smoothed = payload.get("magnitude_db_smoothed")
    return FrequencyResponseResult(
        frequencies_hz=_array(payload.get("frequencies_hz")),
        magnitude_db_raw=_array(payload.get("magnitude_db_raw")),
        magnitude_db_smoothed=None if smoothed is None else _array(smoothed),
        smoothing_fraction=_int(payload.get("smoothing_fraction", 0), "smoothing_fraction"),
        window_s=float(payload.get("window_s", 0.0)),
        lead_in_s=float(payload.get("lead_in_s", 0.0)),
        resolution_hz=float(payload.get("resolution_hz", float("inf"))),
        bin_spacing_hz=float(payload.get("bin_spacing_hz", float("inf"))),
        gated=read_flag(payload.get("gated", False), "gated"),
        excitation_band=excitation_band_from_dict(payload.get("excitation_band")),
        reference=str(payload.get("reference", "")),
        # A --no-curves file keeps only the count.
        stored_points=(
            _opt_int(payload.get("points"), "points")
            if payload.get("frequencies_hz") is None
            else None
        ),
    )


def hum_from_dict(data: Any) -> HumCandidate:
    payload = _obj(data, "hum")
    harmonics = tuple((float(a), float(b)) for a, b in payload.get("harmonics") or ())
    return HumCandidate(
        base_hz=float(payload["base_hz"]),
        harmonics=harmonics,
        strongest_prominence_db=_opt_float(payload.get("strongest_prominence_db")),
        detected=read_flag(payload.get("detected", False), "detected"),
        distinct_harmonics_hz=tuple(float(x) for x in payload.get("distinct_harmonics_hz") or ()),
        note=_opt_str(payload.get("note")),
    )


def noise_from_dict(data: Any) -> NoiseResult:
    payload = _obj(data, "noise")
    bands = tuple(
        (float(item[0]), None if item[1] is None else float(item[1]))
        for item in payload.get("band_levels_dbfs") or ()
    )
    psd_f = payload.get("psd_frequencies_hz")
    psd = payload.get("psd_db")
    return NoiseResult(
        segment_source=_opt_str(payload.get("segment_source")),
        segment_start_s=_opt_float(payload.get("segment_start_s")),
        segment_duration_s=_opt_float(payload.get("segment_duration_s")),
        rms_dbfs=_opt_float(payload.get("rms_dbfs")),
        peak_dbfs=_opt_float(payload.get("peak_dbfs")),
        band_levels_dbfs=bands,
        psd_frequencies_hz=None if psd_f is None else _array(psd_f),
        psd_db=None if psd is None else _array(psd),
        hum=tuple(hum_from_dict(h) for h in payload.get("hum") or ()),
        calibration=str(payload.get("calibration", "")),
        psd_reference=str(payload.get("psd_reference", "")),
        notes=_str_tuple(payload.get("notes")),
    )


def reflections_from_dict(data: Any) -> ReflectionsResult:
    payload = _obj(data, "reflections")
    window = payload.get("window_ms", (0.0, 0.0))
    analysed = payload.get("analysed_window_ms")
    return ReflectionsResult(
        direct_sound_time_s=float(payload.get("direct_sound_time_s", 0.0)),
        direct_sound_confidence=str(payload.get("direct_sound_confidence", "")),
        window_ms=(float(window[0]), float(window[1])),
        threshold_db=float(payload.get("threshold_db", 0.0)),
        reflections=tuple(
            Reflection(delay_ms=float(r["delay_ms"]), relative_db=float(r["relative_db"]))
            for r in payload.get("reflections") or ()
        ),
        notes=_str_tuple(payload.get("notes")),
        analysed_window_ms=_pair(analysed),
        window_truncated=read_flag(payload.get("window_truncated", False), "window_truncated"),
    )


def resonances_from_dict(data: Any) -> ResonanceResult:
    payload = _obj(data, "resonances")
    candidates = []
    for item in payload.get("candidates") or ():
        row = _obj(item, "resonance candidate")
        candidates.append(
            ResonanceCandidate(
                frequency_hz=float(row["frequency_hz"]),
                level_above_baseline_db=float(row["level_above_baseline_db"]),
                narrowband_decay_20db_s=_opt_float(row.get("narrowband_decay_20db_s")),
                filter_ringing_20db_s=_opt_float(row.get("filter_ringing_20db_s")),
                decay_distinguishable=read_flag(
                    row.get("decay_distinguishable", False), "decay_distinguishable"
                ),
                surroundings_decay_20db_s=_opt_float(row.get("surroundings_decay_20db_s")),
            )
        )
    return ResonanceResult(
        max_frequency_hz=float(payload.get("max_frequency_hz", 0.0)),
        candidates=tuple(candidates),
        notes=_str_tuple(payload.get("notes")),
        searched_range_hz=_pair(payload.get("searched_range_hz")),
    )


def placement_length_from_dict(data: Any) -> PlacementLength:
    payload = _obj(data, "placement length")
    alts = payload.get("alternatives_m") or ()
    return PlacementLength(
        metres=_opt_float(payload.get("metres")),
        validity=_validity(payload.get("validity", Validity.NOT_COMPUTED)),
        reason=_opt_str(payload.get("reason")),
        input_uncertainty_m=_opt_float(payload.get("input_uncertainty_m")),
        alternatives_m=tuple(float(x) for x in alts),
        missing_input=_opt_str(payload.get("missing_input")),
    )


def boundary_from_dict(data: Any) -> BoundaryCandidate:
    payload = _obj(data, "boundary candidate")
    return BoundaryCandidate(
        delay_ms=float(payload["delay_ms"]),
        relative_db=float(payload["relative_db"]),
        excess_path_m=float(payload["excess_path_m"]),
        mirror_path_m=_opt_float(payload.get("mirror_path_m")),
        product_m2=_opt_float(payload.get("product_m2")),
        geometric_mean_m=_opt_float(payload.get("geometric_mean_m")),
        mean_distance_bracket_m=_pair(payload.get("mean_distance_bracket_m")),
        specular_ceiling_db=_opt_float(payload.get("specular_ceiling_db")),
        surface=_opt_str(payload.get("surface")),
        interpretable_as_plane=_opt_bool(
            payload.get("interpretable_as_plane"), "interpretable_as_plane"
        ),
        excluded_reason=_opt_str(payload.get("excluded_reason")),
    )


def placement_from_dict(data: Any) -> PlacementResult | None:
    if data is None:
        return None
    payload = _obj(data, "placement")
    return PlacementResult(
        tier=_int(payload.get("tier", 0), "tier"),
        candidates=tuple(boundary_from_dict(c) for c in payload.get("candidates") or ()),
        source_height_m=placement_length_from_dict(payload.get("source_height_m", {})),
        ceiling_height_m=placement_length_from_dict(payload.get("ceiling_height_m", {})),
        horizontal_separation_m=placement_length_from_dict(
            payload.get("horizontal_separation_m", {})
        ),
        speed_of_sound_m_s=float(payload.get("speed_of_sound_m_s", 0.0)),
        temperature_c=float(payload.get("temperature_c", 20.0)),
        temperature_assumed=read_flag(
            payload.get("temperature_assumed", True), "temperature_assumed"
        ),
        distance_m=_opt_float(payload.get("distance_m")),
        mic_height_m=_opt_float(payload.get("mic_height_m")),
        analysed_window_ms=_pair(payload.get("analysed_window_ms")),
        window_truncated=read_flag(payload.get("window_truncated", False), "window_truncated"),
        notes=_str_tuple(payload.get("notes")),
        speed_of_sound_reference=str(payload.get("speed_of_sound_reference", "")),
        coordinates_withheld=str(payload.get("coordinates_withheld", "")),
    )


def analysis_result_from_dict(data: Any) -> AnalysisResult:
    payload = _obj(data, "result")
    version = read_schema_version(payload, RESULT_SCHEMA_VERSION, "result")
    try:
        return AnalysisResult(
            created_at=str(payload.get("created_at", "")),
            sample_rate=_int(payload["sample_rate"], "sample_rate", low=1),
            sweep_settings=dict(payload.get("sweep_settings") or {}),
            analysis_settings=dict(payload.get("analysis_settings") or {}),
            impulse_response=impulse_from_dict(payload.get("impulse_response")),
            decay=decay_result_from_dict(payload.get("decay")),
            frequency_response=frequency_response_from_dict(payload.get("frequency_response")),
            noise=noise_from_dict(payload.get("noise")),
            reflections=reflections_from_dict(payload.get("reflections")),
            resonances=resonances_from_dict(payload.get("resonances")),
            warnings=_str_tuple(payload.get("warnings")),
            clipping=clipping_from_dict(payload.get("clipping")),
            placement=placement_from_dict(payload.get("placement")),
            schema_version=version,
            roomscope_version=str(payload.get("roomscope_version", "")),
        )
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        # IndexError: a one-element range or pair; OverflowError: int(Infinity).
        raise SessionError(
            _("result.json is incomplete or invalid: {error}").format(error=exc)
        ) from exc
