"""Lenient JSON loading: unknown keys are ignored, schema versions are gated.

Readers accept every 1.x file they understand. A *higher* ``schema_version``
is refused with the running ReverbScope version in the message. Unknown keys
are dropped and logged at INFO. Writers stay strict: ``to_dict`` output is
validated against the shipped schemas in the test suite, never at runtime.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from reverbscope.errors import ConfigurationError, SessionError
from reverbscope.i18n import _, pgettext
from reverbscope.version import __version__

log = logging.getLogger("reverbscope.models")


def record_name(kind: str) -> str:
    """``kind`` (the English name of a file or of a record in it) for a message.

    Loading errors name what was wrong ("metric delta must be a JSON object").
    The known names are translated (context ``"file record"``); a JSON key
    (``impulse_response``) or an unknown name is shown as it is.
    """
    names = {
        "settings": pgettext("file record", "settings"),
        "sweep settings": pgettext("file record", "sweep settings"),
        "analysis settings": pgettext("file record", "analysis settings"),
        "calibration": pgettext("file record", "calibration"),
        "project": pgettext("file record", "project"),
        "position entry": pgettext("file record", "position entry"),
        "session": pgettext("file record", "session"),
        "recent sessions": pgettext("file record", "recent sessions"),
        "result": pgettext("file record", "result"),
        "comparison": pgettext("file record", "comparison"),
        "compare settings": pgettext("file record", "compare settings"),
        "metric delta": pgettext("file record", "metric delta"),
        "reflection match": pgettext("file record", "reflection match"),
        "resonance match": pgettext("file record", "resonance match"),
        "frequency-response delta": pgettext("file record", "frequency-response delta"),
        "sweep sidecar": pgettext("file record", "sweep sidecar"),
        "decay": pgettext("file record", "decay"),
        "decay metric": pgettext("file record", "decay metric"),
        "band decay": pgettext("file record", "band decay"),
        "excitation band": pgettext("file record", "excitation band"),
        "harmonic distortion": pgettext("file record", "harmonic distortion"),
        "aliased distortion": pgettext("file record", "aliased distortion"),
        "clipping": pgettext("file record", "clipping"),
        "loopback": pgettext("file record", "loopback"),
        "hum": pgettext("file record", "hum"),
        "noise": pgettext("file record", "noise"),
        "reflections": pgettext("file record", "reflections"),
        "resonances": pgettext("file record", "resonances"),
        "resonance candidate": pgettext("file record", "resonance candidate"),
        "placement": pgettext("file record", "placement"),
        "placement length": pgettext("file record", "placement length"),
        "boundary candidate": pgettext("file record", "boundary candidate"),
    }
    return names.get(kind, kind)


def read_schema_version(data: Mapping[str, Any], known: int, kind: str) -> int:
    """Return the file's schema version, or raise if it is newer than ``known``."""
    raw = data.get("schema_version", known)
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise SessionError(
            _("{kind} schema_version is not an integer").format(kind=record_name(kind))
        ) from exc
    if version > known:
        raise SessionError(
            _(
                "{kind} schema version {version} cannot be read by ReverbScope {running}; "
                "this version reads schema {known} and below. Open the file in a newer ReverbScope."
            ).format(kind=record_name(kind), version=version, running=__version__, known=known)
        )
    return version


def drop_unknown(data: Mapping[str, Any], known: set[str], *, kind: str) -> dict[str, Any]:
    """Copy known keys only; log the rest at INFO."""
    unknown = sorted(set(data) - known)
    if unknown:
        log.info("ignoring unknown %s fields: %s", kind, unknown)
    return {key: data[key] for key in data if key in known}


def settings_payload(data: Mapping[str, Any], known: set[str], *, kind: str) -> dict[str, Any]:
    """Lenient payload for settings dataclasses (``ConfigurationError`` on bad types)."""
    if not isinstance(data, Mapping):
        raise ConfigurationError(_("{kind} must be a JSON object").format(kind=record_name(kind)))
    return drop_unknown(data, known, kind=kind)


def record_payload(data: object, known: set[str], *, kind: str) -> dict[str, Any]:
    """:func:`drop_unknown` for a nested record read from a file.

    Raises :class:`SessionError` when ``data`` is not a JSON object.
    """
    if not isinstance(data, Mapping):
        raise SessionError(_("{kind} must be a JSON object").format(kind=record_name(kind)))
    return drop_unknown(data, known, kind=kind)


def build_record[T](cls: type[T], payload: Mapping[str, Any], *, kind: str) -> T:
    """``cls(**payload)`` for data read from a file.

    A missing required field (``TypeError``) or a value the class rejects
    (``ValueError``) becomes :class:`SessionError`, so an untrusted file never
    surfaces a bare Python exception (#11).
    """
    try:
        return cls(**payload)
    except SessionError:
        raise
    except (TypeError, ValueError) as exc:
        raise SessionError(
            _("invalid {kind} in file: {error}").format(kind=record_name(kind), error=exc)
        ) from exc
