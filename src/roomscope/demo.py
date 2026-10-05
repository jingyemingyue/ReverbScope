"""Synthetic demo: try the whole workflow without an interface or a microphone.

:func:`run_demo` writes the same files a real Universal DAW Mode measurement
produces -- a sweep WAV with its sidecar and one "recorded" WAV per microphone
position -- but the recordings are *simulated*: the sweep is convolved with a
made-up room impulse response and noise is added. Both positions are then
analysed with :func:`roomscope.core.pipeline.analyze` and compared with
:func:`roomscope.core.compare.compare`, exactly as ``roomscope analyze`` and
``roomscope compare`` would.

Nothing here is a measurement of a real room. Every session the demo saves is
marked ``mode = "synthetic_demo"`` and says so in its notes, so a demo result
can never be mistaken for hardware evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

from roomscope.audio.fake import make_rir
from roomscope.models.audio import AudioSignal, FloatArray
from roomscope.models.comparison import ComparisonResult
from roomscope.models.configuration import SweepSettings
from roomscope.models.result import AnalysisResult

#: ``MeasurementSession.mode`` of every session the demo writes.
DEMO_MODE = "synthetic_demo"
DEMO_ROOM_NAME = "Synthetic demo room"
DEMO_NOTES = (
    "SYNTHETIC DEMO: simulated with `roomscope demo`. No audio hardware was used; "
    "this is not a measurement of a real room."
)
#: Notes of a take recorded on the fake audio backend (the desktop Demo,
#: ``roomscope --backend fake measure``). Its session is marked
#: :data:`DEMO_MODE` too: the "room" is simulated just the same.
FAKE_BACKEND_NOTES = (
    "SYNTHETIC DEMO: recorded with the fake audio backend. No audio hardware was used; "
    "this is not a measurement of a real room."
)
DEMO_PROFILE = "vocal"


@dataclass(frozen=True)
class DemoPosition:
    """One simulated microphone position in the demo room."""

    key: str
    label: str
    description: str
    rt60_s: float
    #: Discrete reflections as ``(delay_s, level_db)`` relative to the direct sound.
    reflections: tuple[tuple[float, float], ...]
    #: Peak amplitude of the decaying 110 Hz room mode added to the response.
    mode_amplitude: float
    #: Amplitude of the 50 Hz mains hum fundamental in the recording.
    hum_amplitude: float
    seed: int


#: Position A sits close to a desk and a side wall; B was moved back from both.
#: The room mode is a property of the room, so it stays at both positions.
DEMO_POSITIONS: tuple[DemoPosition, ...] = (
    DemoPosition(
        key="position-a",
        label="A",
        description="close to the desk and the side wall",
        rt60_s=0.45,
        reflections=((0.0024, -3.0), (0.0071, -9.0)),
        mode_amplitude=0.012,
        hum_amplitude=3e-4,
        seed=1,
    ),
    DemoPosition(
        key="position-b",
        label="B",
        description="moved 1 m back from the desk",
        rt60_s=0.45,
        reflections=((0.0093, -14.0),),
        mode_amplitude=0.004,
        hum_amplitude=1e-5,
        seed=2,
    ),
)

#: Frequency and decay constant of the simulated room mode.
MODE_HZ = 110.0
MODE_TAU_S = 0.12
#: Broadband noise of the simulated microphone chain (linear RMS).
NOISE_RMS = 3e-5


def demo_sweep_settings(sample_rate: int = 48000) -> SweepSettings:
    """A short sweep so the demo finishes in a few seconds."""
    return SweepSettings(
        sample_rate=sample_rate, duration_s=5.0, pre_silence_s=1.0, post_silence_s=2.5
    )


def demo_room_response(position: DemoPosition, sample_rate: int) -> FloatArray:
    """Synthetic impulse response: direct sound, reflections, diffuse tail, one mode."""
    reflections = [(delay, 10.0 ** (level / 20.0)) for delay, level in position.reflections]
    rir = make_rir(
        sample_rate,
        rt60_s=position.rt60_s,
        reflections=reflections,
        diffuse_level=0.02,
        seed=position.seed,
    )
    t = np.arange(rir.shape[0]) / sample_rate
    mode = position.mode_amplitude * np.exp(-t / MODE_TAU_S) * np.sin(2.0 * np.pi * MODE_HZ * t)
    return np.asarray(rir + mode, dtype=np.float64)


def simulate_take(position: DemoPosition, settings: SweepSettings) -> FloatArray:
    """What a microphone at ``position`` would record while the sweep plays."""
    from roomscope.core.sweep import measurement_signal

    excitation = measurement_signal(settings)
    rir = demo_room_response(position, settings.sample_rate)
    recorded = fftconvolve(excitation, rir)[: excitation.shape[0] + rir.shape[0]]
    t = np.arange(recorded.shape[0]) / settings.sample_rate
    rng = np.random.default_rng(position.seed + 10)
    recorded = recorded + rng.normal(0.0, NOISE_RMS, recorded.shape[0])
    for harmonic, scale in ((1, 1.0), (2, 0.5), (3, 0.25)):
        recorded += position.hum_amplitude * scale * np.sin(2.0 * np.pi * 50.0 * harmonic * t)
    return np.asarray(recorded, dtype=np.float64)


@dataclass(frozen=True)
class DemoTake:
    position: DemoPosition
    recording_path: Path
    session_dir: Path
    result: AnalysisResult


@dataclass(frozen=True)
class DemoRun:
    out_dir: Path
    sweep_path: Path
    settings: SweepSettings
    takes: tuple[DemoTake, ...]
    comparison: ComparisonResult
    comparison_path: Path
    profile: str = DEMO_PROFILE


def run_demo(out_dir: Path, *, sample_rate: int = 48000, profile: str = DEMO_PROFILE) -> DemoRun:
    """Write the sweep, simulate and analyse both positions, and compare them.

    Layout of ``out_dir``::

        sweep.wav (+ sidecar)     the test signal, as ``roomscope sweep`` writes it
        position-a.wav            simulated recording at position A
        position-b.wav            simulated recording at position B
        position-a/ position-b/   saved sessions (``roomscope show`` opens them)
        comparison.json           A -> B, as ``roomscope compare --out`` writes it
    """
    from roomscope.core.compare import compare
    from roomscope.core.pipeline import Reference, analyze
    from roomscope.io.session_store import save_comparison, save_measurement
    from roomscope.io.wav import write_sweep_file, write_wav
    from roomscope.models.comparison import CompareSettings
    from roomscope.models.configuration import AnalysisSettings
    from roomscope.models.session import MeasurementSession

    out_dir.mkdir(parents=True, exist_ok=True)
    settings = demo_sweep_settings(sample_rate)
    sweep_path, _sidecar = write_sweep_file(settings, out_dir / "sweep.wav")
    reference = Reference.from_settings(settings)
    analysis_settings = AnalysisSettings()
    takes: list[DemoTake] = []
    for position in DEMO_POSITIONS:
        samples = simulate_take(position, settings)
        recording_path = write_wav(
            out_dir / f"{position.key}.wav", samples, settings.sample_rate, subtype="FLOAT"
        )
        result = analyze(AudioSignal(samples, settings.sample_rate), reference, analysis_settings)
        session = MeasurementSession(
            mode=DEMO_MODE,
            room_name=DEMO_ROOM_NAME,
            measurement_position=f"{position.label}: {position.description}",
            microphone_name="simulated omni",
            notes=DEMO_NOTES,
            sweep_settings=settings,
            analysis_settings=analysis_settings,
            sweep_path=str(sweep_path),
            recording_path=str(recording_path),
            recording_profile=profile,
        )
        session_dir = out_dir / position.key
        save_measurement(session_dir, session, result, copy_recording=False)
        takes.append(DemoTake(position, recording_path, session_dir, result))
    baseline, candidate = takes[0], takes[1]
    comparison = replace(
        compare(
            baseline.result,
            candidate.result,
            settings=CompareSettings(same_input_gain=True),
        ),
        baseline_session=str(baseline.session_dir),
        candidate_session=str(candidate.session_dir),
    )
    comparison_path = save_comparison(out_dir / "comparison.json", comparison)
    return DemoRun(
        out_dir=out_dir,
        sweep_path=sweep_path,
        settings=settings,
        takes=tuple(takes),
        comparison=comparison,
        comparison_path=comparison_path,
        profile=profile,
    )
