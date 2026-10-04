"""Measurement session model.

A session records everything needed to re-analyse a measurement later: the
sweep definition, the file paths of the raw audio, the equipment metadata and
the analysis summary. Raw audio is never embedded in the JSON; it stays in WAV
files next to the session file so that the measurement can be repeated.
"""

from __future__ import annotations

import platform as py_platform
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.models.configuration import AnalysisSettings, SweepSettings
from roomscope.models.loadutil import drop_unknown, read_schema_version, record_name
from roomscope.version import __version__

SESSION_SCHEMA_VERSION = 1

#: JSON types accepted for the plain fields of a session read from a file,
#: keyed by the field's annotation.
_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "str | None": (str, type(None)),
    "int | None": (int, type(None)),
    "dict[str, Any]": (dict,),
}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class MeasurementSession:
    """One measurement of one position in one room."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=utc_now_iso)
    mode: str = "universal_daw"  # or "standalone"
    room_name: str = ""
    measurement_position: str = ""
    microphone_name: str = ""
    microphone_type: str = ""
    microphone_calibration: str = "uncalibrated"
    audio_interface: str = ""
    #: 1-based interface channels of a Standalone take (microphone input,
    #: loudspeaker output; ``loopback_channel`` below is the electrical
    #: return). ``None`` in Universal DAW Mode, where the DAW did the routing;
    #: the analysed columns of the WAV are ``analysis_settings.channel`` /
    #: ``analysis_settings.loopback_channel`` (0-based). Sessions written by
    #: the CLI before v0.4.1 stored the 0-based column here instead (#13).
    input_channel: int | None = None
    output_channel: int | None = None
    loudspeaker: str = ""
    sample_rate: int | None = None
    bit_depth: str | None = None
    sweep_settings: SweepSettings = field(default_factory=SweepSettings)
    analysis_settings: AnalysisSettings = field(default_factory=AnalysisSettings)
    #: Paths are stored relative to the session directory when possible.
    sweep_path: str | None = None
    recording_path: str | None = None
    impulse_response_path: str | None = None
    result_path: str | None = None
    #: Scalar summary of the analysis (no curves) for quick listing.
    analysis_summary: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    #: Recording profile used when the result was last interpreted.
    recording_profile: str = "generic"
    roomscope_version: str = field(default_factory=lambda: __version__)
    platform: str = field(default_factory=lambda: f"{py_platform.system()} {py_platform.release()}")
    #: 1-based interface input of the electrical loopback (see ``input_channel``).
    loopback_channel: int | None = None
    schema_version: int = SESSION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sweep_settings"] = self.sweep_settings.to_dict()
        data["analysis_settings"] = self.analysis_settings.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MeasurementSession:
        if not isinstance(data, dict):
            raise SessionError(
                _("{kind} must be a JSON object").format(kind=record_name("session"))
            )
        version = read_schema_version(data, SESSION_SCHEMA_VERSION, "session")
        payload = drop_unknown(data, {f.name for f in fields(cls)}, kind="session")
        for f in fields(cls):
            expected = _FIELD_TYPES.get(str(f.type))
            if f.name in payload and expected and not isinstance(payload[f.name], expected):
                # Listings sort by created_at and read analysis_summary; a
                # wrong type there would fail later instead of here (#11).
                raise SessionError(
                    _("invalid {kind} in file: {error}").format(
                        kind=record_name("session"),
                        error=_("{field} has the wrong type").format(field=f.name),
                    )
                )
        if "sweep_settings" in payload:
            payload["sweep_settings"] = SweepSettings.from_dict(payload["sweep_settings"])
        if "analysis_settings" in payload:
            payload["analysis_settings"] = AnalysisSettings.from_dict(payload["analysis_settings"])
        payload["schema_version"] = version
        return cls(**payload)
