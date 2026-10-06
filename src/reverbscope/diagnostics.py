"""Environment report for bug reports and debugging (``reverbscope doctor``).

Everything a maintainer asks first: ReverbScope's version, edition and build
(the commit a desktop bundle was built from), the Python and platform, the
versions of the libraries that carry the measurement (NumPy, SciPy,
libsndfile, PortAudio, Qt), the settings that change a measurement, where
ReverbScope keeps its files, and which host APIs and devices PortAudio sees,
optionally with the sample rates each device accepts (probed; nothing is
played).

Nothing leaves the machine: the report is printed, or copied by the user.
Paths under the home folder are shown as ``~`` so the account name does not
end up in a public issue. Device names are kept because they identify the
hardware; they can contain a person's name ("Anna's AirPods"), and the report
says so.
"""

from __future__ import annotations

import json
import platform
import sys
import unicodedata
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from reverbscope.i18n import N_, _, diag, localize, pgettext

#: Distribution name -> import name. A desktop bundle usually carries no
#: package metadata (PyInstaller copies it only when a hook asks), so the
#: module's own ``__version__`` is the fallback.
PACKAGES = {
    "numpy": "numpy",
    "scipy": "scipy",
    "soundfile": "soundfile",
    "sounddevice": "sounddevice",
    "matplotlib": "matplotlib",
    "PySide6_Essentials": "PySide6",
    "shiboken6": "shiboken6",
}

#: Written next to this module by packaging/reverbscope.spec (desktop bundles only).
BUILD_INFO_FILENAME = "build_info.json"

#: The last line of the report (English); :func:`privacy_note` translates it.
PRIVACY_NOTE = N_(
    "Review before posting: device names can contain personal names; "
    "paths under your home folder are shown as ~."
)

#: Settings that change what a measurement does or how the app behaves.
#: ``output_dir`` is reported as set / not set, never as a path.
_SETTINGS_KEYS = (
    "language",
    "default_profile",
    "audio_backend",
    "copy_recording",
    "theme",
    "developer_tools",
)


