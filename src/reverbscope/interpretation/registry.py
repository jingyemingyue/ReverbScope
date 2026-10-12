"""Recording-profile registry: built-ins plus ``reverbscope.profiles`` entry points."""

from __future__ import annotations

import logging

from reverbscope.errors import ConfigurationError
from reverbscope.i18n import _, quoted
from reverbscope.interpretation.profiles import (
    AcousticGuitarProfile,
    ChoirProfile,
    DrumsProfile,
    GenericProfile,
    RecordingProfile,
    RoomMicProfile,
    VocalProfile,
    VoiceOverProfile,
)

log = logging.getLogger("reverbscope.interpretation")

# The parser builder lists the profiles several times per command, and every
# listing walks the entry points again (so a plugin installed or patched while
# the process runs is still seen). A plugin that cannot be used would
# otherwise repeat the same warning on every walk: seven times for
# `reverbscope --version`. Each distinct message is logged once per process.
_reported: set[str] = set()


def _warn_once(message: str, *args: object) -> None:
    text = message % args
    if text in _reported:
        return
    _reported.add(text)
    log.warning("%s", text)


_BUILTINS: dict[str, RecordingProfile] = {
    "generic": GenericProfile(),
    "vocal": VocalProfile(),
    "voiceover": VoiceOverProfile(),
    "acoustic_guitar": AcousticGuitarProfile(),
    "drums": DrumsProfile(),
    "room_mic": RoomMicProfile(),
    "choir": ChoirProfile(),
}


def _entry_points() -> dict[str, RecordingProfile]:
    found: dict[str, RecordingProfile] = {}
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return found
    for item in entry_points().select(group="reverbscope.profiles"):
        if item.name in _BUILTINS:
            _warn_once("ignoring third-party profile %r; name collides with a built-in", item.name)
            continue
        if item.name in found:
            _warn_once(
                "ignoring third-party profile %r; another package registers the same name",
                item.name,
            )
            continue
        try:
            loaded = item.load()
        except Exception as exc:
            _warn_once("profile %r failed to import: %s", item.name, exc)
            continue
        # Every command lists the profiles while it builds its options, so a
        # plugin that cannot be created is skipped, as an exporter is: it must
        # not stop `reverbscope --version` or the desktop app.
        try:
            profile = loaded() if isinstance(loaded, type) else loaded
        except Exception as exc:
            _warn_once("profile %r could not be created: %s", item.name, exc)
            continue
        if not isinstance(profile, RecordingProfile):
            _warn_once(
                "ignoring third-party profile %r; it lacks name, description, interpret or "
                "interpret_comparison",
                item.name,
            )
            continue
        found[item.name] = profile
    return found


def profile_origins() -> dict[str, str]:
    origins = dict.fromkeys(_BUILTINS, "builtin")
    origins.update(dict.fromkeys(_entry_points(), "entry_point"))
    return origins


def available_profiles() -> list[str]:
    return sorted({*_BUILTINS, *_entry_points()})


def get_profile(name: str) -> RecordingProfile:
    table: dict[str, RecordingProfile] = {**_entry_points(), **_BUILTINS}
    try:
        return table[name]
    except KeyError as exc:
        raise ConfigurationError(
            _("unknown recording profile {name}; available: {available}").format(
                name=quoted(name), available=available_profiles()
            )
        ) from exc
