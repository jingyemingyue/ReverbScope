"""``roomscope config``: the settings, read and written from the command line.

The command line keeps the same ``settings.json`` as the desktop app's
Settings dialog (:mod:`roomscope.settings`), so the Terminal Edition has
settings too. One grammar for every setting: ``roomscope config KEY
[VALUE]``, where ``auto`` goes back to the default. A value is checked before
anything is written; a value the setting cannot take changes nothing.

This module knows the keys, checks values and words them; the screens are
laid out by :mod:`roomscope.cli.render`.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from roomscope.audio.backend import ENV_BACKEND
from roomscope.edition import ENV_EDITION
from roomscope.i18n import (
    DEFAULT_LANG,
    LANGUAGE_NAMES,
    ORIGIN_DESKTOP,
    ORIGIN_LOCALE,
    ORIGIN_MACOS,
    ORIGIN_WINDOWS,
    SOURCE_ENVIRONMENT,
    SOURCE_OPTION,
    SOURCE_SETTINGS,
    LanguageChoice,
    _,
    available_locales,
    pgettext,
    supported_language,
)
from roomscope.settings import UserSettings

#: The settings, in the order they are listed.
KEYS: tuple[str, ...] = (
    "language",
    "profile",
    "backend",
    "output-folder",
    "copy-recording",
    "developer-tools",
    "theme",
)
#: The :class:`~roomscope.settings.UserSettings` field each key stores.
FIELDS = {
    "language": "language",
    "profile": "default_profile",
    "backend": "audio_backend",
    "output-folder": "output_dir",
    "copy-recording": "copy_recording",
    "developer-tools": "developer_tools",
    "theme": "theme",
}
#: The field names of settings.json are accepted for their keys too.
_ALIASES = {
    "default-profile": "profile",
    "audio-backend": "backend",
    "output-dir": "output-folder",
}
#: The value that goes back to a setting's default, for every key.
AUTO = "auto"
BACKENDS = ("portaudio", "fake")
THEMES = ("system", "light", "dark")
_ON = frozenset({"on", "true", "yes", "1"})
_OFF = frozenset({"off", "false", "no", "0"})


#: How to switch to the other interface language, written in that language on
#: purpose (never translated): whoever cannot read the current one can still
#: find it. Keyed by the language in effect: the label, then the command.
LANGUAGE_HINTS = {
    "en": ("中文界面：", "roomscope config language zh_CN"),
    "zh_CN": ("English interface: ", "roomscope config language en"),
}


def language_hint_parts(current: str) -> tuple[str, str] | None:
    """``(label, command)`` leading to the other language, or ``None``
    without its catalog. The command must never be split across lines."""
    target = DEFAULT_LANG if current != DEFAULT_LANG else "zh_CN"
    if target not in available_locales():
        return None
    return LANGUAGE_HINTS.get(current)


def language_hint_lines(current: str, width: int) -> list[str]:
    """The hint as one line where it fits in ``width`` columns; otherwise the
    label, then the command whole on a line of its own, indented."""
    from roomscope.cli.console import cell_width

    parts = language_hint_parts(current)
    if parts is None:
        return []
    label, command = parts
    if cell_width(label + command) <= width:
        return [label + command]
    return [label.rstrip(), "  " + command]


class SettingError(ValueError):
    """A key or value the settings cannot take; nothing was written."""

    def __init__(self, message: str, *, hints: tuple[str, ...] = ("roomscope config --help",)):
        super().__init__(message)
        self.hints = hints


def canonical_key(raw: str) -> str:
    """``raw`` as one of :data:`KEYS` (``copy_recording`` and ``output_dir`` too)."""
    key = raw.strip().lower().replace("_", "-")
    key = _ALIASES.get(key, key)
    if key not in KEYS:
        raise SettingError(
            _("unknown setting {key}; the settings are: {keys}").format(
                key=repr(raw), keys=", ".join(KEYS)
            )
        )
    return key


def _profiles() -> list[str]:
    from roomscope.interpretation import available_profiles

    return list(available_profiles())


def parse_value(key: str, raw: str) -> Any:
    """The value to store for ``key`` given as ``raw`` on the command line."""
    text = raw.strip()
    word = text.lower()
    if key == "language":
        if word == AUTO:
            return ""
        lang = supported_language(text)
        if lang is None:
            raise SettingError(
                _("unknown language {value}; available: {languages}, or auto").format(
                    value=repr(raw), languages=", ".join(languages())
                )
            )
        return lang
    if key == "profile":
        if word == AUTO:
            return UserSettings().default_profile
        name = word.replace("-", "_")
        if name not in _profiles():
            raise SettingError(
                _("unknown profile {value}; available: {profiles}, or auto").format(
                    value=repr(raw), profiles=", ".join(_profiles())
                )
            )
        return name
    if key == "backend":
        if word == AUTO:
            return ""
        name = "portaudio" if word == "sounddevice" else word
        if name not in BACKENDS:
            raise SettingError(
                _("unknown audio backend {value}; choose portaudio, fake or auto").format(
                    value=repr(raw)
                )
            )
        return name
    if key == "output-folder":
        if word == AUTO:
            return ""
        folder = Path(text).expanduser() if text else Path()
        if not text or not folder.is_dir():
            raise SettingError(
                _("{path} is not an existing folder; give a folder, or auto").format(path=repr(raw))
            )
        return str(folder.resolve())
    if key in ("copy-recording", "developer-tools"):
        if word == AUTO:
            return getattr(UserSettings(), FIELDS[key])
        if word in _ON:
            return True
        if word in _OFF:
            return False
        raise SettingError(_("{key} is on or off, not {value}").format(key=key, value=repr(raw)))
    if key == "theme":
        if word in (AUTO, "system"):
            return ""
        if word not in THEMES:
            raise SettingError(
                _("unknown theme {value}; choose system, light, dark or auto").format(
                    value=repr(raw)
                )
            )
        return word
    raise SettingError(f"unknown setting {key!r}")  # canonical_key() admits no other key


def changed(settings: UserSettings, key: str, value: Any) -> UserSettings:
    return replace(settings, **{FIELDS[key]: value})


def typed_value(key: str, settings: UserSettings) -> str:
    """The value as it would be typed after ``roomscope config KEY``."""
    value = getattr(settings, FIELDS[key])
    if isinstance(value, bool):
        return "on" if value else "off"
    if key == "theme":
        return value or "system"
    return str(value) if value else AUTO


def title(key: str) -> str:
    """What a setting is, in words."""
    return {
        "language": _("Interface language"),
        "profile": _("Default profile"),
        "backend": _("Audio backend"),
        "output-folder": _("Session folder (desktop app)"),
        "copy-recording": _("Copy recordings"),
        "developer-tools": _("Developer tools"),
        "theme": _("Theme (desktop app)"),
    }[key]


def choices(key: str) -> str:
    """The values a setting takes, in words (help and errors)."""
    if key == "language":
        return _("{languages}, or auto (follow the system)").format(
            languages=", ".join(languages())
        )
    if key == "profile":
        return _("{profiles}, or auto ({default})").format(
            profiles=", ".join(_profiles()), default=UserSettings().default_profile
        )
    if key == "backend":
        return _("portaudio, fake, or auto (PortAudio)")
    if key == "output-folder":
        return _("an existing folder, or auto (none)")
    if key == "copy-recording":
        return _("on or off (auto: on)")
    if key == "developer-tools":
        return _("on or off (auto: off; a source or pip install always has them)")
    return _("system, light or dark (the desktop app only)")


def language_name(lang: str) -> str:
    """A language's name in the interface language; English for one without a catalog."""
    shown = lang if lang in available_locales() else DEFAULT_LANG
    names = {"en": _("English"), "zh_CN": _("Simplified Chinese")}
    return names.get(shown) or LANGUAGE_NAMES.get(shown, shown)


