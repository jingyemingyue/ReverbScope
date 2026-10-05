from __future__ import annotations

import numpy as np
import pytest

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.errors import ConfigurationError
from roomscope.interpretation import (
    Severity,
    available_profiles,
    interpret,
)
from roomscope.interpretation.profiles import (
    AcousticGuitarProfile,
    ChoirProfile,
    DrumsProfile,
    RoomMicProfile,
    VocalProfile,
    VoiceOverProfile,
    profile_title,
)
from roomscope.models.configuration import SweepSettings
from roomscope.models.result import EnergyMetric, Reflection, Validity
from tests.conftest import make_rir

ALL_PROFILES = [
    "acoustic_guitar",
    "choir",
    "drums",
    "generic",
    "room_mic",
    "vocal",
    "voiceover",
]


def _hummed_recording(short_sweep: SweepSettings, ir: np.ndarray):
    """A synthetic recording of ``ir`` with detectable 50 Hz mains hum."""
    rec = synthetic_recording(short_sweep, ir, noise_rms=2e-5)
    t = np.arange(rec.n_samples) / rec.sample_rate
    hum = sum(a * np.sin(2 * np.pi * 50.0 * k * t) for k, a in ((1, 4e-4), (2, 2e-4), (3, 1e-4)))
    return type(rec)(samples=rec.samples + hum, sample_rate=rec.sample_rate)


def test_generic_profile_reports_reflection_and_hum(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.35, reflections=[(0.018, 10 ** (-8 / 20))], diffuse_level=0.01)
    rec = _hummed_recording(short_sweep, ir)
    result = analyze(rec, Reference.from_settings(short_sweep))
    findings = interpret(result)
    topics = {f.topic for f in findings}
    assert "early_reflections" in topics
    reflection = next(f for f in findings if f.topic == "early_reflections")
    assert reflection.evidence["delay_ms"] == pytest.approx(18.0, abs=0.5)
    assert any(f.topic == "noise" and f.severity is Severity.WARNING for f in findings)
    assert all(f.to_dict()["message"] for f in findings)


def test_available_profiles_are_listed() -> None:
    assert available_profiles() == ALL_PROFILES


def test_every_profile_has_a_display_name() -> None:
    # The GUI lists profiles by name; the id stays in files and on the command line.
    titles = [profile_title(name) for name in available_profiles()]
    assert all(title != name for title, name in zip(titles, available_profiles(), strict=True))
    assert len(set(titles)) == len(titles)


def test_unknown_profile_rejected(short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir)
    result = analyze(rec, Reference.from_settings(short_sweep))
    with pytest.raises(ConfigurationError):
        interpret(result, "not_a_profile")


def test_every_profile_returns_findings_with_evidence(short_sweep: SweepSettings) -> None:
    """All seven profiles run over the same rich result and never invent numbers."""
    sr = short_sweep.sample_rate
    ir = make_rir(
        sr,
        rt60_s=0.7,
        reflections=[(0.018, 10 ** (-8 / 20))],
        diffuse_level=0.02,
    )
    rec = _hummed_recording(short_sweep, ir)
    result = analyze(rec, Reference.from_settings(short_sweep))
    for name in ALL_PROFILES:
        findings = interpret(result, name)
        assert findings, f"{name} produced no findings on a live room"
        for finding in findings:
            assert finding.message, f"{name}: empty message"
            assert finding.evidence, f"{name}: finding without evidence"


