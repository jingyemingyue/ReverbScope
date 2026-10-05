"""Reserved calibration slot. No dB SPL workflow ships in 1.0."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from reverbscope.models.loadutil import build_record, record_payload


@dataclass(frozen=True)
class CalibrationRecord:
    """A later release may turn dBFS into dB SPL from these numbers.

    In 1.0 the field is accepted, stored, and ignored by the analysis.
    """

    reference_dbfs: float
    reference_db_spl: float
    method: str = ""
    date: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationRecord:
        payload = record_payload(data, {f.name for f in fields(cls)}, kind="calibration")
        return build_record(cls, payload, kind="calibration")
