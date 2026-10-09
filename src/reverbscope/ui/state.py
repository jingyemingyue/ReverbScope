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
    """The session on the Results page: its recording, sweep, settings and result.

    A mode page keeps its own recording and sweep and writes them here only
    when it starts an analysis (or a take is recorded), so one page never
    analyses what another page imported or played.
    """

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
    #: Why the result has no findings: the recording profile failed (a
    #: third-party one from an entry point). Shown on the Results page.
    findings_problem: str = ""
    session: MeasurementSession = field(default_factory=MeasurementSession)
    #: The project the next saved session is added to, under this position
    #: (set by the Project page's "Measure a new position"). A project
    #: outlives one session, so reset() keeps them; Home clears them.
    project_path: Path | None = None
    project_position: str = ""
    #: A live Standalone take whose recording exists only in memory until the
    #: session is saved; New Measurement, Open Session and closing the window
    #: ask before they drop it. Never set for the demo (nothing is lost) or for
    #: a DAW recording (its file is on disk).
    unsaved_take: bool = False
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
        self.findings_problem = ""
        self.unsaved_take = False
        self.session = MeasurementSession(mode=self.mode)

    def leave_project(self) -> None:
        self.project_path = None
        self.project_position = ""

    def claim(self) -> int:
        """A page takes the state for the measurement it starts.

        The take or analysis of any other page that is still running then
        belongs to a session that is gone, and its late result is dropped:
        the last measurement started wins. Returns the generation the new
        measurement runs under.
        """
        self.generation += 1
        return self.generation
