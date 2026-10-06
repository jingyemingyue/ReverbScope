"""Every guided threshold lives here, with why it exists and where it does not apply.

These are engineering choices for a home recording check. They are not ISO
limits, not a room grade, and not a substitute for the measurement itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Threshold:
    name: str
    value: float
    unit: str
    rationale: str
    applicability: str
    limitations: str


STRONG_REFLECTION_LEVEL_DB = Threshold(
    name="strong_reflection_level_db",
    value=-12.0,
    unit="dB",
    rationale=(
        "A specular arrival within about 12 dB of the direct sound is loud enough "
        "to comb-filter a close microphone. The same cut is used as a starting "
        "point by the generic recording profile."
    ),
    applicability="Early reflections already detected by the DSP, relative to the direct sound.",
    limitations="Does not name the surface. A diffuse tail peak can look similar.",
)

STRONG_REFLECTION_WINDOW_MS = Threshold(
    name="strong_reflection_window_ms",
    value=30.0,
    unit="ms",
    rationale="Arrivals inside 30 ms overlap speech and most close-miked sources.",
    applicability="Reflection delay after the detected direct sound.",
    limitations="Wrong if the direct sound itself was mis-identified.",
)

VERY_CLOSE_REFLECTION_MS = Threshold(
    name="very_close_reflection_ms",
    value=10.0,
    unit="ms",
    rationale="Under 10 ms the comb spacing is wide and often audible on voice.",
    applicability="Same reflection list.",
    limitations="Still not a surface identification.",
)

VERY_STRONG_REFLECTION_DB = Threshold(
    name="very_strong_reflection_db",
    value=-8.0,
    unit="dB",
    rationale="Within 8 dB the arrival competes with the direct sound.",
    applicability="Same reflection list.",
    limitations="Relative level, not SPL.",
)

LOW_BAND_MAX_HZ = Threshold(
    name="low_band_max_hz",
    value=250.0,
    unit="Hz",
    rationale="Octave bands at and below 250 Hz are the region a small room stretches.",
    applicability="Bands that already have a valid RT60 estimate.",
    limitations="A single band is not a modal map.",
)

MID_BAND_MIN_HZ = Threshold(
    name="mid_band_min_hz",
    value=500.0,
    unit="Hz",
    rationale="500 Hz to 2 kHz is the comparison region used for 'low versus mid'.",
    applicability="Bands with a valid RT60 estimate.",
    limitations="Empty if the excitation did not cover the mid band.",
)

MID_BAND_MAX_HZ = Threshold(
    name="mid_band_max_hz",
    value=2000.0,
    unit="Hz",
    rationale="Upper edge of the mid comparison region.",
    applicability="Bands with a valid RT60 estimate.",
    limitations="Not a full-band average.",
)

SLOW_LOW_RATIO = Threshold(
    name="slow_low_ratio",
    value=1.5,
    unit="1",
    rationale=(
        "Low-band RT60 more than 1.5 times the mid-band mean is the same engineering "
        "cut the generic profile already uses to call the low end 'clearly longer'."
    ),
    applicability="Only when both sides have a valid RT60 estimate. Invalid decays are skipped.",
    limitations="Not a just-noticeable difference and not a room score.",
)

LOW_PEAK_PROMINENCE_DB = Threshold(
    name="low_peak_prominence_db",
    value=6.0,
    unit="dB",
    rationale="A narrow rise of 6 dB above the low-band median is large enough to mention.",
    applicability="60–200 Hz magnitude, only as a dip or peak against its own median.",
    limitations=(
        "Gated low-frequency resolution is coarse. A broad tilt is not reported as a peak. "
        "A distinguishable resonance from the DSP is preferred over this curve test."
    ),
)

LOW_NULL_DEPTH_DB = Threshold(
    name="low_null_depth_db",
    value=6.0,
    unit="dB",
    rationale="A narrow dip of 6 dB below the low-band median is the matching cut for a null.",
    applicability="60–200 Hz magnitude against its own median, not against a target curve.",
    limitations="Cannot separate a room null from a loudspeaker or microphone null.",
)

FR_CONFIDENT_RESOLUTION_HZ = Threshold(
    name="fr_confident_resolution_hz",
    value=20.0,
    unit="Hz",
    rationale="Below this resolution a 60–200 Hz dip can be told from the window.",
    applicability="Frequency-response resolution_hz.",
    limitations="Coarser windows lower confidence; they do not invent a sharper null.",
)

HIGH_NOISE_RMS_DBFS = Threshold(
    name="high_noise_rms_dbfs",
    value=-45.0,
    unit="dBFS",
    rationale=(
        "A quiet-segment RMS above -45 dBFS is loud for an uncalibrated home recording "
        "and is worth hearing before judging decay."
    ),
    applicability="NoiseResult.rms_dbfs of a verified quiet segment. Uncalibrated.",
    limitations="This is not dB SPL. A quiet segment that is not quiet will read hot.",
)

HOT_PEAK_DBFS = Threshold(
    name="hot_peak_dbfs",
    value=-3.0,
    unit="dBFS",
    rationale="Within 3 dB of full scale a little more gain will clip.",
    applicability="Recording peak from the flat-top check, only when no plateau was found.",
    limitations="A deliberate loud take can sit here without being distorted yet.",
)

LOW_SIGNAL_PEAK_DBFS = Threshold(
    name="low_signal_peak_dbfs",
    value=-36.0,
    unit="dBFS",
    rationale="A whole-file peak below -36 dBFS leaves little level for the sweep.",
    applicability="Recording peak from the flat-top check.",
    limitations="Says the file is quiet, not which gain knob is low.",
)

REFLECTION_LEVEL_DEADBAND_DB = Threshold(
    name="reflection_level_deadband_db",
    value=2.0,
    unit="dB",
    rationale="Under 2 dB a single pair of positions does not show a reflection change.",
    applicability="A/B of the strongest early-reflection level.",
    limitations="Not a significance test. Position scatter can be larger.",
)

DECAY_RATIO_DEADBAND = Threshold(
    name="decay_ratio_deadband",
    value=0.1,
    unit="1",
    rationale="A low/mid RT60 ratio change under 0.1 is called unchanged.",
    applicability="A/B of the low-versus-mid ratio when both sides are valid.",
    limitations="Does not declare one take 'better' as a room score.",
)

NOISE_DEADBAND_DB = Threshold(
    name="noise_deadband_db",
    value=3.0,
    unit="dB",
    rationale="Under 3 dB the quiet-segment RMS is called unchanged.",
    applicability="A/B of NoiseResult.rms_dbfs.",
    limitations="Uncalibrated dBFS. Gain changes move this number.",
)


ALL_THRESHOLDS: tuple[Threshold, ...] = (
    STRONG_REFLECTION_LEVEL_DB,
    STRONG_REFLECTION_WINDOW_MS,
    VERY_CLOSE_REFLECTION_MS,
    VERY_STRONG_REFLECTION_DB,
    LOW_BAND_MAX_HZ,
    MID_BAND_MIN_HZ,
    MID_BAND_MAX_HZ,
    SLOW_LOW_RATIO,
    LOW_PEAK_PROMINENCE_DB,
    LOW_NULL_DEPTH_DB,
    FR_CONFIDENT_RESOLUTION_HZ,
    HIGH_NOISE_RMS_DBFS,
    HOT_PEAK_DBFS,
    LOW_SIGNAL_PEAK_DBFS,
    REFLECTION_LEVEL_DEADBAND_DB,
    DECAY_RATIO_DEADBAND,
    NOISE_DEADBAND_DB,
)