def _package_version(name: str, module: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        pass
    try:
        found = getattr(_import(module), "__version__", None)
    except Exception:  # not installed, or its native library is missing
        return None
    return str(found) if found else None


def _import(module: str) -> Any:
    """Import one of :data:`PACKAGES` by its literal name (no computed imports)."""
    if module == "numpy":
        import numpy

        return numpy
    if module == "scipy":
        import scipy

        return scipy
    if module == "soundfile":
        import soundfile

        return soundfile
    if module == "sounddevice":
        import sounddevice

        return sounddevice
    if module == "matplotlib":
        import matplotlib

        return matplotlib
    if module == "PySide6":
        import PySide6

        return PySide6
    if module == "shiboken6":
        import shiboken6

        return shiboken6
    raise ImportError(module)


def _libsndfile_version() -> str | None:
    try:
        import soundfile

        return str(soundfile.__libsndfile_version__)
    except Exception:
        return None


def build_info(path: Path | None = None) -> dict[str, str] | None:
    """The commit (and CI run) a desktop bundle was built from; None otherwise."""
    path = path or Path(__file__).resolve().parent / BUILD_INFO_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    info = {key: str(data[key]) for key in ("commit", "ci_run", "package") if data.get(key)}
    return info or None


def home_folder() -> Path | None:
    """The home folder, or None when there is none to find.

    ``Path.home()`` raises RuntimeError when HOME is unset and the account has
    no passwd entry (``docker run --user N``, a CI job): a report that hides
    the home folder has nothing to hide there, and must not stop for it.
    """
    try:
        return Path.home()
    except (RuntimeError, OSError):
        return None


def redact_home(path: str | Path, home: str | Path | None = None) -> str:
    """``path`` with the home folder replaced by ``~`` (the account name hidden)."""
    text = str(path)
    if home is None:
        home = home_folder()
    if home is None:
        return text
    prefix = str(home).rstrip("/\\")
    if not prefix:
        return text
    # Windows paths compare case-insensitively (C:\Users\Anna == c:\users\anna).
    fold = "\\" in prefix
    folded = text.casefold() if fold else text
    wanted = prefix.casefold() if fold else prefix
    if folded == wanted:
        return "~"
    for sep in ("/", "\\"):
        if folded.startswith(wanted + sep):
            return "~" + text[len(prefix) :]
    return text


def audio_callback_check() -> str:
    """``"ok"`` when this process can create and call a native callback.

    PortAudio calls ReverbScope's audio function through a cffi callback
    (python-sounddevice, ABI mode). cffi needs memory that is both writable
    and executable for it, which the macOS hardened runtime refuses unless
    the app has ``com.apple.security.cs.allow-unsigned-executable-memory``
    (cffi documentation, "Callbacks (old style)"); SELinux can refuse it too.
    A failure here means Standalone Mode cannot record.
    """
    try:
        import _cffi_backend

        ffi = _cffi_backend.FFI()
        callback = ffi.callback("int(*)(int)", lambda value: value + 1)
        answer = callback(41)
    except Exception as exc:  # MemoryError: "Cannot allocate write+execute memory"
        return diag("failed: {error}", error=repr(exc))
    if answer == 42:
        return "ok"
    return diag("failed: the callback returned {answer}", answer=repr(answer))


def _settings_summary() -> dict[str, Any]:
    try:
        from reverbscope.settings import load_settings

        settings = load_settings().to_dict()
    except Exception as exc:  # a broken settings file must not stop the report
        return {"error": str(exc)}
    summary = {key: settings.get(key) for key in _SETTINGS_KEYS}
    summary["output_dir_set"] = bool(settings.get("output_dir"))
    return summary


def environment_report(
    backend_name: str | None = None, *, probe_rates: bool = False, english_errors: bool = False
) -> dict[str, Any]:
    """The report as a JSON-ready dict; ``probe_rates`` asks every device for its rates.

    ``english_errors`` words a failed backend or settings file in English, as
    the JSON report must be (an error is worded when it is raised); the text
    report keeps the interface language and shows it as raised.
    """
    from contextlib import nullcontext

    from reverbscope import __version__
    from reverbscope.edition import edition
    from reverbscope.i18n import current_locale, english
    from reverbscope.io.recent import reverbscope_home
    from reverbscope.logging_config import LOG_FILENAME
    from reverbscope.settings import settings_path

    errors = english if english_errors else nullcontext
    with errors():
        settings = _settings_summary()
    report: dict[str, Any] = {
        "reverbscope": __version__,
        "edition": edition(),
        "frozen_bundle": bool(getattr(sys, "frozen", False)),
        "build": build_info(),
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "language": current_locale(),
        "packages": {name: _package_version(name, module) for name, module in PACKAGES.items()},
        "libsndfile": _libsndfile_version(),
        "settings": settings,
        "paths": {
            "reverbscope_home": redact_home(reverbscope_home()),
            "settings": redact_home(settings_path()),
            "log": redact_home(reverbscope_home() / LOG_FILENAME),
        },
    }
    try:
        from reverbscope.audio.backend import get_backend
        from reverbscope.audio.inventory import build_inventory

        with errors():
            inventory = build_inventory(get_backend(backend_name), probe_rates=probe_rates)
    except Exception as exc:  # the report must print even without audio
        report["audio"] = {"error": str(exc)}
    else:
        report["audio"] = inventory.to_dict()
    report["audio_callbacks"] = audio_callback_check()
    return report


def privacy_note() -> str:
    """:data:`PRIVACY_NOTE` in the active language."""
    return _(
        "Review before posting: device names can contain personal names; "
        "paths under your home folder are shown as ~."
    )


def _rates(rates: list[int], known: bool = True) -> str:
    if not known:  # the device could not be opened: "none" would claim it refuses them all
        return _("unknown")
    return ", ".join(str(rate) for rate in rates) or pgettext("sample rates", "none")


def _edition_name(edition: str) -> str:
    if edition == "developer":
        return pgettext("edition", "developer")
    if edition == "user":
        return pgettext("edition", "user")
    return edition


def _format_devices(audio: dict[str, Any]) -> list[str]:
    probed = bool(audio.get("rates_probed"))
    lines = [
        _("Devices (* default; sample rates accepted for 1 channel, nothing was played):")
        if probed
        else _("Devices (* default; sample rates not probed, use reverbscope doctor --probe):")
    ]
    for probe in audio.get("devices", []):
        device = probe["device"]
        star = " *" if device.get("is_default_input") or device.get("is_default_output") else ""
        row = _(
            "[{index:>2}] {name}{star} | {host_api} | in {inputs} / out {outputs} | "
            "default {rate:.0f} Hz"
        ).format(
            index=device["index"],
            name=device["name"],
            star=star,
            host_api=device["host_api"],
            inputs=device["max_input_channels"],
            outputs=device["max_output_channels"],
            rate=device["default_sample_rate"],
        )
        lines.append("  " + row)
        details = []
        if probed and device["max_input_channels"] > 0:
            details.append(
                _("record {rates}").format(
                    rates=_rates(probe["input_rates"], probe.get("input_rates_known", True))
                )
            )
        if probed and device["max_output_channels"] > 0:
            details.append(
                _("play {rates}").format(
                    rates=_rates(probe["output_rates"], probe.get("output_rates_known", True))
                )
            )
        recommended_input = bool(probe.get("recommended_input"))
        recommended_output = bool(probe.get("recommended_output"))
        if recommended_input and recommended_output:
            details.append(_("recommended input + output"))
        elif recommended_input:
            details.append(_("recommended input"))
        elif recommended_output:
            details.append(_("recommended output"))
        if details:
            lines.append("       " + "; ".join(details))
    return lines


def _setting_label(key: str) -> str:
    """A settings key of the report in words, as ``reverbscope config`` and the
    Settings dialog name it (the JSON keeps the field names)."""
    return {
        "language": _("Interface language"),
        "default_profile": _("Default profile"),
        "audio_backend": _("Audio backend"),
        "copy_recording": _("Copy recordings"),
        "theme": _("Theme (desktop app)"),
        "developer_tools": _("Developer tools"),
        "output_dir_set": _("Default output folder (desktop app)"),
    }.get(key, key)


def _setting_value(key: str, value: object) -> str:
    if key == "output_dir_set":
        return _("set") if value else _("not set")
    if isinstance(value, bool):
        return pgettext("setting", "on") if value else pgettext("setting", "off")
    return "-" if value in ("", None) else str(value)


def _path_label(key: str) -> str:
    return {
        "reverbscope_home": _("ReverbScope folder"),
        "settings": _("Settings file"),
        "log": _("Log file"),
    }.get(key, key)


def _field(label: str, value: object) -> str:
    """``label`` padded to 20 terminal columns (a CJK character takes two)."""
    width = sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in label)
    return f"  {label}{' ' * max(1, 21 - width)}{value}"


