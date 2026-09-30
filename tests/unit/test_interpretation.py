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
from roomscope.models.result import Reflection
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