def test_voiceover_flags_weaker_reflection_than_generic(short_sweep: SweepSettings) -> None:
    """A -11 dB reflection at 15 ms is below the generic gate but above the VO gate."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.3, reflections=[(0.015, 10 ** (-11 / 20))], diffuse_level=0.01)
    rec = synthetic_recording(short_sweep, ir, noise_rms=2e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    generic = {f.topic for f in interpret(result, "generic")}
    voiceover = {f.topic for f in interpret(result, "voiceover")}
    assert "early_reflections" not in generic
    assert "early_reflections" in voiceover


def test_vocal_flags_decay_that_room_mic_accepts(short_sweep: SweepSettings) -> None:
    """A 0.75 s decay is 'noticeable' for close vocal but usable ambience for a room mic."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.75, diffuse_level=0.03)
    rec = synthetic_recording(short_sweep, ir, noise_rms=2e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    vocal = next(f for f in interpret(result, "vocal") if f.topic == "reverberation")
    room = next(f for f in interpret(result, "room_mic") if f.topic == "reverberation")
    assert vocal.severity is not Severity.INFO
    assert room.severity is Severity.INFO
    assert "room microphone" in room.message


def test_drums_skip_noise_findings(short_sweep: SweepSettings) -> None:
    """Mains hum is reported for every profile except drums, where it is drowned."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.01)
    rec = _hummed_recording(short_sweep, ir)
    result = analyze(rec, Reference.from_settings(short_sweep))
    assert any(f.topic == "noise" for f in interpret(result, "generic"))
    assert not any(f.topic == "noise" for f in interpret(result, "drums"))


def test_profile_messages_name_their_recording_kind() -> None:
    r = Reflection(delay_ms=18.0, relative_db=-11.0)
    messages = {
        profile.name: profile.reflection_message(r)
        for profile in (
            VocalProfile(),
            VoiceOverProfile(),
            AcousticGuitarProfile(),
            DrumsProfile(),
            RoomMicProfile(),
            ChoirProfile(),
        )
    }
    assert "vocal" in messages["vocal"].lower()
    assert "voice-over" in messages["voiceover"].lower()
    assert "acoustic guitar" in messages["acoustic_guitar"].lower()
    assert "drums" in messages["drums"].lower()
    assert "room microphone" in messages["room_mic"].lower()
    assert "ensemble" in messages["choir"].lower()
    # The measured value is the same, but the advice differs per source.
    assert len(set(messages.values())) == 6


def test_clarity_notice_follows_the_profile_and_ignores_an_invalid_ratio(
    short_sweep: SweepSettings,
) -> None:
    """C50/C80 advice is a recording choice, not a grade, and only a VALID ratio counts."""
    from dataclasses import replace

    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.02)
    rec = synthetic_recording(short_sweep, ir, noise_rms=2e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))

    def with_energy(**fields: EnergyMetric):
        band = replace(result.decay.broadband, **fields)
        return replace(result, decay=replace(result.decay, broadband=band))

    low = EnergyMetric("c50", -1.0, "dB", Validity.VALID)
    between = EnergyMetric("c50", 3.0, "dB", Validity.VALID)
    high_c80 = EnergyMetric("c80", 10.0, "dB", Validity.VALID)
    withheld = EnergyMetric("c50", None, "dB", Validity.INSUFFICIENT_RANGE, reason="short")

    voiced = with_energy(c50=low)
    voice = [f for f in interpret(voiced, "voiceover") if f.topic == "clarity"]
    vocal = [f for f in interpret(voiced, "vocal") if f.topic == "clarity"]
    generic = [f for f in interpret(voiced, "generic") if f.topic == "clarity"]
    drums = [f for f in interpret(voiced, "drums") if f.topic == "clarity"]
    assert voice and voice[0].message_id == "clarity.low"
    assert voice[0].evidence["threshold_db"] == 4.0
    assert "voice-over" in voice[0].message.lower()
    assert "not a room grade" in voice[0].message
    assert vocal and vocal[0].evidence["threshold_db"] == 2.0
    assert generic and generic[0].evidence["threshold_db"] == 0.0
    assert drums == []

    middling = with_energy(c50=between)
    assert any(f.topic == "clarity" for f in interpret(middling, "voiceover"))
    assert not any(f.topic == "clarity" for f in interpret(middling, "vocal"))
    assert not any(f.topic == "clarity" for f in interpret(middling, "generic"))

    dry = with_energy(c80=high_c80)
    room = [f for f in interpret(dry, "room_mic") if f.topic == "clarity"]
    assert room and room[0].message_id == "clarity.high"
    assert "room microphone" in room[0].message.lower()
    assert not any(f.topic == "clarity" for f in interpret(dry, "drums"))

    quiet = with_energy(c50=withheld)
    assert not any(f.topic == "clarity" for f in interpret(quiet, "voiceover"))


def test_profile_decay_messages_differ(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.8, diffuse_level=0.03)
    rec = synthetic_recording(short_sweep, ir, noise_rms=2e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    messages = {
        name: next((f.message for f in interpret(result, name) if f.topic == "reverberation"), "")
        for name in ("vocal", "voiceover", "room_mic")
    }
    assert "vocal" in messages["vocal"].lower()
    assert "voice-over" in messages["voiceover"].lower()
    assert "room microphone" in messages["room_mic"].lower()


def test_direct_to_noise_margin_follows_the_playback_level() -> None:
    """The IR peak is the chain gain alone (the inverse filter has unit gain
    for the level-scaled sweep), so the margin ignored the playback level and
    "increase the playback level" could never change it."""
    margins = []
    for level in (-3.0, -40.0):
        settings = SweepSettings(duration_s=2.0, post_silence_s=1.5, level_dbfs=level)
        rec = synthetic_recording(settings, make_rir(48000, rt60_s=0.4) * 0.2, noise_rms=1e-4)
        findings = interpret(analyze(rec, Reference.from_settings(settings)))
        margins.append(
            next(
                f.evidence["direct_to_noise_db"]
                for f in findings
                if f.message_id == "noise.direct_to_noise"
            )
        )
    assert margins[0] - margins[1] == pytest.approx(37.0, abs=1.0)


def test_a_reflection_as_loud_as_the_direct_sound_is_the_strongest() -> None:
    """``level or -99.0`` ranked a 0.0 dB reflection below a -15 dB one."""
    from roomscope.interpretation import interpret_comparison
    from roomscope.models.comparison import ComparisonResult, ReflectionMatch

    matches = tuple(
        ReflectionMatch(
            status="matched",
            baseline_delay_ms=delay,
            candidate_delay_ms=delay,
            baseline_relative_db=level,
            candidate_relative_db=level - 3.0,
        )
        for delay, level in ((2.0, -15.0), (4.0, 0.0))
    )
    comparison = ComparisonResult(comparable=True, common_band=(20.0, 20000.0), reflections=matches)
    finding = next(
        f
        for f in interpret_comparison(comparison)
        if f.message_id == "comparison.reflection_change"
    )
    assert finding.params["baseline_delay_ms"] == 4.0
    # A match read leniently from a file without the candidate delay is skipped, not a crash.
    partial = ComparisonResult(
        comparable=True,
        common_band=(20.0, 20000.0),
        reflections=(
            ReflectionMatch(status="matched", baseline_delay_ms=2.0, baseline_relative_db=-6.0),
        ),
    )
    assert interpret_comparison(partial) is not None


def _noisy_take(*, loopback_db: float | None = None, noise_dbfs: float = -75.0):
    """A -12 dBFS sweep, the direct sound about 50 dB above -75 dBFS noise (the
    generic profile's notice fires below 60 dB), and optionally a loopback
    whose return is ``loopback_db`` from unity gain."""
    from roomscope.core.sweep import measurement_signal
    from roomscope.models.audio import AudioSignal

    settings = SweepSettings(duration_s=1.0, pre_silence_s=1.0, post_silence_s=1.0)
    room = make_rir(48000, rt60_s=0.3, start_delay_s=0.002) * 0.3
    rec = synthetic_recording(settings, room, noise_rms=10 ** (noise_dbfs / 20), seed=1)
    if loopback_db is None:
        return settings, rec, None
    excitation = measurement_signal(settings) * 10 ** (loopback_db / 20)
    lb = np.pad(excitation, (0, rec.n_samples - excitation.shape[0]))
    lb = lb + np.random.default_rng(2).normal(0.0, 1e-6, lb.shape[0])
    return settings, rec, AudioSignal(lb, rec.sample_rate)


def _direct_to_noise_db(result) -> float | None:
    return next(
        (
            f.params["direct_to_noise_db"]
            for f in interpret(result)
            if f.message_id == "noise.direct_to_noise"
        ),
        None,
    )


@pytest.mark.parametrize("loopback_db", [-20.0, 10.0])
def test_direct_to_noise_ignores_the_loopback_return_gain(loopback_db: float) -> None:
    """Compensation divides the IR by the loopback's return gain, while the
    noise is measured on the raw recording: a -20 dB return read the direct
    sound 20 dB too loud and suppressed the notice."""
    settings, rec, loopback = _noisy_take(loopback_db=loopback_db)
    plain = analyze(rec, Reference.from_settings(settings))
    compensated = analyze(rec, Reference.from_settings(settings), loopback=loopback)
    assert compensated.impulse_response.loopback is not None
    assert compensated.impulse_response.loopback.compensation_applied
    expected = _direct_to_noise_db(plain)
    assert expected is not None
    assert _direct_to_noise_db(compensated) == pytest.approx(expected, abs=1.0)


def test_direct_to_noise_with_a_reference_wav() -> None:
    """A reference WAV without its sidecar has no sweep settings; its own peak
    is the level it was played at, so the notice is still given."""
    from roomscope.core.sweep import measurement_signal

    settings, rec, _ = _noisy_take()
    expected = _direct_to_noise_db(analyze(rec, Reference.from_settings(settings)))
    result = analyze(rec, Reference.from_signal(measurement_signal(settings), rec.sample_rate))
    assert result.sweep_settings == {}
    assert expected is not None
    assert _direct_to_noise_db(result) == pytest.approx(expected, abs=1.5)


def _saved_without_direct_level(noise_dbfs: float = -75.0, **sweep_settings: object):
    """The take as a 0.5.0b1 ``result.json`` (no ``direct_level_dbfs``)."""
    settings, rec, _ = _noisy_take(noise_dbfs=noise_dbfs)
    data = analyze(rec, Reference.from_settings(settings)).to_dict(include_curves=False)
    data["impulse_response"].pop("direct_level_dbfs", None)
    data["sweep_settings"].update(sweep_settings)
    return data


def test_direct_level_survives_a_save_and_old_files_fall_back() -> None:
    from roomscope.models.result import AnalysisResult

    settings, rec, _ = _noisy_take()
    result = analyze(rec, Reference.from_settings(settings))
    level = result.impulse_response.direct_level_dbfs
    assert level is not None
    reloaded = AnalysisResult.from_dict(result.to_dict(include_curves=False))
    assert reloaded.impulse_response.direct_level_dbfs == pytest.approx(level)
    # An older file: the IR peak plus the sweep level.
    old = AnalysisResult.from_dict(_saved_without_direct_level())
    assert old.impulse_response.direct_level_dbfs is None
    assert _direct_to_noise_db(old) == pytest.approx(_direct_to_noise_db(result), abs=0.5)


@pytest.mark.parametrize(
    "level",
    [10**400, float("nan"), True, "-12", 3.0],
    ids=["400 digits", "nan", "bool", "string", "above full scale"],
)
def test_a_crafted_sweep_level_is_an_unknown_level(level: object) -> None:
    """float() of a 400-digit integer raised OverflowError inside interpret();
    a level no sweep can have is not used either."""
    from roomscope.models.result import AnalysisResult

    # Noisy enough that any level up to +20 dBFS would give the notice.
    data = _saved_without_direct_level(noise_dbfs=-45.0, level_dbfs=level)
    assert _direct_to_noise_db(AnalysisResult.from_dict(data)) is None


_ISO_NOTE = (
    "ISO 3382-1 quotes a just-noticeable difference for reverberation time of about 5 % "
    "(clause not verified against the standard text). A change is not called significant "
    "from a single pair of positions."
)


_NARROW_NOTE = (
    "common excitation band 100-150 Hz is 0.58 octaves, narrower than the required 1 octave"
)
_SWEEP_NOTE = "sample rates differ (48000 Hz vs 96000 Hz); comparison is still allowed"


@pytest.mark.parametrize(
    ("notes", "reason"),
    [
        ((_ISO_NOTE, _NARROW_NOTE), _NARROW_NOTE),
        (
            (_SWEEP_NOTE, "the excitation bands do not overlap", _ISO_NOTE),
            "the excitation bands do not overlap",
        ),
    ],
    ids=["narrow band last", "sweep note first"],
)
def test_a_refusal_saved_by_an_older_version_names_its_reason(
    notes: tuple[str, ...], reason: str
) -> None:
    """0.5.0b1 saved the refusal after the sweep and ISO notes, and ``show``
    quoted notes[0]: "cannot be compared: ISO 3382-1 quotes ..."."""
    from roomscope.interpretation import interpret_comparison
    from roomscope.models.comparison import ComparisonResult

    comparison = ComparisonResult(comparable=False, common_band=None, notes=notes)
    (finding,) = interpret_comparison(comparison)
    assert finding.message == f"These two sessions cannot be compared: {reason}"
    assert finding.params["notes"] == reason


def test_a_refusal_without_notes_is_translated() -> None:
    """A file without notes fell back to an English literal outside the catalog."""
    from roomscope.i18n import activate
    from roomscope.interpretation import interpret_comparison
    from roomscope.models.comparison import ComparisonResult

    comparison = ComparisonResult.from_dict({"comparable": False, "common_band": None})
    activate("zh_CN")
    (finding,) = interpret_comparison(comparison)
    assert "excitation" not in finding.message
    assert "激励频带" in finding.message


def _reflection_findings(*matches):
    from roomscope.interpretation import interpret_comparison
    from roomscope.models.comparison import ComparisonResult

    comparison = ComparisonResult(comparable=True, common_band=(20.0, 20000.0), reflections=matches)
    return [f for f in interpret_comparison(comparison, "vocal") if f.topic == "early_reflections"]


def test_the_strongest_reflection_counts_unmatched_ones() -> None:
    """Only matched pairs were ranked: a dominant reflection that disappeared,
    or a strong new one, hid behind a weaker matched pair ("went from -9.2 dB
    at 7.1 ms to -9.2 dB at 7.1 ms")."""
    from roomscope.models.comparison import ReflectionMatch

    weak = ReflectionMatch("matched", 7.1, 7.1, -9.2, -9.5)
    (gone,) = _reflection_findings(
        ReflectionMatch("disappeared", baseline_delay_ms=2.4, baseline_relative_db=-3.2), weak
    )
    assert gone.message_id == "comparison.reflection_change"
    assert (gone.params["baseline_delay_ms"], gone.params["baseline_relative_db"]) == (2.4, -3.2)
    assert (gone.params["candidate_delay_ms"], gone.params["candidate_relative_db"]) == (7.1, -9.5)
    (new,) = _reflection_findings(
        weak, ReflectionMatch("appeared", candidate_delay_ms=3.0, candidate_relative_db=-2.0)
    )
    assert (new.params["baseline_delay_ms"], new.params["baseline_relative_db"]) == (7.1, -9.2)
    assert (new.params["candidate_delay_ms"], new.params["candidate_relative_db"]) == (3.0, -2.0)


def test_a_strong_reflection_that_disappeared_is_reported() -> None:
    from roomscope.models.comparison import ReflectionMatch

    (finding,) = _reflection_findings(
        ReflectionMatch("disappeared", baseline_delay_ms=2.4, baseline_relative_db=-3.2),
        # Outside the vocal profile's 25 ms window.
        ReflectionMatch("matched", 40.0, 40.0, -6.0, -6.0),
    )
    assert finding.message_id == "comparison.reflection_disappeared"
    assert (finding.params["delay_ms"], finding.params["relative_db"]) == (2.4, -3.2)
    # A weak one (below the profile's -12 dB) is not worth a finding, as for "appeared".
    weak = ReflectionMatch("disappeared", baseline_delay_ms=2.4, baseline_relative_db=-20.0)
    assert _reflection_findings(weak) == []