def format_environment_report(report: dict[str, Any]) -> str:
    """The report as text in the active language (the JSON stays English)."""
    build = report.get("build") or {}
    heading = (
        _("ReverbScope {version} ({edition} edition, desktop bundle)")
        if report.get("frozen_bundle")
        else _("ReverbScope {version} ({edition} edition)")
    )
    lines = [
        heading.format(version=report["reverbscope"], edition=_edition_name(report["edition"])),
        _("Build: {commit}").format(commit=build["commit"])
        if build.get("commit")
        else _("Build: no commit recorded (source or pip install)"),
    ]
    if build.get("ci_run"):
        lines.append(_("CI run: {url}").format(url=build["ci_run"]))
    lines += [
        _("Python {version} ({implementation}) on {platform} [{machine}]").format(
            version=report["python"],
            implementation=report["implementation"],
            platform=report["platform"],
            machine=report["machine"],
        ),
        _("Language: {language}").format(language=report["language"]),
        _("Packages:"),
    ]
    for name, found in report["packages"].items():
        lines.append(_field(name, found or _("not installed")))
    lines.append(_field("libsndfile", report.get("libsndfile") or _("unknown")))
    lines.append(_("Settings:"))
    settings = report.get("settings", {})
    if "error" in settings:
        lines.append("  " + localize(str(settings["error"])))
    else:
        for key, value in settings.items():
            lines.append(_field(_setting_label(key), _setting_value(key, value)))
    lines.append(_("Paths:"))
    for key, value in report["paths"].items():
        lines.append(_field(_path_label(key), value))
    audio = report.get("audio", {})
    callbacks = report.get("audio_callbacks")
    if callbacks is None:
        lines.append(_("Audio callbacks: not checked"))
    elif callbacks == "ok":
        lines.append(_("Audio callbacks: ok"))
    else:
        lines.append(_("Audio callbacks: {status}").format(status=localize(str(callbacks))))
    lines.append(_("Audio:"))
    if "error" in audio:
        lines.append("  " + _("unavailable: {error}").format(error=localize(str(audio["error"]))))
    else:
        devices = audio.get("devices", [])
        default_in = next(
            (p["device"]["name"] for p in devices if p["device"].get("is_default_input")), None
        )
        default_out = next(
            (p["device"]["name"] for p in devices if p["device"].get("is_default_output")), None
        )
        apis = ", ".join(
            f"{api['name']} ({api['device_count']})" for api in audio.get("host_apis", [])
        )
        lines.append(_field(pgettext("environment report", "backend"), audio.get("backend")))
        lines.append(_field("PortAudio", audio.get("portaudio_version") or "-"))
        lines.append(_field(pgettext("environment report", "host APIs"), apis or "-"))
        lines.append(_field(pgettext("environment report", "devices"), len(devices)))
        lines.append(_field(pgettext("environment report", "default input"), default_in or "-"))
        lines.append(_field(pgettext("environment report", "default output"), default_out or "-"))
        for note in audio.get("notes", []):
            lines.append("  " + _("note: {note}").format(note=localize(note)))
        lines.extend(_format_devices(audio))
    lines.append("")
    lines.append(privacy_note())
    return "\n".join(lines)