def languages() -> list[str]:
    """The languages a setting can name, translations first."""
    found = available_locales()
    return [lang for lang in found if lang != DEFAULT_LANG] + [DEFAULT_LANG]


def language_reason(choice: LanguageChoice) -> str:
    """Why ``choice`` is the language in effect, in words."""
    if choice.source == SOURCE_OPTION:
        reason = _("--lang {value} on this command line").format(value=choice.value)
    elif choice.source == SOURCE_SETTINGS:
        reason = _("the stored setting (roomscope config language {value})").format(
            value=choice.value
        )
    elif choice.source == SOURCE_ENVIRONMENT:
        reason = _("the environment variable {name}={value}").format(
            name=choice.origin, value=choice.value
        )
    elif choice.origin == ORIGIN_MACOS:
        reason = _("the Mac's preferred languages: {value}").format(value=choice.value)
    elif choice.origin == ORIGIN_WINDOWS:
        reason = _("the Windows display language: {value}").format(value=choice.value)
    elif choice.origin == ORIGIN_DESKTOP:
        reason = _("the desktop's UI languages: {value}").format(value=choice.value)
    elif choice.origin == ORIGIN_LOCALE:
        reason = _("the system locale: {value}").format(value=choice.value)
    elif choice.origin:
        reason = _("the environment variable {name}={value}").format(
            name=choice.origin, value=choice.value
        )
    else:
        reason = _("no language is set anywhere")
    if supported_language(choice.lang) is None:
        reason += _("; {lang} has no translation, so English is used").format(lang=choice.lang)
    return reason


def state(key: str, settings: UserSettings, choice: LanguageChoice | None = None) -> str:
    """What the stored value means ("follow the system, now 简体中文")."""
    value = getattr(settings, FIELDS[key])
    if key == "language":
        if value:
            return language_name(str(value))
        if choice is not None and choice.source == SOURCE_ENVIRONMENT:
            return _("not stored; {name}={value} chooses {language}").format(
                name=choice.origin, value=choice.value, language=language_name(choice.lang)
            )
        if choice is not None:
            return _("follow the system (now {language})").format(
                language=language_name(choice.lang)
            )
        return _("follow the system")
    if key == "profile":
        from roomscope.interpretation.profiles import profile_title

        return profile_title(str(value))
    if key == "backend":
        override = os.environ.get(ENV_BACKEND, "").strip()
        if override:
            return _("{name}={value} chooses the backend before this setting").format(
                name=ENV_BACKEND, value=override
            )
        if value == "fake":
            return _("simulated interface, for the demo and tests")
        return "PortAudio" if value else _("PortAudio (the default)")
    if key == "output-folder":
        return _("its Save dialog opens here") if value else _("not set")
    if key == "copy-recording":
        return pgettext("setting", "on") if value else pgettext("setting", "off")
    if key == "developer-tools":
        override = os.environ.get(ENV_EDITION, "").strip()
        if override:
            return _("{name}={value} decides before this setting").format(
                name=ENV_EDITION, value=override
            )
        return _("shown") if value else _("hidden in the installed app")
    return {
        "": _("follow the system"),
        "light": _("light"),
        "dark": _("dark"),
    }.get(str(value), str(value))
