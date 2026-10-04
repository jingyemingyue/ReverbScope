"""Mutable state shared between the GUI pages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from roomscope.core.pipeline import Reference
from roomscope.interpretation import Finding
from roomscope.models.audio import AudioSignal
from roomscope.models.configuration import AnalysisSettings, SweepSettings
from roomscope.models.result import AnalysisResult
from roomscope.models.session import MeasurementSession


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
    #: Bumped by every reset (New Measurement, Open Session). A take or an
    #: analysis that started under another generation belongs to a session
    #: that is gone, and its late result is dropped.
    generation: int = 0

    def reset(self) -> None:
        self.generation += 1
        self.recording_path = None
        self.recording = None
        self.result = None
        self.findings = []
        self.session = MeasurementSession(mode=self.mode)
