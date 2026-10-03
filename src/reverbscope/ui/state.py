"""Mutable state shared between the GUI pages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reverbscope.core.pipeline import Reference
from reverbscope.interpretation import Finding
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession


@dataclass
class MeasurementState:
    mode: str = "universal_daw"
    sweep_settings: SweepSettings = field(default_factory=SweepSettings)
    sweep_path: Path | None = None
    recording_path: Path | None = None
    recording: AudioSignal | None = None
    reference: Reference | None = None
    analysis_settings: AnalysisSettings = field(default_factory=AnalysisSettings)
    profile: str = "generic"
    result: AnalysisResult | None = None
    findings: list[Finding] = field(default_factory=list)
    session: MeasurementSession = field(default_factory=MeasurementSession)

    def reset(self) -> None:
        self.recording_path = None
        self.recording = None
        self.result = None
        self.findings = []
        self.session = MeasurementSession(mode=self.mode)
